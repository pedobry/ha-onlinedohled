"""Daily download of heat and water consumption."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthFailed, PortalConnectionError, async_fetch_series
from .const import CONF_URL, DOMAIN, UPDATE_INTERVAL
from .portal import PortalError, SeriesReading, build_readings, merge_months

_LOGGER = logging.getLogger(__name__)


class OnlineDohledCoordinator(DataUpdateCoordinator[dict[str, SeriesReading]]):
    """Fetch three CSV exports once per day and keep scrolled-off months."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.entry_id = entry.entry_id
        self.username = entry.data["username"]
        self.password = entry.data["password"]
        self.page_url = entry.data[CONF_URL]
        self.store: Store[dict[str, object]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def _async_update_data(self) -> dict[str, SeriesReading]:
        previous = await self.store.async_load() or {}
        stored_series = previous.get("series")
        if not isinstance(stored_series, dict):
            stored_series = {}

        try:
            fetched = await self._async_fetch()
        except AuthFailed as err:
            raise ConfigEntryAuthFailed("Přihlášení do Online Dohledu selhalo") from err
        except (PortalConnectionError, PortalError) as err:
            raise UpdateFailed(str(err)) from err

        series = dict(stored_series)
        for key, parsed in fetched.items():
            previous_item = series.get(key)
            old_months = {}
            if isinstance(previous_item, dict) and isinstance(previous_item.get("months"), dict):
                old_months = previous_item["months"]
            series[key] = {
                "months": merge_months(old_months, parsed.rows),
                "native_unit": parsed.native_unit,
            }
        await self.store.async_save({"series": series})

        timezone = ZoneInfo(self.hass.config.time_zone or "UTC")
        readings = build_readings(series, dt_util.now(), timezone)
        for key, reading in readings.items():
            _LOGGER.info(
                "Online Dohled %s: celkem %s %s, tento měsíc %s %s",
                key,
                reading.total,
                reading.display_unit,
                reading.portal_value,
                reading.portal_unit,
            )
        return readings

    async def _async_fetch(self):
        return await async_fetch_series(self.username, self.password, self.page_url)

