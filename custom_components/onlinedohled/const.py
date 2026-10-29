"""Constants for the Online Dohled integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "onlinedohled"

CONF_URL = "url"

UPDATE_INTERVAL = timedelta(hours=24)

SERIES_HEAT = "heat"
SERIES_COLD_WATER = "cold_water"
SERIES_HOT_WATER = "hot_water"
SERIES_KEYS = (SERIES_HEAT, SERIES_COLD_WATER, SERIES_HOT_WATER)

UNIT_KWH = "kWh"
UNIT_M3 = "m³"
