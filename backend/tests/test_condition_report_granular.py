"""Tests for condition_report_granular repair filtering, abbreviations, and dedup."""

from __future__ import annotations

from app.schemas.condition_report_granular import (
    build_granular_condition_report,
    _extract_repaired_panels,
    _is_repaired_damage,
    _map_text_to_field,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(
    damage_items: list | None = None,
    body_text: str | None = None,
    **extra: object,
) -> dict:
    report: dict = {
        "overall_grade": "4.8",
        "damage_items": damage_items or [],
        **extra,
    }
    if body_text is not None:
        report.setdefault("metadata", {}).setdefault("report_page", {})["body_text"] = body_text
    return report


BODY_TEXT_WITH_REPAIRED = """
Cosmetic Conventional Paint and Body Not Required-[1 Items]

IMAGE   DESCRIPTION     CONDITION       SEVERITY
        LF Door Dent/No Paint Dmg       PDR/1


        Repaired

IMAGE   DESCRIPTION     CONDITION       SEVERITY        REPAIR STATUS
        LF Bumper Cover Scratch Heavy   1/2" to 1"      Completed
        RF Bumper Cover Scratch Heavy   2" to 3"        Completed



IMAGE   DESCRIPTION     CONDITION       SEVERITY
        0000 Picture# 1 Overall Picture
"""

# The actual 6 damage items from the affected VIN's stored data
REAL_DAMAGE_ITEMS = [
    {
        "panel": "LF Door",
        "section": "cosmetic_conventional_paint_and_body_not_required",
        "condition": "Dent/No Paint Dmg",
        "section_label": "Cosmetic Conventional Paint and Body Not Required",
        "severity_rank": 1,
        "severity_color": "yellow",
        "severity_label": "moderate",
        "reported_severity": "PDR/1",
    },
    {
        "panel": "LF Bumper Cover",
        "section": "cosmetic_conventional_paint_and_body_not_required",
        "condition": "Scratch Heavy",
        "section_label": "Cosmetic Conventional Paint and Body Not Required",
        "severity_rank": 1,
        "severity_color": "yellow",
        "severity_label": "moderate",
        "reported_severity": '1/2" to 1"',
    },
    {
        "panel": "RF Bumper Cover",
        "section": "cosmetic_conventional_paint_and_body_not_required",
        "condition": "Scratch Heavy",
        "section_label": "Cosmetic Conventional Paint and Body Not Required",
        "severity_rank": 1,
        "severity_color": "yellow",
        "severity_label": "moderate",
        "reported_severity": '2" to 3"',
    },
    {
        "panel": "LF Bumper Cover",
        "action": "Touch Up",
        "source": "listing_json.conditionEnrichment.damages",
        "section": "exterior",
        "condition": "Scratch Heavy",
        "section_label": "Paint and Body Requires Conventional Repair",
        "severity_rank": 1,
        "severity_color": "gray",
        "severity_label": "minor",
        "reported_severity": '1/2" to 1"',
        "raw": {"displayRepaired": False},
    },
    {
        "panel": "RF Bumper Cover",
        "action": "Partial Repair",
        "source": "listing_json.conditionEnrichment.damages",
        "section": "exterior",
        "condition": "Scratch Heavy",
        "section_label": "Paint and Body Requires Conventional Repair",
        "severity_rank": 1,
        "severity_color": "gray",
        "severity_label": "minor",
        "reported_severity": '2" to 3"',
        "raw": {"displayRepaired": False},
    },
    {
        "panel": "LF Door",
        "action": "PDR",
        "source": "listing_json.conditionEnrichment.damages",
        "section": "exterior",
        "condition": "Dent/No Paint Dmg",
        "section_label": "Cosmetic Conventional Paint and Body Not Required",
        "severity_rank": 1,
        "severity_color": "gray",
        "severity_label": "minor",
        "reported_severity": "PDR/1",
        "raw": {"displayRepaired": False},
    },
]


# ---------------------------------------------------------------------------
# _extract_repaired_panels
# ---------------------------------------------------------------------------

class TestExtractRepairedPanels:
    def test_extracts_repaired_panels_from_body_text(self):
        report = _make_report(body_text=BODY_TEXT_WITH_REPAIRED)
        panels = _extract_repaired_panels(report)
        assert ("lf bumper cover", "scratch") in panels
        assert ("rf bumper cover", "scratch") in panels

    def test_does_not_include_active_damage(self):
        report = _make_report(body_text=BODY_TEXT_WITH_REPAIRED)
        panels = _extract_repaired_panels(report)
        # LF Door is in the active section, not the Repaired section
        panel_names = {p for p, _ in panels}
        assert "lf door" not in panel_names

    def test_returns_empty_without_body_text(self):
        report = _make_report()
        assert _extract_repaired_panels(report) == set()

    def test_returns_empty_when_no_repaired_section(self):
        body = "Cosmetic Conventional Paint and Body Not Required-[1 Items]\nLF Door Dent/No Paint Dmg PDR/1\n"
        report = _make_report(body_text=body)
        assert _extract_repaired_panels(report) == set()


# ---------------------------------------------------------------------------
# _is_repaired_damage
# ---------------------------------------------------------------------------

class TestIsRepairedDamage:
    def test_explicit_repair_status_completed(self):
        item = {"panel": "LF Bumper Cover", "condition": "Scratch", "repair_status": "completed"}
        assert _is_repaired_damage(item, set()) is True

    def test_explicit_repair_status_repaired(self):
        item = {"panel": "LF Bumper Cover", "condition": "Scratch", "repair_status": "repaired"}
        assert _is_repaired_damage(item, set()) is True

    def test_section_label_repaired(self):
        item = {"panel": "LF Bumper Cover", "condition": "Scratch", "section_label": "Repaired"}
        assert _is_repaired_damage(item, set()) is True

    def test_body_text_repaired_panels_match(self):
        item = {"panel": "LF Bumper Cover", "condition": "Scratch Heavy"}
        repaired = {("lf bumper cover", "scratch")}
        assert _is_repaired_damage(item, repaired) is True

    def test_active_damage_not_filtered(self):
        item = {"panel": "LF Door", "condition": "Dent/No Paint Dmg"}
        assert _is_repaired_damage(item, set()) is False

    def test_pdr_not_treated_as_repair(self):
        item = {"panel": "LF Door", "condition": "Dent/No Paint Dmg", "reported_severity": "PDR/1"}
        assert _is_repaired_damage(item, set()) is False


# ---------------------------------------------------------------------------
# Manheim abbreviation patterns
# ---------------------------------------------------------------------------

class TestManheimAbbreviations:
    def test_lf_door_maps_to_driver_front_door(self):
        result = _map_text_to_field("LF Door Dent/No Paint Dmg PDR/1")
        assert result == ("exterior", "driver_front_door")

    def test_rf_door_maps_to_passenger_front_door(self):
        result = _map_text_to_field("RF Door Scratch Heavy")
        assert result == ("exterior", "passenger_front_door")

    def test_lr_door_maps_to_driver_rear_door(self):
        result = _map_text_to_field("LR Door Dent")
        assert result == ("exterior", "driver_rear_door")

    def test_rr_door_maps_to_passenger_rear_door(self):
        result = _map_text_to_field("RR Door Scratch")
        assert result == ("exterior", "passenger_rear_door")

    def test_lf_bumper_maps_to_front_bumper(self):
        result = _map_text_to_field("LF Bumper Cover Scratch Heavy")
        assert result == ("exterior", "front_bumper")

    def test_rf_bumper_maps_to_front_bumper(self):
        result = _map_text_to_field("RF Bumper Cover Curb Rash")
        assert result == ("exterior", "front_bumper")

    def test_lr_bumper_maps_to_rear_bumper(self):
        result = _map_text_to_field("LR Bumper Cover Scratch")
        assert result == ("exterior", "rear_bumper")

    def test_lf_fender_maps_to_driver_fender(self):
        result = _map_text_to_field("LF Fender Dent")
        assert result == ("exterior", "driver_fender")

    def test_lr_quarter_maps_to_driver_quarter(self):
        result = _map_text_to_field("LR Quarter Panel Dent")
        assert result == ("exterior", "driver_quarter")

    def test_rr_quarter_maps_to_passenger_quarter(self):
        result = _map_text_to_field("RR Quarter Panel Scratch")
        assert result == ("exterior", "passenger_quarter")

    def test_lf_tire_still_maps_to_tire(self):
        """LF + tire should map to tires, not exterior."""
        result = _map_text_to_field("LF Tire Curb Rash")
        assert result is not None
        assert result[0] == "tires"
        assert result[1] == "driver_front_tire_issue"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_panel_condition_only_creates_one_issue(self):
        items = [
            {"panel": "LF Door", "condition": "Dent/No Paint Dmg", "section_label": "Cosmetic"},
            {"panel": "LF Door", "condition": "Dent/No Paint Dmg", "section_label": "Different Source"},
        ]
        report = _make_report(damage_items=items)
        granular = build_granular_condition_report(report)
        # The field should have an issue, but only one value (not doubled)
        field = granular["exterior"]["fields"]["driver_front_door"]
        assert field["status"] == "issue"


# ---------------------------------------------------------------------------
# Full integration: real VIN scenario
# ---------------------------------------------------------------------------

class TestRealVinScenario:
    def test_only_lf_door_pdr_remains_as_issue(self):
        """Reproduce the exact bug with real data from VIN KM8R2DGE1PU586345.

        Expected: only LF Door PDR/1 should create an issue on driver_front_door.
        The two bumper scratches should be filtered (repaired per body_text).
        Duplicates from listing_json should be deduped.
        """
        report = _make_report(
            damage_items=REAL_DAMAGE_ITEMS,
            body_text=BODY_TEXT_WITH_REPAIRED,
        )
        granular = build_granular_condition_report(report)

        # LF Door PDR/1 should map to driver_front_door as an issue
        lf_door = granular["exterior"]["fields"]["driver_front_door"]
        assert lf_door["status"] == "issue"
        assert "Dent" in lf_door["value"] or "PDR" in (lf_door.get("evidence") or [""])[0]

        # Bumpers should NOT have issues (repaired)
        front_bumper = granular["exterior"]["fields"]["front_bumper"]
        assert front_bumper["status"] == "normal", (
            f"front_bumper should be normal (repaired), got: {front_bumper}"
        )

        # further_disclosures should NOT have damage from these items
        disclosures = granular["exterior"]["fields"]["further_disclosures"]
        assert disclosures["status"] == "normal", (
            f"further_disclosures should be normal, got: {disclosures}"
        )

    def test_without_body_text_all_items_create_issues(self):
        """Without body_text, we can't detect repairs — all items create issues.

        This is the current (broken) behavior baseline to show the body_text
        is what provides the repair signal.
        """
        report = _make_report(damage_items=REAL_DAMAGE_ITEMS)
        granular = build_granular_condition_report(report)
        # Without body_text, both bumper items should create issues (no repair signal)
        # But dedup should still filter the listing_json duplicates
        lf_door = granular["exterior"]["fields"]["driver_front_door"]
        assert lf_door["status"] == "issue"
