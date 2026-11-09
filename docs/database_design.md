# Database design

SQLite is the local persistence layer. `database/database.py::connect` enables foreign keys, executes the idempotent schema, and applies additive column migrations for supported older databases. Monetary amounts are stored as decimal strings and calculated in Python with `Decimal`.

## Tables and columns

| Table | Columns | Primary key | Foreign keys and constraints |
|---|---|---|---|
| `restaurants` | `restaurant_id`, `name`, `plan`, `onboarding_date`, `rating`, `packaging_charge`, `weekly_ad_budget`, `status` | `restaurant_id` | `plan` is STANDARD or PLUS; `status` is ACTIVE or SUSPENDED. |
| `orders` | `order_id`, `restaurant_id`, `order_time`, `items_gross`, `restaurant_discount`, `platform_discount`, `cofund_discount`, `packaging`, `distance`, `payment_mode`, `outcome`, `refund_reason`, `refund_amount`, `dispute_status`, `cancel_seconds`, `accepted`, `dispute_closed_at`, `processed_at`, `delivery_fee`, `platform_fee`, `rating`, `customer_refund`, `settlement_id` | `order_id` | `restaurant_id` references `restaurants`; `settlement_id` references `settlements`. |
| `order_items` | `order_id`, `line_no`, `name`, `quantity`, `unit_price` | `(order_id, line_no)` | `order_id` references `orders` with cascade delete. |
| `disputes` | `dispute_id`, `order_id`, `opened_at`, `closed_at`, `resolution`, `refund_amount`, `refund_reason` | `dispute_id` | `order_id` references `orders`. |
| `settlements` | `settlement_id`, `restaurant_id`, `week_start`, `gross`, `restaurant_discounts`, `platform_discounts`, `packaging`, `delivery_fees`, `platform_fees`, `commission`, `gst_95`, `commission_gst`, `tds`, `refunds`, `platform_refunds`, `ads`, `penalties`, `reimbursements`, `payout`, `carried_debit`, `order_ids`, `created_at` | `settlement_id` | `restaurant_id` references `restaurants`; unique `(restaurant_id, week_start)`. |
| `settlement_audit` | `audit_id`, `settlement_id`, `order_id`, `gross`, `commission`, `platform_fee`, `delivery_fee`, `tds`, `refund`, `breakup_json`, `recorded_at` | `audit_id` | References `settlements` and `orders`; unique `(settlement_id, order_id)`. |
| `settlement_corrections` | `correction_id`, `settlement_id`, `revision`, `reason`, `previous_statement`, `corrected_statement`, `created_at` | `correction_id` | `settlement_id` references `settlements`; unique `(settlement_id, revision)`. |
| `settlement_correction_audit` | `correction_audit_id`, `correction_id`, `order_id`, `breakup_json`, `recorded_at` | `correction_audit_id` | References correction and order; unique `(correction_id, order_id)`. |
| `processing_history` | `file_hash`, `file_name`, `processed_at` | `file_hash` | File digest prevents byte-identical replay. |
| `ad_debits` | `restaurant_id`, `amount` | `restaurant_id` | Stores current unpaid ad debit. |

## Relationships and indexes

One restaurant has many orders and statements. An order may have many item lines and dispute events, and may be assigned to at most one original settlement. A statement has per-order audit entries and append-only correction revisions; each revision has its own per-order correction audit entries. `ad_debits` retains one current carry balance per restaurant.

The schema's primary keys, unique constraints and SQLite foreign-key indexes support identity and joins. Explicit secondary indexes are not currently declared; the workload is the supplied local demonstration scale. Add query-specific indexes only if the expected dataset or measured query profile warrants them.

## Transactions and data lifecycle

Imports validate a complete file and commit the rows and processing-history hash together. Failed order/dispute batches roll back. Settlement creation inserts the statement, snapshots, order assignments and ad carry in one connection transaction. Corrections append a statement revision and correction audit rows; they do not overwrite the original statement or audit. The local SQLite database is ignored by Git and is not replaced by tests. Schema upgrades are additive; no migration drops or recreates business records.
