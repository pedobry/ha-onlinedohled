"""Pure parsing and totals for Online Dohled CSV exports.

The consumption page is an ASP.NET form. Heat, cold water and hot water are
checkboxes Chck0, Chck1 and Chck2. Export posts BtnExport=csv with Drop1 set
to the current twelve-month window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .const import (
    SERIES_COLD_WATER,
    SERIES_HEAT,
    SERIES_HOT_WATER,
    SERIES_KEYS,
    UNIT_KWH,
    UNIT_M3,
)

PERIOD_CURRENT = "Aktuální"
_QUANT = Decimal("0.001")
_KWH_FACTOR = Decimal(1000) / Decimal("3.6")
_CHECKBOX = re.compile(r"Chck(\d+)$")
_DIACRITICS = str.maketrans(
    "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
    "acdeeinorstuuyzACDEEINORSTUUYZ",
)


class PortalError(Exception):
    """Base error for portal data that is present but unusable."""


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def parse_number(raw: str) -> Decimal:
    """Parse a Czech decimal such as '1,832001' and round to 3 places."""
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        raise PortalError("CSV obsahuje prázdnou hodnotu")
    try:
        number = _q(Decimal(cleaned))
    except Exception as err:
        raise PortalError(f"CSV obsahuje nečitelnou hodnotu {raw!r}") from err
    if number < 0:
        return Decimal("0.000")
    return number


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def decode_csv(raw: bytes, content_type: str) -> str:
    """Decode an export body. The portal sends Windows-1250."""
    if "1250" in content_type.lower():
        return raw.decode("cp1250")
    if "utf-8" in content_type.lower():
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1250")


@dataclass(frozen=True)
class MonthRow:
    """One monthly consumption value in the portal unit."""

    month: date
    value: Decimal


@dataclass(frozen=True)
class ParsedCsv:
    """A single exported series."""

    header: str
    native_unit: str
    rows: tuple[MonthRow, ...]


def parse_consumption_csv(text: str) -> ParsedCsv:
    """Parse a monthly consumption export."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("sep="):
            continue
        lines.append(stripped)
    if not lines or "datum" not in lines[0].lower():
        raise PortalError("Export nevypadá jako CSV spotřeby")

    header = lines[0]
    native_unit = _native_unit(header)
    by_month: dict[date, Decimal] = {}
    for line in lines[1:]:
        date_raw, value_raw = (line.split(";", 1) + [""])[:2]
        try:
            month_s, year_s = date_raw.strip().split("/")
            month = date(int(year_s), int(month_s), 1)
        except ValueError as err:
            raise PortalError(f"Nečitelný měsíc {date_raw!r}") from err
        value = parse_number(value_raw)
        previous = by_month.get(month)
        by_month[month] = value if previous is None else max(previous, value)

    if not by_month:
        raise PortalError("CSV neobsahuje žádný měsíc")
    rows = tuple(MonthRow(month, by_month[month]) for month in sorted(by_month))
    return ParsedCsv(header=header, native_unit=native_unit, rows=rows)


def _native_unit(header: str) -> str:
    match = re.search(r"\[([^\]]+)\]", header)
    if not match:
        return ""
    unit = match.group(1).strip().lower().replace(" ", "").replace("³", "3").replace("^", "")
    if unit == "gj":
        return "GJ"
    if unit == "kwh":
        return "kWh"
    if unit == "mwh":
        return "MWh"
    if unit in {"m3", "m^3"}:
        return "m3"
    if unit in {"l", "ltr", "litr", "litry"}:
        return "l"
    return match.group(1).strip()


def detect_series(header: str) -> str | None:
    """Recognize heat, cold water or hot water from the CSV header."""
    folded = header.lower().translate(_DIACRITICS)
    if "studen" in folded:
        return SERIES_COLD_WATER
    if "tuv" in folded or ("tepl" in folded and "vod" in folded):
        return SERIES_HOT_WATER
    if "tepl" in folded or "[gj]" in folded or " gj" in folded:
        return SERIES_HEAT
    return None


def series_for_checkbox(index: int, header: str) -> str:
    """Map a checkbox export to a series, preferring the CSV header."""
    expected = SERIES_KEYS[index]
    detected = detect_series(header)
    if detected is None:
        return expected
    return detected


def assign_series(
    exports: list[tuple[int, ParsedCsv]],
) -> dict[str, ParsedCsv]:
    """Attach the three exports to heat, cold water and hot water."""
    found: dict[str, ParsedCsv] = {}
    for index, parsed in exports:
        key = series_for_checkbox(index, parsed.header)
        if key in found:
            raise PortalError(
                "Dva exporty vyšly jako stejná veličina "
                f"({found[key].header!r} a {parsed.header!r})"
            )
        found[key] = parsed
    missing = [key for key in SERIES_KEYS if key not in found]
    if missing:
        headers = ", ".join(parsed.header for _, parsed in exports)
        raise PortalError(f"V exportech chybí {', '.join(missing)}. Hlavičky: {headers}")
    return found


def merge_months(stored: dict[str, str], rows: tuple[MonthRow, ...] | list[MonthRow]) -> dict[str, str]:
    """Keep already downloaded months when they fall out of the 12-month window.

    A later export never lowers a stored month. The current month only grows,
    and a closed month that scrolls away stays in the total.
    """
    merged = {key: str(_q(Decimal(value))) for key, value in stored.items()}
    for row in rows:
        key = month_key(row.month)
        new_value = _q(row.value)
        old = merged.get(key)
        if old is None or new_value >= Decimal(old):
            merged[key] = str(new_value)
    return merged


def _stored_decimal(months: dict[str, str], key: str) -> Decimal:
    return _q(Decimal(months[key]))


def display_amount(native_unit: str, amount: Decimal) -> tuple[Decimal, str, str | None]:
    """Convert a portal amount to the unit Home Assistant graphs expect."""
    unit = native_unit.strip()
    if unit == "GJ":
        return _q(amount * _KWH_FACTOR), UNIT_KWH, "energy"
    if unit == "kWh":
        return _q(amount), UNIT_KWH, "energy"
    if unit == "MWh":
        return _q(amount * Decimal(1000)), UNIT_KWH, "energy"
    if unit == "m3":
        return _q(amount), UNIT_M3, "volume"
    if unit == "l":
        return _q(amount / Decimal(1000)), UNIT_M3, "volume"
    return _q(amount), unit, None


def _display_sum(native_unit: str, months: dict[str, str], keys: list[str]) -> Decimal:
    total = sum((_stored_decimal(months, key) for key in keys), Decimal("0"))
    converted, _unit, _unit_class = display_amount(native_unit, total)
    return converted


@dataclass(frozen=True)
class SeriesReading:
    """Sensor state plus hourly statistic points for one series."""

    key: str
    total: float
    display_unit: str
    unit_class: str | None
    current_month: float
    portal_value: float
    portal_unit: str
    points: tuple[tuple[datetime, float], ...]


def build_reading(
    key: str,
    native_unit: str,
    months: dict[str, str],
    now: datetime,
    tz: ZoneInfo,
) -> SeriesReading:
    """Build a monotonic cumulative reading and past statistic points."""
    keys = sorted(months)
    if not keys:
        raise PortalError(f"Řada {key} nemá žádné měsíce")
    current_key = keys[-1]
    converted, display_unit, unit_class = display_amount(
        native_unit, _stored_decimal(months, current_key)
    )
    total = _display_sum(native_unit, months, keys)
    total_float = float(total)
    points: list[tuple[datetime, float]] = []
    for key_index, month in enumerate(keys[:-1]):
        year_s, month_s = month.split("-")
        start = _month_end_hour(int(year_s), int(month_s), tz)
        if start > now:
            continue
        cumulative = float(_display_sum(native_unit, months, keys[: key_index + 1]))
        points.append((start, cumulative))

    snapshot = _previous_hour(now, tz)
    if points and snapshot <= points[-1][0]:
        snapshot = None
    if snapshot is not None and snapshot <= now:
        points.append((snapshot, total_float))

    return SeriesReading(
        key=key,
        total=total_float,
        display_unit=display_unit or "",
        unit_class=unit_class,
        current_month=float(converted),
        portal_value=float(_stored_decimal(months, current_key)),
        portal_unit=native_unit,
        points=tuple(points),
    )


def build_readings(
    series: dict[str, dict[str, object]],
    now: datetime,
    tz: ZoneInfo,
) -> dict[str, SeriesReading]:
    readings: dict[str, SeriesReading] = {}
    for key in SERIES_KEYS:
        item = series.get(key)
        if not item:
            continue
        months = item.get("months")
        native_unit = item.get("native_unit")
        if not isinstance(months, dict) or not months or not isinstance(native_unit, str):
            continue
        readings[key] = build_reading(key, native_unit, months, now, tz)
    return readings


def _month_end_hour(year: int, month: int, tz: ZoneInfo) -> datetime:
    if month == 12:
        first_next = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        first_next = datetime(year, month + 1, 1, tzinfo=tz)
    end = first_next - timedelta(hours=1)
    return end.replace(minute=0, second=0, microsecond=0)


def _previous_hour(now: datetime, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    return local - timedelta(hours=1)


@dataclass(frozen=True)
class LoginForm:
    hidden: dict[str, str]
    username_field: str
    password_field: str
    button_field: str
    button_value: str


@dataclass(frozen=True)
class ConsumptionForm:
    hidden: dict[str, str]
    checkboxes: dict[int, str]
    period_field: str
    export_field: str
    export_value: str


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}
        self.checkboxes: dict[int, str] = {}
        self.username_field = ""
        self.password_field = ""
        self.login_button_field = ""
        self.login_button_value = "Přihlásit"
        self.period_field = ""
        self.export_field = ""
        self.export_value = "csv"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"input", "select"}:
            return
        values = {key.lower(): value or "" for key, value in attrs}
        name = values.get("name", "")
        if not name:
            return
        field_type = values.get("type", "").lower()
        if tag == "input" and field_type == "hidden":
            self.hidden[name] = values.get("value", "")
        if tag == "input" and field_type == "checkbox":
            match = _CHECKBOX.search(name)
            if match:
                self.checkboxes[int(match.group(1))] = name
        if tag == "input" and field_type == "text" and name.endswith("$UserName"):
            self.username_field = name
        if tag == "input" and field_type == "password" and name.endswith("$Password"):
            self.password_field = name
        if tag == "input" and field_type == "submit" and name.endswith("$LoginButton"):
            self.login_button_field = name
            self.login_button_value = values.get("value") or self.login_button_value
        if tag == "select" and name.endswith("$Drop1"):
            self.period_field = name
        if tag == "input" and field_type == "submit" and values.get("value", "").lower() == "csv":
            self.export_field = name
            self.export_value = values.get("value") or "csv"


def parse_login_form(html: str) -> LoginForm:
    parser = _InputParser()
    parser.feed(html)
    if not parser.username_field or not parser.password_field or not parser.login_button_field:
        raise PortalError("Přihlašovací formulář nemá očekávaná pole")
    return LoginForm(
        hidden=parser.hidden,
        username_field=parser.username_field,
        password_field=parser.password_field,
        button_field=parser.login_button_field,
        button_value=parser.login_button_value,
    )


def parse_consumption_form(html: str) -> ConsumptionForm:
    parser = _InputParser()
    parser.feed(html)
    missing = [index for index in (0, 1, 2) if index not in parser.checkboxes]
    if missing:
        raise PortalError(
            "Stránka spotřeby nemá přepínače "
            + ", ".join(f"Chck{index}" for index in missing)
        )
    return ConsumptionForm(
        hidden=parser.hidden,
        checkboxes=parser.checkboxes,
        period_field=parser.period_field or "ctl00$CphDesktop$Drop1",
        export_field=parser.export_field or "ctl00$CphDesktop$BtnExport",
        export_value=parser.export_value or "csv",
    )


def login_form_data(form: LoginForm, username: str, password: str) -> dict[str, str]:
    data = dict(form.hidden)
    data[form.username_field] = username
    data[form.password_field] = password
    data[form.button_field] = form.button_value
    return data


def export_form_data(form: ConsumptionForm, checkbox_index: int) -> dict[str, str]:
    """Build the CSV export body for a single checkbox."""
    data = dict(form.hidden)
    for name in form.checkboxes.values():
        data.pop(name, None)
    data[form.period_field] = PERIOD_CURRENT
    data[form.checkboxes[checkbox_index]] = "on"
    data[form.export_field] = form.export_value
    return data


def device_name_from_url(url: str) -> str:
    parts = [part for part in url.split("/") if part]
    if len(parts) >= 2 and parts[-1].lower().endswith(".aspx"):
        return parts[-2].replace("-", " ")
    return "Online Dohled"


def normalize_page_url(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    raw = url.strip()
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.netloc or not parts.path.lower().endswith(".aspx"):
        raise PortalError("Adresa musí být https odkaz na stránku .aspx")
    return urlunsplit(("https", parts.netloc.lower(), parts.path, "", ""))
