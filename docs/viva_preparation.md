# Viva preparation

## Architecture and technology

1. **Why Python?** It supports clear command-line applications, CSV/JSON processing, Decimal arithmetic and a mature pytest ecosystem with little deployment overhead.
2. **Why SQLite?** This is a local single-application ledger. SQLite gives durable transactions, keys and constraints without requiring a separate database server.
3. **Why Decimal instead of float?** Decimal represents decimal currency values predictably; binary floating point can introduce representation errors. Results are quantized to paise with `ROUND_HALF_UP`.
4. **How is the project divided?** `main.py` parses commands, `src/engine.py` validates and coordinates workflows, `src/calculations.py` computes breakups, and `database/` owns schema and connections.
5. **Why have a CLI?** It makes imports, calculations, settlement and reports repeatable and easy to demonstrate without a web service.
6. **How does data flow?** CLI arguments point to input files; the engine validates and persists source records, calculation functions return financial line items, and reports export stored and computed results.
7. **What does `config.py` do?** It centralizes the project root, local database path and output directory.
8. **How are errors presented?** Domain validation raises `ValueError`; the CLI converts supported input/domain errors into argparse errors and a failing exit status.

## Business logic

9. **How are standard commission rates selected?** STANDARD is 18% and PLUS is 22% after the introductory period.
10. **How does onboarding affect commission?** Orders from onboarding day zero through day 60 inclusive use 12%.
11. **What is the commission base?** Gross item value less restaurant-funded discount. Platform-funded discount is reimbursed and does not reduce restaurant earnings or the commission base.
12. **How is co-funding split?** Half to each funder, with the implementation assigning an odd paisa to the platform portion.
13. **How is packaging handled?** It is a separate amount capped at Rs 30; excess is recorded but not charged.
14. **What is the Section 9(5) GST calculation?** The implementation calculates 5% of gross item value; cancellation/refund adjustments remain a pending policy detail.
15. **How is commission GST calculated?** 18% of commission. It is zero when the percentage commission is replaced by the flat minimum platform fee.
16. **How is TDS handled?** The engine tracks eligible GMV by financial year beginning April 1 and withholds 1% after the threshold under its documented convention. Whether the crossing order itself is withheld needs organizer confirmation.
17. **How do cancellation rules work?** The supported implementation distinguishes customer and restaurant cancellations and uses the 60-second boundary, but refund base and tax details are documented assumptions requiring confirmation.
18. **How are partial refunds funded?** MISSING_ITEM is restaurant-funded, LATE_DELIVERY is platform-funded, and SPILLED is split with an odd paisa assigned to the platform.
19. **How does rating affect commission?** A prior-week average below 3.5 adds two percentage points for the settlement week.
20. **How does rating suspension work?** The applicable recorded weekly average below 3 suspends future order imports. A single low order rating does not suspend when the weekly average is not below 3. Existing orders remain settleable.
21. **How do ads affect payout?** Requested spend is capped by weekly budget and positive pre-ad payout. Unpaid requested spend is carried; the budget not requested expires.
22. **How is a settlement week chosen?** Monday through Sunday, identified by its Monday. Tuesday is the documented payment cycle, but command execution is not restricted to Tuesday.
23. **What happens to delivery and platform fees?** Supplied platform fees are treated as precomputed deductions except for the sub-Rs 100 fixed fee. Delivery fees are reported but excluded from restaurant payout until policy specifies calculation and allocation.

## Database and integrity

24. **What are primary keys used for?** They uniquely identify restaurants, orders, disputes and audit/revision records; settlements use an integer key plus a unique restaurant/week constraint.
25. **Why use foreign keys?** They prevent orders, settlements and audit rows from referring to missing parent records.
26. **What do transactions protect?** A failed multi-row import, settlement, or correction should not leave only part of its related records committed.
27. **How is import idempotency implemented?** A content hash in `processing_history` skips byte-identical files. A different file that repeats an order ID is rejected.
28. **How is settlement replay handled?** A unique restaurant/week key prevents a second original statement; a repeated request returns the existing statement.
29. **How is audit history preserved?** Original settlement and per-order audit rows remain stored. Corrections append numbered revisions and correction audit snapshots.
30. **What is the correction limitation?** Later settlement statements and their ad-debit carries are not automatically recalculated after an earlier correction; this is explicitly disclosed.
31. **Why store money as text in SQLite?** It avoids SQLite's implicit floating-point coercion. Python Decimal performs the arithmetic.
32. **How are schema changes handled?** The connection runs the idempotent schema and applies additive column migrations for existing databases; it does not drop data.

## Testing and validation

33. **Why pytest?** It provides readable assertions, fixtures, parametrization and temporary-directory support for both formulas and workflows.
34. **What is a unit test here?** A calculation test exercises a pure financial function and asserts exact expected amounts and boundaries.
35. **What is an integration test here?** An engine/CLI test imports files, writes to an isolated database, settles and inspects reports.
36. **How is production data protected during tests?** Tests redirect the database connection to temporary paths and generate fixture files in pytest temporary directories.
37. **What edge cases are covered?** Day 60, Rs 100 fee boundary, half-paisa rounding, odd-paisa refund allocation, FY reset, ad carry, dispute ordering, malformed files, rollback and repeated operations.
38. **How do you verify a change did not regress behavior?** Run the directly affected test first, then the complete suite, and inspect the diff and status.
39. **What does the current test result establish?** The recorded full suite run passed 46 tests; it does not establish compliance with unspecified organizer policies or unseen sample outputs.

## Safe live modification exercise

Use strict CSV parsing as the example because it improves malformed-input handling without changing financial calculations.

1. Change `src/engine.py::read_rows` to reject malformed quoting and extra fields instead of accepting a partial row.
2. Add regression cases in `tests/test_engine.py::test_malformed_files_invalid_dates_and_invalid_order_rating_fail_cleanly` and assert the clear validation error.
3. Run the focused test: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_engine.py -q -k malformed_files`.
4. Run the full suite with a fresh temporary base directory and inspect `git diff --check`.
5. Explain that the change preserves valid CSV imports and all Decimal calculations; cite `test_itemized_csv_lines_and_aggregate_csv_compatibility` and the full regression run as evidence.

For a live presentation, use a disposable copy of the project and never edit or test against the checked-in SQLite file.
