# Business rules

- BR-01 Registration stores plan, onboarding date, profile rating, packaging, weekly ad budget and status. A profile rating under 3 at registration initializes the restaurant as suspended. This registration-time profile value is distinct from individual order ratings; weekly-average suspension is governed by BR-13.
- BR-02 Standard commission is 18%; Plus is 22%.
- BR-03 Onboarding days 0 through 60 inclusive use 12% (an order exactly 60 days after onboarding qualifies).
- BR-04 Restaurant discounts reduce the commission base. Platform coupons are reimbursed and do not reduce it. A co-funded discount is split 50:50; an odd paisa is assigned to the platform half.
- BR-05 Packaging is separately payable, capped at Rs 30. The configured/order charge above the cap is recorded as disallowed and not charged.
- BR-06 Platform GST under Section 9(5) is 5% of gross item value and is deducted from restaurant proceeds for remittance.
- BR-07 Commission GST is 18% of commission and is a separate restaurant deduction.
- BR-08 TDS is 1% of order GMV once cumulative financial-year GMV has already exceeded Rs 5,00,000. The crossing order itself is excluded; future orders are included. FY starts April 1.
- BR-09 An accepted restaurant cancellation incurs Rs 100 and the customer refund. A not-yet-accepted cancellation incurs no penalty. Customer refund of cancellation is tracked separately.
- BR-10 Customer cancellation through and including second 60 is free; later cancellation pays the restaurant in full minus commission.
- BR-11 Partial refund reason MISSING_ITEM is restaurant-funded; SPILLED is split equally in paise with any odd paisa assigned to the platform; LATE_DELIVERY is platform-funded.
- BR-12 Average order rating in the preceding Monday–Sunday week below 3.5 adds 2 percentage points to commission in the settlement week. Exactly 3.5 adds no penalty. (Rating data is accepted on each order.)
- BR-13 The applicable recorded weekly average order rating below 3 suspends future order imports; a single low order rating does not trigger suspension when the weekly average is 3 or higher. Existing orders remain eligible for settlement; a later higher rating does not automatically reactivate a suspended restaurant.
- BR-14 Weekly ads cannot exceed weekly budget or available positive payout. Any unpaid requested spend carries as a debit; unspent budget expires. Carry is attempted against the next payout.
- BR-15 Payout week is Monday–Sunday, payable Tuesday. Supply the Monday as week start.
- BR-16 Open disputes are excluded. After closure the order belongs to the Monday–Sunday week containing the dispute close date, including a Sunday 23:59 open/Tues 08:00 close example.
- BR-17 Net item value below Rs 100 has a flat Rs 10 platform fee instead of percentage commission; commission GST is zero on that fee. Exactly Rs 100 uses percentage commission. Platform fee is deducted from payout.
- BR-18 Every money input/result uses Decimal, rounded half-up to Rs 0.01.
- BR-19 Order IDs are unique. Byte-identical import files are skipped. Settled order IDs are locked, statements are unique per restaurant/week, and an audit row is unique per settled order.
- BR-20 Inputs require valid dates, finite nonnegative monetary values, valid references, supported outcomes and refund reasons.
- BR-21 Platform-funded discounts are deducted from gross proceeds and added back as reimbursements, so they do not reduce restaurant earnings or commission base.
- BR-22 Supplied delivery fees appear in breakups, weekly statement totals, and audit rows, but are informational and excluded from restaurant payout because the brief does not identify a collector, recipient, or calculation rule.
- BR-23 For orders at or above Rs 100, a supplied platform fee is assumed to be an already-calculated restaurant deduction. The brief supplies no formula for other platform fees.
- BR-24 CSV dispute events are explicit OPEN/CLOSE events with timestamps. Only a CLOSE event with a supported refund reason and amount changes the order refund ledger.
- BR-25 Post-settlement corrections append a numbered statement revision and correction audit rows; original statements and audit snapshots are retained.

## Statement calculation

Start with item gross; subtract restaurant and platform discounts; add platform-funded reimbursements and packaging; subtract platform fees, commission, both GST deductions, TDS, restaurant-funded refunds, customer cancellation refunds, and penalties. Delivery fee is reported separately and excluded from restaurant payout. Ads are then deducted up to positive payout and the restaurant's weekly budget; unpaid requested ad spend carries forward. A negative pre-ad balance remains visible where other deductions exceed proceeds.

## Verification status

`docs/br_traceability.md` maps each BR-ID to implementation and automated tests. The BR-11 SPILLED split is verified for even, odd, and one-paisa refunds. Some BRs remain partial because the brief does not settle fee allocation, certain tax/cancellation cases, threshold crossing treatment, or downstream correction carry recalculation. Those are listed in the final checklist; they must not be treated as confirmed policy.

## Policy status

**Confirmed by the supplied rule register:** plan rates, introductory period, discount funders, packaging cap, stated tax rates, refund reason funders, rating thresholds, weekly ad cap behavior, Monday-to-Sunday week, dispute exclusion, fee boundary, Decimal rounding, uniqueness and audit requirements.

**Implemented interpretations requiring confirmation where the brief is silent:** initial profile rating under 3 sets registration status to suspended; the crossing TDS order is excluded; canceled orders have zero 9(5) GST and no minimum fee; cancellation refund is modeled from discounted customer item amount plus packaging; the platform fee outside the minimum is treated as a supplied deduction; delivery fee is informational; and correction revisions do not cascade to later statements. These conventions are recorded in `decision_log.md` and are not represented as confirmed organizer policy.

**Pending organizer clarification:** TDS treatment on the threshold-crossing transaction; canceled/refunded-order tax bases; cancellation refund and discount interactions; minimum/general platform-fee taxes and cancellation treatment; delivery-fee formula, collector and payout allocation; whether settlement must execute only on Tuesday; whether one order can combine refund funding reasons; and downstream statement/ad-debit recalculation after historical correction. See `final_requirement_checklist.md` for the impact and evidence.
