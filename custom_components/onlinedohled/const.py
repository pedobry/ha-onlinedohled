"""Constants for the Online Dohled integration."""

from __future__ import annotations

DOMAIN = "onlinedohled"

CONF_URL = "url"

CONF_UPDATE_TIME = "update_time"
DEFAULT_UPDATE_TIME = "06:00:00"

SERIES_HEAT = "heat"
SERIES_COLD_WATER = "cold_water"
SERIES_HOT_WATER = "hot_water"
SERIES_KEYS = (SERIES_HEAT, SERIES_COLD_WATER, SERIES_HOT_WATER)

UNIT_GJ = "GJ"
UNIT_KWH = "kWh"
UNIT_M3 = "m³"
