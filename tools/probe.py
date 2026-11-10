"""Read-only probe of the Remocon-Net (Ariston) cloud API for one ELCO plant.

What it does (all requests are READ-ONLY, nothing is written to the heat pump):
  1. logs in (password is asked interactively, never stored),
  2. checks that numbered menuItems can be read at all for the plant,
  3. reads plant list + plant features and a list of candidate dataItems (known + guessed IDs),
  4. scans numbered menuItems (service parameters) in a range,
and saves everything to probe_result.json (no password, no token) + prints a summary.
The file is written even when the probe stops early (--max-calls, HTTP 429, Ctrl+C).

Usage:
  python probe.py --gateway <GATEWAY_ID>
  python probe.py --gateway <GATEWAY_ID> --only-menu --menu-from 1 --menu-to 1000 --max-calls 400
"""

import argparse
import getpass
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

API = "https://www.remocon-net.remotethermo.com/api/v2/"
USER_AGENT = "RestSharp/106.11.7.0"  # same as the fustom/ariston integration
DELAY = 1.5  # seconds between requests, be gentle with the cloud
# menuItems that work on the gateway itself (signal level, online outdoor temperature) - used to
# check that the plant answers menuItems at all before scanning a range
CHECK_MENU_IDS = [119, 130]

# dataItems known to python-ariston-api (DeviceProperties, zone 0)
DEVICE_ITEMS = [
    "PlantMode", "IsFlameOn", "IsHeatingPumpOn", "Holiday", "OutsideTemp", "Weather",
    "HeatingCircuitPressure", "ChFlowTemp", "ChFlowSetpointTemp", "DhwTemp",
    "DhwStorageTemperature", "DhwTimeProgComfortTemp", "DhwTimeProgEconomyTemp", "DhwMode",
    "AutomaticThermoregulation", "AntilegionellaOnOff", "AntilegionellaTemp",
    "AntilegionellaFreq", "HybridMode", "BufferControlMode",
    "BufferTimeProgComfortHeatingTemp", "BufferTimeProgEconomyHeatingTemp",
    "BufferTimeProgComfortCoolingTemp", "BufferTimeProgEconomyCoolingTemp", "IsQuite",
]
# seen in the web portal response (/R2/PlantHome/GetData)
PORTAL_ITEMS = ["IsResistorOn", "IsDhwBoost"]
# guesses - harmless if they do not exist
GUESS_ITEMS = [
    "IsCoolingPumpOn", "IsCoolingOn", "IsHeatingOn", "IsDhwOn", "IsDefrostOn", "IsDefrost",
    "IsCompressorOn", "CompressorFreq", "HpState", "HpStatus", "IsHpOn", "IsHeatPumpOn",
    "IsBackupHeaterOn", "IsIntegrationOn", "IsElectricHeaterOn", "IsSolarOn",
    "ChReturnTemp", "ChFlowTempHp", "HpFlowTemp", "HpReturnTemp", "DhwComfortTemp",
    "DhwReducedTemp", "DhwStorageTemp", "BufferTemp", "IsBufferOn", "IsAntifreezeOn",
    "IsDhwProtectionOn", "IsSgReady", "PvMode", "IsPvOn", "ExternalTemp",
]
# dataItems known to python-ariston-api (ThermostatProperties, per zone)
ZONE_ITEMS = [
    "ZoneMeasuredTemp", "ZoneDesiredTemp", "ZoneComfortTemp", "ZoneMode", "ZoneHeatRequest",
    "ZoneEconomyTemp", "ZoneDeroga", "IsZonePilotOn", "VirtTempOffsetHeat", "HeatingFlowTemp",
    "HeatingFlowOffset", "CoolingFlowTemp", "CoolingFlowOffset", "ZoneName",
    "VirtTempSetpointHeat", "VirtTempSetpointCool", "VirtComfortTemp", "VirtReducedTemp",
    "VirtTempOffsetCool", "ZoneCoolRequest", "IsZoneCoolingOn",
]


class RateLimited(Exception):
    pass


class Client:
    def __init__(self, api: str, max_calls: int, delay: float = DELAY):
        self.api = api
        self.token = ""
        self.calls = 0
        self.max_calls = max_calls
        self.delay = delay

    def request(self, method: str, path: str, body=None):
        if self.calls >= self.max_calls:
            raise RateLimited(f"reached --max-calls={self.max_calls}, stopping to stay gentle")
        if self.calls:
            time.sleep(self.delay)
        self.calls += 1
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, method=method, headers={
            "User-Agent": USER_AGENT,
            "ar.authToken": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")[:500]
            if err.code == 429:
                raise RateLimited(raw)
            return err.code, raw


def log(msg: str) -> None:
    print(msg, flush=True)


def probe_items(cli, gw, features, items, culture, found, rejected, depth=0):
    """Ask for items; if the whole batch is rejected, bisect to find the bad IDs."""
    status, res = cli.request("POST", f"remote/dataItems/{gw}/get?umsys=si", {
        "useCache": False, "items": items, "features": features, "culture": culture,
    })
    if status == 200 and isinstance(res, dict):
        for it in res.get("items", []) or []:
            found[f"{it.get('id')}@{it.get('zone', it.get('zn', 0))}"] = it
        returned = {f"{it.get('id')}@{it.get('zone', it.get('zn', 0))}" for it in res.get("items", []) or []}
        for it in items:
            key = f"{it['id']}@{it['zn']}"
            if key not in returned and key not in found:
                rejected[key] = "not returned"
        return res
    if len(items) == 1:
        rejected[f"{items[0]['id']}@{items[0]['zn']}"] = f"HTTP {status}: {str(res)[:120]}"
        return None
    mid = len(items) // 2
    probe_items(cli, gw, features, items[:mid], culture, found, rejected, depth + 1)
    probe_items(cli, gw, features, items[mid:], culture, found, rejected, depth + 1)
    return None


def probe_menu(cli, gw, ids, menu, bad):
    """Read menuItems; on a server error split the batch to isolate the IDs that crash it."""
    status, res = cli.request("GET", f"menuItems/{gw}?menuItems={','.join(map(str, ids))}")
    if status == 200 and isinstance(res, list):
        for m in res:
            menu[str(m.get("id", m.get("menuItem", "?")))] = m
        return
    if len(ids) == 1:
        bad[str(ids[0])] = f"HTTP {status}: {str(res)[:80]}"
        return
    mid = len(ids) // 2
    probe_menu(cli, gw, ids[:mid], menu, bad)
    probe_menu(cli, gw, ids[mid:], menu, bad)


def check_menu(cli, gw, menu, bad) -> bool:
    """Read a few menuItems that work on any gateway; False if none of them can be read."""
    for i in CHECK_MENU_IDS:
        probe_menu(cli, gw, [i], menu, bad)
        if str(i) in menu:
            return True
    return False


def scan_menu(cli, gw, start, end, chunk, menu, bad) -> None:
    """Read menuItems start..end in chunks, bisecting a chunk the cloud rejects."""
    for first in range(start, end + 1, chunk):
        ids = list(range(first, min(first + chunk, end + 1)))
        probe_menu(cli, gw, ids, menu, bad)
        log(f"   {ids[0]}-{ids[-1]}: {len(menu)} found, {len(bad)} rejected so far")


def summary(result: dict, calls: int, out: str) -> None:
    data_items = result.get("data_items")
    if data_items is not None:
        print("\n=== VALUES (dataItems) ===")
        for key, it in sorted(data_items.items()):
            val = it.get("value")
            opts = it.get("optTexts") or []
            opt_idx = (it.get("options") or []).index(val) if val in (it.get("options") or []) else None
            text = f" ({opts[opt_idx]})" if opt_idx is not None and opt_idx < len(opts) else ""
            flag = "  [INVALID - probably not present]" if it.get("invalid") or it.get("error") else ""
            print(f"  {key:38} = {val}{text} {it.get('unit') or ''}"
                  f"{'' if it.get('readOnly') else '  [writable]'}{flag}")
        print(f"\n  Not returned / rejected: {len(result.get('data_items_missing', {}))} IDs")
    menu = result.get("menu_items", {})
    print(f"\n=== SERVICE PARAMETERS (menuItems): {len(menu)} ===")
    for key, m in list(menu.items())[:60]:
        print(f"  {key:>5}: {json.dumps(m, ensure_ascii=False)[:150]}")
    errors = result.get("menu_items_errors", {})
    if errors:
        kinds: dict[str, int] = {}
        for err in errors.values():
            kinds[err] = kinds.get(err, 0) + 1
        print(f"\n  Rejected menuItems: {len(errors)}, answers:")
        for err, count in sorted(kinds.items(), key=lambda kv: -kv[1])[:5]:
            print(f"    {count:>4}x {err}")
    if result.get("aborted"):
        print(f"\n!! Stopped early: {result['aborted']} - the file contains what was read until then.")
    print(f"\nRequests: {calls}. Result saved to: {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", required=True, help="Gateway ID (the code after /R2/Plant/Index/ in the portal URL)")
    ap.add_argument("--email", default=None)
    ap.add_argument("--api", default=API)
    ap.add_argument("--culture", default="en-US", help="language of dataItems texts, e.g. en-US, de-DE, cs-CZ")
    ap.add_argument("--menu-from", type=int, default=1)
    ap.add_argument("--menu-to", type=int, default=1000)
    ap.add_argument("--menu-chunk", type=int, default=100)
    ap.add_argument("--out", default="probe_result.json")
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--delay", type=float, default=DELAY, help="seconds between requests")
    ap.add_argument("--only-menu", action="store_true",
                    help="skip plants/features/dataItems, only scan menuItems --menu-from..--menu-to")
    ap.add_argument("--menu-bisect", default=None,
                    help="range like 101-200; overrides --menu-from/--menu-to (kept for older instructions)")
    ap.add_argument("--menu-ids", default="", help="comma list of single menuItem IDs to read as well")
    ap.add_argument("--skip-check", action="store_true",
                    help="scan menuItems even if the initial check (IDs 119, 130) fails")
    args = ap.parse_args()
    if args.menu_bisect:
        args.menu_from, args.menu_to = (int(x) for x in args.menu_bisect.split("-"))
    extra_ids = [int(x) for x in args.menu_ids.split(",") if x.strip()]

    email = args.email or input("Remocon-Net e-mail: ").strip()
    password = getpass.getpass("Remocon-Net password (not shown): ")
    cli = Client(args.api, args.max_calls, args.delay)
    # every collection is stored in `result` before it is filled, so an early stop keeps partial data
    menu: dict = {}
    bad: dict = {}
    result: dict = {"probed_at": datetime.now().isoformat(timespec="seconds"), "api": args.api,
                    "gateway": args.gateway, "culture": args.culture,
                    "menu_items": menu, "menu_items_errors": bad}

    try:
        log("1/5 Logging in...")
        status, res = cli.request("POST", "accounts/login", {"usr": email, "pwd": password})
        del password
        if status != 200 or not isinstance(res, dict) or "token" not in res:
            log(f"   Login failed: HTTP {status} {str(res)[:200]}")
            return 1
        cli.token = res["token"]
        log("   OK")

        log(f"2/5 Checking that menuItems can be read (IDs {', '.join(map(str, CHECK_MENU_IDS))})...")
        menu_ok = check_menu(cli, args.gateway, menu, bad)
        if menu_ok:
            log("   OK")
        else:
            log("   None of them can be read:")
            for i in CHECK_MENU_IDS:
                log(f"     {i}: {bad.get(str(i))}")
            if args.skip_check:
                log("   --skip-check given, scanning anyway.")
            else:
                log("   The cloud probably does not offer menuItems for this plant - not scanning the range"
                    " (use --skip-check to scan anyway).")
                result["aborted"] = "menuItems check failed"

        if not args.only_menu:
            log("3/5 Plants, features and values (dataItems)...")
            status, res = cli.request("GET", "remote/plants/lite")
            result["plants_lite"] = res if status == 200 else f"HTTP {status}: {res}"
            status, res = cli.request("GET", "remote/plants")
            result["plants"] = res if status == 200 else f"HTTP {status}: {res}"
            status, features = cli.request("GET", f"remote/plants/{args.gateway}/features")
            if status != 200 or not isinstance(features, dict):
                log(f"   Could not read features: HTTP {status} {str(features)[:200]}")
                result["features"] = f"HTTP {status}: {features}"
                features = {"zones": [{"num": 1}]}
            else:
                result["features"] = features
            zones = [z.get("num", 1) for z in features.get("zones", [])] or [1]
            items = [{"id": i, "zn": 0} for i in dict.fromkeys(DEVICE_ITEMS + PORTAL_ITEMS + GUESS_ITEMS)]
            for zn in zones:
                items += [{"id": i, "zn": zn} for i in ZONE_ITEMS]
            found: dict = {}
            rejected: dict = {}
            result["data_items"] = found
            result["data_items_missing"] = rejected
            probe_items(cli, args.gateway, features, items, args.culture, found, rejected)
            log(f"   {len(found)} values found")

        if menu_ok or args.skip_check:
            log(f"4/5 Service parameters (menuItems {args.menu_from}-{args.menu_to})...")
            scan_menu(cli, args.gateway, args.menu_from, args.menu_to, args.menu_chunk, menu, bad)
            if extra_ids:
                log(f"   single IDs: {extra_ids}")
                for i in extra_ids:
                    probe_menu(cli, args.gateway, [i], menu, bad)
        log("5/5 Done")

    except RateLimited as err:
        log(f"!! Stopped (HTTP 429 or --max-calls reached), saving what was read. {err}")
        result["aborted"] = f"stopped: {err}"
    except KeyboardInterrupt:
        log("!! Interrupted, saving what was read.")
        result["aborted"] = "interrupted by user"
    except urllib.error.URLError as err:
        log(f"!! Connection error: {err}")
        result["aborted"] = f"connection error: {err}"
    finally:
        cli.token = ""

    # menuItems in numeric order (bisecting fills them out of order)
    result["menu_items"] = dict(sorted(menu.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0))
    result["menu_items_errors"] = dict(sorted(bad.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    summary(result, cli.calls, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
