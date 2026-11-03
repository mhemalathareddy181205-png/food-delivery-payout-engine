# Database design

- `restaurants`: plan, onboarding date, rating, packaging cap input, ad budget, and status.
- `orders`: source financial inputs, outcome, refund and dispute state, optional delivery/platform fees and rating; `settlement_id` locks an order to one statement.
- `order_items`: durable quantity and unit price per order line.
- `disputes`: opened/closed timestamps and resolution linked to the order.
- `settlements`: one statement per restaurant/week, all monetary totals as decimal text, eligible order IDs, and ad carry. Delivery fees and platform discounts/fees have separate columns.
- `settlement_audit`: one immutable calculation snapshot per settlement/order, including delivery and platform fee lines, protected by a unique key.
- `settlement_corrections`: numbered before/after snapshots with a reason; it leaves the original settlement unchanged.
- `settlement_correction_audit`: per-order calculation snapshots for each correction revision.
- `processing_history`: input content hashes to suppress duplicate file processing.
- `ad_debits`: unpaid ad debit carried to a later settlement.

Foreign keys enforce relationships; unique order, statement, and audit constraints prevent accidental duplication. A week is identified by its Monday date. Money stays text so SQLite never coerces exact amounts to floating point. SQLite cannot enforce decimal math, so calculations stay in Python's Decimal layer. Existing databases are upgraded with additive fee and refund columns when opened. Corrections append new records and do not rewrite original audit entries.
