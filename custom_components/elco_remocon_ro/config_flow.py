"""Config flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import DEFAULT_API_URL, RemoconApi, RemoconAuthError, RemoconError
from .const import (
    CONF_API_URL,
    CONF_GATEWAY,
    CONF_PLANT_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

DEFAULT_TITLE = "Tepelné čerpadlo"

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
    }
)


class RemoconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._plants: list[dict[str, Any]] = []

    async def _login(self, user_input: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        api = RemoconApi(
            async_get_clientsession(self.hass),
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            user_input.get(CONF_API_URL, DEFAULT_API_URL),
        )
        try:
            await api.login()
            plants = await api.get_plants()
        except RemoconAuthError:
            return [], {"base": "invalid_auth"}
        except RemoconError:
            return [], {"base": "cannot_connect"}
        if not plants:
            return [], {"base": "no_plants"}
        return plants, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            plants, errors = await self._login(user_input)
            if not errors:
                self._user_input = user_input
                self._plants = plants
                if len(plants) == 1:
                    return await self._create(plants[0])
                return await self.async_step_plant()
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input), errors=errors
        )

    async def async_step_plant(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            plant = next(p for p in self._plants if p.get("gwId") == user_input[CONF_GATEWAY])
            return await self._create(plant)
        options = [
            SelectOptionDict(value=p["gwId"], label=f"{p.get('plantName') or p['gwId']} ({p['gwId']})")
            for p in self._plants
            if p.get("gwId")
        ]
        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema({vol.Required(CONF_GATEWAY): SelectSelector(SelectSelectorConfig(options=options))}),
        )

    async def _create(self, plant: dict[str, Any]) -> ConfigFlowResult:
        gateway = plant["gwId"]
        await self.async_set_unique_id(gateway)
        self._abort_if_unique_id_configured()
        # store only what is needed - no location/address data
        return self.async_create_entry(
            title=DEFAULT_TITLE,
            data={
                CONF_USERNAME: self._user_input[CONF_USERNAME],
                CONF_PASSWORD: self._user_input[CONF_PASSWORD],
                CONF_API_URL: self._user_input.get(CONF_API_URL, DEFAULT_API_URL),
                CONF_GATEWAY: gateway,
                CONF_PLANT_NAME: plant.get("plantName"),
            },
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            _, errors = await self._login(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RemoconOptionsFlow()


class RemoconOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600))}
            ),
        )
