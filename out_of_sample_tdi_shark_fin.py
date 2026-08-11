"""
Out-of-sample validatie voor TDI Shark Fin: LONG + TSL-bevestigd +
RSI-dal <= 30 (de sterkste, bevestigde combinatie - EMA-eis bewust
weggelaten, bleek geen toegevoegde waarde te hebben).

Zelfde methodiek als bij breakout/pullback/Donchian: simuleert over de
volledige 5 jaar data, splitst de resulterende trades ACHTERAF in twee
niet-overlappende periodes.

Gebruik:
    python out_of_sample_tdi_shark_fin.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RR,
    RSI_WINDOW,
    EMA_SPAN,
    get_asset_class,
)
from utils.backtest import prepare_backtest_data, compute_stats
from utils.tdi_shark_fin_strategy import (
    add_tdi_indicators,
    add_long_term_emas,
    simulate_shark_fin_trades,
)


RSI_THRESHOLD = 30


print("===================================")
print("   OUT-OF-SAMPLE VALIDATIE - TDI SHARK FIN")
print(f"   LONG + TSL-bevestigd + RSI-dal <= {RSI_THRESHOLD}")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR}")
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

        if df.empty or len(df) < 220:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_tdi_indicators(df_prepared, rsi_period=13, band_period=34, band_dev=2)
        df_prepared = add_long_term_emas(df_prepared, fast_span=50, slow_span=200)

        trades = simulate_shark_fin_trades(df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR)

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


filtered_trades = [
    t for t in all_trades
    if t["direction"] == "LONG"
    and t.get("tsl_confirmed")
    and t.get("trigger_rsi_level", 100) <= RSI_THRESHOLD
]

closed_trades = [t for t in filtered_trades if t["outcome"] in ("WIN", "LOSS")]

if not closed_trades:
    print("Geen afgeronde trades gevonden in deze combinatie, kan niet splitsen.")
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
    print("TDI SHARK FIN LONG+TSL+RSI<=30: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print(f"Break-even winrate nodig bij RR 1:{RR}: {round(1/(1+RR)*100, 1)}%")
    print()

    compare = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1, RR),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2, RR),
    })
    print(compare.to_string())

    print()
    print("===================================")
    print("ZONDER CRYPTO: PERIODE 1 vs. PERIODE 2")
    print("===================================")

    period_1_no_crypto = [t for t in period_1 if t["asset_class"] != "crypto"]
    period_2_no_crypto = [t for t in period_2 if t["asset_class"] != "crypto"]

    compare_no_crypto = pd.DataFrame({
        "Periode 1 zonder crypto": compute_stats(period_1_no_crypto, RR),
        "Periode 2 zonder crypto": compute_stats(period_2_no_crypto, RR),
    })
    print(compare_no_crypto.to_string())

    pd.DataFrame(period_1).to_csv("oos_tdi_shark_fin_period1.csv", index=False)
    pd.DataFrame(period_2).to_csv("oos_tdi_shark_fin_period2.csv", index=False)
    print()
    print("CSV's opgeslagen: oos_tdi_shark_fin_period1.csv, oos_tdi_shark_fin_period2.csv")