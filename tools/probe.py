"""Read-only probe of the Remocon-Net (Ariston) cloud API for one ELCO plant.

What it does (all requests are READ-ONLY, nothing is written to the heat pump):
  1. logs in (password is asked interactively, never stored),
  2. reads plant list + plant features,
  3. asks for a list of candidate dataItems (known + guessed IDs),
  4. scans numbered menuItems (service parameters) in a range,
and saves everything to probe_result.json (no password, no token) + prints a summary.

Usage:
  python probe.py --gateway <GATEWAY_ID>
  python probe.py --gateway <GATEWAY_ID> --menu-from 1 --menu-to 1000
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
    def __init__(self, api: str, max_calls: int):
        self.api = api
        self.token = ""
        self.calls = 0
        self.max_calls = max_calls

    def request(self, method: str, path: str, body=None):
        if self.calls >= self.max_calls:
            raise RateLimited(f"reached --max-calls={self.max_calls}, stopping to stay gentle")
        if self.calls:
            time.sleep(DELAY)
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", required=True, help="Gateway ID (the code after /R2/Plant/Index/ in the portal URL)")
    ap.add_argument("--email", default=None)
    ap.add_argument("--api", default=API)
    ap.add_argument("--culture", default="cs-CZ")
    ap.add_argument("--menu-from", type=int, default=1)
    ap.add_argument("--menu-to", type=int, default=1000)
    ap.add_argument("--menu-chunk", type=int, default=100)
    ap.add_argument("--out", default="probe_result.json")
    ap.add_argument("--max-calls", type=int, default=120)
    ap.add_argument("--only-menu", action="store_true",
                    help="skip plants/features/dataItems; bisect --menu-bisect range, spot-check --menu-ids")
    ap.add_argument("--menu-bisect", default="101-200", help="range to read with bisect on errors, e.g. 101-200")
    ap.add_argument("--menu-ids", default="301,302,305,310,320,350,400,450,500,600,700,800,900,1000",
                    help="comma list of single IDs to spot-check")
    args = ap.parse_args()

    email = args.email or input("Remocon-Net e-mail: ").strip()
    password = getpass.getpass("Remocon-Net heslo (nezobrazuje se): ")
    cli = Client(args.api, args.max_calls)
    result = {"probed_at": datetime.now().isoformat(timespec="seconds"), "api": args.api,
              "gateway": args.gateway, "culture": args.culture}

    try:
        log("1/5 Přihlášení…")
        status, res = cli.request("POST", "accounts/login", {"usr": email, "pwd": password})
        del password
        if status != 200 or not isinstance(res, dict) or "token" not in res:
            log(f"   Přihlášení selhalo: HTTP {status} {str(res)[:200]}")
            return 1
        cli.token = res["token"]
        log("   OK")

        if args.only_menu:
            menu, bad = {}, {}
            a, b = (int(x) for x in args.menu_bisect.split("-"))
            log(f"Servisní parametry {a}–{b} (s dělením při chybě)…")
            probe_menu(cli, args.gateway, list(range(a, b + 1)), menu, bad)
            log(f"   nalezeno {len(menu)}, chybových čísel {len(bad)}: {', '.join(bad) or '-'}")
            ids = [int(x) for x in args.menu_ids.split(",") if x.strip()]
            log(f"Kontrola jednotlivých čísel: {ids}")
            for i in ids:
                probe_menu(cli, args.gateway, [i], menu, bad)
            result["menu_items"] = menu
            result["menu_items_errors"] = bad
            raise StopIteration

        log("2/5 Seznam zařízení…")
        status, res = cli.request("GET", "remote/plants/lite")
        result["plants_lite"] = res if status == 200 else f"HTTP {status}: {res}"
        status, res = cli.request("GET", "remote/plants")
        result["plants"] = res if status == 200 else f"HTTP {status}: {res}"

        log("3/5 Vlastnosti (features) zařízení…")
        status, features = cli.request("GET", f"remote/plants/{args.gateway}/features")
        if status != 200 or not isinstance(features, dict):
            log(f"   Nepodařilo se načíst features: HTTP {status} {str(features)[:200]}")
            result["features"] = f"HTTP {status}: {features}"
            features = {"zones": [{"num": 1}]}
        else:
            result["features"] = features
        zones = [z.get("num", 1) for z in features.get("zones", [])] or [1]

        log(f"4/5 Servisní parametry (menuItems {args.menu_from}–{args.menu_to})…")
        menu = {}
        menu_errors = {}
        for start in range(args.menu_from, args.menu_to + 1, args.menu_chunk):
            ids = list(range(start, min(start + args.menu_chunk, args.menu_to + 1)))
            status, res = cli.request("GET", f"menuItems/{args.gateway}?menuItems={','.join(map(str, ids))}")
            if status == 200 and isinstance(res, list):
                for m in res:
                    menu[str(m.get("id", m.get("menuItem", "?")))] = m
            else:
                menu_errors[f"{ids[0]}-{ids[-1]}"] = f"HTTP {status}: {str(res)[:120]}"
            log(f"   {ids[0]}–{ids[-1]}: celkem nalezeno {len(menu)}")
        result["menu_items"] = menu
        result["menu_items_errors"] = menu_errors

        log("5/5 Hodnoty (dataItems)…")
        items = [{"id": i, "zn": 0} for i in dict.fromkeys(DEVICE_ITEMS + PORTAL_ITEMS + GUESS_ITEMS)]
        for zn in zones:
            items += [{"id": i, "zn": zn} for i in ZONE_ITEMS]
        found, rejected = {}, {}
        probe_items(cli, args.gateway, features, items, args.culture, found, rejected)
        result["data_items"] = found
        result["data_items_missing"] = rejected

    except StopIteration:
        pass  # --only-menu finished
    except RateLimited as err:
        log(f"!! Zastaveno (HTTP 429 nebo limit požadavků), ukládám co mám. {err}")
        result["aborted"] = f"stopped: {err}"
    except urllib.error.URLError as err:
        log(f"!! Chyba spojení: {err}")
        result["aborted"] = f"connection error: {err}"
    finally:
        cli.token = ""

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    # summary
    print("\n=== HODNOTY (dataItems) ===")
    for key, it in sorted(result.get("data_items", {}).items()):
        val = it.get("value")
        opts = it.get("optTexts") or []
        opt_idx = (it.get("options") or []).index(val) if val in (it.get("options") or []) else None
        text = f" ({opts[opt_idx]})" if opt_idx is not None and opt_idx < len(opts) else ""
        flag = "  [NEPLATNÉ - asi neexistuje]" if it.get("invalid") or it.get("error") else ""
        print(f"  {key:38} = {val}{text} {it.get('unit') or ''}"
              f"{'' if it.get('readOnly') else '  [zapisovatelné]'}{flag}")
    missing = result.get("data_items_missing", {})
    print(f"\n  Nevráceno / odmítnuto: {len(missing)} ID")
    print(f"\n=== SERVISNÍ PARAMETRY (menuItems): {len(result.get('menu_items', {}))} ===")
    for key, m in list(result.get("menu_items", {}).items())[:60]:
        print(f"  {key:>5}: {json.dumps(m, ensure_ascii=False)[:150]}")
    print(f"\nPožadavků celkem: {cli.calls}. Výsledek uložen do: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
