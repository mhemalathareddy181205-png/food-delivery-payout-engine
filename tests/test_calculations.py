from datetime import date
from decimal import Decimal
import pytest
from src.calculations import money,commission_rate,order_breakup

REST={'plan':'STANDARD','onboarding_date':'2026-01-01','packaging_charge':'35'}
def row(**x):
 d={'items_gross':'200','restaurant_discount':'0','platform_discount':'0','cofund_discount':'0','order_time':'2026-04-01T12:00:00','outcome':'DELIVERED','refund_amount':'0'}; d.update(x); return d
def test_rounding_and_reject_invalid():
 assert money('1.005')==Decimal('1.01')
 with pytest.raises(ValueError): money('-1')
 with pytest.raises(ValueError): money('NaN')
def test_onboarding_day_60_inclusive():
 assert commission_rate('PLUS',date(2026,1,1),date(2026,3,2))==Decimal('.12')
 assert commission_rate('STANDARD',date(2021,1,1),date(2021,3,2))==Decimal('.12')
 assert commission_rate('PLUS',date(2021,1,1),date(2021,3,3))==Decimal('.22')
def test_fee_boundary_and_packaging_cap():
 b=order_breakup(row(items_gross='100'),{'plan':'STANDARD','onboarding_date':'2020-01-01','packaging_charge':'35'})
 assert b['commission']==Decimal('18.00') and b['packaging']==Decimal('30.00') and b['packaging_excess']==Decimal('5.00')
 b=order_breakup(row(items_gross='99'),{'plan':'STANDARD','onboarding_date':'2020-01-01','packaging_charge':'0'})
 assert b['commission']==Decimal('0.00') and b['platform_fee']==Decimal('10.00')
def test_discount_funding_and_cofund():
 b=order_breakup(row(items_gross='200',restaurant_discount='20',platform_discount='10',cofund_discount='21'),REST)
 assert b['restaurant_discount']==Decimal('30.50') and b['platform_discount']==Decimal('20.50') and b['commission_base']==Decimal('169.50')
 assert b['platform_reimbursement']==Decimal('20.50')
def test_odd_paisa_cofund_and_packaging_cap_together():
 b=order_breakup(row(items_gross='200',cofund_discount='0.01'),REST)
 assert b['restaurant_discount']==Decimal('0.00') and b['platform_discount']==Decimal('0.01')
 assert b['packaging']==Decimal('30.00') and b['packaging_excess']==Decimal('5.00')
def test_customer_cancel_exactly_60_is_free_and_later_is_paid():
 b=order_breakup(row(outcome='CANCELLED_BY_CUSTOMER',cancel_seconds='60'),REST)
 assert b['commission']==0 and b['customer_refund']==Decimal('230.00') and b['net_restaurant_amount']==Decimal('0.00')
 b=order_breakup(row(outcome='CANCELLED_BY_CUSTOMER',cancel_seconds='61'),REST)
 assert b['customer_refund']==0 and b['commission']==Decimal('36.00')
 b=order_breakup(row(items_gross='200',restaurant_discount='10',platform_discount='20',packaging='30',outcome='CANCELLED_BY_CUSTOMER',cancel_seconds='60'),REST)
 assert b['customer_refund']==Decimal('200.00') and b['net_restaurant_amount']==Decimal('0.00')
def test_restaurant_cancel_and_refund_funding():
 b=order_breakup(row(outcome='CANCELLED_BY_RESTAURANT',accepted='1'),REST)
 assert b['penalty']==Decimal('100.00') and b['customer_refund']==Decimal('230.00') and b['commission']==0 and b['net_restaurant_amount']==Decimal('-100.00')
 assert order_breakup(row(outcome='CANCELLED_BY_RESTAURANT',accepted='0'),REST)['penalty']==0
 for reason,restaurant,platform in [('MISSING_ITEM','10','0'),('SPILLED','5','5'),('LATE_DELIVERY','0','10')]:
  b=order_breakup(row(outcome='REFUND_PARTIAL',refund_reason=reason,refund_amount='10'),REST)
  assert b['restaurant_refund']==Decimal(restaurant) and b['platform_refund']==Decimal(platform)

def test_spilled_refund_odd_paisa_is_assigned_to_platform():
 b=order_breakup(row(outcome='REFUND_PARTIAL',refund_reason='SPILLED',refund_amount='10.01'),REST)
 assert b['restaurant_refund']==Decimal('5.00')
 assert b['platform_refund']==Decimal('5.01')
 one_paisa=order_breakup(row(outcome='REFUND_PARTIAL',refund_reason='SPILLED',refund_amount='0.01'),REST)
 assert one_paisa['restaurant_refund']==Decimal('0.00')
 assert one_paisa['platform_refund']==Decimal('0.01')

def test_commission_rates_for_both_plans_after_introductory_period():
 d=date(2026,4,1)
 assert commission_rate('STANDARD',date(2020,1,1),d)==Decimal('.18')
 assert commission_rate('PLUS',date(2020,1,1),d)==Decimal('.22')

def test_commission_gst_is_eighteen_percent_and_zero_on_flat_fee():
 regular=order_breakup(row(items_gross='100'),{'plan':'STANDARD','onboarding_date':'2020-01-01','packaging_charge':'0'})
 small=order_breakup(row(items_gross='99'),{'plan':'STANDARD','onboarding_date':'2020-01-01','packaging_charge':'0'})
 assert regular['commission_gst']==Decimal('3.24')
 assert small['commission_gst']==Decimal('0.00')

@pytest.mark.parametrize('changes',[
 {'restaurant_discount':'201'}, {'refund_reason':'UNKNOWN','outcome':'REFUND_PARTIAL'},
 {'items_gross':'-1'}, {'items_gross':'NaN'}, {'outcome':'UNKNOWN'},
])
def test_order_calculation_rejects_invalid_financial_inputs_and_outcomes(changes):
 with pytest.raises((ValueError,ArithmeticError)):
  order_breakup(row(**changes),REST)
def test_rating_uplift_adds_two_points():
 assert order_breakup(row(),REST,True)['commission_rate']==Decimal('.20')
