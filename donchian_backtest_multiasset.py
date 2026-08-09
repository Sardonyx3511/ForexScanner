"""
Multi-asset backtest voor de Donchian Channel breakout-strategie - los
te draaien. Test over de volledige 213-markten-set, meerdere RR's.

Gebruik:
    python donchian_backtest_multiasset.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RSI_WINDOW,
    EMA_SPAN,
    clean_pair_name,
    get_asset_class,
)
from utils.backtest import compute_stats
from utils.donchian_strategy import prepare_donchian_data, simulate_donchian_trades


RR_VARIANTS = [1.0, 1.5, 2.0]
CHANNEL_WINDOW = 20


print("===================================")
print("   DONCHIAN BREAKOUT-STRATEGIE - MULTI-ASSET BACKTEST")
print(f"   {len(ALL_PAIRS)} markten, kanaal-periode: {CHANNEL_WINDOW} dagen")
print(f"   RR-varianten: {RR_VARIANTS}")
print("===================================")
print()


all_trades_by_rr = {rr: [] for rr in RR_VARIANTS}
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

        if df.empty or len(df) < 150:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_donchian_data(
            df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN, channel_window=CHANNEL_WINDOW
        )

        results_per_rr = []

        for rr in RR_VARIANTS:

            trades = simulate_donchian_trades(
                df_prepared, pair,
                atr_multiplier=ATR_MULTIPLIER,
                rr=rr,
            )

            for t in trades:
                t["asset_class"] = asset_class

            all_trades_by_rr[rr].extend(trades)
            results_per_rr.append(f"RR{rr}: {len(trades)}t")

        print(" | ".join(results_per_rr))

    except Exception as e:
        print(f"FOUT: {e}")
        failed.append(pair)
        continue


print()
print(f"Overgeslagen: {len(skipped)}")
print(f"Gefaald: {len(failed)} -> {failed}")


# ============================================
# Totaaloverzicht per RR
# ============================================

overall_by_rr = {}

for rr in RR_VARIANTS:

    print()
    print("===================================")
    print(f"TOTAALOVERZICHT DONCHIAN - RR 1:{rr}")
    print("===================================")

    overall_stats = compute_stats(all_trades_by_rr[rr], rr)
    overall_by_rr[rr] = overall_stats

    for key, value in overall_stats.items():
        print(f"{key}: {value}")


print()
print("===================================")
print("VERGELIJKING RR-VARIANTEN - DONCHIAN")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

compare_rr = pd.DataFrame({
    f"RR 1:{rr}": overall_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_rr.to_string())


# ============================================
# LONG vs. SHORT, per RR
# ============================================

print()
print("===================================")
print("LONG vs. SHORT")
print("===================================")

for rr in RR_VARIANTS:
    longs = [t for t in all_trades_by_rr[rr] if t["direction"] == "LONG"]
    shorts = [t for t in all_trades_by_rr[rr] if t["direction"] == "SHORT"]

    compare_dir = pd.DataFrame({
        "LONG": compute_stats(longs, rr),
        "SHORT": compute_stats(shorts, rr),
    })
    print(f"--- RR 1:{rr} ---")
    print(compare_dir.to_string())
    print()


# ============================================
# Per assetklasse (RR 1:2)
# ============================================

print("===================================")
print("PER ASSETKLASSE (RR 1:2)")
print("===================================")

rr_focus = 2.0
per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in all_trades_by_rr[rr_focus] if t["asset_class"] == cls]
    stats = compute_stats(class_trades, rr_focus)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


# ============================================
# Met crypto vs. zonder crypto (RR 1:2)
# ============================================

print()
print("===================================")
print("MET CRYPTO vs. ZONDER CRYPTO (RR 1:2)")
print("===================================")

without_crypto = [t for t in all_trades_by_rr[rr_focus] if t["asset_class"] != "crypto"]

compare_crypto = pd.DataFrame({
    "Met crypto (alles)": compute_stats(all_trades_by_rr[rr_focus], rr_focus),
    "Zonder crypto": compute_stats(without_crypto, rr_focus),
})
print(compare_crypto.to_string())


# ============================================
# CSV's opslaan
# ============================================

for rr in RR_VARIANTS:
    trades_df = pd.DataFrame(all_trades_by_rr[rr])
    if not trades_df.empty:
        trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
        trades_df.to_csv(f"donchian_trades_rr{rr}.csv", index=False)

print()
print("CSV's opgeslagen: donchian_trades_rrX.csv")