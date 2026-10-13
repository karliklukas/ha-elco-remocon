"""Diagnostics (Settings -> Devices -> Download diagnostics)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_GATEWAY
from .coordinator import RemoconConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, CONF_GATEWAY, "gwId", "gw", "gwSerial", "sn", "location", "loc", "addr"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: RemoconConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "features": async_redact_data(coordinator.features or {}, TO_REDACT),
        "plant": async_redact_data(coordinator.plant, TO_REDACT),
        "data": asdict(coordinator.data) if coordinator.data else None,
        "energy": (
            {
                "bucket_end": energy.bucket_end.isoformat(),
                "imported": energy.imported,
                "sequences": {f"k{k}_p{p}": v for (k, p), v in energy.sequences.items()},
            }
            if coordinator.energy and (energy := coordinator.energy.data)
            else None
        ),
    }
