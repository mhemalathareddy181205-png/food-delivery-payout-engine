# Test plan

Run the suite from PowerShell with `& '.\.venv\Scripts\python.exe' -m pytest tests -q --basetemp="$env:TEMP\food-delivery-pytest" -p no:cacheprovider`. Tests use `tmp_path` SQLite databases and generated fixtures; they do not use the project's local settlement database or overwrite sample data.

Calculation tests cover half-up currency rounding, invalid amounts/outcomes, both standard commission rates, the inclusive onboarding day-60 rate, fee boundaries, commission GST, discount funding, packaging cap, cancellation timing/penalty, all refund funders, SPILLED odd-paisa allocation, and rating uplift. Engine tests cover registration and suspension, aggregate and itemized imports, validation and atomic rollback, file idempotency, dispute timestamps/transitions/refunds, close-week assignment, TDS threshold and FY reset, ad budget and carry, duplicate payout handling, correction revision idempotency/history, CSV/JSON reports, and a CLI happy path using only temporary files and a temporary database.

`docs/br_traceability.md` names the tests linked to each BR-ID. The suite covers documented business behavior; unresolved organizer rules remain partial and are not assigned invented expected outputs. The checked-in data still lacks the organizer's complete multiweek sample and expected outputs.
