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
from .const import CONF_URL, DOMAIN
from .portal import PortalError, SeriesReading, build_readings, merge_months

_LOGGER = logging.getLogger(__name__)


class OnlineDohledCoordinator(DataUpdateCoordinator[dict[str, SeriesReading]]):
    """Fetch three CSV exports once per day at a configured time and keep scrolled-off months."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Downloads are triggered at the configured time of day, see __init__.py.
            update_interval=None,
            config_entry=entry,
        )
        self.entry_id = entry.entry_id
        self.username = entry.data["username"]
        self.password = entry.data["password"]
        self.page_url = entry.data[CONF_URL]
        self.store: Store[dict[str, object]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        # Cleared once after upgrading from absolute-sum imports that broke the energy dashboard.
        self.reset_statistics: bool = False

    async def _async_update_data(self) -> dict[str, SeriesReading]:
        previous = await self.store.async_load() or {}
        stored_series = previous.get("series")
        if not isinstance(stored_series, dict):
            stored_series = {}
        sum_rebased = bool(previous.get("sum_rebased"))

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
            old_baseline = None
            if isinstance(previous_item, dict):
                if isinstance(previous_item.get("months"), dict):
                    old_months = previous_item["months"]
                baseline = previous_item.get("sum_baseline_native")
                if isinstance(baseline, str):
                    old_baseline = baseline
            series[key] = {
                "months": merge_months(old_months, parsed.rows),
                "native_unit": parsed.native_unit,
                "sum_baseline_native": old_baseline,
            }

        timezone = ZoneInfo(self.hass.config.time_zone or "UTC")
        readings = build_readings(series, dt_util.now(), timezone)
        for key, reading in readings.items():
            item = series.get(key)
            if isinstance(item, dict):
                item["sum_baseline_native"] = reading.sum_baseline_native
            _LOGGER.info(
                "Online Dohled %s: celkem %s %s, tento měsíc %s %s",
                key,
                reading.total,
                reading.display_unit,
                reading.portal_value,
                reading.portal_unit,
            )
        # Existing installs had absolute cumulative values in ``sum``; wipe once so
        # the rebased import does not sit next to those old points.
        self.reset_statistics = bool(stored_series) and not sum_rebased
        await self.store.async_save({"series": series, "sum_rebased": True})
        return readings

    async def _async_fetch(self):
        return await async_fetch_series(self.username, self.password, self.page_url)

