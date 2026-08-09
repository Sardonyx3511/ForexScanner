"""
Out-of-sample validatie voor de Donchian-breakout-strategie (LONG-only,
de sterkste bevinding uit de filter-vergelijking) - los te draaien.

Zelfde methodiek als bij breakout/pullback/mean-reversion: simuleert
over de volledige 5 jaar data, splitst de resulterende trades ACHTERAF
in twee niet-overlappende periodes.

Gebruik:
    python out_of_sample_donchian.py
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
print("   OUT-OF-SAMPLE VALIDATIE - DONCHIAN (LONG-only)")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR_FOCUS}")
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
    print("DONCHIAN LONG-ONLY: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print(f"Break-even winrate nodig bij RR 1:{RR_FOCUS}: {round(1/(1+RR_FOCUS)*100, 1)}%")
    print()

    compare = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1, RR_FOCUS),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2, RR_FOCUS),
    })
    print(compare.to_string())

    # Ook zonder crypto, per periode - extra robuustheidscheck
    period_1_no_crypto = [t for t in period_1 if t["asset_class"] != "crypto"]
    period_2_no_crypto = [t for t in period_2 if t["asset_class"] != "crypto"]

    print()
    print("===================================")
    print("ZONDER CRYPTO: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print()

    compare_no_crypto = pd.DataFrame({
        f"Periode 1 zonder crypto": compute_stats(period_1_no_crypto, RR_FOCUS),
        f"Periode 2 zonder crypto": compute_stats(period_2_no_crypto, RR_FOCUS),
    })
    print(compare_no_crypto.to_string())

    pd.DataFrame(period_1).to_csv("oos_donchian_period1_long.csv", index=False)
    pd.DataFrame(period_2).to_csv("oos_donchian_period2_long.csv", index=False)
    print()
    print("CSV's opgeslagen: oos_donchian_period1_long.csv, oos_donchian_period2_long.csv")