"""Pure Decimal calculations for order and payout ledgers."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

def money(value):
    try: value = Decimal(str(value if value not in (None, "") else 0))
    except Exception as exc: raise ValueError(f"Invalid monetary amount: {value}") from exc
    if not value.is_finite() or value < 0: raise ValueError(f"Amount must be finite and non-negative: {value}")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def commission_rate(plan, onboarding_date, order_date, penalty=False):
    days=(order_date-onboarding_date).days
    if days < 0: raise ValueError("Order date cannot precede onboarding date")
    rate=Decimal("0.12") if days <= 60 else Decimal("0.18") if plan.upper()=="STANDARD" else Decimal("0.22")
    return rate + (Decimal("0.02") if penalty else Decimal("0"))

def order_breakup(row, restaurant, rating_penalty=False):
    gross=money(row["items_gross"])
    own=money(row.get("restaurant_discount",0)); platform=money(row.get("platform_discount",0)); cofund=money(row.get("cofund_discount",0))
    co_platform=money(cofund/2); co_own=cofund-co_platform
    own+=co_own; platform+=co_platform
    if own+platform>gross: raise ValueError("Discounts cannot exceed item value")
    net=gross-own
    pack_requested=money(row.get("packaging", restaurant.get("packaging_charge",0)))
    packaging=min(pack_requested,Decimal("30.00")); excess=pack_requested-packaging
    d=date.fromisoformat(row.get("order_time",row.get("order_date"))[:10]); onboard=date.fromisoformat(restaurant["onboarding_date"][:10])
    status=row.get("outcome","DELIVERED").upper(); reason=row.get("refund_reason","").upper()
    rate=commission_rate(restaurant["plan"],onboard,d,rating_penalty)
    commission=ZERO if net < 100 else money(net*rate)
    refund=money(row.get("refund_amount",0)); rr=ZERO; pr=ZERO; customer_refund=ZERO; restaurant_penalty=ZERO
    if status=="CANCELLED_BY_CUSTOMER":
        customer_refund=gross-own-platform+packaging
        if int(row.get("cancel_seconds",0))<=60: commission=ZERO; rr=ZERO
        else: customer_refund=ZERO
    elif status=="CANCELLED_BY_RESTAURANT":
        commission=ZERO
        customer_refund=gross-own-platform+packaging
        if int(row.get("accepted",1)): restaurant_penalty=Decimal("100.00")
    elif status=="REFUND_PARTIAL":
        if reason=="MISSING_ITEM": rr=refund
        elif reason=="SPILLED": rr=money(refund/2)
        elif reason=="LATE_DELIVERY": pr=refund
        else: raise ValueError(f"Unsupported refund reason: {reason}")
    elif status!="DELIVERED": raise ValueError(f"Unsupported outcome: {status}")
    gst95=ZERO if status in ("CANCELLED_BY_RESTAURANT","CANCELLED_BY_CUSTOMER") and customer_refund else money(gross*Decimal("0.05")); commission_gst=money(commission*Decimal("0.18"))
    delivery=money(row.get("delivery_fee",0)); platform_fee=money(row.get("platform_fee",0))
    if net < 100 and status in ("DELIVERED","REFUND_PARTIAL"):
        commission=ZERO
        platform_fee=Decimal("10.00")
    elif status in ("CANCELLED_BY_RESTAURANT","CANCELLED_BY_CUSTOMER"):
        platform_fee=ZERO
    reimbursement=ZERO if status in ("CANCELLED_BY_RESTAURANT","CANCELLED_BY_CUSTOMER") else platform
    return {"gross":gross,"restaurant_discount":money(own),"platform_discount":money(platform),"commission_base":net,
      "commission_rate":rate,"commission":commission,"packaging":packaging,"packaging_excess":excess,
      "delivery_fee":delivery,"platform_fee":platform_fee,"gst_95":gst95,"commission_gst":commission_gst,
      "refund":refund,"restaurant_refund":rr,"platform_refund":pr,"customer_refund":customer_refund,
      "penalty":restaurant_penalty,"platform_reimbursement":reimbursement,"net_restaurant_amount":(net-platform+packaging-commission-commission_gst-gst95-platform_fee-rr-restaurant_penalty+reimbursement-customer_refund).quantize(CENT,rounding=ROUND_HALF_UP),}
