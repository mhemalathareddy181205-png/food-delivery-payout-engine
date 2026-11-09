# Final requirement checklist

Statuses use **VERIFIED**, **PARTIAL**, **PENDING CLARIFICATION**, or **NOT IMPLEMENTED**. VERIFIED means implementation and named tests support the documented scope; it does not imply that unspecified organizer policy has been confirmed.

| Requirement | Status | Evidence / remaining qualification |
|---|---|---|
| Register restaurants and their commission, onboarding, rating, packaging, ad budget | VERIFIED | CSV registration persists profile values; ratings below 3 suspend imports. |
| Accept aggregate order files | VERIFIED | Existing aggregate CSV and JSON formats remain supported. |
| Persist itemized lines in order input | VERIFIED | CSV supports repeated order rows with `item_name,item_quantity,item_unit_price`; JSON accepts `items`. Gross must match line totals or is calculated. |
| Persist discounts, distance, payment mode, outcomes, refunds | VERIFIED | Stored on each order; supported partial refund reasons are explicit. |
| Derive delivery fee from distance/payment mode | PENDING CLARIFICATION | The brief defines neither rate nor fee owner. An explicit fee amount is displayed and totalled, but excluded from payout. |
| Calculate and settle general platform fee | PARTIAL | The required sub-Rs 100 Rs 10 fee replaces commission and is deducted. Other platform fees are only accepted as precomputed input; formula and tax treatment are unspecified. |
| Standard/Plus and first-60-day commission | VERIFIED | 18%, 22%, and inclusive 12% introductory period. |
| Commission discount base and discount-funder split | VERIFIED | Restaurant discount reduces base; platform discount is offset by platform reimbursement; co-funding splits to paise. |
| Packaging cap and no packaging commission | VERIFIED | Rs 30 cap, excess disallowed. |
| 9(5) GST and GST on commission | PARTIAL | 5% of gross item value and 18% of commission. Canceled-order GST and refunds' GST adjustments are not specified; documented behavior is an assumption. |
| Financial-year TDS threshold | PARTIAL | Decimal GMV ledger resets April 1; canceled orders excluded. Crossing-order treatment is an assumption pending organizer confirmation. |
| Restaurant/customer cancellations and partial refund funders | PARTIAL | Funding and timing rules are implemented. Full refund base, canceled-order taxes/minimum fee, and interactions with discounts are assumptions; multiple dispute refund funders on one order are rejected. |
| Weekly rating uplift and suspension | VERIFIED | Prior-week average below 3.5 adds two points; below 3 suspends imports. A later higher rating does not automatically reactivate the restaurant. |
| Weekly ad budget, zero-floor ad charge, debit carry | VERIFIED | Ads cannot push positive pre-ad proceeds below zero; unpaid authorized ad amount carries. Non-ad deductions may yield a negative statement balance. |
| Monday–Sunday payout assignment and Tuesday cycle | PARTIAL | Weeks and Tuesday schedule are represented; CLI does not enforce that settlement is run only on Tuesday. |
| Open disputes and close-week assignment | VERIFIED | CSV OPEN/CLOSE events preserve timestamps; closed dispute moves to close-date week. |
| Explicit dispute refund adjustment | PARTIAL | Close event applies an explicit supported refund. Resolution text alone does nothing; only one funding reason per order is supported. |
| Settlement corrections with historical audit retention | PARTIAL | Corrections append statement revisions and per-order correction audit. Later statements/carry are not automatically cascaded. |
| Order breakups, weekly statements, reports, CSV/JSON | VERIFIED | Reports use calculated order details and latest corrected settlement revision; audit export includes original and correction rows. |
| Duplicate processing prevention | VERIFIED | File hashes are type-namespaced; statements and audit rows have uniqueness constraints. |
| Decimal/ROUND_HALF_UP monetary arithmetic | VERIFIED | Financial inputs and calculations use `Decimal`; statement outputs round to paise. |
| Eight named edge cases | VERIFIED | See `tests/test_calculations.py` and `tests/test_engine.py`; TDS FY reset, fee lines, and correction paths have additional tests. |
| BR-11 SPILLED refund split, including odd paisa to platform | VERIFIED | `test_restaurant_cancel_and_refund_funding` and `test_spilled_refund_odd_paisa_is_assigned_to_platform` cover even, odd, and one-paisa totals. |
| Input validation and atomicity edge cases | VERIFIED | Required fields, malformed files, invalid dates/ratings/flags, unknown references, duplicate order IDs, item total mismatch, and dispute batch rollback have isolated tests. |
| CLI sample flow on safe test data | VERIFIED | `test_cli_workflow_uses_only_test_database_and_safe_files` initializes, registers, imports, breaks up, settles, and reports using a temporary SQLite database. |
| Every BR-ID has an implementation and test reference | VERIFIED | See [`docs/br_traceability.md`](br_traceability.md); ambiguous policies remain marked partial. |
| Required design PDF | VERIFIED | Generate with `py generate_design_pdf.py`; current artifact is `docs/design.pdf`. |
| Organizer sample and expected outputs | PENDING CLARIFICATION | Only the small checked-in sample is available. Exact 200-order/10-restaurant and hidden-output reconciliation cannot be confirmed. |
| Repository naming, PDF submission package, demo video/email | NOT IMPLEMENTED | These require organizer submission details and external actions; no repository/email/video was created. |
| Optional multi-restaurant split/dynamic cuisine demand | NOT IMPLEMENTED | Stretch goals, not core requirements. |

## Test map for named edge cases

| Brief edge case | Test |
|---|---|
| Onboarded exactly 60 days before order | `test_onboarding_day_60_inclusive` |
| Co-funded discount with packaging above cap | `test_odd_paisa_cofund_and_packaging_cap_together` |
| GMV crosses Rs 5 lakh during payout week | `test_tds_crossing_order_and_following_order` |
| Customer cancellation at exactly 60 seconds | `test_customer_cancel_exactly_60_is_free_and_later_is_paid` |
| Weekly average exactly 3.5 | `test_rating_average_exactly_3_5_has_no_penalty` |
| Ad spend exceeds available payout | `test_rating_penalty_and_ad_debit_carry_forward` |
| Dispute opened Sunday 23:59, closes Tuesday 08:00 | `test_dispute_closing_moves_order_to_close_week_and_duplicate_settlement_is_safe` |
| Net item value exactly Rs 100 | `test_fee_boundary_and_packaging_cap` |
| SPILLED refund odd paisa assigned to platform | `test_spilled_refund_odd_paisa_is_assigned_to_platform` |
| Repeating an unchanged correction does not append a revision | `test_correction_repeat_is_idempotent_and_appends_only_when_changed` |
| CLI flow does not touch the local database | `test_cli_workflow_uses_only_test_database_and_safe_files` |

The latest suite run after the audit-approved changes passed **47 tests**. See the traceability table for BR-by-BR test coverage and partial requirements. The project is not considered fully compliant while delivery-fee allocation, general platform-fee rules, tax/cancellation details, the TDS threshold convention, or correction carry cascades remain unresolved.

## BR-01 through BR-25 status summary

| BR-ID | Status | Evidence and limitation |
|---|---|---|
| BR-01 | VERIFIED | `test_registration_persists_profile_and_suspends_low_profile_rating` asserts persisted profile fields and registration-time status. Weekly-average behavior is separately covered by BR-13. |
| BR-02 | VERIFIED | Standard and Plus post-introductory rates have direct expected-value coverage. |
| BR-03 | VERIFIED | Inclusive day-60 boundary has direct coverage. |
| BR-04 | VERIFIED | Discount funders, base, co-funding and paise split have expected-value coverage. |
| BR-05 | VERIFIED | Packaging cap and excess handling are directly covered. |
| BR-06 | PARTIAL | 5% of gross is implemented; canceled/refunded GST adjustments are unspecified. |
| BR-07 | VERIFIED | 18% commission GST and zero on flat minimum fee are covered for the documented base. |
| BR-08 | PARTIAL | FY ledger and reset are tested; crossing-order convention awaits confirmation. |
| BR-09 | PARTIAL | Accepted cancellation penalty is tested; refund base and tax treatment are assumptions. |
| BR-10 | PARTIAL | Sixty-second boundary is tested; refund, discount and tax details need confirmation. |
| BR-11 | VERIFIED | All three refund funders and odd-paisa-to-platform allocation are tested. |
| BR-12 | VERIFIED | Prior-week uplift and exact 3.5 boundary are tested. |
| BR-13 | VERIFIED | Weekly average below 3 suspends; a low single rating with weekly average 3 does not. |
| BR-14 | VERIFIED | Budget cap, positive payout limit and unpaid debit carry are tested. |
| BR-15 | PARTIAL | Monday-to-Sunday boundaries are represented; Tuesday execution is not enforced. |
| BR-16 | VERIFIED | Open-dispute exclusion and close-date week assignment are tested for supported events. |
| BR-17 | PARTIAL | Rs 100 boundary and fixed fee are tested; fee tax and cancellation interaction are unresolved. |
| BR-18 | VERIFIED | Decimal half-up behavior and financial boundary cases are tested. |
| BR-19 | VERIFIED | File replay, duplicate orders, settlement replay and audit behavior are tested. |
| BR-20 | VERIFIED | Covered input validation, supported values, and atomic failures have direct tests; organizer-specific constraints remain unknown. |
| BR-21 | VERIFIED | Platform-funded discount reimbursement is covered. |
| BR-22 | PARTIAL | Fee line is reported and excluded from payout under the documented assumption; formula and allocation need policy. |
| BR-23 | PARTIAL | Supplied fee is treated as precomputed; formula and tax treatment are unspecified. |
| BR-24 | PARTIAL | Timestamped explicit refunds work; multiple funding reasons on one order are rejected by the current schema. |
| BR-25 | PARTIAL | Corrections append revisions and audit; later statements/carry are not cascaded. |

## Organizer decisions still needed

Confirm the TDS crossing-order rule; GST/refund bases for canceled and refunded orders; cancellation refund and discount interactions; minimum/general platform-fee tax and cancellation treatment; delivery-fee formula, collector and recipient; whether settlement execution must be Tuesday-only; whether one order may have refunds with multiple funders; and whether historical corrections must recalculate later statements and advertising debit balances. These decisions affect expected values and should be approved before the related partial statuses can become verified.
