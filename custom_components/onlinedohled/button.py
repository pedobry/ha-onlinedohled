"""Manual refresh of Online Dohled exports."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from .coordinator import OnlineDohledCoordinator
from .entity import OnlineDohledEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Create the refresh button."""
    coordinator: OnlineDohledCoordinator = entry.runtime_data
    async_add_entities([OnlineDohledRefreshButton(coordinator)])


class OnlineDohledRefreshButton(OnlineDohledEntity, ButtonEntity):
    """Download the three CSV exports now."""

    def __init__(self, coordinator: OnlineDohledCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "refresh")
        self._attr_name = "Obnovit spotřeby"
        self._attr_icon = "mdi:download"

    async def async_press(self) -> None:
        """Request an immediate download."""
        await self.coordinator.async_request_refresh()
