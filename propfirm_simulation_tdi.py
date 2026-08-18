"""
Propfirm-simulatie specifiek voor de TDI aanhoudende-bias-strategie
(V1: LONG-only, zonder crypto) - met concurrent-positielimiet.

Leest de al opgeslagen tdi_persistent_bias_trades.csv opnieuw in (geen
nieuwe download nodig) en filtert naar de V1-configuratie.

Gebruik (nadat tdi_persistent_bias_backtest.py al eerder is gedraaid):
    python propfirm_simulation_tdi.py
"""

import pandas as pd

from config.settings import RR


ACCOUNT_START = 5000
RISK_PER_TRADE = 50          # 1%
DAILY_DD_LIMIT = 200         # 4%
MAX_DD_FLOOR = 4500          # max drawdown $500
PROFIT_TARGET = 5500         # +$500

CONCURRENT_SCENARIOS = [2, 3, 4, 5, 999]  # 999 = ongelimiteerd (ter vergelijking)


df = pd.read_csv("tdi_persistent_bias_trades.csv", parse_dates=["entry_date", "exit_date"])
df = df[df["outcome"].isin(["WIN", "LOSS"])].copy()

df = df[(df["direction"] == "LONG") & (df["asset_class"] != "crypto")].copy()

trades = df.to_dict("records")
trades.sort(key=lambda t: t["entry_date"])

print(f"V1-trades beschikbaar (LONG, zonder crypto): {len(trades)}")
print(f"Periode: {trades[0]['entry_date'].date()} t/m {trades[-1]['entry_date'].date()}")
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


account_start_date = trades[0]["entry_date"]

print("===================================")
print("TDI AANHOUDENDE BIAS (V1) - PROPFIRM-SIMULATIE")
print(f"Start: $5.000 | Risico: 1% (${RISK_PER_TRADE}) | Target: $5.500 | Max DD: $4.500")
print("===================================")
print()

for max_c in CONCURRENT_SCENARIOS:

    label = "Onbeperkt" if max_c == 999 else f"Max {max_c} tegelijk"
    result = simulate_portfolio(trades, max_c)

    print(f"--- {label} ---")

    if result["target_date"] is not None:
        weeks_to_target = (result["target_date"] - account_start_date).days / 7
        print(f"  Target bereikt na {result['target_trades']} trades, "
              f"{round(weeks_to_target, 1)} weken ({round(weeks_to_target/4.33,1)} maanden)")
    else:
        print("  Target NIET bereikt binnen de beschikbare data")

    if result["dd_date"] is not None:
        weeks_to_dd = (result["dd_date"] - account_start_date).days / 7
        print(f"  ⚠️ Max drawdown geraakt na {result['dd_trades']} trades, "
              f"{round(weeks_to_dd, 1)} weken")
    else:
        print("  Max drawdown NIET geraakt (veilig gebleven)")

    print(f"  Eindsaldo: ${result['balance']} | Trades genomen: {result['trades_taken']} "
          f"| Overgeslagen (limiet): {result['trades_skipped']}")
    print(f"  Dagen met daily-limiet-breach: {result['daily_breaches']}")
    print()


print("===================================")
print("GEMIDDELD AANTAL TRADES PER WEEK (bij een gekozen limiet)")
print("===================================")

total_weeks = (trades[-1]["entry_date"] - trades[0]["entry_date"]).days / 7

for max_c in [3, 4]:
    result = simulate_portfolio(trades, max_c)
    trades_per_week = result["trades_taken"] / total_weeks
    print(f"Max {max_c} tegelijk: {round(trades_per_week, 2)} trades/week "
          f"(over {round(total_weeks,1)} weken totaal, {result['trades_taken']} trades genomen)")