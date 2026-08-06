"""
Vergelijkt de twee squeeze-detectiemethodes voor de breakout-strategie:
- 'percentile': huidige bandbreedte t.o.v. eigen historie
- 'keltner': Bollinger Bands binnen Keltner Channel (TTM Squeeze-stijl)

Alle overige strategie-onderdelen (EMA-richting, breakout-trigger,
volumebevestiging, exit via SL/TP) blijven identiek, zodat dit een
eerlijke vergelijking is van alleen de squeeze-detectie zelf.

Gebruik:
    python breakout_squeeze_method_compare.py
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
    get_asset_class,
)
from utils.backtest import compute_stats
from utils.breakout_strategy import prepare_breakout_data, simulate_breakout_trades


RR_FOCUS = 2.0
SQUEEZE_METHODS = ["percentile", "keltner"]


print("===================================")
print("   SQUEEZE-METHODE VERGELIJKING")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR_FOCUS}")
print("===================================")
print()


trades_by_method = {m: [] for m in SQUEEZE_METHODS}
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

        results = []
        for method in SQUEEZE_METHODS:

            trades = simulate_breakout_trades(
                df_prepared, pair,
                atr_multiplier=ATR_MULTIPLIER,
                rr=RR_FOCUS,
                squeeze_method=method,
                divergence_lookback=DIVERGENCE_LOOKBACK,
                divergence_order=DIVERGENCE_ORDER,
            )

            for t in trades:
                t["asset_class"] = asset_class

            trades_by_method[method].extend(trades)
            results.append(f"{method}: {len(trades)}t")

        print(" | ".join(results))

    except Exception as e:
        print(f"FOUT: {e}")
        continue


print()
print(f"Overgeslagen: {len(skipped)}")


# ============================================
# Totaaloverzicht: beide methodes, alle trades vs. volume-subset
# ============================================

print()
print("===================================")
print("SQUEEZE-METHODE VERGELIJKING - ALLE TRADES")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR_FOCUS}: {round(1/(1+RR_FOCUS)*100, 1)}%")
print()

compare_all = pd.DataFrame({
    f"Percentile-methode": compute_stats(trades_by_method["percentile"], RR_FOCUS),
    f"Keltner-methode (TTM)": compute_stats(trades_by_method["keltner"], RR_FOCUS),
})
print(compare_all.to_string())


print()
print("===================================")
print("SQUEEZE-METHODE VERGELIJKING - ALLEEN VOLUME-BEVESTIGDE TRADES")
print("(dit was de sterkste subset bij de percentile-methode)")
print("===================================")
print()

vol_percentile = [t for t in trades_by_method["percentile"] if t.get("volume_used")]
vol_keltner = [t for t in trades_by_method["keltner"] if t.get("volume_used")]

compare_vol = pd.DataFrame({
    f"Percentile-methode": compute_stats(vol_percentile, RR_FOCUS),
    f"Keltner-methode (TTM)": compute_stats(vol_keltner, RR_FOCUS),
})
print(compare_vol.to_string())


# CSV's opslaan
for method in SQUEEZE_METHODS:
    df_out = pd.DataFrame(trades_by_method[method])
    if not df_out.empty:
        df_out.to_csv(f"squeeze_compare_{method}_trades.csv", index=False)

print()
print("CSV's opgeslagen: squeeze_compare_percentile_trades.csv, squeeze_compare_keltner_trades.csv")