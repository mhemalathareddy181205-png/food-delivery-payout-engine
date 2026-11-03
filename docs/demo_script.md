# Demo script

1. Initialize SQLite and register the sample restaurant.
2. Import `data\orders.csv`; import the identical file again to show it reports zero new rows.
3. Print ORD001's order breakup and explain gross items, restaurant funded discount, commission base, capped packaging, commission GST, and Section 9(5) GST deduction.
4. For dispute demonstration, create an order with `dispute_status=OPEN`, import it, close it Tuesday with `close-dispute`, then settle the Monday containing Tuesday. Point out that settlement selection uses close date.
5. Run weekly payout with an ad spend value, rerun the same command, and show that the same statement ID/order list is returned.
6. Export settlement and audit CSVs and inspect the calculated values.

PowerShell commands are in the README. The fixture contains no dispute, so step 4 uses a temporary order input with a unique ID and date.
