# PS-039 – Food Delivery Commission and Restaurant Payout Engine — Sample Data Pack

Prepared by 10 SECONDS for Team T022.

## Files

| File | What it holds | Row count |
|---|---|---|
| `restaurants.csv` | 10 restaurants with commission plan, onboarding date, packaging setting, weekly ad budget and FY-to-date GMV | 10 data rows |
| `ad_spend.csv` | Actual ad spend per restaurant per payout week | 27 data rows |
| `disputes.csv` | Order disputes with open and close times | 4 data rows |
| `commands.txt` | 200 orders over 3 weeks with outcomes (25 refunds, 15 cancellations), payouts and print requests | 665 command lines (excluding comments) |

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix. An empty cell means "not applicable" and only appears in columns whose notes say so.

### `restaurants.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| restaurant_id | string | RST-nn | — | primary key |
| restaurant_name | string | — | — | fictional |
| cuisine | string | — | — | — |
| commission_plan | enum | — | STANDARD, PLUS | 18% / 22% |
| onboarding_date | date | — | — | 12% for the first 60 days |
| packaging_charge | decimal | Rs | — | what the restaurant charges per order (cap Rs 30) |
| weekly_ad_budget | decimal | Rs | — | — |
| opening_fy_gmv | decimal | Rs | — | platform GMV from 2026-04-01 to 2026-10-04 (194-O threshold) |
| gstin | string | 15 chars | — | fake but well-formed |

### `ad_spend.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| restaurant_id | string | — | restaurants.csv | — |
| week_start | date | Monday | — | — |
| ad_spend | decimal | Rs | — | deduct up to the weekly budget |

### `disputes.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| dispute_id | string | DSP-nnn | — | — |
| order_id | string | ORD-nnnn | — | an ORDER in commands.txt |
| opened_ts | timestamp | — | — | — |
| closed_ts | timestamp | — | — | — |
| reason | string | — | — | informational |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. An empty argument (two adjacent `|`) means "not supplied". Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `ORDER` | `order_id|ts|restaurant_id|items|restaurant_discount|platform_coupon|cofunded_discount|packaging_charge|distance_km|delivery_fee|payment_mode` | items = `name:qty:unit_price` joined by `,` |
| `ACCEPTED` | `order_id|ts` | Restaurant accepts the order |
| `DELIVERED` | `order_id|ts|rating` | Order delivered; rating 1-5 or empty |
| `CANCEL_CUSTOMER` | `order_id|ts` | Customer cancellation (free within 60 s of the order) |
| `CANCEL_RESTAURANT` | `order_id|ts` | Restaurant cancellation |
| `REFUND` | `order_id|ts|reason|amount` | Partial refund; reason MISSING_ITEM, SPILLED or LATE_DELIVERY |
| `PAYOUT` | `week_start` | Compute the weekly payout for orders delivered Mon–Sun of that week (plus disputes closed in it) |
| `PRINT_BREAKUP` | `order_id` | Print the order-level breakup |
| `PRINT_STATEMENT` | `restaurant_id|week_start` | Print the weekly payout statement |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 Restaurant onboarded exactly 60 days before the order date**
  - RST-03 onboarded 2026-08-07: orders on 2026-10-05 (59 days), 2026-10-06 (exactly 60 days) and 2026-10-07 (61 days) -> where the 12% introductory commission stops — restaurants.csv row 3 (RST-03); commands.txt line 10 (`ORDER|ORD-0004|2026-10-05 13:10:00|RST-03|Chicken Dum Biryani:2:280.00,Veg Biryani:2:210.00|0.00|0.00|0.00|25.00|5.1|0.00|UPI`); commands.txt line 34 (`ORDER|ORD-0015|2026-10-06 13:05:00|RST-03|Chicken Dum Biryani:1:280.00,Mutton Biryani:2:360.00|0.00|0.00|0.00|25.00|0.8|45.00|WALLET`); commands.txt line 54 (`ORDER|ORD-0024|2026-10-07 12:55:00|RST-03|Raita:2:45.00|0.00|0.00|0.00|25.00|2.9|25.00|CARD`)
- **EC-02 Co-funded discount on an order with packaging above the cap**
  - RST-02 charges packaging Rs 45.00 (capped to 30.00, Rs 15 disallowed); this order also carries a Rs 120 co-funded 50:50 discount -> Rs 60 reduces the commission base — restaurants.csv row 2 (RST-02); commands.txt line 86 (`ORDER|ORD-0040|2026-10-08 20:15:00|RST-02|Chicken Dum Biryani:1:280.00,Mutton Biryani:3:360.00,Double Ka Meetha:2:90.00|0.00|0.00|120.00|45.00|3.7|25.00|UPI`)
- **EC-03 GMV crossing Rs 5 lakh in the middle of a payout week**
  - RST-05 opens FY 2026-27 with GMV just under Rs 5 lakh (restaurants.csv); its week-2 orders push cumulative GMV past Rs 5 lakh on Wednesday 2026-10-14 -> 1% TDS (194-O) only from the crossing — restaurants.csv row 5 (RST-05); commands.txt line 159 (`ORDER|ORD-0071|2026-10-12 19:10:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|4.0|0.00|WALLET`); commands.txt line 191 (`ORDER|ORD-0084|2026-10-13 20:11:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|1.7|0.00|COD`); commands.txt line 214 (`ORDER|ORD-0095|2026-10-14 13:12:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|3.6|25.00|CARD`); commands.txt line 249 (`ORDER|ORD-0112|2026-10-15 21:13:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|4.7|45.00|UPI`); commands.txt line 263 (`ORDER|ORD-0118|2026-10-16 20:14:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|0.8|35.00|UPI`); commands.txt line 278 (`ORDER|ORD-0124|2026-10-17 13:15:00|RST-05|Veg Hakka Noodles:4:170.00,Chilli Paneer:3:220.00,Gobi Manchurian:2:180.00|0.00|0.00|0.00|25.00|5.1|45.00|UPI`)
- **EC-04 Customer cancellation at exactly 60 seconds**
  - CANCEL_CUSTOMER exactly 60 s after the order (boundary of the free window) and a control at 59 s — commands.txt line 106 (`ORDER|ORD-0049|2026-10-09 19:30:00|RST-07|Butter Naan:2:55.00|0.00|0.00|0.00|25.00|6.6|45.00|UPI`); commands.txt line 107 (`CANCEL_CUSTOMER|ORD-0049|2026-10-09 19:31:00`); commands.txt line 108 (`ORDER|ORD-0050|2026-10-09 19:45:00|RST-07|Dal Makhani:1:210.00|0.00|0.00|0.00|25.00|3.9|35.00|UPI`); commands.txt line 109 (`CANCEL_CUSTOMER|ORD-0050|2026-10-09 19:45:59`)
- **EC-05 Weekly average rating exactly 3.5**
  - RST-10 week 1 ratings 3,4,3,4,4,3,5,2 -> average exactly 3.50 (penalty applies only below 3.5) — commands.txt line 7 (`ORDER|ORD-0002|2026-10-05 12:20:00|RST-10|Paneer Butter Masala:2:240.00|0.00|0.00|0.00|30.00|1.5|0.00|COD`); commands.txt line 36 (`ORDER|ORD-0016|2026-10-06 13:20:00|RST-10|Butter Naan:2:55.00|0.00|0.00|0.00|30.00|2.1|25.00|COD`); commands.txt line 60 (`ORDER|ORD-0027|2026-10-07 14:20:00|RST-10|Dal Makhani:2:210.00|0.00|0.00|0.00|30.00|6.8|25.00|UPI`); commands.txt line 82 (`ORDER|ORD-0037|2026-10-08 15:20:00|RST-10|Jeera Rice:2:150.00|0.00|0.00|0.00|30.00|1.7|0.00|UPI`); commands.txt line 103 (`ORDER|ORD-0047|2026-10-09 16:20:00|RST-10|Gulab Jamun:2:60.00|0.00|0.00|0.00|30.00|3.3|25.00|WALLET`); commands.txt line 126 (`ORDER|ORD-0057|2026-10-10 17:20:00|RST-10|Paneer Butter Masala:2:240.00|0.00|0.00|0.00|30.00|4.3|45.00|UPI`); commands.txt line 144 (`ORDER|ORD-0064|2026-10-11 18:20:00|RST-10|Butter Naan:2:55.00|0.00|0.00|0.00|30.00|3.2|45.00|UPI`); commands.txt line 17 (`ORDER|ORD-0007|2026-10-05 19:20:00|RST-10|Dal Makhani:2:210.00|0.00|0.00|0.00|30.00|3.0|45.00|CARD`)
- **EC-06 Ad spend larger than the week's payout**
  - RST-01 has a Rs 5,000 weekly ad budget and spends Rs 4,800 in week 2 while its week-2 payout is only a couple of small orders -> payout floors at 0, remainder carried as a debit (budget does not carry) — ad_spend.csv row 10 (RST-01)
- **EC-07 Dispute opened Sunday 23:59 and closed Tuesday 08:00**
  - Order delivered Sunday 2026-10-11 23:35; dispute opened 2026-10-11 23:59:00 and closed Tuesday 2026-10-13 08:00:00, one hour before the PAYOUT for week 1 runs — commands.txt line 149 (`ORDER|ORD-0067|2026-10-11 22:50:00|RST-07|Paneer Butter Masala:3:240.00,Jeera Rice:2:150.00|0.00|0.00|0.00|25.00|6.7|45.00|CARD`); disputes.csv row 1 (DSP-001)
- **EC-08 Net item value exactly Rs 100**
  - RST-06: items 135.00 minus restaurant discount 35.00 = net item value exactly 100.00 (percentage commission) vs the 95.00 order (< 100 -> flat Rs 10 platform fee) — commands.txt line 259 (`ORDER|ORD-0116|2026-10-16 17:05:00|RST-06|Chocolate Pastry:1:85.00,Bun Maska:1:50.00|35.00|0.00|0.00|0.00|3.4|25.00|UPI`); commands.txt line 260 (`ORDER|ORD-0117|2026-10-16 17:25:00|RST-06|Veg Puff:1:35.00,Honey Cake:1:60.00|0.00|0.00|0.00|0.00|7.2|35.00|CARD`)
- **Extra traps (not in the brief, but realistic):**
  - RST-09 week 1 ratings average 3.40 -> +2 percentage points of commission on its week-2 orders — restaurants.csv row 9 (RST-09)
  - RST-08 week 2 average rating 2.60 (< 3.0) -> new orders suspended in week 3; its order on 2026-10-20 must be rejected — commands.txt line 157 (`ORDER|ORD-0070|2026-10-12 13:30:00|RST-08|Masala Dosa:1:95.00,Bisi Bele Bath:1:110.00|0.00|0.00|0.00|0.00|6.4|0.00|CARD`); commands.txt line 332 (`ORDER|ORD-0148|2026-10-20 13:00:00|RST-08|Masala Dosa:2:95.00|0.00|0.00|0.00|0.00|5.6|45.00|COD`)
  - Restaurant cancels after acceptance -> Rs 100 penalty plus the full customer refund borne by the restaurant — commands.txt line 349 (`ORDER|ORD-0155|2026-10-21 20:05:00|RST-07|Butter Naan:2:55.00,Dal Makhani:1:210.00|0.00|0.00|0.00|25.00|2.6|45.00|CARD`); commands.txt line 351 (`CANCEL_RESTAURANT|ORD-0155|2026-10-21 20:19:00`)
  - REFUND with reason COLD_FOOD (not MISSING_ITEM / SPILLED / LATE_DELIVERY) -> reject the refund line — commands.txt line 373 (`ORDER|ORD-0167|2026-10-22 21:10:00|RST-02|Veg Biryani:2:210.00|0.00|0.00|0.00|45.00|5.2|35.00|UPI`); commands.txt line 381 (`REFUND|ORD-0167|2026-10-22 23:10:00|COLD_FOOD|80.00`)
  - RST-04 charges packaging exactly Rs 30.00 -> allowed in full (cap is 'up to Rs 30') — restaurants.csv row 4 (RST-04)
  - ORD-0060 gets DELIVERED twice (rider-app retry) -> process once — commands.txt line 133 (`DELIVERED|ORD-0060|2026-10-10 23:02:48|4`); commands.txt line 134 (`DELIVERED|ORD-0060|2026-10-10 23:02:48|4`)

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `order_breakup.csv`

One row per PRINT_BREAKUP.

Columns, in order: `order_id`, `restaurant_id`, `status`, `gross_item_value`, `restaurant_discount`, `platform_coupon`, `cofunded_restaurant_share`, `cofunded_platform_share`, `net_item_value`, `packaging_allowed`, `packaging_disallowed`, `commission_rate`, `commission`, `platform_fee`, `gst_on_commission`, `gst_9_5`, `tds_194o`, `coupon_reimbursement`, `refund_restaurant_share`, `refund_platform_share`, `penalty`, `restaurant_net`, `rule_ids`

### `weekly_statement.csv`

One row per PRINT_STATEMENT.

Columns, in order: `restaurant_id`, `week_start`, `orders_settled`, `orders_excluded_dispute`, `gross_payable`, `ad_spend_deducted`, `debit_brought_forward`, `net_payout`, `debit_carried_forward`, `avg_rating`, `next_week_commission_uplift_pp`, `suspended_next_week`

Binding choices: `status` is DELIVERED, CANCELLED_BY_CUSTOMER_FREE, CANCELLED_BY_CUSTOMER_CHARGED, CANCELLED_BY_RESTAURANT, REJECTED or DISPUTED; avg_rating has 2 decimals and ignores unrated orders; commission_rate is printed as a percentage (18.0); FY GMV for 194-O = opening_fy_gmv + gross item value of orders delivered in this stream.
