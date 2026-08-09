"""
Out-of-sample validatie voor de Pullback-strategie (SHORT + RSI-
divergentie, de sterkste bevinding uit eerdere tests) - los te draaien.

Zelfde methodiek als out_of_sample_breakout.py: simuleert over de
volledige 5 jaar data, en splitst de resulterende trades ACHTERAF in
twee niet-overlappende periodes om te checken of de bevinding in BEIDE
periodes apart standhoudt.

Gebruik:
    python out_of_sample_pullback.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RSI_WINDOW,
    EMA_SPAN,
    DIVERGENCE_LOOKBACK,
    DIVERGENCE_ORDER,
    clean_pair_name,
    get_asset_class,
)
from utils.backtest import prepare_backtest_data, compute_stats
from utils.pullback_strategy import simulate_pullback_trades


RR_FOCUS = 1.5  # beste RR uit de eerdere pullback-tests


print("===================================")
print("   OUT-OF-SAMPLE VALIDATIE - PULLBACK-STRATEGIE")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR_FOCUS}")
print("   Focus: SHORT + RSI-divergentie (sterkste eerdere bevinding)")
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

        if df.empty or len(df) < 100:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        trades = simulate_pullback_trades(
            df_prepared, pair,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR_FOCUS,
            divergence_lookback=DIVERGENCE_LOOKBACK,
            divergence_order=DIVERGENCE_ORDER,
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
# Splitsen in twee niet-overlappende periodes op basis van entry-datum
# ============================================

closed_trades = [t for t in all_trades if t["outcome"] in ("WIN", "LOSS")]

if not closed_trades:
    print("Geen afgeronde trades gevonden, kan niet splitsen.")
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

    # Focus op de sterkste eerdere subset: SHORT + divergentie
    period_1_short_div = [t for t in period_1 if t.get("rsi_divergence") and t["direction"] == "SHORT"]
    period_2_short_div = [t for t in period_2 if t.get("rsi_divergence") and t["direction"] == "SHORT"]

    print()
    print("===================================")
    print("ALLE TRADES: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print(f"Break-even winrate nodig bij RR 1:{RR_FOCUS}: {round(1/(1+RR_FOCUS)*100, 1)}%")
    print()

    compare_all = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1, RR_FOCUS),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2, RR_FOCUS),
    })
    print(compare_all.to_string())

    print()
    print("===================================")
    print("SHORT + DIVERGENTIE-SUBSET: PERIODE 1 vs. PERIODE 2")
    print("(dit is de sterkste bevinding uit de eerdere test - hier draait het om)")
    print("===================================")
    print()

    compare_short_div = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1_short_div, RR_FOCUS),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2_short_div, RR_FOCUS),
    })
    print(compare_short_div.to_string())

    # CSV's opslaan voor eigen verder onderzoek
    pd.DataFrame(period_1_short_div).to_csv("oos_pullback_period1_short_div.csv", index=False)
    pd.DataFrame(period_2_short_div).to_csv("oos_pullback_period2_short_div.csv", index=False)
    print()
    print("CSV's opgeslagen: oos_pullback_period1_short_div.csv, oos_pullback_period2_short_div.csv")