"""Shared device info for Online Dohled entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OnlineDohledCoordinator
from .portal import device_name_from_url


class OnlineDohledEntity(CoordinatorEntity[OnlineDohledCoordinator]):
    """Entity attached to one Online Dohled account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OnlineDohledCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=device_name_from_url(coordinator.page_url),
            manufacturer="GTBC",
            model="Online Dohled",
            configuration_url=coordinator.page_url,
        )
