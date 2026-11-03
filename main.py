"""Command line interface for PS-039."""
import argparse,json
from src.engine import import_restaurants,import_orders,import_disputes,get_breakup,settle,close_dispute,correct_settlement,report,list_settlements
from database.database import connect

def main():
 p=argparse.ArgumentParser(description='Food delivery commission and restaurant payout engine'); s=p.add_subparsers(dest='command',required=True)
 for name in ('register-restaurants','process-orders'):
  x=s.add_parser(name); x.add_argument('--file',required=True)
 x=s.add_parser('order-breakup'); x.add_argument('--order-id',required=True)
 x=s.add_parser('weekly-payout'); x.add_argument('--restaurant-id',required=True); x.add_argument('--week-start',required=True); x.add_argument('--ad-spend',default='0')
 x=s.add_parser('close-dispute'); x.add_argument('--order-id',required=True); x.add_argument('--closed-at',required=True); x.add_argument('--resolution',default='RESOLVED')
 x=s.add_parser('process-disputes'); x.add_argument('--file',required=True)
 x=s.add_parser('correct-settlement'); x.add_argument('--settlement-id',required=True,type=int); x.add_argument('--reason',required=True)
 x=s.add_parser('report'); x.add_argument('--type',choices=['orders','settlements','audit'],required=True); x.add_argument('--output',required=True); x.add_argument('--format',choices=['csv','json'])
 x=s.add_parser('list-settlements'); x.add_argument('--restaurant-id')
 x=s.add_parser('init-db')
 a=p.parse_args()
 try:
  if a.command=='register-restaurants': result={'registered':import_restaurants(a.file)}
  elif a.command=='process-orders': result={'imported':import_orders(a.file)}
  elif a.command=='order-breakup': result=get_breakup(a.order_id)
  elif a.command=='weekly-payout': result=settle(a.restaurant_id,a.week_start,a.ad_spend)
  elif a.command=='close-dispute': close_dispute(a.order_id,a.closed_at,a.resolution); result={'closed':a.order_id}
  elif a.command=='process-disputes': result={'processed_events':import_disputes(a.file)}
  elif a.command=='correct-settlement': result=correct_settlement(a.settlement_id,a.reason)
  elif a.command=='report': result={'rows':report(a.type,a.output,a.format),'file':a.output}
  elif a.command=='list-settlements':
   result=list_settlements(a.restaurant_id)
  else: connect().close(); result={'database':'ready'}
  print(json.dumps(result,indent=2,default=str))
 except (ValueError,KeyError,TypeError) as e: p.error(str(e))
if __name__=='__main__': main()
