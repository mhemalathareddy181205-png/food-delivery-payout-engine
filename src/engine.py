"""Validated file ingestion, persisted order ledgers, disputes and payouts."""
import csv, json, hashlib
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from database.database import connect
from src.calculations import money, order_breakup, order_breakup_full, dynamic_commission_by_cuisine, multi_restaurant_split

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

def read_rows(path):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise ValueError(f"Input file not found: {p}")
    if not p.stat().st_size:
        raise ValueError("Input file is empty")
    try:
        if p.suffix.lower() == '.json':
            x = json.loads(p.read_text(encoding='utf-8-sig'))
            rows = x.get('rows') if isinstance(x, dict) else x
            if not isinstance(rows, list):
                raise ValueError('JSON must be an array or contain a rows array')
            return rows
        with p.open(newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, strict=True)
            if not reader.fieldnames or any(not name for name in reader.fieldnames):
                raise ValueError('CSV must include valid column headers')
            rows = list(reader)
            if not rows:
                raise ValueError('CSV must include a header and at least one data row')
            if any(None in row for row in rows):
                raise ValueError('CSV rows cannot contain more fields than the header')
            return rows
    except (json.JSONDecodeError, UnicodeError, csv.Error) as e:
        raise ValueError(f'Malformed input: {e}') from e

def _normalize_item_csv(rows):
    item_fields = {'item_name', 'item_quantity', 'item_unit_price'}
    if not any(any(row.get(k) not in (None, '') for k in item_fields) for row in rows):
        return rows
    groups = {}
    reserved = item_fields
    for row in rows:
        order_id = (row.get('order_id') or '').strip()
        if not order_id:
            raise ValueError('Every itemized CSV row must have order_id')
        order = groups.setdefault(order_id, {k: v for k, v in row.items() if k not in reserved and v not in (None, '')})
        if 'items' not in order:
            order['items'] = []
        for key, value in row.items():
            if key in reserved or value in (None, ''):
                continue
            if key in order and order[key] not in ('', value):
                raise ValueError(f'Conflicting order-level value for {key} on {order_id}')
            order[key] = value
        if any(row.get(k) not in (None, '') for k in item_fields):
            if not row.get('item_name') or not row.get('item_unit_price'):
                raise ValueError('Itemized CSV lines require item_name and item_unit_price')
            order['items'].append({'name': row['item_name'], 'quantity': row.get('item_quantity') or '1', 'unit_price': row['item_unit_price']})
    for order in groups.values():
        if not order['items']:
            raise ValueError('Each itemized order requires at least one item line')
        total = sum((Decimal(str(i['quantity'])) * money(i['unit_price']) for i in order['items']), Decimal(0))
        if not order.get('items_gross'):
            order['items_gross'] = str(money(total))
    return list(groups.values())

def import_restaurants(path):
    rows = read_rows(path)
    db = connect()
    try:
        for r in rows:
            name = r.get('restaurant_name') or r.get('name')
            plan = r.get('commission_plan') or r.get('plan')
            if not r.get('restaurant_id') or not name or not plan or not r.get('onboarding_date'):
                raise ValueError('Restaurant rows require restaurant_id, name, plan, onboarding_date')
            plan = plan.strip().upper()
            status = r.get('status', 'ACTIVE').strip().upper()
            rating_val = r.get('rating')
            rating = Decimal(str(rating_val)) if rating_val not in (None, '') else Decimal('5.0')
            if not rating.is_finite() or plan not in ('STANDARD', 'PLUS') or status not in ('ACTIVE', 'SUSPENDED') or not 0 <= rating <= 5:
                raise ValueError('Invalid plan, status, or rating')
            date.fromisoformat(r['onboarding_date'][:10])
            pack = money(r.get('packaging_charge', 0))
            budget = money(r.get('weekly_ad_budget', 0))
            cuisine = r.get('cuisine', '')
            opening_fy_gmv = str(money(r.get('opening_fy_gmv', 0)))
            gstin = r.get('gstin', '')
            status = 'SUSPENDED' if rating < 3 else status
            db.execute('INSERT INTO restaurants(restaurant_id,name,plan,onboarding_date,rating,packaging_charge,weekly_ad_budget,status,cuisine,opening_fy_gmv,gstin) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(restaurant_id) DO UPDATE SET name=excluded.name,plan=excluded.plan,onboarding_date=excluded.onboarding_date,rating=excluded.rating,packaging_charge=excluded.packaging_charge,weekly_ad_budget=excluded.weekly_ad_budget,status=excluded.status,cuisine=excluded.cuisine,opening_fy_gmv=excluded.opening_fy_gmv,gstin=excluded.gstin',
                       (r['restaurant_id'], name, plan, r['onboarding_date'], str(rating), str(pack), str(budget), status, cuisine, opening_fy_gmv, gstin))
        db.commit()
        return len(rows)
    finally:
        db.close()

def import_ad_spend(path):
    rows = read_rows(path)
    db = connect()
    try:
        count = 0
        for r in rows:
            db.execute('INSERT OR REPLACE INTO ad_spend(restaurant_id,week_start,ad_spend) VALUES(?,?,?)',
                       (r['restaurant_id'].strip(), r['week_start'].strip(), str(money(r['ad_spend']))))
            count += 1
        db.commit()
        return count
    finally:
        db.close()

def import_orders(path):
    p = Path(path)
    rows = read_rows(p)
    rows = _normalize_item_csv(rows) if p.suffix.lower() == '.csv' else rows
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    db = connect()
    try:
        if db.execute('SELECT 1 FROM processing_history WHERE file_hash=?', (digest,)).fetchone():
            return 0
        latest_ratings = {}
        seen_order_ids = set()
        for r in rows:
            required = ('order_id', 'restaurant_id', 'order_time', 'items_gross')
            if any(not r.get(key) for key in required):
                raise ValueError('Order rows require order_id, restaurant_id, order_time, and items_gross')
            if r['order_id'] in seen_order_ids or db.execute('SELECT 1 FROM orders WHERE order_id=?', (r['order_id'],)).fetchone():
                raise ValueError(f"Duplicate order ID: {r['order_id']}")
            seen_order_ids.add(r['order_id'])
            rest = db.execute('SELECT * FROM restaurants WHERE restaurant_id=?', (r['restaurant_id'],)).fetchone()
            if not rest:
                raise ValueError(f"Unknown restaurant: {r['restaurant_id']}")
            t = datetime.fromisoformat(r['order_time'])
            outcome = r.get('outcome', 'DELIVERED').upper()
            if rest['status'] == 'SUSPENDED':
                raise ValueError(f"Restaurant {r['restaurant_id']} is suspended")
            if outcome not in ('DELIVERED', 'CANCELLED_BY_RESTAURANT', 'CANCELLED_BY_CUSTOMER', 'REFUND_PARTIAL'):
                raise ValueError('Invalid outcome')
            if r.get('dispute_status', 'CLOSED').upper() not in ('OPEN', 'CLOSED'):
                raise ValueError('Invalid dispute status')
            order_breakup(r | {'outcome': outcome, 'order_time': t.isoformat()}, dict(rest))
            item_total = Decimal(0)
            for item in r.get('items', []):
                quantity = Decimal(str(item.get('quantity', 1)))
                if not quantity.is_finite() or quantity <= 0:
                    raise ValueError('Item quantity must be positive and finite')
                item_total += quantity * money(item['unit_price'])
            if r.get('items') and money(item_total) != money(r['items_gross']):
                raise ValueError('Item quantity and unit prices must sum to items_gross')
            cancel_seconds = int(r.get('cancel_seconds', 0))
            accepted = int(r.get('accepted', 1))
            if cancel_seconds < 0 or accepted not in (0, 1):
                raise ValueError('cancel_seconds must be non-negative and accepted must be 0 or 1')
            vals = (r['order_id'], r['restaurant_id'], t.isoformat(), str(money(r['items_gross'])), str(money(r.get('restaurant_discount', 0))),
                    str(money(r.get('platform_discount', 0))), str(money(r.get('cofund_discount', 0))), str(money(r.get('packaging', rest['packaging_charge']))),
                    str(money(r.get('distance', 0))), r.get('payment_mode', 'UNKNOWN'), outcome, r.get('refund_reason', '').upper(),
                    str(money(r.get('refund_amount', 0))), r.get('dispute_status', 'CLOSED').upper(), cancel_seconds, accepted,
                    r.get('dispute_closed_at', ''), datetime.now().isoformat(timespec='seconds'), str(money(r.get('delivery_fee', 0))),
                    str(money(r.get('platform_fee', 0))), str(money(r.get('rating', 0))) if r.get('rating') else '', str(money(r.get('customer_refund', 0))))
            db.execute('INSERT INTO orders(order_id,restaurant_id,order_time,items_gross,restaurant_discount,platform_discount,cofund_discount,packaging,distance,payment_mode,outcome,refund_reason,refund_amount,dispute_status,cancel_seconds,accepted,dispute_closed_at,processed_at,delivery_fee,platform_fee,rating,customer_refund) VALUES(' + ','.join('?' * 22) + ')', vals)
            if r.get('rating') not in (None, ''):
                rating = Decimal(str(r['rating']))
                if not rating.is_finite() or rating < 0 or rating > 5:
                    raise ValueError('Rating must be between zero and five')
                latest_ratings.setdefault(r['restaurant_id'], []).append((t.date(), rating))
            for i, item in enumerate(r.get('items', []), 1):
                db.execute('INSERT INTO order_items VALUES(?,?,?,?,?)', (r['order_id'], i, item['name'], str(Decimal(str(item.get('quantity', 1)))), str(money(item['unit_price']))))
            if r.get('dispute_status', 'CLOSED').upper() == 'OPEN':
                db.execute('INSERT OR IGNORE INTO disputes(dispute_id,order_id,opened_at) VALUES(?,?,?)', (r.get('dispute_id', r['order_id']), r['order_id'], r.get('dispute_opened_at', t.isoformat())))
        for rid, entries in latest_ratings.items():
            latest_date = max(day for day, _ in entries)
            week_start = latest_date - timedelta(days=latest_date.weekday())
            week_end = week_start + timedelta(days=6)
            week_ratings = [Decimal(x[0]) for x in db.execute("SELECT rating FROM orders WHERE restaurant_id=? AND rating!='' AND substr(order_time,1,10) BETWEEN ? AND ?", (rid, week_start.isoformat(), week_end.isoformat()))]
            rating = sum(week_ratings, Decimal(0)) / len(week_ratings)
            old_status = db.execute('SELECT status FROM restaurants WHERE restaurant_id=?', (rid,)).fetchone()[0]
            db.execute('UPDATE restaurants SET rating=?,status=? WHERE restaurant_id=?', (str(rating), 'SUSPENDED' if rating < 3 else old_status, rid))
        db.execute('INSERT INTO processing_history VALUES(?,?,?)', (digest, p.name, datetime.now().isoformat(timespec='seconds')))
        db.commit()
        return len(rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def close_dispute(order_id, closed_at, resolution='RESOLVED'):
    at = datetime.fromisoformat(closed_at)
    db = connect()
    try:
        r = db.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
        if not r:
            raise ValueError(f'Unknown order: {order_id}')
        if r['dispute_status'] != 'OPEN':
            raise ValueError('Dispute is not open')
        db.execute("UPDATE orders SET dispute_status='CLOSED',dispute_closed_at=? WHERE order_id=?", (at.isoformat(), order_id))
        db.execute("UPDATE disputes SET closed_at=?,resolution=? WHERE order_id=? AND closed_at=''", (at.isoformat(), resolution, order_id))
        db.commit()
    finally:
        db.close()

def import_disputes(path):
    p = Path(path)
    if p.suffix.lower() != '.csv':
        raise ValueError('Dispute event importer accepts CSV files only')
    rows = read_rows(p)
    digest = hashlib.sha256(b'disputes:' + p.read_bytes()).hexdigest()
    db = connect()
    try:
        if db.execute('SELECT 1 FROM processing_history WHERE file_hash=?', (digest,)).fetchone():
            return 0
        if rows and 'opened_ts' in rows[0] and 'closed_ts' in rows[0]:
            count = 0
            for r in rows:
                db.execute('INSERT OR REPLACE INTO order_disputes(dispute_id,order_id,opened_ts,closed_ts,reason) VALUES(?,?,?,?,?)',
                           (r['dispute_id'].strip(), r['order_id'].strip(), r['opened_ts'].strip(), r['closed_ts'].strip(), r['reason'].strip()))
                count += 1
            db.execute('INSERT INTO processing_history VALUES(?,?,?)', (digest, p.name, datetime.now().isoformat(timespec='seconds')))
            db.commit()
            return count
        count = 0
        for event in rows:
            required = ('dispute_id', 'order_id', 'event', 'event_at')
            if any(not event.get(key) for key in required):
                raise ValueError('Dispute rows require dispute_id, order_id, event, and event_at')
            dispute_id = event['dispute_id'].strip()
            order_id = event['order_id'].strip()
            action = event['event'].strip().upper()
            at = datetime.fromisoformat(event['event_at'])
            order = db.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
            if order is None:
                raise ValueError(f'Unknown order: {order_id}')
            if action == 'OPEN':
                existing = db.execute('SELECT * FROM disputes WHERE dispute_id=?', (dispute_id,)).fetchone()
                if existing:
                    raise ValueError(f'Duplicate dispute ID: {dispute_id}')
                if order['dispute_status'] == 'OPEN':
                    raise ValueError(f'Order already has an open dispute: {order_id}')
                if at < datetime.fromisoformat(order['order_time']):
                    raise ValueError('Dispute open cannot precede order time')
                db.execute('INSERT INTO disputes(dispute_id,order_id,opened_at) VALUES(?,?,?)', (dispute_id, order_id, at.isoformat()))
                db.execute("UPDATE orders SET dispute_status='OPEN',dispute_closed_at='' WHERE order_id=?", (order_id,))
            elif action == 'CLOSE':
                dispute = db.execute('SELECT * FROM disputes WHERE dispute_id=?', (dispute_id,)).fetchone()
                if dispute is None or dispute['closed_at']:
                    raise ValueError(f'No open dispute: {dispute_id}')
                if dispute['order_id'] != order_id:
                    raise ValueError(f'Dispute {dispute_id} belongs to a different order')
                if at < datetime.fromisoformat(dispute['opened_at']):
                    raise ValueError('Dispute close cannot precede opening')
                amount = money(event.get('refund_amount', 0))
                reason = event.get('refund_reason', '').strip().upper()
                if amount > 0 and reason not in ('MISSING_ITEM', 'SPILLED', 'LATE_DELIVERY'):
                    raise ValueError('A positive dispute refund requires a supported refund_reason')
                if amount > 0:
                    if order['outcome'] not in ('DELIVERED', 'REFUND_PARTIAL'):
                        raise ValueError('Dispute refunds can adjust delivered or partially refunded orders only')
                    if order['refund_amount'] not in ('0', '0.00') and order['refund_reason'] != reason:
                        raise ValueError('A single order cannot combine dispute refunds with different funding reasons')
                    amount = money(Decimal(order['refund_amount']) + amount) if order['refund_reason'] == reason else amount
                    db.execute("UPDATE orders SET outcome='REFUND_PARTIAL',refund_amount=?,refund_reason=? WHERE order_id=?", (str(amount), reason, order_id))
                db.execute('UPDATE disputes SET closed_at=?,resolution=?,refund_amount=?,refund_reason=? WHERE dispute_id=?', (at.isoformat(), event.get('resolution', 'RESOLVED'), str(money(event.get('refund_amount', 0))), reason, dispute_id))
                db.execute("UPDATE orders SET dispute_status='CLOSED',dispute_closed_at=? WHERE order_id=?", (at.isoformat(), order_id))
            else:
                raise ValueError(f'Unsupported dispute event: {action}')
            count += 1
        db.execute('INSERT INTO processing_history VALUES(?,?,?)', (digest, p.name, datetime.now().isoformat(timespec='seconds')))
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def _penalty_for_order(db, restaurant_id, order_time):
    d = date.fromisoformat(order_time[:10])
    monday = d - timedelta(days=d.weekday())
    previous = monday - timedelta(days=7)
    ratings = [Decimal(x[0]) for x in db.execute("SELECT rating FROM orders WHERE restaurant_id=? AND rating!='' AND substr(order_time,1,10) BETWEEN ? AND ?", (restaurant_id, previous.isoformat(), (monday - timedelta(days=1)).isoformat()))]
    return bool(ratings) and sum(ratings, Decimal(0)) / len(ratings) < Decimal('3.5')

def _tds_for_order(db, r):
    d = date.fromisoformat(r['order_time'][:10])
    fy = date(d.year if d.month >= 4 else d.year - 1, 4, 1)
    rest = db.execute('SELECT opening_fy_gmv FROM restaurants WHERE restaurant_id=?', (r['restaurant_id'],)).fetchone()
    opening_gmv = Decimal(rest['opening_fy_gmv']) if rest and rest['opening_fy_gmv'] else Decimal('0.00')
    rows = db.execute("SELECT order_id,order_time,items_gross,outcome FROM orders WHERE restaurant_id=? AND order_time>=? AND outcome NOT IN ('CANCELLED_BY_RESTAURANT','CANCELLED_BY_CUSTOMER') ORDER BY order_time,order_id", (r['restaurant_id'], fy.isoformat())).fetchall()
    cumulative = opening_gmv
    for x in rows:
        if x['order_id'] == r['order_id']:
            new_cum = cumulative + Decimal(r['items_gross'])
            return money(Decimal(r['items_gross']) * Decimal('.01')) if new_cum > Decimal('500000') and r['outcome'] not in ('CANCELLED_BY_RESTAURANT', 'CANCELLED_BY_CUSTOMER') else Decimal('0.00')
        cumulative += Decimal(x['items_gross'])
    return Decimal('0.00')

def _breakup_row(r, rest, penalty=False):
    return order_breakup(dict(r), dict(rest), penalty)

def get_breakup(order_id):
    db = connect()
    try:
        r = db.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
        if not r:
            raise ValueError(f'Unknown order: {order_id}')
        effective_time = r['dispute_closed_at'] or r['order_time']
        result = _breakup_row(r, db.execute('SELECT * FROM restaurants WHERE restaurant_id=?', (r['restaurant_id'],)).fetchone(), _penalty_for_order(db, r['restaurant_id'], effective_time))
        tds = _tds_for_order(db, r)
        result['net_restaurant_amount'] = (result['net_restaurant_amount'] - tds).quantize(Decimal('.01'))
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in result.items()} | {'tds': str(tds), 'order_id': order_id, 'restaurant_id': r['restaurant_id'], 'items': [dict(x) for x in db.execute('SELECT name,quantity,unit_price FROM order_items WHERE order_id=?', (order_id,))]}
    finally:
        db.close()

def _latest_settlement(db, statement):
    correction = db.execute('SELECT revision,reason,corrected_statement FROM settlement_corrections WHERE settlement_id=? ORDER BY revision DESC LIMIT 1', (statement['settlement_id'],)).fetchone()
    if correction:
        statement.update(json.loads(correction['corrected_statement']))
        statement['correction_revision'] = correction['revision']
        statement['correction_reason'] = correction['reason']
    else:
        statement['correction_revision'] = 0
        statement['correction_reason'] = ''
    return statement

def correct_settlement(settlement_id, reason):
    if not reason or not reason.strip():
        raise ValueError('Correction reason is required')
    db = connect()
    try:
        base = db.execute('SELECT * FROM settlements WHERE settlement_id=?', (settlement_id,)).fetchone()
        if base is None:
            raise ValueError(f'Unknown settlement: {settlement_id}')
        current = _latest_settlement(db, dict(base))
        order_ids = json.loads(base['order_ids'])
        if not order_ids:
            raise ValueError('Cannot correct a statement without settled orders')
        marks = ','.join('?' for _ in order_ids)
        found = db.execute(f'SELECT * FROM orders WHERE order_id IN ({marks})', (*order_ids,)).fetchall()
        by_id = {r['order_id']: r for r in found}
        rows = [by_id[x] for x in order_ids if x in by_id]
        if len(rows) != len(order_ids):
            raise ValueError('A source order for this settlement is missing')
        restaurant = db.execute('SELECT * FROM restaurants WHERE restaurant_id=?', (base['restaurant_id'],)).fetchone()
        start = date.fromisoformat(base['week_start'])
        prior = [Decimal(x[0]) for x in db.execute("SELECT rating FROM orders WHERE restaurant_id=? AND rating!='' AND substr(order_time,1,10) BETWEEN ? AND ?", (base['restaurant_id'], (start - timedelta(days=7)).isoformat(), (start - timedelta(days=1)).isoformat()))]
        rating_penalty = bool(prior) and sum(prior, Decimal(0)) / len(prior) < Decimal('3.5')
        totals = {k: Decimal('0.00') for k in ('gross', 'restaurant_discounts', 'platform_discounts', 'packaging', 'delivery_fees', 'platform_fees', 'commission', 'gst_95', 'commission_gst', 'tds', 'refunds', 'platform_refunds', 'penalties', 'reimbursements')}
        calculations = []
        for row in rows:
            b = _breakup_row(row, restaurant, rating_penalty)
            tds = _tds_for_order(db, row)
            for key, value in [('gross', b['gross']), ('restaurant_discounts', b['restaurant_discount']), ('platform_discounts', b['platform_discount']), ('packaging', b['packaging']), ('delivery_fees', b['delivery_fee']), ('platform_fees', b['platform_fee']), ('commission', b['commission']), ('gst_95', b['gst_95']), ('commission_gst', b['commission_gst']), ('tds', tds), ('refunds', b['restaurant_refund'] + b['customer_refund']), ('platform_refunds', b['platform_refund']), ('penalties', b['penalty']), ('reimbursements', b['platform_reimbursement'])]:
                totals[key] += value
            calculations.append((row, b, tds))
        due = totals['gross'] - totals['restaurant_discounts'] - totals['platform_discounts'] + totals['packaging'] - totals['platform_fees'] - totals['commission'] - totals['gst_95'] - totals['commission_gst'] - totals['tds'] - totals['refunds'] - totals['penalties'] + totals['reimbursements']
        original_ads = Decimal(current['ads'])
        ads = min(original_ads, max(Decimal(0), due))
        carry = Decimal(current['carried_debit']) + (original_ads - ads)
        corrected = {key: str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) for key, value in totals.items()}
        corrected.update({'ads': str(ads.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)), 'payout': str((due - ads).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)), 'carried_debit': str(carry.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))})
        old_json = json.dumps(current, sort_keys=True)
        new_json = json.dumps(corrected, sort_keys=True)
        latest = db.execute('SELECT COALESCE(MAX(revision),0) FROM settlement_corrections WHERE settlement_id=?', (settlement_id,)).fetchone()[0]
        if latest and all(str(current.get(k)) == v for k, v in corrected.items()):
            return current
        cursor = db.execute('INSERT INTO settlement_corrections(settlement_id,revision,reason,previous_statement,corrected_statement,created_at) VALUES(?,?,?,?,?,?)', (settlement_id, latest + 1, reason.strip(), old_json, new_json, datetime.now().isoformat(timespec='seconds')))
        correction_id = cursor.lastrowid
        for row, b, tds in calculations:
            breakup = {k: str(v) for k, v in b.items()} | {'tds': str(tds)}
            db.execute('INSERT INTO settlement_correction_audit(correction_id,order_id,breakup_json,recorded_at) VALUES(?,?,?,?)', (correction_id, row['order_id'], json.dumps(breakup), datetime.now().isoformat(timespec='seconds')))
        later = db.execute('SELECT 1 FROM settlements WHERE restaurant_id=? AND week_start>? LIMIT 1', (base['restaurant_id'], base['week_start'])).fetchone()
        if not later:
            db.execute('INSERT INTO ad_debits(restaurant_id,amount) VALUES(?,?) ON CONFLICT(restaurant_id) DO UPDATE SET amount=excluded.amount', (base['restaurant_id'], corrected['carried_debit']))
        db.commit()
        current.update(corrected)
        current['correction_revision'] = latest + 1
        current['correction_reason'] = reason.strip()
        return current
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def settle(restaurant_id, week_start, ad_spend=0):
    start = date.fromisoformat(week_start)
    end = start + timedelta(days=6)
    if start.weekday() != 0:
        raise ValueError('week-start must be a Monday')
    db = connect()
    try:
        rest = db.execute('SELECT * FROM restaurants WHERE restaurant_id=?', (restaurant_id,)).fetchone()
        if not rest:
            raise ValueError('Unknown restaurant')
        exists = db.execute('SELECT * FROM settlements WHERE restaurant_id=? AND week_start=?', (restaurant_id, week_start)).fetchone()
        if exists:
            return _latest_settlement(db, dict(exists))
        rs = db.execute("SELECT * FROM orders WHERE restaurant_id=? AND settlement_id IS NULL AND dispute_status!='OPEN' AND ((dispute_closed_at='' AND substr(order_time,1,10) BETWEEN ? AND ?) OR (dispute_closed_at!='' AND substr(dispute_closed_at,1,10) BETWEEN ? AND ?)) ORDER BY order_time,order_id", (restaurant_id, start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())).fetchall()
        
        opening_gmv = Decimal(rest['opening_fy_gmv']) if rest['opening_fy_gmv'] else Decimal('0.00')
        years = {}
        for r in rs:
            d = date.fromisoformat(r['order_time'][:10])
            years.setdefault(d.year if d.month >= 4 else d.year - 1, None)
        gmv_before = {}
        for fy_year in years:
            fy = date(fy_year, 4, 1)
            year_orders = db.execute("SELECT order_id,order_time,items_gross FROM orders WHERE restaurant_id=? AND order_time>=? AND order_time<? AND outcome NOT IN ('CANCELLED_BY_RESTAURANT','CANCELLED_BY_CUSTOMER') ORDER BY order_time,order_id", (restaurant_id, fy.isoformat(), date(fy_year + 1, 4, 1).isoformat())).fetchall()
            cumulative = opening_gmv
            for y in year_orders:
                new_cum = cumulative + Decimal(y['items_gross'])
                gmv_before[y['order_id']] = (cumulative, new_cum)
                cumulative = new_cum
        totals = {k: Decimal('0.00') for k in ('gross', 'restaurant_discounts', 'platform_discounts', 'packaging', 'delivery_fees', 'platform_fees', 'commission', 'gst_95', 'commission_gst', 'tds', 'refunds', 'platform_refunds', 'penalties', 'reimbursements')}
        ledger = []
        prior_ratings = [Decimal(x[0]) for x in db.execute("SELECT rating FROM orders WHERE restaurant_id=? AND rating!='' AND substr(order_time,1,10) BETWEEN ? AND ?", (restaurant_id, (start - timedelta(days=7)).isoformat(), (start - timedelta(days=1)).isoformat()))]
        penalty = bool(prior_ratings) and sum(prior_ratings, Decimal(0)) / len(prior_ratings) < Decimal('3.5')
        for r in rs:
            b = _breakup_row(r, rest, penalty)
            g = Decimal(r['items_gross'])
            cum_tuple = gmv_before.get(r['order_id'], (Decimal(0), Decimal(0)))
            tds = money(g * Decimal('.01')) if r['outcome'] not in ('CANCELLED_BY_RESTAURANT', 'CANCELLED_BY_CUSTOMER') and cum_tuple[1] > Decimal('500000') else Decimal('0.00')
            for k, v in [('gross', b['gross']), ('restaurant_discounts', b['restaurant_discount']), ('platform_discounts', b['platform_discount']), ('packaging', b['packaging']), ('delivery_fees', b['delivery_fee']), ('platform_fees', b['platform_fee']), ('commission', b['commission']), ('gst_95', b['gst_95']), ('commission_gst', b['commission_gst']), ('tds', tds), ('refunds', b['restaurant_refund'] + b['customer_refund']), ('platform_refunds', b['platform_refund']), ('penalties', b['penalty']), ('reimbursements', b['platform_reimbursement'])]:
                totals[k] += v
            ledger.append((r, b, tds))
        due = totals['gross'] - totals['restaurant_discounts'] - totals['platform_discounts'] + totals['packaging'] - totals['platform_fees'] - totals['commission'] - totals['gst_95'] - totals['commission_gst'] - totals['tds'] - totals['refunds'] - totals['penalties'] + totals['reimbursements']
        debit_row = db.execute('SELECT amount FROM ad_debits WHERE restaurant_id=?', (restaurant_id,)).fetchone()
        outstanding = Decimal(debit_row[0]) if debit_row else Decimal(0)
        requested = min(money(ad_spend), money(rest['weekly_ad_budget'])) + outstanding
        ads = min(requested, max(Decimal(0), due))
        carry = requested - ads
        payout = due - ads
        cur = db.execute('INSERT INTO settlements(restaurant_id,week_start,gross,restaurant_discounts,platform_discounts,packaging,delivery_fees,platform_fees,commission,gst_95,commission_gst,tds,refunds,platform_refunds,ads,penalties,reimbursements,payout,carried_debit,order_ids,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (restaurant_id, week_start, *[str(totals[k]) for k in ('gross', 'restaurant_discounts', 'platform_discounts', 'packaging', 'delivery_fees', 'platform_fees', 'commission', 'gst_95', 'commission_gst', 'tds', 'refunds', 'platform_refunds')], str(ads), str(totals['penalties']), str(totals['reimbursements']), str(payout.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)), str(money(carry)), json.dumps([r['order_id'] for r in rs]), datetime.now().isoformat(timespec='seconds')))
        sid = cur.lastrowid
        for r, b, t in ledger:
            audit_breakup = {k: str(v) for k, v in b.items()} | {'tds': str(t)}
            db.execute('INSERT INTO settlement_audit(settlement_id,order_id,gross,commission,platform_fee,delivery_fee,tds,refund,breakup_json,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)', (sid, r['order_id'], str(b['gross']), str(b['commission']), str(b['platform_fee']), str(b['delivery_fee']), str(t), str(b['restaurant_refund'] + b['customer_refund']), json.dumps(audit_breakup), datetime.now().isoformat(timespec='seconds')))
            db.execute('UPDATE orders SET settlement_id=? WHERE order_id=?', (sid, r['order_id']))
        db.execute('INSERT INTO ad_debits VALUES(?,?) ON CONFLICT(restaurant_id) DO UPDATE SET amount=excluded.amount', (restaurant_id, str(money(carry))))
        db.commit()
        return dict(db.execute('SELECT * FROM settlements WHERE settlement_id=?', (sid,)).fetchone())
    finally:
        db.close()

def report(kind, output, fmt=None):
    db = connect()
    try:
        table = {'orders': ('SELECT * FROM orders ORDER BY order_time,order_id',), 'settlements': ('SELECT * FROM settlements ORDER BY week_start,restaurant_id',), 'audit': ('SELECT * FROM settlement_audit ORDER BY audit_id',)}
        if kind not in table:
            raise ValueError('Report type must be orders, settlements, or audit')
        raw = [dict(x) for x in db.execute(table[kind][0])]
        if kind == 'orders':
            rows = []
            for order in raw:
                rest = db.execute('SELECT * FROM restaurants WHERE restaurant_id=?', (order['restaurant_id'],)).fetchone()
                effective_time = order['dispute_closed_at'] or order['order_time']
                breakup = order_breakup(order, dict(rest), _penalty_for_order(db, order['restaurant_id'], effective_time))
                tds = _tds_for_order(db, order)
                breakup['net_restaurant_amount'] = (breakup['net_restaurant_amount'] - tds).quantize(Decimal('.01'))
                rows.append(order | {f'calc_{k}': str(v) for k, v in breakup.items()} | {'calc_tds': str(tds)})
        elif kind == 'settlements':
            rows = [_latest_settlement(db, row) for row in raw]
        elif kind == 'audit':
            rows = []
            for row in raw:
                row['audit_type'] = 'ORIGINAL'
                row['correction_id'] = ''
                row['reason'] = ''
                rows.append(row)
            for c in db.execute('SELECT c.correction_id,c.settlement_id,c.reason,c.created_at,a.order_id,a.breakup_json,a.recorded_at FROM settlement_corrections c JOIN settlement_correction_audit a ON a.correction_id=c.correction_id ORDER BY c.correction_id,a.order_id'):
                b = json.loads(c['breakup_json'])
                refund_total = Decimal(b.get('restaurant_refund', '0.00')) + Decimal(b.get('customer_refund', '0.00'))
                rows.append({'audit_type': 'CORRECTION', 'correction_id': c['correction_id'], 'settlement_id': c['settlement_id'], 'order_id': c['order_id'], 'reason': c['reason'], 'gross': b.get('gross', ''), 'commission': b.get('commission', ''), 'platform_fee': b.get('platform_fee', ''), 'delivery_fee': b.get('delivery_fee', ''), 'tds': b.get('tds', ''), 'refund': str(refund_total), 'breakup_json': c['breakup_json'], 'recorded_at': c['recorded_at']})
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        fmt = (fmt or p.suffix.lstrip('.')).lower()
        with p.open('w', newline='', encoding='utf-8') as f:
            if fmt == 'json':
                json.dump(rows, f, indent=2)
            elif fmt == 'csv':
                if rows:
                    w = csv.DictWriter(f, fieldnames=rows[0].keys())
                    w.writeheader()
                    w.writerows(rows)
            else:
                raise ValueError('Report format must be csv or json')
        return len(rows)
    finally:
        db.close()

def list_settlements(restaurant_id=None):
    db = connect()
    try:
        if restaurant_id:
            rows = db.execute('SELECT * FROM settlements WHERE restaurant_id=? ORDER BY week_start', (restaurant_id,)).fetchall()
        else:
            rows = db.execute('SELECT * FROM settlements ORDER BY week_start,restaurant_id').fetchall()
        return [_latest_settlement(db, dict(row)) for row in rows]
    finally:
        db.close()

# -------------------------------------------------------------
# COMMAND STREAM ENGINE (Evaluation Pipeline)
# -------------------------------------------------------------

def process_command_stream(commands_path, restaurants_path=None, ad_spend_path=None, disputes_path=None, output_dir=None):
    """
    Executes commands.txt in strict file order according to PS-039 Sample Data Pack.
    Produces order_breakup.csv and weekly_statement.csv.
    """
    cmd_p = Path(commands_path)
    base_dir = cmd_p.parent

    rest_p = Path(restaurants_path) if restaurants_path else (base_dir / "restaurants.csv" if (base_dir / "restaurants.csv").exists() else Path("data/restaurants.csv"))
    ad_p = Path(ad_spend_path) if ad_spend_path else (base_dir / "ad_spend.csv" if (base_dir / "ad_spend.csv").exists() else Path("data/ad_spend.csv"))
    disp_p = Path(disputes_path) if disputes_path else (base_dir / "disputes.csv" if (base_dir / "disputes.csv").exists() else Path("data/disputes.csv"))
    out_dir = Path(output_dir) if output_dir else base_dir

    # 1. Load restaurants
    restaurants = {}
    with rest_p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rid = row["restaurant_id"].strip()
            name = row.get("restaurant_name") or row.get("name", "")
            plan = (row.get("commission_plan") or row.get("plan", "STANDARD")).strip().upper()
            restaurants[rid] = {
                "restaurant_id": rid,
                "restaurant_name": name.strip(),
                "cuisine": row.get("cuisine", "").strip(),
                "commission_plan": plan,
                "onboarding_date": date.fromisoformat(row["onboarding_date"].strip()[:10]),
                "packaging_charge": money(row.get("packaging_charge", 0)),
                "weekly_ad_budget": money(row.get("weekly_ad_budget", 0)),
                "opening_fy_gmv": money(row.get("opening_fy_gmv", 0)),
                "gstin": row.get("gstin", "").strip(),
                "suspended": False,
                "commission_uplift_pp": Decimal("0.0"),
                "debit_carried": Decimal("0.00"),
                "delivered_gmv": Decimal("0.00"),
            }

    # 2. Load ad_spend
    ad_spend_data = {}
    if ad_p.exists():
        with ad_p.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ad_spend_data[(row["restaurant_id"].strip(), row["week_start"].strip())] = money(row["ad_spend"])

    # 3. Load disputes
    disputes = {}
    if disp_p.exists():
        with disp_p.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                disputes[row["order_id"].strip()] = {
                    "dispute_id": row["dispute_id"].strip(),
                    "opened_ts": datetime.fromisoformat(row["opened_ts"].strip()),
                    "closed_ts": datetime.fromisoformat(row["closed_ts"].strip()),
                    "reason": row["reason"].strip(),
                }

    orders = {}
    order_list = []
    statements = {}
    breakup_rows = []
    statement_rows = []
    weekly_ratings = {}

    with cmd_p.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    for line in lines:
        parts = line.split("|")
        cmd = parts[0]

        if cmd == "ORDER":
            oid = parts[1]
            ts = datetime.fromisoformat(parts[2])
            rid = parts[3]
            items_str = parts[4]
            rest_disc = money(parts[5])
            plat_coupon = money(parts[6])
            cofund_disc = money(parts[7])
            pack_charge = money(parts[8])
            dist = parts[9]
            del_fee = money(parts[10])
            pay_mode = parts[11]

            gross = Decimal("0.00")
            items_list = []
            for item_part in items_str.split(","):
                iname, iqty, iprice = item_part.split(":")
                qty = Decimal(iqty)
                unit_price = money(iprice)
                gross += qty * unit_price
                items_list.append({"name": iname, "qty": qty, "unit_price": unit_price})
            gross = money(gross)

            rest = restaurants[rid]
            is_rejected = rest["suspended"]

            ord_obj = {
                "order_id": oid,
                "ts": ts,
                "restaurant_id": rid,
                "items": items_list,
                "gross_item_value": gross,
                "restaurant_discount": rest_disc,
                "platform_coupon": plat_coupon,
                "cofunded_discount": cofund_disc,
                "packaging_charge": pack_charge,
                "distance_km": dist,
                "delivery_fee": del_fee,
                "payment_mode": pay_mode,
                "status": "REJECTED" if is_rejected else "ORDERED",
                "accepted": False,
                "delivered_ts": None,
                "rating": None,
                "refund_restaurant_share": Decimal("0.00"),
                "refund_platform_share": Decimal("0.00"),
                "penalty": Decimal("0.00"),
                "settled": False,
                "settlement_week": None,
                "commission_uplift_pp": rest["commission_uplift_pp"],
            }
            orders[oid] = ord_obj
            order_list.append(ord_obj)

        elif cmd == "ACCEPTED":
            oid = parts[1]
            if oid in orders and orders[oid]["status"] != "REJECTED":
                orders[oid]["accepted"] = True

        elif cmd == "DELIVERED":
            oid = parts[1]
            ts = datetime.fromisoformat(parts[2])
            rating_str = parts[3] if len(parts) > 3 else ""

            if oid in orders:
                ord_obj = orders[oid]
                if ord_obj["status"] == "DELIVERED":
                    continue  # duplicate delivery retry
                ord_obj["status"] = "DELIVERED"
                ord_obj["delivered_ts"] = ts
                if rating_str:
                    ord_obj["rating"] = int(rating_str)
                    deliv_date = ts.date()
                    mon = deliv_date - timedelta(days=deliv_date.weekday())
                    mon_str = mon.isoformat()
                    rid = ord_obj["restaurant_id"]
                    weekly_ratings.setdefault(mon_str, {}).setdefault(rid, []).append(int(rating_str))

                rest = restaurants[ord_obj["restaurant_id"]]
                prior_gmv = rest["opening_fy_gmv"] + rest["delivered_gmv"]
                new_gmv = prior_gmv + ord_obj["gross_item_value"]
                ord_obj["prior_gmv"] = prior_gmv
                ord_obj["new_gmv"] = new_gmv
                rest["delivered_gmv"] += ord_obj["gross_item_value"]

        elif cmd == "CANCEL_CUSTOMER":
            oid = parts[1]
            ts = datetime.fromisoformat(parts[2])
            if oid in orders:
                ord_obj = orders[oid]
                elapsed = (ts - ord_obj["ts"]).total_seconds()
                if elapsed <= 60:
                    ord_obj["status"] = "CANCELLED_BY_CUSTOMER_FREE"
                else:
                    ord_obj["status"] = "CANCELLED_BY_CUSTOMER_CHARGED"

        elif cmd == "CANCEL_RESTAURANT":
            oid = parts[1]
            ts = datetime.fromisoformat(parts[2])
            if oid in orders:
                ord_obj = orders[oid]
                ord_obj["status"] = "CANCELLED_BY_RESTAURANT"
                if ord_obj["accepted"]:
                    ord_obj["penalty"] = Decimal("100.00")
                else:
                    ord_obj["penalty"] = Decimal("0.00")
                pack_allowed = min(ord_obj["packaging_charge"], Decimal("30.00"))
                cust_paid = ord_obj["gross_item_value"] - ord_obj["restaurant_discount"] - ord_obj["platform_coupon"] - ord_obj["cofunded_discount"] + pack_allowed
                ord_obj["refund_restaurant_share"] = cust_paid

        elif cmd == "REFUND":
            oid = parts[1]
            ts = datetime.fromisoformat(parts[2])
            reason = parts[3]
            amt = money(parts[4])

            if reason not in ("MISSING_ITEM", "SPILLED", "LATE_DELIVERY"):
                continue

            if oid in orders:
                ord_obj = orders[oid]
                if reason == "MISSING_ITEM":
                    ord_obj["refund_restaurant_share"] += amt
                elif reason == "SPILLED":
                    plat_share = money(amt / 2)
                    rest_share = amt - plat_share
                    ord_obj["refund_restaurant_share"] += rest_share
                    ord_obj["refund_platform_share"] += plat_share
                elif reason == "LATE_DELIVERY":
                    ord_obj["refund_platform_share"] += amt

        elif cmd == "PAYOUT":
            w_start = parts[1]
            week_monday = date.fromisoformat(w_start)
            week_sunday = week_monday + timedelta(days=6)

            for rid, rest in restaurants.items():
                settled_orders = []
                excluded_dispute_count = 0

                for ord_obj in order_list:
                    if ord_obj["restaurant_id"] != rid:
                        continue
                    if ord_obj["status"] == "REJECTED" or ord_obj["settled"]:
                        continue

                    event_dt = ord_obj["delivered_ts"] or ord_obj["ts"]
                    event_date = event_dt.date()

                    oid = ord_obj["order_id"]
                    disp = disputes.get(oid)

                    if disp:
                        disp_close_date = disp["closed_ts"].date()
                        if week_monday <= event_date <= week_sunday:
                            if disp_close_date > week_sunday:
                                excluded_dispute_count += 1
                                continue
                            else:
                                settled_orders.append(ord_obj)
                                ord_obj["settled"] = True
                                ord_obj["settlement_week"] = w_start
                        elif week_monday <= disp_close_date <= week_sunday:
                            settled_orders.append(ord_obj)
                            ord_obj["settled"] = True
                            ord_obj["settlement_week"] = w_start
                    else:
                        if week_monday <= event_date <= week_sunday:
                            settled_orders.append(ord_obj)
                            ord_obj["settled"] = True
                            ord_obj["settlement_week"] = w_start

                gross_payable = Decimal("0.00")
                for o in settled_orders:
                    b = order_breakup_full(o, rest)
                    gross_payable += b["_net_val"]
                gross_payable = money(gross_payable)

                actual_ad_spend = ad_spend_data.get((rid, w_start), Decimal("0.00"))
                budget = rest["weekly_ad_budget"]
                spend_requested = min(actual_ad_spend, budget)

                debit_bf = rest["debit_carried"]
                available = max(Decimal("0.00"), gross_payable)

                recovered_debit = min(debit_bf, available)
                rem_debit = debit_bf - recovered_debit
                available -= recovered_debit

                deducted_ad = min(spend_requested, available)
                available -= deducted_ad
                unpaid_ad = spend_requested - deducted_ad

                debit_cf = rem_debit + unpaid_ad
                rest["debit_carried"] = debit_cf

                net_payout = gross_payable - recovered_debit - deducted_ad
                if gross_payable <= Decimal("0.00"):
                    net_payout = gross_payable
                    deducted_ad = Decimal("0.00")
                    debit_cf = debit_bf + spend_requested
                    rest["debit_carried"] = debit_cf

                ratings = weekly_ratings.get(w_start, {}).get(rid, [])
                if ratings:
                    avg_r = (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(CENT, rounding=ROUND_HALF_UP)
                    avg_r_str = f"{avg_r:.2f}"
                else:
                    avg_r = None
                    avg_r_str = ""

                if avg_r is not None and avg_r < Decimal("3.50"):
                    next_uplift = Decimal("2.0")
                else:
                    next_uplift = Decimal("0.0")

                if avg_r is not None and avg_r < Decimal("3.00"):
                    suspended_next = True
                    rest["suspended"] = True
                else:
                    suspended_next = False

                rest["commission_uplift_pp"] = next_uplift

                statement = {
                    "restaurant_id": rid,
                    "week_start": w_start,
                    "orders_settled": len(settled_orders),
                    "orders_excluded_dispute": excluded_dispute_count,
                    "gross_payable": f"{gross_payable:.2f}",
                    "ad_spend_deducted": f"{deducted_ad:.2f}",
                    "debit_brought_forward": f"{debit_bf:.2f}",
                    "net_payout": f"{net_payout:.2f}",
                    "debit_carried_forward": f"{debit_cf:.2f}",
                    "avg_rating": avg_r_str,
                    "next_week_commission_uplift_pp": f"{next_uplift:.1f}",
                    "suspended_next_week": str(suspended_next).lower(),
                }
                statements[(rid, w_start)] = statement

        elif cmd == "PRINT_BREAKUP":
            oid = parts[1]
            ord_obj = orders[oid]
            rest = restaurants[ord_obj["restaurant_id"]]
            b = order_breakup_full(ord_obj, rest)
            # Remove private helper
            b_out = {k: v for k, v in b.items() if not k.startswith("_")}
            breakup_rows.append(b_out)

        elif cmd == "PRINT_STATEMENT":
            rid = parts[1]
            w_start = parts[2]
            stmt = statements.get((rid, w_start))
            if stmt:
                statement_rows.append(stmt)

    # Write output files
    out_dir.mkdir(parents=True, exist_ok=True)
    breakup_file = out_dir / "order_breakup.csv"
    statement_file = out_dir / "weekly_statement.csv"

    breakup_cols = [
        "order_id", "restaurant_id", "status", "gross_item_value", "restaurant_discount",
        "platform_coupon", "cofunded_restaurant_share", "cofunded_platform_share",
        "net_item_value", "packaging_allowed", "packaging_disallowed", "commission_rate",
        "commission", "platform_fee", "gst_on_commission", "gst_9_5", "tds_194o",
        "coupon_reimbursement", "refund_restaurant_share", "refund_platform_share",
        "penalty", "restaurant_net", "rule_ids"
    ]

    with breakup_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=breakup_cols)
        writer.writeheader()
        writer.writerows(breakup_rows)

    statement_cols = [
        "restaurant_id", "week_start", "orders_settled", "orders_excluded_dispute",
        "gross_payable", "ad_spend_deducted", "debit_brought_forward", "net_payout",
        "debit_carried_forward", "avg_rating", "next_week_commission_uplift_pp",
        "suspended_next_week"
    ]

    with statement_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=statement_cols)
        writer.writeheader()
        writer.writerows(statement_rows)

    return {
        "order_breakups_count": len(breakup_rows),
        "weekly_statements_count": len(statement_rows),
        "breakup_file": str(breakup_file),
        "statement_file": str(statement_file),
    }
