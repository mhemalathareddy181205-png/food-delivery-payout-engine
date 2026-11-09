# Test plan

## Execution

Run from PowerShell at the repository root. Use a fresh temporary base directory if Windows reports cleanup or access errors:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp='C:\food delivery\pytest-temp-final' -p no:cacheprovider
```

Tests redirect SQLite to `tmp_path` databases and create their own input/output files. They do not use the checked-in local database or overwrite sample CSV files.

## Coverage types

- **Unit and expected-value tests:** `tests/test_calculations.py` verifies Decimal half-up rounding, invalid amounts, commission plans and onboarding day 60, the Rs 100 fee boundary, GST, discount funding, packaging cap, cancellation timing, refund allocation including odd paisa, and rating uplift.
- **Input validation tests:** empty/malformed JSON, strictly parsed malformed CSV, missing fields, extra CSV fields, malformed dates, unknown restaurant IDs, duplicate IDs, invalid outcomes/flags, invalid ratings and itemized order total mismatch.
- **Database and transaction tests:** imports use isolated SQLite databases; duplicate batches fail atomically; dispute event batches roll back; constraints and settlement assignment are exercised through engine calls.
- **Dispute integration tests:** OPEN/CLOSE ordering, duplicate/invalid transitions, close-week selection, supported explicit refunds and rejection of unsupported/mixed funders.
- **Settlement and financial boundaries:** TDS threshold and April reset, prior-week rating cutoff, ad budget and carry, negative payout, duplicate settlement, correction revision replay, and audit retention.
- **Report tests:** calculated order CSV/JSON, settlement report revisions, and audit rows for original and corrected statements.
- **CLI integration:** `test_cli_workflow_uses_only_test_database_and_safe_files` invokes the entry point with temporary files/database and exercises initialization, registration, orders, breakup, settlement and reports.
- **Regression:** run the complete suite after any code change; retain exact expected values and existing assertions.

## Business rule links

`docs/br_traceability.md` maps every BR-ID to the implementation and named tests. Policy details the brief does not define remain documented as partial/pending; tests assert the current documented interpretation and do not establish organizer approval.

## Current gaps in test evidence

The current suite does not establish Tuesday-only execution, a delivery-fee formula/allocation, unknown cancellation tax bases, whether TDS applies to the crossing transaction, mixed funding reasons on one order, or automatic cascade of historical corrections into later statements. Those gaps require policy decisions before expected behavior can be tested safely. The supplied data also does not contain the organizer's full 10-restaurant/200-order fixture and expected outputs.
