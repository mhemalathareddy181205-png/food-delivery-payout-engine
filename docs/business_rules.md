# Business Rules Register (PS-039)

- **BR-01 Commission Plans & Introductory Rate**:
  Standard commission is 18% of net item value; Plan PLUS is 22% (includes free listing boost). The first 60 days from onboarding (days 0 through 60 inclusive) qualify for an introductory 12% commission rate. Commission is strictly never charged on packaging.
- **BR-02 Discount Funding & Commission Base**:
  Restaurant-funded discounts reduce the commission base (`net_item_value = gross_item_value - restaurant_discount`). Platform coupons do not reduce the commission base; the platform reimburses the restaurant for the coupon amount (`coupon_reimbursement = platform_coupon`). Co-funded offers (50:50) split the discount: the restaurant's 50% reduces the commission base, while the platform's 50% is reimbursed. If an odd paisa exists, it is assigned to the platform half.
- **BR-03 Packaging Charge & Cap**:
  A restaurant may charge up to Rs 30 per order for packaging. Any packaging charge above Rs 30 is capped and the excess is disallowed (`packaging_allowed = min(packaging_charge, 30.00)`, `packaging_disallowed = max(0.00, packaging_charge - 30.00)`). Commission is never charged on packaging.
- **BR-04 Section 9(5) GST & Commission GST**:
  Under Section 9(5) of the CGST Act, the platform is liable to pay 5% GST on the restaurant item value directly to the government; this 5% is deducted from the restaurant's payout as a statutory deduction (`gst_9_5 = round(gross_item_value * 0.05)`). Separately, 18% GST is charged to the restaurant on the platform commission (`gst_on_commission = round(commission * 0.18)`).
- **BR-05 Section 194-O TDS Threshold**:
  Under Section 194-O of the Income Tax Act, the platform deducts 1% TDS on the gross item value for restaurants whose cumulative financial-year GMV on the platform exceeds Rs 5 lakh (`tds_194o = round(gross_item_value * 0.01)`). FY GMV resets on April 1 and equals `opening_fy_gmv` plus delivered order gross GMV. When an order pushes cumulative GMV past Rs 5 lakh, 1% TDS applies from that crossing transaction onward.
- **BR-06 Cancellation Rules**:
  - `CANCELLED_BY_RESTAURANT`: If cancelled after acceptance, costs the restaurant a flat Rs 100 penalty (`penalty = 100.00`) and the full customer refund is borne by the restaurant (`refund_restaurant_share = customer_refund`). If cancelled before acceptance, penalty is zero.
  - `CANCELLED_BY_CUSTOMER`: If cancelled within 60 seconds of order placement (`cancel_seconds <= 60`), cancellation is free to the customer (`CANCELLED_BY_CUSTOMER_FREE`); customer gets 100% refund, no commission is charged, and restaurant net is 0.00. If cancelled after 60 seconds (`CANCELLED_BY_CUSTOMER_CHARGED`), customer pays 100% and restaurant is paid in full minus commission, packaging allowed, coupon reimbursement, and statutory taxes.
- **BR-07 Partial Refund Funding Reasons**:
  Partial refunds are allocated strictly according to fault/category:
  - `MISSING_ITEM`: 100% borne by restaurant (`refund_restaurant_share += refund_amount`).
  - `SPILLED`: Split 50% restaurant and 50% platform. Any odd paisa is assigned to the platform share.
  - `LATE_DELIVERY`: 100% borne by platform (`refund_platform_share += refund_amount`).
  - Unsupported refund reasons (e.g. `COLD_FOOD`) are rejected and excluded from the refund ledger.
- **BR-08 Rating Penalties & Order Suspension**:
  Average order rating in the preceding Monday–Sunday week dictates penalties for the following week:
  - Average rating strictly below 3.50 adds 2.0 percentage points to commission for the following week (`next_week_commission_uplift_pp = 2.0`). An average of exactly 3.50 incurs no penalty (`0.0`).
  - Average rating strictly below 3.00 suspends the restaurant from accepting new orders (`suspended_next_week = true`). Any new order placed while suspended is immediately `REJECTED`. Unrated orders are excluded from the weekly average.
- **BR-09 Advertising Spend & Debit Carry-Forward**:
  Actual ad spend is deducted from weekly payout up to the restaurant's weekly budget and available positive proceeds (`gross_payable`). Unspent budget does not carry over. Ad spend deductions never push the payout below zero; any remaining unpaid ad spend rolls forward as a debit (`debit_carried_forward`).
- **BR-10 Weekly Payout Cycle & Dispute Settlement**:
  Settlement runs weekly on Tuesday for orders delivered Monday through Sunday. Orders with an open dispute are excluded from the delivery week's statement (`orders_excluded_dispute = 1`) and are settled in the weekly statement corresponding to when the dispute closes.
- **BR-11 Minimum Order Platform Fee**:
  Orders with net item value below Rs 100 attract a flat Rs 10 platform fee charged to the restaurant instead of percentage commission (`platform_fee = 10.00`, `commission = 0.00`, `gst_on_commission = 0.00`). Orders with net item value of exactly Rs 100 or above use normal percentage commission (`platform_fee = 0.00`).
