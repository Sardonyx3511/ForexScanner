"""
Gecombineerde propfirm-simulatie: breakout + pullback + Donchian + TDI
aanhoudende bias SAMEN, elk met zijn eigen, al gevalideerde
configuratie (inclusief crypto-scope):

- Breakout: LONG+SHORT, volume waar beschikbaar, RR 1:2, MET crypto
- Pullback: alleen SHORT + divergentie, RR 1:1,5, MET crypto
- Donchian: alleen LONG, RR 1:2, MET crypto
- TDI aanhoudende bias: alleen LONG, RR 1:2, ZONDER crypto

Gebruik:
    python propfirm_simulation_all4.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RR,
    PULLBACK_RR,
    RSI_WINDOW,
    EMA_SPAN,
    DIVERGENCE_LOOKBACK,
    DIVERGENCE_ORDER,
    get_asset_class,
)
from utils.breakout_strategy import prepare_breakout_data, simulate_breakout_trades
from utils.pullback_strategy import simulate_pullback_trades
from utils.donchian_strategy import simulate_donchian_trades
from utils.donchian_indicator import add_donchian_channels
from utils.tdi_shark_fin_strategy import (
    add_tdi_indicators,
    add_long_term_emas,
    simulate_shark_fin_persistent_bias_trades,
)


ACCOUNT_START = 5000
RISK_PER_TRADE = 50
DAILY_DD_LIMIT = 200
MAX_DD_FLOOR = 4500
PROFIT_TARGET = 5500

CONCURRENT_SCENARIOS = [2, 3, 4, 5, 999]


print("===================================")
print("   DATA VERZAMELEN - ALLE 4 STRATEGIEËN SAMEN")
print(f"   {len(ALL_PAIRS)} markten")
print("===================================")
print()


all_trades = []
skipped = []

for pair in ALL_PAIRS:

    asset_class = get_asset_class(pair)
    print(f"Verwerken: {pair} [{asset_class}] ...", end=" ")

    try:
        df = yf.download(
            pair,
            period="5y",
            interval="1d",
            multi_level_index=False,
            progress=False
        )

        if df.empty or len(df) < 220:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_donchian_channels(df_prepared, window=20)
        df_prepared = add_tdi_indicators(df_prepared, rsi_period=13, band_period=34, band_dev=2)
        df_prepared = add_long_term_emas(df_prepared, fast_span=50, slow_span=200)

        bo_trades = simulate_breakout_trades(df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR)
        for t in bo_trades:
            t["strategy"] = "breakout"
            t["asset_class"] = asset_class

        pb_trades_all = simulate_pullback_trades(
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=PULLBACK_RR,
            divergence_lookback=DIVERGENCE_LOOKBACK, divergence_order=DIVERGENCE_ORDER
        )
        pb_trades = [t for t in pb_trades_all if t["direction"] == "SHORT" and t.get("rsi_divergence")]
        for t in pb_trades:
            t["strategy"] = "pullback"
            t["asset_class"] = asset_class

        dc_trades_all = simulate_donchian_trades(df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR)
        dc_trades = [t for t in dc_trades_all if t["direction"] == "LONG"]
        for t in dc_trades:
            t["strategy"] = "donchian"
            t["asset_class"] = asset_class

        tdi_trades = []
        if asset_class != "crypto":
            tdi_trades_all = simulate_shark_fin_persistent_bias_trades(
                df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR
            )
            tdi_trades = [t for t in tdi_trades_all if t["direction"] == "LONG"]
            for t in tdi_trades:
                t["strategy"] = "tdi"
                t["asset_class"] = asset_class

        all_trades.extend(bo_trades)
        all_trades.extend(pb_trades)
        all_trades.extend(dc_trades)
        all_trades.extend(tdi_trades)

        print(f"BO:{len(bo_trades)} PB:{len(pb_trades)} DC:{len(dc_trades)} TDI:{len(tdi_trades)}")

    except Exception as e:
        print(f"FOUT: {e}")
        continue


print()
print(f"Overgeslagen: {len(skipped)}")

closed_trades = [t for t in all_trades if t["outcome"] in ("WIN", "LOSS")]
print(f"Totaal aantal afgeronde trades (alle 4 strategieën): {len(closed_trades)}")

per_strategy_count = {}
for t in closed_trades:
    per_strategy_count[t["strategy"]] = per_strategy_count.get(t["strategy"], 0) + 1
print(f"Verdeling: {per_strategy_count}")

closed_trades.sort(key=lambda t: t["entry_date"])


def get_rr_for_trade(t):
    if t["strategy"] == "pullback":
        return PULLBACK_RR
    return RR


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

        rr = get_rr_for_trade(t)
        r_multiple = rr if t["outcome"] == "WIN" else -1
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


account_start_date = closed_trades[0]["entry_date"]

print()
print("===================================")
print("GECOMBINEERD (breakout + pullback + Donchian + TDI)")
print(f"Start: $5.000 | Risico: 1% (${RISK_PER_TRADE}) | Target: $5.500 | Max DD: $4.500")
print("===================================")
print()

for max_c in CONCURRENT_SCENARIOS:

    label = "Onbeperkt" if max_c == 999 else f"Max {max_c} tegelijk"
    result = simulate_portfolio(closed_trades, max_c)

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
print("GEMIDDELD AANTAL TRADES PER WEEK (bij max 3 en max 4)")
print("===================================")

total_weeks = (closed_trades[-1]["entry_date"] - closed_trades[0]["entry_date"]).days / 7

for max_c in [3, 4]:
    result = simulate_portfolio(closed_trades, max_c)
    trades_per_week = result["trades_taken"] / total_weeks
    print(f"Max {max_c} tegelijk: {round(trades_per_week, 2)} trades/week "
          f"(over {round(total_weeks,1)} weken, {result['trades_taken']} trades genomen)")


pd.DataFrame(closed_trades).to_csv("propfirm_simulation_all4_trades.csv", index=False)
print()
print("CSV opgeslagen: propfirm_simulation_all4_trades.csv")