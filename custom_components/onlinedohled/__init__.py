"""Online Dohled consumption integration."""

from __future__ import annotations

from datetime import datetime, time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import CONF_UPDATE_TIME, DEFAULT_UPDATE_TIME
from .coordinator import OnlineDohledCoordinator

PLATFORMS = ["sensor", "button"]

type OnlineDohledConfigEntry = ConfigEntry[OnlineDohledCoordinator]


def update_time(entry: ConfigEntry) -> time:
    """Return the configured local time of the daily download."""
    raw = entry.options.get(CONF_UPDATE_TIME, DEFAULT_UPDATE_TIME)
    try:
        return time.fromisoformat(raw)
    except (TypeError, ValueError):
        return time.fromisoformat(DEFAULT_UPDATE_TIME)


async def async_setup_entry(hass: HomeAssistant, entry: OnlineDohledConfigEntry) -> bool:
    """Set up Online Dohled from a config entry."""
    coordinator = OnlineDohledCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    at = update_time(entry)

    @callback
    def _scheduled_refresh(_now: datetime) -> None:
        hass.async_create_task(coordinator.async_request_refresh())

    entry.async_on_unload(
        async_track_time_change(
            hass, _scheduled_refresh, hour=at.hour, minute=at.minute, second=at.second
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OnlineDohledConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
