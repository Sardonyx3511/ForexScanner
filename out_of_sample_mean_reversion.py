"""
Out-of-sample validatie voor de Mean Reversion-strategie (LONG-only,
de sterke richting uit de eerdere test) - los te draaien.

Zelfde methodiek als bij breakout en pullback: simuleert over de
volledige 5 jaar data, splitst de resulterende trades ACHTERAF in twee
niet-overlappende periodes.

Gebruik:
    python out_of_sample_mean_reversion.py
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
from utils.breakout_strategy import prepare_breakout_data
from utils.mean_reversion_strategy import simulate_mean_reversion_trades, compute_variable_rr_stats


print("===================================")
print("   OUT-OF-SAMPLE VALIDATIE - MEAN REVERSION (LONG-only)")
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

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        trades = simulate_mean_reversion_trades(
            df_prepared, pair,
            atr_multiplier=ATR_MULTIPLIER,
        )

        for t in trades:
            t["asset_class"] = asset_class

        all_trades.extend(trades)
        n_closed = sum(1 for t in trades if t["outcome"] in ("WIN", "LOSS"))
        print(f"{n_closed} trades")

    except Exception as e:
        print(f"FOUT: {e}")
        continue


print()
print(f"Overgeslagen: {len(skipped)}")
print(f"Totaal aantal trades verzameld: {len(all_trades)}")


# ============================================
# Alleen LONG, dan splitsen in twee niet-overlappende periodes
# ============================================

long_trades = [t for t in all_trades if t["direction"] == "LONG"]
closed_trades = [t for t in long_trades if t["outcome"] in ("WIN", "LOSS")]

if not closed_trades:
    print("Geen afgeronde LONG-trades gevonden, kan niet splitsen.")
else:
    entry_dates = [t["entry_date"] for t in closed_trades]
    min_date = min(entry_dates)
    max_date = max(entry_dates)
    midpoint = min_date + (max_date - min_date) / 2

    print()
    print(f"Periode: {min_date.date()} t/m {max_date.date()}")
    print(f"Splitspunt (midden): {midpoint.date()}")

    period_1 = [t for t in closed_trades if t["entry_date"] < midpoint]
    period_2 = [t for t in closed_trades if t["entry_date"] >= midpoint]

    print()
    print("===================================")
    print("MEAN REVERSION LONG-ONLY: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print()

    compare = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_variable_rr_stats(period_1),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_variable_rr_stats(period_2),
    })
    print(compare.to_string())

    pd.DataFrame(period_1).to_csv("oos_mean_reversion_period1_long.csv", index=False)
    pd.DataFrame(period_2).to_csv("oos_mean_reversion_period2_long.csv", index=False)
    print()
    print("CSV's opgeslagen: oos_mean_reversion_period1_long.csv, oos_mean_reversion_period2_long.csv")