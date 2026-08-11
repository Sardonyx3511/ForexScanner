"""
Isoleert de Donchian LONG-only resultaten per assetklasse (RR 1:2) -
specifiek om te checken of forex een zwakke plek is, zoals bij de
ongefilterde LONG+SHORT-baseline het geval leek.

Gebruik:
    python donchian_long_per_assetclass.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RSI_WINDOW,
    EMA_SPAN,
    get_asset_class,
)
from utils.backtest import compute_stats
from utils.donchian_strategy import prepare_donchian_data, simulate_donchian_trades


RR_FOCUS = 2.0


print("===================================")
print("   DONCHIAN LONG-ONLY PER ASSETKLASSE (RR 1:2)")
print(f"   {len(ALL_PAIRS)} markten")
print("===================================")
print()


all_trades = []
skipped = []

for pair in ALL_PAIRS:

    asset_class = get_asset_class(pair)
    print(f"Backtesten: {pair} [{asset_class}] ...", end=" ")

    try:
        df = yf.download(
            pair,
            period="5y",
            interval="1d",
            multi_level_index=False,
            progress=False
        )

        if df.empty or len(df) < 150:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_donchian_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        trades = simulate_donchian_trades(
            df_prepared, pair,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR_FOCUS,
        )

        for t in trades:
            t["asset_class"] = asset_class

        all_trades.extend(trades)
        print(f"{len(trades)} trades")

    except Exception as e:
        print(f"FOUT: {e}")
        continue


print()
print(f"Overgeslagen: {len(skipped)}")


# ============================================
# ALLEEN LONG, per assetklasse
# ============================================

long_trades = [t for t in all_trades if t["direction"] == "LONG"]

print()
print("===================================")
print("LONG-ONLY PER ASSETKLASSE")
print("===================================")
print("Break-even winrate nodig bij RR 1:2: 33.3%")
print()

per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in long_trades if t["asset_class"] == cls]
    stats = compute_stats(class_trades, RR_FOCUS)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


# ============================================
# Forex specifiek: nog wat extra detail
# ============================================

print()
print("===================================")
print("FOREX LONG-ONLY - DETAIL")
print("===================================")

forex_long = [t for t in long_trades if t["asset_class"] == "forex"]
forex_stats = compute_stats(forex_long, RR_FOCUS)
for key, value in forex_stats.items():
    print(f"{key}: {value}")

# Aantal trades per week, alleen forex
if forex_long:
    entry_dates = [t["entry_date"] for t in forex_long if t["outcome"] in ("WIN", "LOSS")]
    if entry_dates:
        span_weeks = (max(entry_dates) - min(entry_dates)).days / 7
        trades_per_week = len(entry_dates) / span_weeks if span_weeks > 0 else 0
        print(f"\nForex LONG-only trades per week (over alle forex-paren samen): {round(trades_per_week, 2)}")

trades_df = pd.DataFrame(long_trades)
if not trades_df.empty:
    trades_df.to_csv("donchian_long_per_assetclass_trades.csv", index=False)
print()
print("CSV opgeslagen: donchian_long_per_assetclass_trades.csv")