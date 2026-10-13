# ELCO Remocon-Net (read-only) for Home Assistant

Unofficial, **read-only** Home Assistant integration for ELCO heat pumps connected to the
**Remocon-Net** cloud (Ariston group, GALEVO controller family – e.g. *AEROTOP MONO.2* with
*REMOCON PLUS.2*). It never writes anything to the heat pump.

It is meant as a companion to
[fustom/ariston-remotethermo-home-assistant-v3](https://github.com/fustom/ariston-remotethermo-home-assistant-v3)
(used for control) and adds the states and temperatures that integration does not expose,
e.g. *heat pump running*, *DHW heating rod*, *heat pump operating mode (defrost, …)*,
*water temperature from the heat pump*, *CH flow temperature* and *room humidity*.

> Entity names are in Czech. Not affiliated with ELCO, Ariston or Remocon-Net. The cloud API is
> undocumented and may change without notice.

## Entities

| Entity | Source |
|---|---|
| TČ běží (heat pump running) | dataItem `IsHeatingPumpOn` |
| Spirála teplé vody (DHW heating rod) | dataItem `IsResistorOn` |
| Záložní spirála topení (CH backup heater) | menuItem 337 |
| Boost teplé vody, Tichý režim, Požadavek na teplo, Dovolená | dataItems |
| Režim TČ (off / standby / heating / defrost / …) | menuItem 340 |
| Teplota vody z TČ / Teplota výstupu topení | menuItems 348 / 349 |
| Teplota v místnosti, Vlhkost v místnosti | dataItem `ZoneMeasuredTemp`, menuItem 146 |
| Teplota zásobníku TV | dataItem `DhwStorageTemperature` |
| Venkovní teplota (controller / heat pump / online) | dataItem `OutsideTemp`, menuItems 341 / 130 |
| Set-points, modes, pressure, signal strength | dataItems / menuItems |

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/karliklukas/ha-elco-remocon`, type *Integration*.
2. Install **ELCO Remocon-Net (read-only)** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → ELCO Remocon-Net (read-only)* and log in
   with your Remocon-Net e-mail and password.

The update interval (default 120 s, minimum 60 s) can be changed in the integration options.
Each update makes two requests to the cloud.

## Notes

* `menuItems` are numbered controller parameters. The cloud fails the **whole** request (HTTP 500)
  when a single unsupported number is requested, so only numbers verified on a real plant are
  listed in `const.py`. If your controller differs, run `tools/probe.py` first.
* `tools/probe.py` is a read-only probe that lists what the cloud returns for your plant
  (`python tools/probe.py --gateway <GATEWAY_ID>`). Its output contains account/location data –
  do not publish it.

---

### Česky ve zkratce

Neoficiální integrace **jen pro čtení** pro tepelná čerpadla ELCO v cloudu Remocon-Net (řízení
GALEVO). Doplňuje integraci fustom/ariston o stavy (TČ běží, spirála, odmrazování…) a skutečné
teploty. Instalace přes HACS jako vlastní repozitář, přihlášení stejným e-mailem a heslem jako
v aplikaci Remocon-Net.
