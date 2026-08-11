"""
Leest de al opgeslagen propfirm_simulation_trades.csv opnieuw in (geen
nieuwe download nodig) en berekent de VERSTREKEN TIJD tussen account-
start en het bereiken van target/max drawdown - dat is het zinvolle
getal, in plaats van de historische kalenderdatums uit de vorige run.

Gebruik (nadat propfirm_simulation.py al eerder is gedraaid):
    python propfirm_analysis.py
"""

import pandas as pd

from config.settings import RR, PULLBACK_RR


ACCOUNT_START = 5000
RISK_PER_TRADE = 50
DAILY_DD_LIMIT = 200
MAX_DD_FLOOR = 4500
PROFIT_TARGET = 5500

CONCURRENT_SCENARIOS = [2, 3, 4, 999]


df = pd.read_csv("propfirm_simulation_trades.csv", parse_dates=["entry_date", "exit_date"])
trades = df.to_dict("records")
trades.sort(key=lambda t: t["entry_date"])

account_start_date = trades[0]["entry_date"]
print(f"Account-startdatum (eerste trade in de dataset): {account_start_date.date()}")
print(f"Laatste trade in de dataset: {trades[-1]['entry_date'].date()}")
print()


def simulate_portfolio(trades, max_concurrent):

    balance = ACCOUNT_START
    open_until = []
    daily_pnl = {}

    target_reached_date = None
    target_reached_trades = None
    dd_breached_date = None
    dd_breached_trades = None
    daily_breach_count = 0
    daily_breach_dates = []

    trades_taken = 0
    trades_skipped_limit = 0

    for t in trades:

        entry_date = t["entry_date"]
        open_until = [d for d in open_until if d > entry_date]
        open_count = len(open_until)

        if open_count >= max_concurrent:
            trades_skipped_limit += 1
            continue

        trades_taken += 1
        open_until.append(t["exit_date"])

        if t["strategy"] == "pullback":
            r_multiple = PULLBACK_RR if t["outcome"] == "WIN" else -1
        else:
            r_multiple = RR if t["outcome"] == "WIN" else -1

        pnl = r_multiple * RISK_PER_TRADE
        balance += pnl

        exit_day = t["exit_date"]
        daily_pnl[exit_day] = daily_pnl.get(exit_day, 0) + pnl

        if daily_pnl[exit_day] <= -DAILY_DD_LIMIT and exit_day not in daily_breach_dates:
            daily_breach_count += 1
            daily_breach_dates.append(exit_day)

        if balance >= PROFIT_TARGET and target_reached_date is None:
            target_reached_date = exit_day
            target_reached_trades = trades_taken

        if balance <= MAX_DD_FLOOR:
            dd_breached_date = exit_day
            dd_breached_trades = trades_taken
            break

    return {
        "balance": round(balance, 2),
        "trades_taken": trades_taken,
        "trades_skipped": trades_skipped_limit,
        "target_date": target_reached_date,
        "target_trades": target_reached_trades,
        "dd_date": dd_breached_date,
        "dd_trades": dd_breached_trades,
        "daily_breaches": daily_breach_count,
    }


print("===================================")
print("VERSTREKEN TIJD TOT TARGET / MAX DRAWDOWN")
print("(vanaf de eerste trade in de gesimuleerde periode)")
print("===================================")
print()

for max_c in CONCURRENT_SCENARIOS:
    label = "Onbeperkt" if max_c == 999 else f"Max {max_c} tegelijk"
    result = simulate_portfolio(trades, max_c)

    print(f"--- {label} ---")

    if result["target_date"] is not None:
        weeks_to_target = (result["target_date"] - account_start_date).days / 7
        print(f"  Target bereikt na {result['target_trades']} trades, "
              f"{round(weeks_to_target, 1)} weken ({round(weeks_to_target/4.33,1)} maanden) na accountstart")
    else:
        print("  Target NIET bereikt binnen de gesimuleerde periode")

    if result["dd_date"] is not None:
        weeks_to_dd = (result["dd_date"] - account_start_date).days / 7
        print(f"  Max drawdown geraakt na {result['dd_trades']} trades, "
              f"{round(weeks_to_dd, 1)} weken ({round(weeks_to_dd/4.33,1)} maanden) na accountstart")
    else:
        print("  Max drawdown NIET geraakt binnen de gesimuleerde periode")

    print(f"  Eindsaldo (aan het einde van de 5-jaar dataset, of bij DD-breach): ${result['balance']}")
    print(f"  Trades genomen: {result['trades_taken']} | overgeslagen (limiet): {result['trades_skipped']}")
    print(f"  Dagen met daily-limiet-breach: {result['daily_breaches']}")
    print()