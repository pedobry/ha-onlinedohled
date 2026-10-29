"""Consumption sensors backed by monthly CSV exports."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from homeassistant.components.recorder.models.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_change_statistics_unit,
    async_import_statistics,
    can_convert_units,
    get_metadata,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import SERIES_KEYS
from .coordinator import OnlineDohledCoordinator
from .entity import OnlineDohledEntity
from .portal import SeriesReading

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

_NAMES = {
    "heat": "Spotřeba tepla",
    "cold_water": "Studená voda",
    "hot_water": "Teplá voda",
}
_ICONS = {
    "heat": "mdi:radiator",
    "cold_water": "mdi:water",
    "hot_water": "mdi:water-thermometer",
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Create one sensor per consumption series."""
    coordinator: OnlineDohledCoordinator = entry.runtime_data
    async_add_entities(OnlineDohledSensor(coordinator, key) for key in SERIES_KEYS)


class OnlineDohledSensor(OnlineDohledEntity, SensorEntity):
    """Monotonic consumption total for the energy dashboard."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: OnlineDohledCoordinator, key: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, key)
        self._attr_name = _NAMES[key]
        self._attr_icon = _ICONS[key]
        self._import_lock = asyncio.Lock()

    @property
    def _reading(self) -> SeriesReading | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self._reading is not None

    @property
    def native_value(self) -> float | None:
        reading = self._reading
        return None if reading is None else reading.total

    @property
    def native_unit_of_measurement(self) -> str | None:
        reading = self._reading
        if reading is None or not reading.display_unit:
            return None
        return reading.display_unit

    @property
    def device_class(self) -> SensorDeviceClass | None:
        reading = self._reading
        if reading is None:
            return None
        if reading.unit_class == "energy":
            return SensorDeviceClass.ENERGY
        if reading.unit_class == "volume":
            return SensorDeviceClass.WATER
        return None

    @property
    def extra_state_attributes(self) -> dict[str, float | str]:
        reading = self._reading
        if reading is None:
            return {}
        return {
            "current_month": reading.current_month,
            "portal_value": reading.portal_value,
            "portal_unit": reading.portal_unit,
        }

    def _handle_coordinator_update(self) -> None:
        """Convert stored history, then write the new state."""
        self.hass.async_create_task(self._async_import_and_write())

    async def _async_import_and_write(self) -> None:
        async with self._import_lock:
            await self._async_import_statistics()
            self.async_write_ha_state()

    async def _async_import_statistics(self) -> None:
        reading = self._reading
        if (
            reading is None
            or not reading.points
            or not reading.unit_class
            or not reading.display_unit
            or not self.entity_id
        ):
            return
        metadata: StatisticMetaData = {
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
            "name": self._attr_name,
            "source": "recorder",
            "statistic_id": self.entity_id,
            "unit_class": reading.unit_class,
            "unit_of_measurement": reading.display_unit,
        }
        statistics: list[StatisticData] = [
            {"start": start, "state": value, "sum": value} for start, value in reading.points
        ]
        try:
            await self._async_convert_existing_unit(reading.display_unit, reading.unit_class)
            async_import_statistics(self.hass, metadata, statistics)
        except Exception:
            _LOGGER.exception("Historie %s se nepodařila zapsat", self.entity_id)

    async def _async_convert_existing_unit(self, new_unit: str, unit_class: str) -> None:
        """Rewrite an earlier kWh history into GJ before new points are stored."""
        metadata = await self.hass.async_add_executor_job(
            partial(get_metadata, self.hass, statistic_ids={self.entity_id})
        )
        row = metadata.get(self.entity_id)
        if row is None:
            return
        old_unit = row[1].get("unit_of_measurement")
        if not old_unit or old_unit == new_unit:
            return
        if not can_convert_units(unit_class, old_unit, new_unit):
            raise HomeAssistantError(
                f"Historii {self.entity_id} nelze převést z {old_unit} na {new_unit}"
            )
        await async_change_statistics_unit(
            self.hass,
            self.entity_id,
            new_unit_of_measurement=new_unit,
            old_unit_of_measurement=old_unit,
        )
