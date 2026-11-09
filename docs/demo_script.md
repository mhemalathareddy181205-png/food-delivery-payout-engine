# Five-minute project demonstration

## Safe setup

Run from the project root in PowerShell. For the recording, use an isolated copy of the sample inputs with unique IDs and a temporary database path configured for the demo; do not initialize or mutate the checked-in `database/settlements.sqlite3`. The automated CLI integration test uses a temporary database and directory and is the verified safe workflow.

```powershell
Set-Location 'C:\food delivery'
& '.\.venv\Scripts\python.exe' main.py --help
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp="$env:TEMP\food-delivery-demo-pytest" -p no:cacheprovider
```

The CLI database location comes from `config.py`. To perform a live workflow without touching local sample data, make a temporary project copy that excludes `.git`, `.venv`, output files, and the local SQLite database, then use the copy's `data` files. Keep all demo outputs in that copy's `output` directory.

## Timeline and narration

| Time | Show on screen | Explain |
|---|---|---|
| 0:00–0:25 | Project root and README overview | The business problem is producing consistent restaurant payouts with explainable deductions and a durable audit trail. |
| 0:25–0:55 | `main.py --help`; architecture diagram in `docs/design.md` | The CLI routes to the engine, Decimal calculations are isolated, and SQLite stores the ledger. |
| 0:55–1:25 | `init-db`, restaurant input format and registration command | Profiles include plan, onboarding date, rating, packaging and ad budget; inputs are validated. |
| 1:25–2:05 | Import order CSV, show input columns, run `order-breakup` | Explain gross, discounts, commission base, commission, packaging cap and separate tax lines. Mention the pending policy assumptions from the checklist. |
| 2:05–2:45 | Run weekly settlement, inspect settlement report | Monday is the week key. The statement records eligible orders, deductions, ads, payout, and debit carry. Repeating settlement returns the existing statement. |
| 2:45–3:35 | Show dispute OPEN/CLOSE rows and correction report/audit | Open disputes are held out. The close date chooses the payout week. A post-settlement refund creates an appended correction and audit entries. |
| 3:35–4:15 | Open CSV and JSON outputs | Order reports show calculated fields; settlement reports show the latest revision; audit reports retain original and correction entries. |
| 4:15–4:45 | Run tests and show the result | Tests cover financial boundaries, validation, transactions, idempotency, reports, and a temporary-database CLI workflow. State the actual result from this run. |
| 4:45–5:00 | Final checklist | Summarize what is verified and name remaining organizer decisions, rather than claiming unknown policies are complete. |

## Exact workflow commands

In the isolated demo copy, with `R001`, `ORD001`, and dates matching its data files:

```powershell
& '.\.venv\Scripts\python.exe' main.py init-db
& '.\.venv\Scripts\python.exe' main.py register-restaurants --file data\restaurants.csv
& '.\.venv\Scripts\python.exe' main.py process-orders --file data\orders.csv
& '.\.venv\Scripts\python.exe' main.py order-breakup --order-id ORD001
& '.\.venv\Scripts\python.exe' main.py weekly-payout --restaurant-id R001 --week-start 2026-10-26 --ad-spend 50
& '.\.venv\Scripts\python.exe' main.py report --type orders --output output\orders.json
& '.\.venv\Scripts\python.exe' main.py report --type settlements --output output\settlements.csv
& '.\.venv\Scripts\python.exe' main.py report --type audit --output output\audit.json
```

Dispute and correction demonstration in a fresh isolated project copy (the order falls in the prior week; the dispute closes Tuesday):

```powershell
& '.\.venv\Scripts\python.exe' main.py init-db
& '.\.venv\Scripts\python.exe' main.py register-restaurants --file data\restaurants.csv
$demoOrder = Join-Path $env:TEMP 'food-delivery-dispute-order.csv'
@'
order_id,restaurant_id,order_time,items_gross,outcome
ORD-DISPUTE-002,R001,2026-10-25T12:00:00,250.00,DELIVERED
'@ | Set-Content -LiteralPath $demoOrder -Encoding utf8
& '.\.venv\Scripts\python.exe' main.py process-orders --file $demoOrder
& '.\.venv\Scripts\python.exe' main.py weekly-payout --restaurant-id R001 --week-start 2026-10-19
$demoEvents = Join-Path $env:TEMP 'food-delivery-dispute-events.csv'
@'
dispute_id,order_id,event,event_at,resolution,refund_amount,refund_reason
DSP-DEMO-002,ORD-DISPUTE-002,OPEN,2026-10-26T23:59:00,,,
DSP-DEMO-002,ORD-DISPUTE-002,CLOSE,2026-10-27T15:00:00,REFUND_APPROVED,10.00,MISSING_ITEM
'@ | Set-Content -LiteralPath $demoEvents -Encoding utf8
& '.\.venv\Scripts\python.exe' main.py process-disputes --file $demoEvents
& '.\.venv\Scripts\python.exe' main.py correct-settlement --settlement-id 1 --reason "Approved dispute adjustment"
& '.\.venv\Scripts\python.exe' main.py report --type audit --output output\audit-after-correction.json
```

The checked-in dispute fixture references `ORD-DISPUTE-002`, which is not in `data/orders.csv`; its paired order example also predates the OPEN event incorrectly. Do not overwrite either sample file. In the disposable project copy, create a corrected order input with that ID and an order timestamp before `2026-10-26T23:59:00`, import it, settle its order week, then process `data/dispute_demo.csv` and correct that original statement. A separate not-yet-settled example can run settlement for the week containing the close timestamp. The automated dispute test verifies that close-week assignment. Do not replay an already processed event file expecting it to apply twice.

## Recording checklist

- [ ] Close unrelated windows and show the project title and five-minute agenda.
- [ ] Use an isolated working copy and confirm its output/database locations before running commands.
- [ ] Keep terminal font readable and commands/results visible.
- [ ] Explain each important monetary line and state where policy remains unresolved.
- [ ] Show a real test result from the recording session.
- [ ] Open at least one CSV/JSON report and the audit output.
- [ ] Do not display credentials, personal paths outside the intended demo, or production data.
- [ ] Save and play back the recording to check audio, legibility and complete capture.

This file prepares the demonstration; it does not claim that a video recording has been created.
