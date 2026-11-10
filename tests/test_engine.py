import csv,json
import sqlite3
from pathlib import Path
import pytest
import database.database as database
from src.engine import import_restaurants,import_orders,import_disputes,close_dispute,correct_settlement,settle,report,get_breakup

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
 assert s['tds']=='2.00'
 out=tmp_path/'calculated.json'; report('orders',out)
 by_id={x['order_id']:x for x in json.loads(out.read_text(encoding='utf-8'))}
 assert by_id['O1']['calc_tds']=='0.00' and by_id['O2']['calc_tds']=='1.00' and by_id['O3']['calc_tds']=='1.00'

def test_tds_gmv_resets_at_april_financial_year_boundary(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'fy-boundary.json'
 f.write_text(json.dumps([order('MARCH','2026-03-31T23:00:00','500100'),order('APRIL','2026-04-01T01:00:00','100')]),encoding='utf-8')
 import_orders(f); s=settle('R','2026-03-30')
 assert s['tds']=='5001.00'

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

def test_registration_validation_and_duplicate_orders_are_atomic(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch)
 bad_rest=tmp_path/'bad-rest.csv'; bad_rest.write_text('restaurant_id,name,plan,onboarding_date,rating\nX,Bad,STANDARD,2026-01-01,NaN\n',encoding='utf-8')
 with pytest.raises((ValueError,ArithmeticError)): import_restaurants(bad_rest)
 duplicate=tmp_path/'dupes.json'; duplicate.write_text(json.dumps([order('DUP','2026-04-06T10:00:00'),order('DUP','2026-04-06T11:00:00')]),encoding='utf-8')
 with pytest.raises(ValueError,match='Duplicate order ID'): import_orders(duplicate)
 c=sqlite3.connect(database.DB_PATH)
 assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0
 assert c.execute('SELECT COUNT(*) FROM processing_history').fetchone()[0]==0
 c.close()

def test_registration_persists_profile_and_suspends_low_profile_rating(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch)
 profile=tmp_path/'profile.csv'
 profile.write_text('restaurant_id,name,plan,onboarding_date,rating,packaging_charge,weekly_ad_budget\nLOW,Low Kitchen,PLUS,2025-01-01,2.9,12.50,300\n',encoding='utf-8')
 assert import_restaurants(profile)==1
 c=sqlite3.connect(database.DB_PATH)
 row=c.execute('SELECT name,plan,onboarding_date,rating,packaging_charge,weekly_ad_budget,status FROM restaurants WHERE restaurant_id=?',('LOW',)).fetchone()
 c.close()
 assert row==('Low Kitchen','PLUS','2025-01-01','2.9','12.50','300.00','SUSPENDED')

@pytest.mark.parametrize('bad_csv,expected',[
 ('order_id,restaurant_id,order_time\nO,R,2026-04-06T10:00:00\n','require order_id'),
 ('order_id,restaurant_id,order_time,items_gross\nO,UNKNOWN,2026-04-06T10:00:00,100\n','Unknown restaurant'),
 ('order_id,restaurant_id,order_time,items_gross,cancel_seconds\nO,R,2026-04-06T10:00:00,100,-1\n','non-negative'),
 ('order_id,restaurant_id,order_time,items_gross,accepted\nO,R,2026-04-06T10:00:00,100,2\n','accepted must'),
])
def test_order_import_rejects_missing_references_and_invalid_flags(tmp_path,monkeypatch,bad_csv,expected):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'bad.csv'; f.write_text(bad_csv,encoding='utf-8')
 with pytest.raises(ValueError,match=expected): import_orders(f)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0; c.close()

def test_invalid_settlement_week_and_same_week_payout_are_safe(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00','500')]),encoding='utf-8'); import_orders(f)
 with pytest.raises(ValueError,match='Monday'): settle('R','2026-04-07')
 first=settle('R','2026-04-06','10'); again=settle('R','2026-04-06','200')
 assert again['settlement_id']==first['settlement_id'] and again['ads']==first['ads']
 assert len(json.loads(first['order_ids']))==1

def test_ad_budget_caps_requested_spend_and_zero_ad_is_allowed(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); c=sqlite3.connect(database.DB_PATH); c.execute("UPDATE restaurants SET weekly_ad_budget='25.00'"); c.commit(); c.close()
 f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00','1000')]),encoding='utf-8'); import_orders(f)
 statement=settle('R','2026-04-06','100')
 assert statement['ads']=='25.00' and statement['carried_debit']=='0.00'

def test_dispute_events_reject_invalid_transitions_and_roll_back_batch(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00')]),encoding='utf-8'); import_orders(f)
 events=tmp_path/'bad-events.csv'; events.write_text('dispute_id,order_id,event,event_at\nD1,O,OPEN,2026-04-06T09:00:00\nD1,O,CLOSE,2026-04-06T12:00:00\n',encoding='utf-8')
 with pytest.raises(ValueError,match='cannot precede order time'): import_disputes(events)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM disputes').fetchone()[0]==0; c.close()
 good=tmp_path/'open.csv'; good.write_text('dispute_id,order_id,event,event_at\nD1,O,OPEN,2026-04-06T11:00:00\n',encoding='utf-8'); import_disputes(good)
 duplicate=tmp_path/'duplicate-open.csv'; duplicate.write_text('dispute_id,order_id,event,event_at\nD1,O,OPEN,2026-04-06T12:00:00\n',encoding='utf-8')
 with pytest.raises(ValueError,match='Duplicate dispute ID'): import_disputes(duplicate)

def test_dispute_refund_requires_supported_reason_and_same_funding_reason(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00')]),encoding='utf-8'); import_orders(f)
 def event_file(dispute,reason):
  opened=tmp_path/f'{dispute}-open.csv'; opened.write_text(f'dispute_id,order_id,event,event_at\n{dispute},O,OPEN,2026-04-06T11:00:00\n',encoding='utf-8'); import_disputes(opened)
  closed=tmp_path/f'{dispute}-close.csv'; closed.write_text(f'dispute_id,order_id,event,event_at,refund_amount,refund_reason\n{dispute},O,CLOSE,2026-04-06T12:00:00,1.00,{reason}\n',encoding='utf-8'); return closed
 with pytest.raises(ValueError,match='supported refund_reason'): import_disputes(event_file('D1','UNKNOWN'))
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT dispute_status FROM orders WHERE order_id="O"').fetchone()[0]=='OPEN'; c.close()

def test_dispute_close_without_refund_label_does_not_change_order_refund(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00')]),encoding='utf-8'); import_orders(f)
 events=tmp_path/'events.csv'; events.write_text('dispute_id,order_id,event,event_at,resolution\nD1,O,OPEN,2026-04-06T11:00:00,\nD1,O,CLOSE,2026-04-07T11:00:00,REFUND_APPROVED\n',encoding='utf-8')
 assert import_disputes(events)==2
 c=sqlite3.connect(database.DB_PATH); result=c.execute('SELECT outcome,refund_amount,refund_reason FROM orders WHERE order_id="O"').fetchone(); c.close()
 assert result==('DELIVERED','0.00','')

def test_dispute_close_before_open_and_unknown_order_are_rejected_atomically(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00')]),encoding='utf-8'); import_orders(f)
 close_first=tmp_path/'close-first.csv'; close_first.write_text('dispute_id,order_id,event,event_at\nD,O,CLOSE,2026-04-06T12:00:00\nD,O,OPEN,2026-04-06T11:00:00\n',encoding='utf-8')
 with pytest.raises(ValueError,match='No open dispute'): import_disputes(close_first)
 unknown=tmp_path/'unknown.csv'; unknown.write_text('dispute_id,order_id,event,event_at\nD,NOPE,OPEN,2026-04-06T11:00:00\n',encoding='utf-8')
 with pytest.raises(ValueError,match='Unknown order'): import_disputes(unknown)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM disputes').fetchone()[0]==0; c.close()

def test_itemized_csv_total_mismatch_and_empty_file_fail_without_partial_orders(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch)
 lines=tmp_path/'mismatch.csv'; lines.write_text('order_id,restaurant_id,order_time,items_gross,item_name,item_quantity,item_unit_price\nI1,R,2026-04-06T10:00:00,25,Bowl,2,10\n',encoding='utf-8')
 with pytest.raises(ValueError,match='sum to items_gross'): import_orders(lines)
 empty=tmp_path/'empty.csv'; empty.write_text('',encoding='utf-8')
 with pytest.raises(ValueError,match='empty'): import_orders(empty)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0; c.close()

def test_malformed_files_invalid_dates_and_invalid_order_rating_fail_cleanly(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch)
 malformed=tmp_path/'bad.json'; malformed.write_text('{not json',encoding='utf-8')
 with pytest.raises(ValueError,match='Malformed input'): import_orders(malformed)
 malformed_csv=tmp_path/'bad.csv'; malformed_csv.write_text('order_id,restaurant_id,order_time,items_gross\n"O,R,2026-04-06T10:00:00,100\n',encoding='utf-8')
 with pytest.raises(ValueError,match='Malformed input'): import_orders(malformed_csv)
 extra_column=tmp_path/'extra.csv'; extra_column.write_text('order_id,restaurant_id,order_time,items_gross\nO,R,2026-04-06T10:00:00,100,unexpected\n',encoding='utf-8')
 with pytest.raises(ValueError,match='more fields than the header'): import_orders(extra_column)
 invalid_date=tmp_path/'date.json'; invalid_date.write_text(json.dumps([order('DATE','not-a-date')]),encoding='utf-8')
 with pytest.raises(ValueError): import_orders(invalid_date)
 invalid_rating=tmp_path/'rating.json'; invalid_rating.write_text(json.dumps([order('RATING','2026-04-06T10:00:00') | {'rating':'5.1'}]),encoding='utf-8')
 with pytest.raises(ValueError,match='between zero and five'): import_orders(invalid_rating)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0; c.close()

def test_orders_already_imported_remain_settleable_after_rating_suspension(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'ratings.json'; f.write_text(json.dumps([order('LOW','2026-04-06T10:00:00','100','CLOSED','2.9')]),encoding='utf-8'); import_orders(f)
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT status FROM restaurants WHERE restaurant_id="R"').fetchone()[0]=='SUSPENDED'; c.close()
 result=settle('R','2026-04-06')
 assert json.loads(result['order_ids'])==['LOW']

def test_same_order_cannot_accumulate_disputes_with_different_refund_funders(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00')]),encoding='utf-8'); import_orders(f)
 def event(dispute, action, reason=''):
  path=tmp_path/f'{dispute}-{action}.csv'
  if action=='OPEN': path.write_text(f'dispute_id,order_id,event,event_at\n{dispute},O,OPEN,2026-04-06T11:00:00\n',encoding='utf-8')
  else: path.write_text(f'dispute_id,order_id,event,event_at,refund_amount,refund_reason\n{dispute},O,CLOSE,2026-04-06T12:00:00,1.00,{reason}\n',encoding='utf-8')
  return import_disputes(path)
 event('D1','OPEN'); event('D1','CLOSE','MISSING_ITEM'); event('D2','OPEN')
 with pytest.raises(ValueError,match='different funding reasons'): event('D2','CLOSE','SPILLED')

def test_correction_repeat_is_idempotent_and_appends_only_when_changed(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00','200')]),encoding='utf-8'); import_orders(f)
 original=settle('R','2026-04-06'); first=correct_settlement(original['settlement_id'],'Review complete'); second=correct_settlement(original['settlement_id'],'Review complete')
 assert first['correction_revision']==second['correction_revision']==1
 c=sqlite3.connect(database.DB_PATH); assert c.execute('SELECT COUNT(*) FROM settlement_corrections').fetchone()[0]==1; c.close()

def test_json_and_csv_reports_include_calculated_orders_and_audit(tmp_path,monkeypatch):
 setup_db(tmp_path,monkeypatch); f=tmp_path/'orders.json'; f.write_text(json.dumps([order('O','2026-04-06T10:00:00','200')]),encoding='utf-8'); import_orders(f); settle('R','2026-04-06')
 out=tmp_path/'orders.csv'; assert report('orders',out,'csv')==1
 with out.open(encoding='utf-8',newline='') as stream: rows=list(csv.DictReader(stream))
 assert rows[0]['calc_commission']=='36.00' and rows[0]['calc_commission_gst']=='6.48'
 audit=tmp_path/'audit.csv'; assert report('audit',audit,'csv')==1
 assert 'ORIGINAL' in audit.read_text(encoding='utf-8')

def test_cli_workflow_uses_only_test_database_and_safe_files(tmp_path,monkeypatch,capsys):
 import sys,main
 monkeypatch.setattr(database,'DB_PATH',tmp_path/'cli.sqlite3')
 root=Path(__file__).resolve().parents[1]; monkeypatch.setattr(database,'ROOT',root)
 restaurants=tmp_path/'restaurants.csv'; restaurants.write_text('restaurant_id,name,plan,onboarding_date,rating\nR,Test Kitchen,STANDARD,2020-01-01,4.5\n',encoding='utf-8')
 orders=tmp_path/'orders.csv'; orders.write_text('order_id,restaurant_id,order_time,items_gross\nCLI1,R,2026-04-06T10:00:00,200\nCLI2,R,2026-04-06T11:00:00,100\n',encoding='utf-8')
 events=tmp_path/'disputes.csv'; events.write_text('dispute_id,order_id,event,event_at,refund_amount,refund_reason\nDSP1,CLI1,OPEN,2026-04-07T09:00:00,,\nDSP1,CLI1,CLOSE,2026-04-08T09:00:00,10.00,MISSING_ITEM\nDSP2,CLI2,OPEN,2026-04-07T10:00:00,,\n',encoding='utf-8')
 for args in (['init-db'],['register-restaurants','--file',str(restaurants)],['process-orders','--file',str(orders)],['order-breakup','--order-id','CLI1'],['weekly-payout','--restaurant-id','R','--week-start','2026-04-06'],['process-disputes','--file',str(events)],['correct-settlement','--settlement-id','1','--reason','Approved dispute refund'],['close-dispute','--order-id','CLI2','--closed-at','2026-04-09T09:00:00'],['list-settlements','--restaurant-id','R'],['report','--type','orders','--output',str(tmp_path/'orders.csv'),'--format','csv'],['report','--type','settlements','--output',str(tmp_path/'report.json')],['report','--type','audit','--output',str(tmp_path/'audit.json')]):
  monkeypatch.setattr(sys,'argv',['main.py',*args]); main.main()
  assert capsys.readouterr().out.strip()
 assert json.loads((tmp_path/'report.json').read_text(encoding='utf-8'))[0]['payout']=='211.28'
 audit=json.loads((tmp_path/'audit.json').read_text(encoding='utf-8'))
 assert [row['audit_type'] for row in audit]==['ORIGINAL','ORIGINAL','CORRECTION','CORRECTION']
 c=sqlite3.connect(database.DB_PATH)
 assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
 assert c.execute('SELECT COUNT(*) FROM settlement_corrections').fetchone()[0]==1
 assert c.execute('SELECT COUNT(*) FROM settlement_correction_audit').fetchone()[0]==2
 c.close()
