"""Command line interface for PS-039 Food Delivery Commission and Restaurant Payout Engine."""
import argparse
import json
import sys
from pathlib import Path
from src.engine import (
    import_restaurants,
    import_orders,
    import_disputes,
    import_ad_spend,
    get_breakup,
    settle,
    close_dispute,
    correct_settlement,
    report,
    list_settlements,
    process_command_stream,
)
from database.database import connect

def main():
    # Direct command-file execution support: e.g. python main.py commands.txt or python main.py data/commands.txt
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-") and Path(sys.argv[1]).exists() and Path(sys.argv[1]).suffix.lower() == ".txt":
        res = process_command_stream(sys.argv[1])
        print(json.dumps(res, indent=2))
        return

    p = argparse.ArgumentParser(description="Food delivery commission and restaurant payout engine")
    s = p.add_subparsers(dest="command", required=True)

    # Subcommand: run-commands
    rc = s.add_parser("run-commands", help="Execute command file (commands.txt) and produce order_breakup.csv and weekly_statement.csv")
    rc.add_argument("--commands", "-c", required=True, help="Path to commands.txt")
    rc.add_argument("--restaurants", help="Path to restaurants.csv (defaults to same folder or data/)")
    rc.add_argument("--ad-spend", help="Path to ad_spend.csv (defaults to same folder or data/)")
    rc.add_argument("--disputes", help="Path to disputes.csv (defaults to same folder or data/)")
    rc.add_argument("--output-dir", "-o", default=".", help="Directory to save order_breakup.csv and weekly_statement.csv")

    for name in ("register-restaurants", "process-orders"):
        x = s.add_parser(name)
        x.add_argument("--file", required=True)
    x = s.add_parser("order-breakup")
    x.add_argument("--order-id", required=True)
    x = s.add_parser("weekly-payout")
    x.add_argument("--restaurant-id", required=True)
    x.add_argument("--week-start", required=True)
    x.add_argument("--ad-spend", default="0")
    x = s.add_parser("close-dispute")
    x.add_argument("--order-id", required=True)
    x.add_argument("--closed-at", required=True)
    x.add_argument("--resolution", default="RESOLVED")
    x = s.add_parser("process-disputes")
    x.add_argument("--file", required=True)
    x = s.add_parser("correct-settlement")
    x.add_argument("--settlement-id", required=True, type=int)
    x.add_argument("--reason", required=True)
    x = s.add_parser("report")
    x.add_argument("--type", choices=["orders", "settlements", "audit"], required=True)
    x.add_argument("--output", required=True)
    x.add_argument("--format", choices=["csv", "json"])
    x = s.add_parser("list-settlements")
    x.add_argument("--restaurant-id")
    x = s.add_parser("init-db")

    a = p.parse_args()
    try:
        if a.command == "run-commands":
            result = process_command_stream(
                commands_path=a.commands,
                restaurants_path=a.restaurants,
                ad_spend_path=a.ad_spend,
                disputes_path=a.disputes,
                output_dir=a.output_dir,
            )
        elif a.command == "register-restaurants":
            result = {"registered": import_restaurants(a.file)}
        elif a.command == "process-orders":
            result = {"imported": import_orders(a.file)}
        elif a.command == "order-breakup":
            result = get_breakup(a.order_id)
        elif a.command == "weekly-payout":
            result = settle(a.restaurant_id, a.week_start, a.ad_spend)
        elif a.command == "close-dispute":
            close_dispute(a.order_id, a.closed_at, a.resolution)
            result = {"closed": a.order_id}
        elif a.command == "process-disputes":
            result = {"processed_events": import_disputes(a.file)}
        elif a.command == "correct-settlement":
            result = correct_settlement(a.settlement_id, a.reason)
        elif a.command == "report":
            result = {"rows": report(a.type, a.output, a.format), "file": a.output}
        elif a.command == "list-settlements":
            result = list_settlements(a.restaurant_id)
        else:
            connect().close()
            result = {"database": "ready"}
        print(json.dumps(result, indent=2, default=str))
    except (ValueError, KeyError, TypeError) as e:
        p.error(str(e))

if __name__ == "__main__":
    main()
