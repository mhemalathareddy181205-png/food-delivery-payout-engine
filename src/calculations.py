"""Pure Decimal calculations for order and payout ledgers."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

def money(value):
    try:
        value = Decimal(str(value if value not in (None, "") else 0))
    except Exception as exc:
        raise ValueError(f"Invalid monetary amount: {value}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"Amount must be finite and non-negative: {value}")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def commission_rate(plan, onboarding_date, order_date, penalty=False):
    days = (order_date - onboarding_date).days
    if days < 0:
        raise ValueError("Order date cannot precede onboarding date")
    rate = Decimal("0.12") if days <= 60 else Decimal("0.18") if plan.upper() == "STANDARD" else Decimal("0.22")
    return rate + (Decimal("0.02") if penalty else Decimal("0"))

def order_breakup(row, restaurant, rating_penalty=False):
    gross = money(row["items_gross"])
    own = money(row.get("restaurant_discount", 0))
    platform = money(row.get("platform_discount", 0))
    cofund = money(row.get("cofund_discount", 0))
    co_platform = money(cofund / 2)
    co_own = cofund - co_platform
    own += co_own
    platform += co_platform
    if own + platform > gross:
        raise ValueError("Discounts cannot exceed item value")
    net = gross - own
    pack_requested = money(row.get("packaging", restaurant.get("packaging_charge", 0)))
    packaging = min(pack_requested, Decimal("30.00"))
    excess = pack_requested - packaging
    d = date.fromisoformat(row.get("order_time", row.get("order_date"))[:10])
    onboard = date.fromisoformat(restaurant["onboarding_date"][:10])
    status = row.get("outcome", "DELIVERED").upper()
    reason = row.get("refund_reason", "").upper()
    plan_name = restaurant.get("commission_plan") or restaurant.get("plan", "STANDARD")
    rate = commission_rate(plan_name, onboard, d, rating_penalty)
    commission = ZERO if net < 100 else money(net * rate)
    refund = money(row.get("refund_amount", 0))
    rr = ZERO
    pr = ZERO
    customer_refund = ZERO
    restaurant_penalty = ZERO
    if status == "CANCELLED_BY_CUSTOMER":
        customer_refund = gross - own - platform + packaging
        if int(row.get("cancel_seconds", 0)) <= 60:
            commission = ZERO
            rr = ZERO
        else:
            customer_refund = ZERO
    elif status == "CANCELLED_BY_RESTAURANT":
        commission = ZERO
        customer_refund = gross - own - platform + packaging
        if int(row.get("accepted", 1)):
            restaurant_penalty = Decimal("100.00")
    elif status == "REFUND_PARTIAL":
        if reason == "MISSING_ITEM":
            rr = refund
        elif reason == "SPILLED":
            # BR-11 assigns an odd paisa to the platform half.
            pr = money(refund / 2)
            rr = refund - pr
        elif reason == "LATE_DELIVERY":
            pr = refund
        else:
            raise ValueError(f"Unsupported refund reason: {reason}")
    elif status != "DELIVERED":
        raise ValueError(f"Unsupported outcome: {status}")
    gst95 = ZERO if status in ("CANCELLED_BY_RESTAURANT", "CANCELLED_BY_CUSTOMER") and customer_refund else money(gross * Decimal("0.05"))
    commission_gst = money(commission * Decimal("0.18"))
    delivery = money(row.get("delivery_fee", 0))
    platform_fee = money(row.get("platform_fee", 0))
    if net < 100 and status in ("DELIVERED", "REFUND_PARTIAL"):
        commission = ZERO
        platform_fee = Decimal("10.00")
    elif status in ("CANCELLED_BY_RESTAURANT", "CANCELLED_BY_CUSTOMER"):
        platform_fee = ZERO
    reimbursement = ZERO if status in ("CANCELLED_BY_RESTAURANT", "CANCELLED_BY_CUSTOMER") else platform
    return {
        "gross": gross,
        "restaurant_discount": money(own),
        "platform_discount": money(platform),
        "commission_base": net,
        "commission_rate": rate,
        "commission": commission,
        "packaging": packaging,
        "packaging_excess": excess,
        "delivery_fee": delivery,
        "platform_fee": platform_fee,
        "gst_95": gst95,
        "commission_gst": commission_gst,
        "refund": refund,
        "restaurant_refund": rr,
        "platform_refund": pr,
        "customer_refund": customer_refund,
        "penalty": restaurant_penalty,
        "platform_reimbursement": reimbursement,
        "net_restaurant_amount": (net - platform + packaging - commission - commission_gst - gst95 - platform_fee - rr - restaurant_penalty + reimbursement - customer_refund).quantize(CENT, rounding=ROUND_HALF_UP),
    }

def order_breakup_full(ord_obj, rest):
    """
    Computes exact 23-column breakup for evaluation according to PS-039 Sample Data Pack.
    """
    gross = money(ord_obj["gross_item_value"])
    status = ord_obj["status"]
    rules = []

    rest_disc = money(ord_obj.get("restaurant_discount", 0))
    plat_coupon = money(ord_obj.get("platform_coupon", 0))
    cofund = money(ord_obj.get("cofunded_discount", 0))

    cofund_plat = money(cofund / 2)
    cofund_rest = cofund - cofund_plat

    net_item_val = gross - rest_disc - cofund_rest
    if rest_disc > 0 or plat_coupon > 0 or cofund > 0:
        rules.append("BR-02")

    pack_charge = money(ord_obj.get("packaging_charge", 0))
    pack_allowed = min(pack_charge, Decimal("30.00"))
    pack_disallowed = max(ZERO, pack_charge - Decimal("30.00"))
    if pack_charge > 0:
        rules.append("BR-03")

    order_d = ord_obj["ts"].date() if hasattr(ord_obj["ts"], "date") else date.fromisoformat(str(ord_obj["ts"])[:10])
    onboard_d = rest["onboarding_date"] if hasattr(rest["onboarding_date"], "days") else date.fromisoformat(str(rest["onboarding_date"])[:10])
    days_onboard = (order_d - onboard_d).days

    if days_onboard <= 60:
        base_rate = Decimal("12.0")
    else:
        plan_name = rest.get("commission_plan") or rest.get("plan", "STANDARD")
        base_rate = Decimal("18.0") if plan_name.upper() == "STANDARD" else Decimal("22.0")

    uplift = Decimal(str(ord_obj.get("commission_uplift_pp", "0.0")))
    comm_rate = base_rate + uplift
    if uplift > 0:
        rules.append("BR-08")

    comm = ZERO
    plat_fee = ZERO
    gst_comm = ZERO
    gst95 = ZERO
    tds = ZERO
    reimburse = ZERO
    ref_rest = money(ord_obj.get("refund_restaurant_share", 0))
    ref_plat = money(ord_obj.get("refund_platform_share", 0))
    penalty = money(ord_obj.get("penalty", 0))

    if status == "REJECTED":
        rules.append("BR-08")
        net_item_val = ZERO
        pack_allowed = ZERO
        pack_disallowed = ZERO
        comm_rate = Decimal("0.0")
        comm = ZERO
        rest_net = ZERO
    elif status == "CANCELLED_BY_CUSTOMER_FREE":
        rules.append("BR-06")
        comm = ZERO
        rest_net = ZERO
    elif status == "CANCELLED_BY_RESTAURANT":
        rules.append("BR-06")
        comm = ZERO
        rest_net = -penalty
    elif status in ("DELIVERED", "CANCELLED_BY_CUSTOMER_CHARGED"):
        if status == "CANCELLED_BY_CUSTOMER_CHARGED":
            rules.append("BR-06")

        if net_item_val < Decimal("100.00"):
            rules.append("BR-11")
            plat_fee = Decimal("10.00")
            comm = ZERO
            gst_comm = ZERO
        else:
            rules.append("BR-01")
            comm = money(net_item_val * (comm_rate / Decimal("100.00")))
            gst_comm = money(comm * Decimal("0.18"))

        gst95 = money(gross * Decimal("0.05"))
        rules.append("BR-04")

        # TDS Section 194-O on cumulative GMV crossing Rs 5 lakh
        new_gmv = ord_obj.get("new_gmv", ZERO)
        if new_gmv > Decimal("500000.00"):
            tds = money(gross * Decimal("0.01"))
            rules.append("BR-05")

        reimburse = plat_coupon + cofund_plat
        if ref_rest > 0 or ref_plat > 0:
            rules.append("BR-07")

        rest_net = (net_item_val + pack_allowed + reimburse
                    - comm - plat_fee - gst_comm - gst95 - tds
                    - ref_rest - penalty).quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "order_id": ord_obj["order_id"],
        "restaurant_id": ord_obj["restaurant_id"],
        "status": status,
        "gross_item_value": f"{gross:.2f}",
        "restaurant_discount": f"{rest_disc:.2f}",
        "platform_coupon": f"{plat_coupon:.2f}",
        "cofunded_restaurant_share": f"{cofund_rest:.2f}",
        "cofunded_platform_share": f"{cofund_plat:.2f}",
        "net_item_value": f"{net_item_val:.2f}",
        "packaging_allowed": f"{pack_allowed:.2f}",
        "packaging_disallowed": f"{pack_disallowed:.2f}",
        "commission_rate": f"{comm_rate:.1f}",
        "commission": f"{comm:.2f}",
        "platform_fee": f"{plat_fee:.2f}",
        "gst_on_commission": f"{gst_comm:.2f}",
        "gst_9_5": f"{gst95:.2f}",
        "tds_194o": f"{tds:.2f}",
        "coupon_reimbursement": f"{reimburse:.2f}",
        "refund_restaurant_share": f"{ref_rest:.2f}",
        "refund_platform_share": f"{ref_plat:.2f}",
        "penalty": f"{penalty:.2f}",
        "restaurant_net": f"{rest_net:.2f}",
        "rule_ids": ",".join(sorted(set(rules))),
        "_net_val": rest_net,
    }

# Stretch goal helpers
def dynamic_commission_by_cuisine(cuisine, base_rate, demand_multiplier=Decimal("1.0")):
    """
    Stretch goal: Dynamic commission adjustment based on cuisine demand index.
    e.g. Biryani in peak demand: demand_multiplier = 1.1 -> adds 10% to base rate.
    """
    cuisine_weights = {
        "BIRYANI": Decimal("1.05"),
        "NORTH INDIAN": Decimal("1.02"),
        "CHINESE": Decimal("1.00"),
        "SOUTH INDIAN": Decimal("0.98"),
        "BAKERY": Decimal("0.95"),
    }
    weight = cuisine_weights.get(cuisine.upper(), Decimal("1.00"))
    adjusted_rate = (base_rate * weight * demand_multiplier).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return adjusted_rate

def multi_restaurant_split(item_lines, discounts_by_rest, packaging_by_rest):
    """
    Stretch goal: Split a multi-restaurant order across participating restaurants.
    Returns per-restaurant item totals, discounts, packaging and revenue breakdown.
    """
    splits = {}
    for item in item_lines:
        rid = item["restaurant_id"]
        splits.setdefault(rid, {"gross": Decimal("0.00"), "items": []})
        item_total = money(Decimal(str(item["quantity"])) * money(item["unit_price"]))
        splits[rid]["gross"] += item_total
        splits[rid]["items"].append(item)
    for rid, data in splits.items():
        data["packaging"] = packaging_by_rest.get(rid, Decimal("0.00"))
        data["discount"] = discounts_by_rest.get(rid, Decimal("0.00"))
        data["net_base"] = data["gross"] - data["discount"]
    return splits
