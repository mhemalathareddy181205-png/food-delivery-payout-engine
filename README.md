# PS-039 Food Delivery Commission and Restaurant Payout Engine

Python 3.10+, SQLite, CSV/JSON command files. The application registers restaurants, imports orders and dispute events, prints calculated breakups, settles Monday–Sunday weeks, retains correction history, and exports calculated reports. Monetary values use `Decimal` with `ROUND_HALF_UP` to paise.

## Setup (Windows PowerShell)

Run from `C:\food delivery`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --help
```

If `py.exe` is unavailable or blocked, use the existing virtual environment directly:

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' main.py --help
```

The requirements install pytest and ReportLab. The checked-in PDF can be regenerated after editing `docs/design.md`:

```powershell
python generate_design_pdf.py
```

## Initialize and run the sample

```powershell
python main.py init-db
python main.py register-restaurants --file data\restaurants.csv
python main.py process-orders --file data\orders.csv
python main.py order-breakup --order-id ORD001
python main.py weekly-payout --restaurant-id R001 --week-start 2026-10-26 --ad-spend 50
python main.py list-settlements --restaurant-id R001
```

Restaurant CSV columns: `restaurant_id,name,plan,onboarding_date,rating,packaging_charge,weekly_ad_budget`, plus optional `status`.

Aggregate order CSV remains supported with one row per order and `items_gross`. For named item lines, provide one CSV row per item using `item_name,item_quantity,item_unit_price`; repeat order-level fields on each line, and provide the same `order_id`. `items_gross` may be omitted and is then calculated from the item lines. If supplied, it must match their total. JSON remains supported, with `items:[{"name":"Meal","quantity":2,"unit_price":"10.00"}]`. Named line items persist in `order_items` and appear in `order-breakup`.

## Dispute event CSV

Run `process-disputes` with a CSV containing one event per row:

```text
dispute_id,order_id,event,event_at,resolution,refund_amount,refund_reason
DSP001,ORD001,OPEN,2026-10-25T23:59:00,,,
DSP001,ORD001,CLOSE,2026-10-27T08:00:00,REFUND_APPROVED,25.00,MISSING_ITEM
```

`event` is `OPEN` or `CLOSE`. Closing timestamps must not precede opening timestamps. A positive adjustment requires a supported reason: `MISSING_ITEM`, `SPILLED`, or `LATE_DELIVERY`. The supplied amount is added to an existing partial refund only when its funding reason matches; different refund funders on one order are rejected because the order ledger currently has one partial-refund reason. A free-text resolution with no explicit amount does not create a refund.

```powershell
python main.py process-disputes --file data\dispute_events.csv
```

Open disputed orders are excluded from new settlements. After close, their payout week is the week containing the close timestamp. If the order was already settled, the original statement remains unchanged; use the correction workflow below after the closing event to create a revised statement.

## Settlement corrections

Corrections never overwrite the original statement or original per-order audit rows. They append a numbered correction revision and per-order correction audit entries. To correct a settled order after a dispute adjustment:

```powershell
python main.py process-disputes --file data\dispute_events.csv
python main.py correct-settlement --settlement-id 1 --reason "Approved dispute refund"
python main.py list-settlements --restaurant-id R001
```

`weekly-payout` and settlement reports show the latest revision while audit exports retain original and correction rows. Corrections preserve the prior ad charge and adjust its carry only when the corrected statement is the restaurant's latest settlement. Later statements are not automatically cascaded or recalculated; correct those statements separately if required.

## Reports and tests

Reports are calculated from persisted orders/statements and written as CSV or JSON. The output directory is created as needed.

```powershell
python main.py report --type orders --output output\orders.json
python main.py report --type settlements --output output\settlements.csv
python main.py report --type audit --output output\audit.csv
python main.py report --type audit --output output\audit.json
python -m pytest tests -q
```

For repeatable verification using the working virtual environment and an isolated pytest temporary directory:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp="$env:TEMP\food-delivery-pytest" -p no:cacheprovider
```

Repeat an identical input file to confirm import idempotency. Repeat a payout for the same restaurant/week to receive its existing statement rather than a duplicate settlement.

## Assumptions and unresolved requirements

- The Rs 10 fee for net item value below Rs 100 is represented as a platform fee instead of percentage commission. Commission GST is not applied to that fee because the brief only specifies GST on commission; organizers should confirm the tax treatment.
- At or above Rs 100, `platform_fee` is treated as an already-calculated restaurant deduction. The brief does not supply a general platform-fee formula.
- `delivery_fee` must be supplied as an amount. It is shown per order, included in statement totals and audit, and excluded from restaurant payout. The brief does not specify its formula, collector, or recipient. Delivery-fee calculation and allocation therefore remain unresolved.
- No cancellation-specific GST or minimum-fee rules are given. The current documented behavior treats canceled orders as having no realized item value and no minimum platform fee; confirm with the organizers.
- TDS excludes the transaction that crosses the Rs 5 lakh threshold; canceled orders are excluded from GMV. These conventions require organizer confirmation for exact evaluation.
- Dispute events support explicit partial refunds by the three documented reasons. They do not infer a refund from resolution text, support multiple funding reasons on a single order, or model a dispute-specific full cancellation.
- A dispute adjustment after settlement requires the correction command. Later statements that depend on changed carry are not automatically revised.
- The supplied fixture has one restaurant and one order, not the organizer's 10-restaurant/200-order data or visible expected-output set. Exact hidden-set reconciliation cannot be claimed.
- BR-11 `SPILLED` refunds split to paise; if the amount contains an odd paisa, that paisa is assigned to the platform. The regression test covers odd and one-paisa amounts.
- The full suite uses isolated temporary databases. The latest run passed 46 tests; see [BR traceability](docs/br_traceability.md) for test links and partial statuses.

See [the final checklist](docs/final_requirement_checklist.md), [business rules](docs/business_rules.md), [decision log](docs/decision_log.md), and [design PDF](docs/design.pdf) for traceable assumptions and status.
