"""
Onderzoekt strengere filters voor Donchian LONG-only, gericht op
'minder maar betere signalen'. Test meerdere drempels voor
uitbraaksterkte, gecombineerd met de EMA-uitlijning.

Gebruik:
    python donchian_stricter_filter_research.py
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
from utils.backtest import compute_stats
from utils.donchian_strategy import prepare_donchian_data, simulate_donchian_trades


RR_FOCUS = 2.0
STRENGTH_THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.5, 2.0]


print("===================================")
print("   DONCHIAN - ONDERZOEK STRENGERE FILTERS")
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
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR_FOCUS
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

longs = [t for t in all_trades if t["direction"] == "LONG"]
print(f"Totaal LONG-trades: {len(longs)}")


print()
print("===================================")
print("LONG + EMA-UITLIJNING + UITBRAAKSTERKTE-DREMPELS")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR_FOCUS}: {round(1/(1+RR_FOCUS)*100, 1)}%")
print()

long_ema = [t for t in longs if t.get("ema_aligned")]

results = {}
for threshold in STRENGTH_THRESHOLDS:
    subset = [t for t in long_ema if t.get("breakout_strength_atr", 0) >= threshold]
    label = f">= {threshold} ATR" if threshold > 0 else "Geen drempel (LONG+EMA)"
    results[label] = compute_stats(subset, RR_FOCUS)

compare_df = pd.DataFrame(results)
print(compare_df.to_string())


print()
print("===================================")
print("ZONDER CRYPTO - PER DREMPEL (robuustheidscheck)")
print("===================================")
print()

results_no_crypto = {}
for threshold in STRENGTH_THRESHOLDS:
    subset = [t for t in long_ema if t.get("breakout_strength_atr", 0) >= threshold and t["asset_class"] != "crypto"]
    label = f">= {threshold} ATR" if threshold > 0 else "Geen drempel"
    results_no_crypto[label] = compute_stats(subset, RR_FOCUS)

compare_no_crypto_df = pd.DataFrame(results_no_crypto)
print(compare_no_crypto_df.to_string())


print()
print("===================================")
print("PER ASSETKLASSE BIJ DREMPEL >= 1.0 ATR (kandidaat 'strenger')")
print("===================================")

candidate = [t for t in long_ema if t.get("breakout_strength_atr", 0) >= 1.0]

per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in candidate if t["asset_class"] == cls]
    stats = compute_stats(class_trades, RR_FOCUS)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


pd.DataFrame(longs).to_csv("donchian_stricter_filter_trades.csv", index=False)
print()
print("CSV opgeslagen: donchian_stricter_filter_trades.csv")