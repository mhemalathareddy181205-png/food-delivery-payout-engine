import csv,json
import sqlite3
from pathlib import Path
import pytest
import database.database as database
from src.engine import import_restaurants,import_orders,import_disputes,close_dispute,correct_settlement,settle,report

def setup_db(tmp_path,monkeypatch):
 monkeypatch.setattr(database,'DB_PATH',tmp_path/'db.sqlite3')
 root=Path(__file__).resolve().parents[1]
 monkeypatch.setattr(database,'ROOT',root)
 f=tmp_path/'restaurants.csv'
 f.write_text('restaurant_id,name,plan,onboarding_date,rating,packaging_charge,weekly_ad_budget\nR,Kitchen,STANDARD,2020-01-01,4.5,0,500\n',encoding='utf-8')
 import_restaurants(f)
 return f

def order(order_id,when,gross='100',dispute='CLOSED',rating=''):
 return {'order_id':order_id,'restaurant_id':'R','order_time':when,'items_gross':gross,'outcome':'DELIVERED','dispute_status':dispute,'rating':rating}

def test_dispute_closing_moves_order_to_close_week_and_duplicate_settlement_is_safe(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 f.write_text(json.dumps([order('O1','2026-10-25T23:59:00',dispute='OPEN')]),encoding='utf-8')
 assert import_orders(f)==1; assert import_orders(f)==0
 close_dispute('O1','2026-10-27T08:00:00')
 assert json.loads(settle('R','2026-10-19')['order_ids'])==[]
 statement=settle('R','2026-10-26')
 assert json.loads(statement['order_ids'])==['O1']
 assert settle('R','2026-10-26')['settlement_id']==statement['settlement_id']

def test_tds_crossing_order_and_following_order(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 f.write_text(json.dumps([order('O1','2026-04-06T10:00:00','500000'),order('O2','2026-04-07T10:00:00','100'),order('O3','2026-04-08T10:00:00','100')]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-04-06')
 assert s['tds']=='1.00'
 out=tmp_path/'calculated.json'; report('orders',out)
 by_id={x['order_id']:x for x in json.loads(out.read_text(encoding='utf-8'))}
 assert by_id['O2']['calc_tds']=='0.00' and by_id['O3']['calc_tds']=='1.00'

def test_tds_gmv_resets_at_april_financial_year_boundary(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'fy-boundary.json'
 f.write_text(json.dumps([order('MARCH','2026-03-31T23:00:00','500100'),order('APRIL','2026-04-01T01:00:00','100')]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-03-30')
 assert s['tds']=='0.00'

def test_order_report_includes_computed_breakup(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 f.write_text(json.dumps([order('O1','2026-04-06T10:00:00','100')]),encoding='utf-8')
 import_orders(f); out=tmp_path/'orders.json'
 assert report('orders',out)==1
 result=json.loads(out.read_text(encoding='utf-8'))
 assert result[0]['calc_commission']=='18.00' and result[0]['calc_gst_95']=='5.00'

def test_rating_penalty_and_ad_debit_carry_forward(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 f.write_text(json.dumps([order('RATE','2026-04-06T10:00:00','100','CLOSED','3.4'),order('PAY','2026-04-13T10:00:00','500')]),encoding='utf-8')
 import_orders(f)
 first=settle('R','2026-04-06','500')
 assert first['commission']=='18.00' # exactly Rs 100 uses the percentage rate
 assert first['payout']=='0.00' and first['carried_debit']=='426.24' # ads exceed available payout
 second=settle('R','2026-04-13','500')
 assert second['commission']=='100.00' # 20% of Rs 500 after low prior-week rating
 assert second['ads']!='0.00' and second['carried_debit']!='0.00'

def test_rating_average_exactly_3_5_has_no_penalty(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'ratings.json'
 f.write_text(json.dumps([order('RATE','2026-04-06T10:00:00','100','CLOSED','3.5'),order('PAY','2026-04-13T10:00:00','500')]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-04-13')
 assert s['commission']=='90.00'

def test_platform_minimum_fee_is_deducted_delivery_fee_is_reported_only(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 order_row=order('SMALL','2026-04-06T10:00:00','99') | {'platform_fee':'3','delivery_fee':'12'}
 larger=order('LARGE','2026-04-06T11:00:00','200') | {'platform_discount':'20','platform_fee':'5','delivery_fee':'20'}
 f.write_text(json.dumps([order_row,larger]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-04-06')
 assert s['commission']=='36.00' and s['platform_fees']=='15.00'
 assert s['delivery_fees']=='32.00' and s['payout']=='226.57'
 assert s['platform_discounts']=='20.00' and s['reimbursements']=='20.00'

def test_low_rating_suspends_future_orders(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'
 f.write_text(json.dumps([order('RATE','2026-04-06T10:00:00','100','CLOSED','2.9')]),encoding='utf-8')
 import_orders(f)
 later=tmp_path/'later.json'; later.write_text(json.dumps([order('LATER','2026-04-07T10:00:00')]),encoding='utf-8')
 with pytest.raises(ValueError,match='suspended'):
  import_orders(later)

def test_single_low_rating_does_not_suspend_when_weekly_average_is_three(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'weekly-ratings.json'
 f.write_text(json.dumps([order('RATING-LOW','2026-04-06T10:00:00','100','CLOSED','2.0'),order('RATING-HIGH','2026-04-06T12:00:00','100','CLOSED','4.0')]),encoding='utf-8')
 import_orders(f)
 later=tmp_path/'later.json'; later.write_text(json.dumps([order('LATER','2026-04-07T10:00:00')]),encoding='utf-8')
 assert import_orders(later)==1

def test_accepted_restaurant_cancellation_penalty_is_not_lost_when_payout_is_negative(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'cancel.json'
 f.write_text(json.dumps([order('CANCEL','2026-04-06T10:00:00','50') | {'outcome':'CANCELLED_BY_RESTAURANT','accepted':1}]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-04-06')
 assert s['penalties']=='100.00' and s['payout']=='-100.00'

def test_itemized_csv_lines_and_aggregate_csv_compatibility(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch)
 lines=tmp_path/'items.csv'
 lines.write_text('order_id,restaurant_id,order_time,outcome,item_name,item_quantity,item_unit_price\nI1,R,2026-04-06T10:00:00,DELIVERED,Bowl,2,10.00\nI1,R,2026-04-06T10:00:00,DELIVERED,Drink,1,5.00\n',encoding='utf-8')
 assert import_orders(lines)==1
 import sqlite3
 c=sqlite3.connect(database.DB_PATH)
 assert c.execute('SELECT COUNT(*) FROM order_items WHERE order_id=?',('I1',)).fetchone()[0]==2
 assert c.execute('SELECT items_gross FROM orders WHERE order_id=?',('I1',)).fetchone()[0]=='25.00'; c.close()
 aggregate=tmp_path/'aggregate.csv'
 aggregate.write_text('order_id,restaurant_id,order_time,items_gross,outcome\nA1,R,2026-04-06T11:00:00,125.00,DELIVERED\n',encoding='utf-8')
 assert import_orders(aggregate)==1

def test_dispute_csv_refund_creates_append_only_settlement_correction(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); orders=tmp_path/'orders.json'
 orders.write_text(json.dumps([order('D1','2026-10-25T23:59:00','200')]),encoding='utf-8')
 import_orders(orders); original=settle('R','2026-10-19'); original_payout=original['payout']
 opened=tmp_path/'open.csv'
 opened.write_text('dispute_id,order_id,event,event_at\nDSP1,D1,OPEN,2026-10-27T08:00:00\n',encoding='utf-8')
 assert import_disputes(opened)==1
 closed=tmp_path/'close.csv'
 closed.write_text('dispute_id,order_id,event,event_at,resolution,refund_amount,refund_reason\nDSP1,D1,CLOSE,2026-10-28T08:00:00,REFUND_APPROVED,20.00,MISSING_ITEM\n',encoding='utf-8')
 assert import_disputes(closed)==1 and import_disputes(closed)==0
 revised=correct_settlement(original['settlement_id'],'Approved missing item refund')
 assert revised['payout']=='127.52' and revised['correction_revision']==1
 assert settle('R','2026-10-19')['payout']=='127.52'
 c=sqlite3.connect(database.DB_PATH)
 assert c.execute('SELECT payout FROM settlements WHERE settlement_id=?',(original['settlement_id'],)).fetchone()[0]==original_payout
 assert c.execute('SELECT COUNT(*) FROM settlement_audit WHERE settlement_id=?',(original['settlement_id'],)).fetchone()[0]==1
 assert c.execute('SELECT COUNT(*) FROM settlement_correction_audit').fetchone()[0]==1; c.close()
 report_file=tmp_path/'revised.csv'; report('settlements',report_file)
 assert '127.52' in report_file.read_text(encoding='utf-8')
 audit_file=tmp_path/'audit.json'; report('audit',audit_file,'json')
 assert len(json.loads(audit_file.read_text(encoding='utf-8')))==2
