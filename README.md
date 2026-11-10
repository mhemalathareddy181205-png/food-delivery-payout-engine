# PS-039 Food Delivery Commission and Restaurant Payout Engine

## Overview and objectives

This project implements the restaurant-side settlement engine a food delivery platform uses to compute what each restaurant earns per order after commission, ad spend, discounts funded by each party, refunds, Section 194-O TDS, and GST under the Section 9(5) regime.

The engine is **command-file driven** (no UI), designed for restaurant partner managers to verify weekly settlement statements and resolve payout disputes down to the paisa. It supports both command-file streaming (`commands.txt`) and granular CLI subcommands. Financial arithmetic is strictly implemented using Python's `Decimal` with `ROUND_HALF_UP` paise rounding.

## Project structure

```text
main.py                    CLI and command-file execution entry point
config.py                  project paths and shared settings
src/calculations.py        pure Decimal financial calculations and stretch goals
src/engine.py              command-stream processor, validation, settlement, disputes, reports
database/database.py       SQLite connection and additive schema migrations
database/schema.sql        tables, keys, and foreign-key constraints
data/                      Sample Data Pack: restaurants.csv, ad_spend.csv, disputes.csv, commands.txt
tests/                     test suite (test_calculations.py, test_engine.py, test_sample_pack.py)
docs/                      business rules, design document, decision log, traceability, viva guide
generate_design_pdf.py     design Markdown to PDF generator (ReportLab)
```

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --help
```

If `py.exe` is unavailable, use python directly:

```powershell
python -m pip install -r requirements.txt
```

## Running the Command-File Engine (Evaluation Pipeline)

To run the complete evaluation stream on `commands.txt` and produce `order_breakup.csv` and `weekly_statement.csv`:

```powershell
python main.py data/commands.txt
```

Or using the explicit subcommand:

```powershell
python main.py run-commands --commands data/commands.txt --output-dir .
```

This processes the 665 command lines (200 orders, 25 refunds, 15 cancellations, 4 disputes, weekly payouts, and print directives) in strict file order, generating:
1. `order_breakup.csv`: per-order financial breakup for all 200 orders with all 23 columns specified in the evaluation rubric.
2. `weekly_statement.csv`: weekly settlement statements for all 30 restaurant weeks with all 12 columns specified in the evaluation rubric.

## Granular CLI Commands

```powershell
python main.py init-db
python main.py register-restaurants --file data/restaurants.csv
python main.py process-orders --file data/orders.csv
python main.py order-breakup --order-id ORD-0001
python main.py process-disputes --file data/disputes.csv
python main.py close-dispute --order-id ORD-0067 --closed-at 2026-10-13T08:00:00
python main.py weekly-payout --restaurant-id RST-01 --week-start 2026-10-05 --ad-spend 2000
python main.py correct-settlement --settlement-id 1 --reason "Dispute refund adjustment"
python main.py list-settlements --restaurant-id RST-01
python main.py report --type orders --output output/orders.json
python main.py report --type settlements --output output/settlements.csv
python main.py report --type audit --output output/audit.csv
```

## Running Tests

Run the full automated test suite (49 passing tests):

```powershell
python -m pytest tests -v
```

On Windows systems with temp folder permission restrictions:

```powershell
python -m pytest tests -v --basetemp=.tmp_pytest -p no:cacheprovider
```

## Business Rules and Edge Cases Implemented

| Rule ID | Domain Rule & Edge Case | Implementation & Status |
|---|---|---|
| **BR-01** | Commission rates (18% Standard, 22% Plus, 12% first 60 days, no commission on packaging) | **VERIFIED** — EC-01 verified: RST-03 day 59 (12%), day 60 (12%), day 61 (18%). Packaging never taxed. |
| **BR-02** | Discount funding (restaurant discount reduces base; platform coupon reimbursed; co-funding 50:50) | **VERIFIED** — EC-02 verified: co-funded Rs 120 splits Rs 60 restaurant (reduces base), Rs 60 platform. |
| **BR-03** | Packaging cap (capped at Rs 30, excess disallowed) | **VERIFIED** — EC-02 verified: Rs 45 charge capped at Rs 30, Rs 15 disallowed. Rs 30 charges allowed in full. |
| **BR-04** | GST regime (Section 9(5) 5% deducted on gross; 18% GST on commission charged separately) | **VERIFIED** — 5% deducted for government remittance; 18% charged on platform commission. |
| **BR-05** | TDS Section 194-O (1% on gross item value when yearly GMV exceeds Rs 5 lakh) | **VERIFIED** — EC-03 verified: RST-05 opening GMV Rs 495,750; crossing occurs Wed 2026-10-14 on ORD-0095; 1% TDS applies from crossing. |
| **BR-06** | Order cancellations (restaurant cancel after acceptance: Rs 100 penalty + refund; customer cancel <= 60s free, > 60s charged) | **VERIFIED** — EC-04 verified: 60s free (ORD-0049), 59s free (ORD-0050), >60s paid minus commission (ORD-0056). All 6 restaurant cancellations penalize Rs 100. |
| **BR-07** | Partial refunds (MISSING_ITEM: 100% restaurant; SPILLED: 50:50; LATE_DELIVERY: 100% platform; invalid rejected) | **VERIFIED** — Odd paisa on SPILLED assigned to platform. Trap 4 verified: COLD_FOOD refund rejected. |
| **BR-08** | Rating penalties (preceding week avg < 3.5 adds 2pp commission; < 3.0 suspends new orders) | **VERIFIED** — EC-05 verified: RST-10 avg 3.50 has 0 uplift. Trap 1: RST-09 avg 3.40 gets +2pp. Trap 2: RST-08 avg 2.60 suspended in week 3, rejecting ORD-0148. |
| **BR-09** | Weekly ad spend (deducted up to budget and positive earnings; never pushes payout below 0; debit carries) | **VERIFIED** — EC-06 verified: RST-01 week 2 spend 4800 floors payout at 0.00; debit carries forward. |
| **BR-10** | Weekly payout cycle (Tuesday payout for Mon–Sun; open disputes excluded, settled when closed) | **VERIFIED** — EC-07 verified: ORD-0067 opened Sun 23:59, closed Tue 08:00 -> excluded from week 1, settled week 2. |
| **BR-11** | Minimum order fee (net item value < Rs 100 attracts flat Rs 10 fee instead of percentage commission) | **VERIFIED** — EC-08 verified: ORD-0116 net Rs 100 uses commission; ORD-0117 net Rs 95 uses flat Rs 10 platform fee. |

## Stretch Goals (Extra Credit in Viva)

1. **Multi-Restaurant Orders**: Implemented in `src/calculations.py` (`multi_restaurant_split`). Supports single orders containing item lines from multiple restaurants, computing per-restaurant revenue, discounts, packaging, and net settlement.
2. **Dynamic Commission by Cuisine Demand**: Implemented in `src/calculations.py` (`dynamic_commission_by_cuisine`). Applies dynamic multipliers based on real-time cuisine demand elasticity (e.g., Biryani peak demand index).

## Regenerating the Design PDF

```powershell
python generate_design_pdf.py
```
Outputs `docs/design.pdf`.
