"""End-to-end DuckDB checks for signed contributions, margins and coverage."""
from pathlib import Path

import pandas as pd
import pytest

from insightflow.period_analysis import compare_sales, drilldown


def ledger(*rows):
    return pd.DataFrame(rows, columns=["date", "product", "revenue", "profit"])


def test_demo_comparison_and_same_period_drilldown():
    frame = pd.read_csv(Path(__file__).resolve().parents[1] / "sample_data/sales.csv")
    r = compare_sales(frame, 2026, "H1", "category")
    assert r["previous"]["revenue"] == 6186
    assert r["current"]["revenue"] == 5886
    assert r["changes"]["profit_delta"] == -148
    assert r["changes"]["revenue_growth"] == pytest.approx(-300 / 6186)
    assert r["contributions"].delta_revenue.sum() == r["changes"]["revenue_delta"]
    assert r["contributions"].delta_profit.sum() == r["changes"]["profit_delta"]
    assert r["current"]["months"] == [f"2026-{i:02d}" for i in range(1, 7)]
    assert not r["warnings"]
    detail = drilldown(frame, 2026, "H1", "Backpack")
    assert detail["previous"]["margin"] == detail["current"]["margin"] == .45
    assert detail["current"]["revenue_share"] == pytest.approx(2160 / 5886)
    assert detail["current"]["profit_share"] == pytest.approx(972 / 2910)
    assert detail["previous"]["company_margin"] == pytest.approx(3058 / 6186)
    assert detail["changes"]["margin_pp"] == 0
    assert detail["sql_params"] == ["Backpack"]


def test_empty_period_is_unknown_but_entrant_and_exit_are_zero_in_observed_period():
    frame = ledger(("2025-01-01", "old", 120, 12), ("2026-03-31", "new", 80, 16),
                   ("2026-04-01", "wrong quarter", 999, 333))
    r = compare_sales(frame, 2026, "Q1")
    table = r["contributions"].set_index("name")
    assert set(table.index) == {"new", "old"}
    assert table.loc["new", "prev_revenue"] == table.loc["old", "curr_revenue"] == 0
    assert table.delta_revenue.sum() == -40
    assert r["changes"]["margin_pp"] == pytest.approx(10)
    assert "2025-02" in " ".join(r["warnings"])
    detail = drilldown(frame, 2026, "Q1", "new")
    assert detail["previous"]["rows"] == 0 and detail["previous"]["margin"] is None
    assert detail["previous"]["revenue_share"] == 0
    missing = compare_sales(frame, 2025, "Q1")
    assert missing["previous"]["rows"] == 0
    assert missing["previous"]["revenue"] is None
    assert all(v is None for v in missing["changes"].values())
    assert missing["contributions"].delta_profit.isna().all()
    empty = compare_sales(frame, 2023, "H2")
    assert empty["contributions"].empty and empty["current"]["months"] == []
    assert empty["current"]["profit"] is None


def test_weighted_margin_negative_baseline_and_tie_order():
    frame = ledger(("2025-02-01", "Beta", 100, -8), ("2025-02-02", "Alpha", 10, 1),
                   ("2026-02-04", "Alpha", 15, 7), ("2026-02-02", "Beta", 105, 20))
    r = compare_sales(frame, 2026, "H1")
    assert list(r["contributions"].name) == ["Alpha", "Beta"]
    assert r["current"]["margin"] == pytest.approx(27 / 120)
    assert r["changes"]["profit_delta"] == 34 and r["changes"]["profit_growth"] is None
    assert drilldown(frame, 2026, "H1", "Beta")["previous"]["profit_share"] is None
    frame["revenue"] = 0
    r = compare_sales(frame, 2026, "H1")
    assert r["current"]["margin"] is None
    assert r["changes"]["revenue_growth"] is None and r["changes"]["margin_pp"] is None


def test_signed_cents_no_cutoff_and_parameterized_product_names():
    frame = ledger(*( ("2025-01-01", f"sku-{i}", "0.10", "-0.01") for i in range(1001) ),
                   ("2026-01-01", "Kid's mat", "0.31", "0.02"))
    result = compare_sales(frame, 2026, "FY")
    assert len(result["contributions"]) == 1002
    assert result["changes"]["revenue_delta"] == pytest.approx(-99.79)
    assert result["contributions"].delta_revenue.sum() == pytest.approx(-99.79)
    detail = drilldown(frame, 2026, "FY", "Kid's mat")
    assert detail["current"]["profit"] == pytest.approx(.02)
    assert detail["sql_params"] == ["Kid's mat"]


@pytest.mark.parametrize("col,bad", [
    ("profit", None), ("profit", "NaN"), ("revenue", "oops"), ("revenue", "1.1234567"),
    ("revenue", float("inf")), ("product", "   "), ("date", "2025-02-30"), ("date", 45200)
])
def test_invalid_values_identified_even_outside_window(col, bad):
    f = ledger(("2022-01-01", "ok", "5.20", "1.20"))
    f[col] = bad
    with pytest.raises(ValueError, match=col):
        compare_sales(f, 2026, "Q2")


def test_schema_and_period_errors_are_explicit():
    f = ledger(("2025-06-30", "A", 10, 2))
    with pytest.raises(ValueError, match='category'):
        compare_sales(f, 2026, "H1", "category")
    with pytest.raises(ValueError, match='H1'):
        compare_sales(f, 2026, "YTD")
    with pytest.raises(ValueError, match='年份'):
        compare_sales(f, True, "FY")
    with pytest.raises(ValueError, match='无记录'):
        drilldown(f, 2026, "H1", "Missing")
