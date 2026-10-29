"""Config flow for Online Dohled."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AuthFailed, PortalConnectionError, async_fetch_series
from .const import CONF_URL, DOMAIN
from .portal import PortalError, device_name_from_url, normalize_page_url

_LOGGER = logging.getLogger(__name__)

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_URL): str,
    }
)
_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class OnlineDohledConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config entry for one Online Dohled account."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Ask for credentials and the consumption page URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_page_url(user_input[CONF_URL])
            except PortalError:
                errors["base"] = "invalid_url"
            else:
                username = user_input[CONF_USERNAME].strip()
                password = user_input[CONF_PASSWORD]
                errors = await self._async_test(username, password, url)
                if not errors:
                    await self.async_set_unique_id(f"{username.lower()}|{url}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=device_name_from_url(url),
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_URL: url,
                        },
                    )
        return self.async_show_form(step_id="user", data_schema=_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Start a password refresh after a failed login."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Ask for a new password and reload the entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            errors = await self._async_test(
                entry.data[CONF_USERNAME],
                password,
                entry.data[CONF_URL],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_REAUTH_SCHEMA,
            errors=errors,
        )

    async def _async_test(self, username: str, password: str, url: str) -> dict[str, str]:
        try:
            await async_fetch_series(username, password, url)
        except AuthFailed:
            return {"base": "invalid_auth"}
        except PortalConnectionError:
            _LOGGER.exception("Online Dohled není dostupný")
            return {"base": "cannot_connect"}
        except PortalError:
            _LOGGER.exception("Export z Online Dohledu selhal")
            return {"base": "export_failed"}
        except Exception:
            _LOGGER.exception("Neočekávaná chyba Online Dohledu")
            return {"base": "unknown"}
        return {}
