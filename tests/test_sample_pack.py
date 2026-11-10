"""
Automated test suite verifying the official PS-039 Sample Data Pack,
including all planted scenarios EC-01 to EC-08, traps, and stretch goals.
"""
import csv
from decimal import Decimal
from pathlib import Path
import pytest
from src.engine import process_command_stream
from src.calculations import dynamic_commission_by_cuisine, multi_restaurant_split, money

def test_sample_data_pack_execution(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"

    commands_file = data_dir / "commands.txt"
    restaurants_file = data_dir / "restaurants.csv"
    ad_spend_file = data_dir / "ad_spend.csv"
    disputes_file = data_dir / "disputes.csv"

    res = process_command_stream(
        commands_path=commands_file,
        restaurants_path=restaurants_file,
        ad_spend_path=ad_spend_file,
        disputes_path=disputes_file,
        output_dir=tmp_path,
    )

    assert res["order_breakups_count"] == 200
    assert res["weekly_statements_count"] == 30

    breakup_file = tmp_path / "order_breakup.csv"
    statement_file = tmp_path / "weekly_statement.csv"

    assert breakup_file.exists()
    assert statement_file.exists()

    # Read breakups by order_id
    with breakup_file.open(newline="", encoding="utf-8") as f:
        breakups = {row["order_id"]: row for row in csv.DictReader(f)}

    # Read statements by (restaurant_id, week_start)
    with statement_file.open(newline="", encoding="utf-8") as f:
        statements = {(row["restaurant_id"], row["week_start"]): row for row in csv.DictReader(f)}

    assert len(breakups) == 200
    assert len(statements) == 30

    # -------------------------------------------------------------
    # EC-01: Restaurant onboarded exactly 60 days before order date
    # RST-03 onboarded 2026-08-07
    # -------------------------------------------------------------
    # ORD-0004 on 2026-10-05 (59 days): 12%
    assert breakups["ORD-0004"]["commission_rate"] == "12.0"
    assert breakups["ORD-0004"]["commission"] == "117.60"

    # ORD-0015 on 2026-10-06 (60 days): 12%
    assert breakups["ORD-0015"]["commission_rate"] == "12.0"
    assert breakups["ORD-0015"]["commission"] == "120.00"

    # ORD-0024 on 2026-10-07 (61 days): STANDARD plan -> 18%
    assert breakups["ORD-0024"]["commission_rate"] == "18.0"
    # ORD-0024 net item value is 90.00 (< 100), so flat Rs 10 platform fee, commission 0.00
    assert breakups["ORD-0024"]["platform_fee"] == "10.00"
    assert breakups["ORD-0024"]["commission"] == "0.00"

    # -------------------------------------------------------------
    # EC-02: Co-funded discount on order with packaging above cap
    # RST-02 packaging 45.00 capped to 30.00, 15.00 disallowed
    # co-funded discount 120.00 -> 60.00 restaurant, 60.00 platform
    # -------------------------------------------------------------
    ord40 = breakups["ORD-0040"]
    assert ord40["packaging_allowed"] == "30.00"
    assert ord40["packaging_disallowed"] == "15.00"
    assert ord40["cofunded_restaurant_share"] == "60.00"
    assert ord40["cofunded_platform_share"] == "60.00"
    assert ord40["net_item_value"] == "1480.00"

    # -------------------------------------------------------------
    # EC-03: GMV crossing Rs 5 lakh in the middle of a payout week
    # RST-05 opening GMV 495,750.00
    # ORD-0071: 1700 -> cum 497,450 (no TDS)
    # ORD-0084: 1700 -> cum 499,150 (no TDS)
    # ORD-0095 (Wed 2026-10-14): 1700 -> cum 500,850 (crosses 5 lakh -> TDS 1% = 17.00)
    # -------------------------------------------------------------
    assert breakups["ORD-0071"]["tds_194o"] == "0.00"
    assert breakups["ORD-0084"]["tds_194o"] == "0.00"
    assert breakups["ORD-0095"]["tds_194o"] == "17.00"
    assert breakups["ORD-0112"]["tds_194o"] == "17.00"
    assert breakups["ORD-0118"]["tds_194o"] == "17.00"
    assert breakups["ORD-0124"]["tds_194o"] == "17.00"

    # -------------------------------------------------------------
    # EC-04: Customer cancellation at exactly 60 seconds
    # ORD-0049: cancelled at exactly 60s -> FREE
    # ORD-0050: cancelled at 59s -> FREE
    # ORD-0056: cancelled after 420s -> CHARGED
    # -------------------------------------------------------------
    assert breakups["ORD-0049"]["status"] == "CANCELLED_BY_CUSTOMER_FREE"
    assert breakups["ORD-0049"]["restaurant_net"] == "0.00"

    assert breakups["ORD-0050"]["status"] == "CANCELLED_BY_CUSTOMER_FREE"
    assert breakups["ORD-0050"]["restaurant_net"] == "0.00"

    assert breakups["ORD-0056"]["status"] == "CANCELLED_BY_CUSTOMER_CHARGED"
    assert Decimal(breakups["ORD-0056"]["restaurant_net"]) > Decimal("0.00")

    # -------------------------------------------------------------
    # EC-05: Weekly average rating exactly 3.5
    # RST-10 week 1 ratings average exactly 3.50 -> no penalty
    # -------------------------------------------------------------
    s_rst10_w1 = statements[("RST-10", "2026-10-05")]
    assert s_rst10_w1["avg_rating"] == "3.50"
    assert s_rst10_w1["next_week_commission_uplift_pp"] == "0.0"
    assert s_rst10_w1["suspended_next_week"] == "false"

    # -------------------------------------------------------------
    # EC-06: Ad spend larger than the week's payout
    # RST-01 week 2 spend 4800, payout floors at 0.00, debit carried forward
    # -------------------------------------------------------------
    s_rst01_w2 = statements[("RST-01", "2026-10-12")]
    assert s_rst01_w2["net_payout"] == "0.00"
    assert Decimal(s_rst01_w2["debit_carried_forward"]) > Decimal("5000.00")

    # -------------------------------------------------------------
    # EC-07: Dispute opened Sunday 23:59 and closed Tuesday 08:00
    # ORD-0067 excluded from week 1, settled in week 2
    # -------------------------------------------------------------
    s_rst07_w1 = statements[("RST-07", "2026-10-05")]
    assert s_rst07_w1["orders_excluded_dispute"] == "1"

    # -------------------------------------------------------------
    # EC-08: Net item value exactly Rs 100
    # ORD-0116: net item value 100.00 -> percentage commission
    # ORD-0117: net item value 95.00 (< 100) -> flat Rs 10 platform fee
    # -------------------------------------------------------------
    ord116 = breakups["ORD-0116"]
    assert ord116["net_item_value"] == "100.00"
    assert ord116["commission"] == "20.00"
    assert ord116["platform_fee"] == "0.00"

    ord117 = breakups["ORD-0117"]
    assert ord117["net_item_value"] == "95.00"
    assert ord117["commission"] == "0.00"
    assert ord117["platform_fee"] == "10.00"

    # -------------------------------------------------------------
    # Extra Traps
    # -------------------------------------------------------------
    # Trap 1: RST-09 week 1 ratings average 3.40 -> +2 percentage points in week 2
    s_rst09_w1 = statements[("RST-09", "2026-10-05")]
    assert s_rst09_w1["avg_rating"] == "3.40"
    assert s_rst09_w1["next_week_commission_uplift_pp"] == "2.0"

    # Trap 2: RST-08 week 2 rating 2.60 (< 3.0) -> suspended in week 3; ORD-0148 rejected
    s_rst08_w2 = statements[("RST-08", "2026-10-12")]
    assert s_rst08_w2["avg_rating"] == "2.60"
    assert s_rst08_w2["suspended_next_week"] == "true"
    assert breakups["ORD-0148"]["status"] == "REJECTED"
    assert breakups["ORD-0148"]["restaurant_net"] == "0.00"

    # Trap 3: Restaurant cancellation after acceptance -> Rs 100 penalty
    for can_oid in ("ORD-0076", "ORD-0120", "ORD-0155", "ORD-0182", "ORD-0188", "ORD-0200"):
        assert breakups[can_oid]["status"] == "CANCELLED_BY_RESTAURANT"
        assert breakups[can_oid]["penalty"] == "100.00"
        assert breakups[can_oid]["restaurant_net"] == "-100.00"

    # Trap 4: COLD_FOOD refund rejected (ORD-0167)
    assert breakups["ORD-0167"]["refund_restaurant_share"] == "0.00"
    assert breakups["ORD-0167"]["refund_platform_share"] == "0.00"

    # Trap 5: Packaging exactly Rs 30 allowed in full (RST-04)
    assert breakups["ORD-0008"]["packaging_allowed"] == "30.00"
    assert breakups["ORD-0008"]["packaging_disallowed"] == "0.00"

    # Trap 6: Duplicate delivery retry processed once (ORD-0060)
    assert breakups["ORD-0060"]["status"] == "DELIVERED"

def test_stretch_goals():
    # 1. Dynamic cuisine demand commission
    base_rate = Decimal("18.0")
    biryani_rate = dynamic_commission_by_cuisine("BIRYANI", base_rate, demand_multiplier=Decimal("1.10"))
    assert biryani_rate > base_rate

    # 2. Multi-restaurant order split
    items = [
        {"restaurant_id": "RST-01", "name": "Dosa", "quantity": 2, "unit_price": "80.00"},
        {"restaurant_id": "RST-02", "name": "Biryani", "quantity": 1, "unit_price": "280.00"},
    ]
    discounts = {"RST-01": Decimal("20.00"), "RST-02": Decimal("40.00")}
    packaging = {"RST-01": Decimal("15.00"), "RST-02": Decimal("25.00")}
    splits = multi_restaurant_split(items, discounts, packaging)

    assert "RST-01" in splits and "RST-02" in splits
    assert splits["RST-01"]["gross"] == Decimal("160.00")
    assert splits["RST-01"]["net_base"] == Decimal("140.00")
    assert splits["RST-02"]["gross"] == Decimal("280.00")
    assert splits["RST-02"]["net_base"] == Decimal("240.00")
