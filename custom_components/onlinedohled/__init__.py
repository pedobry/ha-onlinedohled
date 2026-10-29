"""Online Dohled consumption integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import OnlineDohledCoordinator

PLATFORMS = ["sensor", "button"]

type OnlineDohledConfigEntry = ConfigEntry[OnlineDohledCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OnlineDohledConfigEntry) -> bool:
    """Set up Online Dohled from a config entry."""
    coordinator = OnlineDohledCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OnlineDohledConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
