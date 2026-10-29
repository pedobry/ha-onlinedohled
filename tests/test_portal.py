"""Tests for Online Dohled CSV totals, without importing Home Assistant."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "onlinedohled"

HEAT_CSV = """Datum; Spotreba tepla [GJ]
11/2025;2,577
12/2025;1,832001
1/2026;2,271
2/2026;1,565998
3/2026;1,418999
4/2026;0,02799988
5/2026;0
6/2026;0
7/2026;0
8/2026;0
9/2026;0
10/2026;0,7599983
"""

PAGE = (
    "https://app.onlinedohled.cz/GTBC/Z217063/"
    "BD-Sladova-Svetovar/Spotreba03.aspx"
)


def load_portal():
    package = types.ModuleType("onlinedohled")
    package.__path__ = [str(ROOT)]
    sys.modules["onlinedohled"] = package
    for name in ("const", "portal"):
        spec = importlib.util.spec_from_file_location(
            f"onlinedohled.{name}",
            ROOT / f"{name}.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules["onlinedohled.portal"]


portal = load_portal()


class PortalTests(unittest.TestCase):
    def test_heat_csv_rounds_and_converts_to_kwh(self) -> None:
        parsed = portal.parse_consumption_csv(HEAT_CSV)
        months = portal.merge_months({}, parsed.rows)
        self.assertEqual(months["2025-12"], "1.832")
        self.assertEqual(months["2026-02"], "1.566")
        self.assertEqual(months["2026-03"], "1.419")
        self.assertEqual(months["2026-04"], "0.028")
        self.assertEqual(months["2026-10"], "0.760")
        native = sum((Decimal(value) for value in months.values()), Decimal("0"))
        self.assertEqual(native, Decimal("10.453"))

        tz = ZoneInfo("Europe/Prague")
        now = datetime(2026, 10, 29, 10, 36, tzinfo=tz)
        reading = portal.build_reading("heat", parsed.native_unit, months, now, tz)

        self.assertEqual(reading.display_unit, "GJ")
        self.assertEqual(reading.unit_class, "energy")
        self.assertAlmostEqual(reading.total, 10.453, places=3)
        self.assertAlmostEqual(reading.current_month, 0.760, places=3)
        self.assertAlmostEqual(reading.portal_value, 0.760, places=3)
        self.assertEqual(reading.portal_unit, "GJ")

        self.assertEqual(len(reading.points), 12)
        self.assertEqual(reading.points[0][0], datetime(2025, 11, 30, 23, tzinfo=tz))
        self.assertAlmostEqual(reading.points[0][1], 2.577, places=3)
        self.assertEqual(reading.points[-2][0], datetime(2026, 9, 30, 23, tzinfo=tz))
        self.assertEqual(reading.points[-1][0], datetime(2026, 10, 29, 9, tzinfo=tz))
        self.assertAlmostEqual(reading.points[-1][1], reading.total, places=6)
        self.assertNotIn(datetime(2026, 10, 31, 23, tzinfo=tz), [point[0] for point in reading.points])

        previous = None
        for start, value in reading.points:
            self.assertEqual(start.minute, 0)
            self.assertEqual(start.second, 0)
            self.assertEqual(start.microsecond, 0)
            self.assertIsNotNone(start.tzinfo)
            if previous is not None:
                self.assertGreater(start, previous[0])
                self.assertGreaterEqual(value, previous[1])
            previous = (start, value)

    def test_cp1250_header(self) -> None:
        raw = "Datum; Spotřeba tepla [GJ]\n10/2026;1,5\n".encode("cp1250")
        text = portal.decode_csv(raw, "text/csv; charset=windows-1250")
        parsed = portal.parse_consumption_csv(text)
        self.assertIn("Spotřeba", parsed.header)
        self.assertEqual(parsed.native_unit, "GJ")
        self.assertEqual(portal.detect_series(parsed.header), "heat")

    def test_merge_keeps_history_and_never_drops(self) -> None:
        parsed = portal.parse_consumption_csv(HEAT_CSV)
        stored = portal.merge_months({"2024-11": "5.000", "2026-10": "0.500"}, parsed.rows)
        self.assertEqual(stored["2024-11"], "5.000")
        self.assertEqual(stored["2026-10"], "0.760")

        lowered = portal.merge_months(
            stored,
            [
                portal.MonthRow(parsed.rows[0].month, Decimal("1.000")),
                portal.MonthRow(parsed.rows[-1].month, Decimal("0.100")),
            ],
        )
        self.assertEqual(lowered["2025-11"], "2.577")
        self.assertEqual(lowered["2026-10"], "0.760")
        self.assertEqual(lowered["2024-11"], "5.000")

        tz = ZoneInfo("Europe/Prague")
        reading = portal.build_reading(
            "heat",
            "GJ",
            lowered,
            datetime(2026, 10, 29, 10, 36, tzinfo=tz),
            tz,
        )
        self.assertAlmostEqual(reading.total, 15.453, places=3)

    def test_water_units(self) -> None:
        cold = portal.parse_consumption_csv(
            "Datum; Spotřeba studené vody [m³]\n10/2026;1,25\n"
        )
        self.assertEqual(cold.native_unit, "m3")
        self.assertEqual(portal.detect_series(cold.header), "cold_water")
        hot = portal.parse_consumption_csv(
            "Datum; Spotreba teple vody [m3]\n10/2026;12,5\n"
        )
        self.assertEqual(portal.detect_series(hot.header), "hot_water")
        liters = portal.parse_consumption_csv("Datum; TUV [l]\n10/2026;2500\n")
        amount, unit, unit_class = portal.display_amount("l", liters.rows[0].value)
        self.assertEqual((amount, unit, unit_class), (Decimal("2.500"), "m³", "volume"))

    def test_assign_series_and_duplicate(self) -> None:
        heat = portal.parse_consumption_csv(HEAT_CSV)
        cold = portal.parse_consumption_csv("Datum; Studena voda [m3]\n10/2026;1\n")
        hot = portal.parse_consumption_csv("Datum; Tepla voda [m3]\n10/2026;2\n")
        assigned = portal.assign_series([(0, heat), (1, cold), (2, hot)])
        self.assertEqual(set(assigned), {"heat", "cold_water", "hot_water"})
        with self.assertRaises(portal.PortalError):
            portal.assign_series([(0, heat), (1, heat), (2, hot)])

    def test_header_overrides_checkbox_index(self) -> None:
        self.assertEqual(
            portal.series_for_checkbox(1, "Datum; Spotreba tepla [GJ]"),
            "heat",
        )

    def test_export_posts_one_checkbox(self) -> None:
        html = """
        <input type="hidden" name="__VIEWSTATE" value="secret" />
        <input type="checkbox" name="ctl00$CphDesktop$Chck2" />
        <input type="checkbox" name="ctl00$CphDesktop$Chck0" />
        <input type="checkbox" name="ctl00$CphDesktop$Chck1" />
        <select name="ctl00$CphDesktop$Drop1"></select>
        <input type="submit" name="ctl00$CphDesktop$BtnExport" value="csv" />
        """
        form = portal.parse_consumption_form(html)
        self.assertEqual(form.checkboxes[0], "ctl00$CphDesktop$Chck0")
        self.assertEqual(form.checkboxes[1], "ctl00$CphDesktop$Chck1")
        data = portal.export_form_data(form, 1)
        self.assertEqual(data["__VIEWSTATE"], "secret")
        self.assertEqual(data["ctl00$CphDesktop$Drop1"], "Aktuální")
        self.assertEqual(data["ctl00$CphDesktop$Chck1"], "on")
        self.assertEqual(data["ctl00$CphDesktop$BtnExport"], "csv")
        self.assertNotIn("ctl00$CphDesktop$Chck0", data)
        self.assertNotIn("ctl00$CphDesktop$Chck2", data)

    def test_login_form(self) -> None:
        html = """
        <input type="hidden" name="__VIEWSTATE" value="abc" />
        <input type="text" name="Login1$UserName" />
        <input type="password" name="Login1$Password" />
        <input type="submit" name="Login1$LoginButton" value="Přihlásit" />
        """
        form = portal.parse_login_form(html)
        data = portal.login_form_data(form, "user", "secret")
        self.assertEqual(data["Login1$UserName"], "user")
        self.assertEqual(data["Login1$Password"], "secret")
        self.assertEqual(data["Login1$LoginButton"], "Přihlásit")
        self.assertEqual(data["__VIEWSTATE"], "abc")

    def test_page_url(self) -> None:
        raw = PAGE + "?x=1"
        mixed = raw.replace("app.onlinedohled.cz", "APP.onlinedohled.cz")
        self.assertEqual(portal.normalize_page_url(mixed), PAGE)
        self.assertEqual(portal.device_name_from_url(PAGE), "BD Sladova Svetovar")
        with self.assertRaises(portal.PortalError):
            portal.normalize_page_url("http://app.onlinedohled.cz/Spotreba03.aspx")


if __name__ == "__main__":
    unittest.main()
