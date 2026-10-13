<img src="custom_components/elco_remocon_ro/brand/icon.png" alt="ELCO" width="96" align="right">

# ELCO Remocon-Net (read-only) for Home Assistant

[![Validate](https://github.com/karliklukas/ha-elco-remocon/actions/workflows/validate.yml/badge.svg)](https://github.com/karliklukas/ha-elco-remocon/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

Unofficial, **read-only** Home Assistant integration for ELCO heat pumps connected to the
**Remocon-Net** cloud (Ariston group, **GALEVO** controller family – e.g. *AEROTOP MONO.2* with
*REMOCON PLUS.2*). It shows what the heat pump is doing – running, heating, defrosting, heating
rods on – together with the real flow, room and hot-water temperatures. **It never writes
anything to the heat pump.**

> Not affiliated with ELCO, Ariston or Remocon-Net. The cloud API is undocumented and may change
> without notice. Entity names are in Czech.

## Features

- Heat pump **operating mode** – off / standby / heating / *heating with booster* / **defrost** /
  freeze protection / failure … (20 states)
- **Heat pump running**, **DHW heating rod** and **CH backup heater** on/off
- **Water temperature from the heat pump** and **CH flow temperature** (real values, not only set-points)
- Room temperature and **humidity**, DHW tank temperature, outdoor temperature (controller, heat pump sensor, online)
- Set-points, system / zone / DHW / buffer modes, pressure, signal strength
- Config flow (UI), re-authentication, options (update interval), diagnostics
- Robust polling: a failed gateway read is retried once and the last values are kept for up to
  3 failed polls in a row, so short cloud hiccups do not make everything *unavailable*

## Requirements

- Home Assistant **2025.3** or newer (the brand icon is shown from **2026.3**)
- ELCO heat pump with a Remocon-Net gateway on the **GALEVO** platform – in the
  [Remocon-Net portal](https://www.remocon-net.remotethermo.com) the plant URL contains
  `/R2/Plant/Index/`. Plants with `/R2/BsbPlantDashboard/` (BSB family) are **not** supported
  (see [thomasgregg/elco-aerotop](https://github.com/thomasgregg/elco-aerotop) for those).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=karliklukas&repository=ha-elco-remocon&category=integration)

1. Click the button above (or HACS → ⋮ → **Custom repositories** → add
   `https://github.com/karliklukas/ha-elco-remocon`, type **Integration**).
2. Download **ELCO Remocon-Net (read-only)** and restart Home Assistant.
3. Add the integration and log in with your Remocon-Net e-mail and password. Leave the API URL at its default.

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=elco_remocon_ro)

   (or **Settings → Devices & services → Add integration → ELCO Remocon-Net (read-only)**)

### Manual

Copy `custom_components/elco_remocon_ro` into `<config>/custom_components/` and restart Home Assistant.

## Configuration

| Option | Default | Notes |
|---|---|---|
| Update interval | 120 s | 60–3600 s. One update = 2 cloud requests; each reads live data from the gateway (~10 s). |

## Entities

Entity IDs start with `sensor.tepelne_cerpadlo_` / `binary_sensor.tepelne_cerpadlo_` (device name *Tepelné čerpadlo*).

| Entity | Type | Cloud source |
|---|---|---|
| TČ běží – heat pump running | binary | dataItem `IsHeatingPumpOn` |
| Spirála teplé vody – DHW heating rod | binary | dataItem `IsResistorOn` |
| Záložní spirála topení – CH backup heater | binary | menuItem 337 |
| Boost TV, Tichý režim, Požadavek na teplo, Dovolená, Ekvitermní regulace | binary | dataItems |
| HV vstup 1 – HV input 1 (SG Ready / PV) | binary, diagnostic | menuItem 304 |
| Režim TČ – heat pump operating mode | text | menuItem 340 |
| Teplota vody z TČ / Teplota výstupu topení | °C | menuItems 348 / 349 |
| Požadovaná teplota výstupu | °C | dataItem `ChFlowSetpointTemp` |
| Teplota v místnosti / Vlhkost v místnosti | °C / % | dataItem `ZoneMeasuredTemp` / menuItem 146 |
| Teplota zásobníku TV | °C | dataItem `DhwStorageTemperature` |
| Venkovní teplota (controller / TČ / online) | °C | dataItem `OutsideTemp` / menuItems 341, 130 *(online disabled by default)* |
| Room, DHW and buffer comfort / economy set-points | °C | dataItems |
| Režim systému / zóny / TV / akumulace | text (localized by the cloud) | dataItems |
| Tlak v systému | bar | dataItem `HeatingCircuitPressure` |
| Posun topné křivky, HV vstup 1 – funkce, Síla signálu | diagnostic | dataItem / menuItems 303, 119 |

## Dashboard example

Gauges below use [Modern Circular Gauge](https://github.com/selvalt7/modern-circular-gauge)
(HACS) – the set-point is shown as a dot on the ring:

```yaml
type: custom:modern-circular-gauge
entity: sensor.tepelne_cerpadlo_teplota_v_mistnosti
name: Místnost
min: 15
max: 28
decimals: 1
segments:
  - from: 15
    color: [11, 182, 239]
  - from: 19
    color: [76, 175, 80]
  - from: 24
    color: [255, 152, 0]
secondary:
  entity: sensor.tepelne_cerpadlo_pozadovana_teplota_mistnosti
  show_gauge: outer
  label: Cíl
```

Real and requested flow temperature in one tile – a template helper
(*Settings → Helpers → Template → Sensor*) with this state template:

```jinja
{% set a = states('sensor.tepelne_cerpadlo_teplota_vystupu_topeni') %}
{% set t = states('sensor.tepelne_cerpadlo_pozadovana_teplota_vystupu') %}
{% if is_number(a) and is_number(t) %}{{ ('%.1f' % (a|float)) | replace('.', ',') }} °C · cíl {{ ('%.1f' % (t|float)) | replace('.', ',') }} °C{% else %}—{% endif %}
```

## Troubleshooting

- **Everything unavailable for a few minutes** – the gateway sometimes answers
  `Gateway error … InternalError`. The integration retries and keeps the last values for 3 polls;
  longer outages are reported. Running another integration that polls the same gateway
  (e.g. the Ariston integration) increases the load – prefer one.
- **Debug logging**:
  ```yaml
  logger:
    logs:
      custom_components.elco_remocon_ro: debug
  ```
- **Diagnostics**: *Settings → Devices & services → ELCO Remocon-Net → ⋮ → Download diagnostics*
  (credentials, gateway ID and location are redacted).

## How it works

- `dataItems` – named values (`POST remote/dataItems/{gateway}/get`). Unknown IDs are silently ignored by the cloud.
- `menuItems` – numbered controller parameters (`GET menuItems/{gateway}?menuItems=…`).
  **A single unsupported number fails the whole request (HTTP 500)**, so only numbers verified on a
  real plant are requested (`MENU_IDS` in `const.py`; known crashers are listed there).
- If your controller differs, run the read-only probe first and open an issue with the
  (anonymised) results:
  ```
  python tools/probe.py --gateway <GATEWAY_ID>
  ```
  The probe output contains account and location data – **do not publish it as is**.

## Development

```
pip install aiohttp pytest pytest-asyncio
pytest
```

The tests cover the HA-independent parts (API client against a fake cloud, value mapping).
CI runs the HACS validation, hassfest and the tests on every push.

Releases follow the `version` in `manifest.json` (`vX.Y.Z` tags). HACS offers updates per release.

---

### Česky ve zkratce

Neoficiální integrace **jen pro čtení** pro tepelná čerpadla ELCO v cloudu Remocon-Net (řízení
GALEVO, např. AEROTOP MONO.2). Ukazuje, co čerpadlo dělá – běží, topí, odmrazuje, spínají spirály –
a skutečné teploty výstupu, místnosti a teplé vody. Do čerpadla nic nezapisuje. Instalace přes HACS
jako vlastní repozitář, přihlášení stejným e-mailem a heslem jako v aplikaci Remocon-Net.
