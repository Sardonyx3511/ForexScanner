"""
Multi-asset backtest voor TDI Shark Fin, met vergelijking van de twee
extra bevestigingen die je zelf observeerde: TSL vs. RSI Price Line
momentum, en EMA50/EMA200-confluence.

Gebruik:
    python tdi_shark_fin_backtest.py
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


print("===================================")
print("   TDI SHARK FIN - MULTI-ASSET BACKTEST")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR}")
print("===================================")
print()


all_trades = []
skipped = []
failed = []

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
            print("overgeslagen (te weinig data)")
            skipped.append(pair)
            continue

        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_tdi_indicators(df_prepared, rsi_period=13, band_period=34, band_dev=2)
        df_prepared = add_long_term_emas(df_prepared, fast_span=50, slow_span=200)

        trades = simulate_shark_fin_trades(df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR)

        for t in trades:
            t["asset_class"] = asset_class

        all_trades.extend(trades)

        n_closed = sum(1 for t in trades if t["outcome"] in ("WIN", "LOSS"))
        print(f"{n_closed} trades")

    except Exception as e:
        print(f"FOUT: {e}")
        failed.append(pair)
        continue


print()
print(f"Overgeslagen: {len(skipped)}")
print(f"Gefaald: {len(failed)} -> {failed}")


print()
print("===================================")
print("BASELINE (geen extra filters)")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR}: {round(1/(1+RR)*100, 1)}%")
print()

baseline_stats = compute_stats(all_trades, RR)
for key, value in baseline_stats.items():
    print(f"{key}: {value}")


print()
print("===================================")
print("LOSSE FILTERS (elk apart, t.o.v. baseline)")
print("===================================")
print()

tsl_only = [t for t in all_trades if t.get("tsl_confirmed")]
ema_only = [t for t in all_trades if t.get("ema_confluence")]
ema_trend_only = [t for t in all_trades if t.get("ema_trend_pullback")]
both = [t for t in all_trades if t.get("tsl_confirmed") and t.get("ema_confluence")]
tsl_and_trend = [t for t in all_trades if t.get("tsl_confirmed") and t.get("ema_trend_pullback")]

compare_filters = pd.DataFrame({
    "Baseline": compute_stats(all_trades, RR),
    "TSL-bevestigd": compute_stats(tsl_only, RR),
    "EMA-confluence (oud)": compute_stats(ema_only, RR),
    "EMA-trend-pullback (nieuw)": compute_stats(ema_trend_only, RR),
    "TSL + EMA-confluence (oud)": compute_stats(both, RR),
    "TSL + EMA-trend-pullback (nieuw)": compute_stats(tsl_and_trend, RR),
})
print(compare_filters.to_string())


print()
print("===================================")
print("PER RICHTING - MET/ZONDER TSL-BEVESTIGING")
print("(de observatie was specifiek voor SHORT bij de channel high)")
print("===================================")
print()

short_trades = [t for t in all_trades if t["direction"] == "SHORT"]
short_tsl = [t for t in short_trades if t.get("tsl_confirmed")]
short_no_tsl = [t for t in short_trades if not t.get("tsl_confirmed")]

long_trades = [t for t in all_trades if t["direction"] == "LONG"]
long_tsl = [t for t in long_trades if t.get("tsl_confirmed")]
long_no_tsl = [t for t in long_trades if not t.get("tsl_confirmed")]

compare_short = pd.DataFrame({
    "SHORT + TSL-bevestigd": compute_stats(short_tsl, RR),
    "SHORT zonder TSL": compute_stats(short_no_tsl, RR),
})
print("--- SHORT ---")
print(compare_short.to_string())
print()

compare_long = pd.DataFrame({
    "LONG + TSL-bevestigd": compute_stats(long_tsl, RR),
    "LONG zonder TSL": compute_stats(long_no_tsl, RR),
})
print("--- LONG ---")
print(compare_long.to_string())


print()
print("===================================")
print("TSL + EMA-TREND-PULLBACK PER ASSETKLASSE (de verfijnde combinatie)")
print("===================================")

per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in tsl_and_trend if t["asset_class"] == cls]
    stats = compute_stats(class_trades, RR)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))

print()
print("===================================")
print("TSL + EMA-TREND-PULLBACK: MET vs. ZONDER CRYPTO")
print("===================================")

tsl_trend_no_crypto = [t for t in tsl_and_trend if t["asset_class"] != "crypto"]
compare_crypto = pd.DataFrame({
    "Met crypto": compute_stats(tsl_and_trend, RR),
    "Zonder crypto": compute_stats(tsl_trend_no_crypto, RR),
})
print(compare_crypto.to_string())


pd.DataFrame(all_trades).to_csv("tdi_shark_fin_trades.csv", index=False)
print()
print("CSV opgeslagen: tdi_shark_fin_trades.csv")


# ============================================
# RSI-DREMPEL-VERGELIJKING (nieuwe vraag: moet de piek/dal boven/onder
# een absolute drempel liggen, niet alleen 'buiten de statistische band'?)
# ============================================

print()
print("===================================")
print("RSI-DREMPEL-VERGELIJKING - SHORT (piek moet boven X liggen)")
print("===================================")
print()

short_all = [t for t in all_trades if t["direction"] == "SHORT"]

short_thresholds = {}
for threshold in [0, 60, 70, 80]:
    subset = [t for t in short_all if t.get("trigger_rsi_level", 0) >= threshold]
    short_thresholds[f">= {threshold}"] = compute_stats(subset, RR)

print(pd.DataFrame(short_thresholds).to_string())


print()
print("===================================")
print("RSI-DREMPEL-VERGELIJKING - LONG (dal moet onder X liggen)")
print("===================================")
print()

long_all = [t for t in all_trades if t["direction"] == "LONG"]

long_thresholds = {}
for threshold in [100, 40, 30, 20]:
    subset = [t for t in long_all if t.get("trigger_rsi_level", 100) <= threshold]
    long_thresholds[f"<= {threshold}"] = compute_stats(subset, RR)

print(pd.DataFrame(long_thresholds).to_string())


# ============================================
# GECOMBINEERD: LONG + TSL + drempel (de sterkste eerdere bevinding,
# nu met een extra RSI-drempel erbovenop)
# ============================================

print()
print("===================================")
print("LONG + TSL + RSI-DREMPEL (combinatie van de sterkste bevindingen)")
print("===================================")
print()

long_tsl_all = [t for t in long_all if t.get("tsl_confirmed")]

long_tsl_thresholds = {}
for threshold in [0, 40, 30, 20]:
    subset = [t for t in long_tsl_all if t.get("trigger_rsi_level", 100) <= threshold]
    long_tsl_thresholds[f"<= {threshold}"] = compute_stats(subset, RR)

print(pd.DataFrame(long_tsl_thresholds).to_string())