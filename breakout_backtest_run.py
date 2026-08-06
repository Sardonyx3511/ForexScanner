"""
Backtest-script voor de Bollinger Squeeze breakout-strategie - los te
draaien. Test over ALLE 97 markten, want deze strategie profiteert
specifiek van echte volumedata die vooral bij crypto/indices/
commodities aanwezig is (niet bij forex/metals).

Gebruik:
    python breakout_backtest_run.py
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
from utils.backtest import compute_stats
from utils.breakout_strategy import prepare_breakout_data, simulate_breakout_trades, has_reliable_volume


RR_VARIANTS = [1.0, 1.5, 2.0]


print("===================================")
print("   BREAKOUT-STRATEGIE (Bollinger Squeeze) - BACKTEST")
print(f"   {len(ALL_PAIRS)} markten, RR-varianten: {RR_VARIANTS}")
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
            print("overgeslagen (te weinig data)")
            skipped.append(pair)
            continue

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        vol_tag = "met volume" if has_reliable_volume(df) else "zonder volume"

        results_per_rr = []

        for rr in RR_VARIANTS:

            trades = simulate_breakout_trades(
                df_prepared, pair,
                atr_multiplier=ATR_MULTIPLIER,
                rr=rr,
                divergence_lookback=DIVERGENCE_LOOKBACK,
                divergence_order=DIVERGENCE_ORDER,
            )

            for t in trades:
                t["asset_class"] = asset_class

            all_trades_by_rr[rr].extend(trades)
            results_per_rr.append(f"RR{rr}: {len(trades)}t")

        print(f"({vol_tag}) " + " | ".join(results_per_rr))

    except Exception as e:
        print(f"FOUT: {e}")
        failed.append(pair)
        continue


print()
print(f"Overgeslagen: {len(skipped)} -> {skipped}")
print(f"Gefaald: {len(failed)} -> {failed}")


# ============================================
# Totaaloverzicht per RR
# ============================================

overall_by_rr = {}

for rr in RR_VARIANTS:

    print()
    print("===================================")
    print(f"TOTAALOVERZICHT BREAKOUT-STRATEGIE - RR 1:{rr}")
    print("===================================")

    overall_stats = compute_stats(all_trades_by_rr[rr], rr)
    overall_by_rr[rr] = overall_stats

    for key, value in overall_stats.items():
        print(f"{key}: {value}")


print()
print("===================================")
print("VERGELIJKING RR-VARIANTEN - BREAKOUT-STRATEGIE")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

compare_rr = pd.DataFrame({
    f"RR 1:{rr}": overall_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_rr.to_string())


# ============================================
# Uitsplitsing: markten MET vs. ZONDER volumebevestiging
# ============================================

print()
print("===================================")
print("MET VOLUME-BEVESTIGING vs. ZONDER (RR 1:2)")
print("===================================")

rr_focus = 2.0
with_vol = [t for t in all_trades_by_rr[rr_focus] if t.get("volume_used")]
without_vol = [t for t in all_trades_by_rr[rr_focus] if not t.get("volume_used")]

compare_vol = pd.DataFrame({
    "Met volume-bevestiging": compute_stats(with_vol, rr_focus),
    "Zonder volume-bevestiging": compute_stats(without_vol, rr_focus),
})
print(compare_vol.to_string())


# ============================================
# Robuustheidschecks op de volume-bevestigde subset (RR 1:2):
# per assetklasse, en LONG vs SHORT
# ============================================

print()
print("===================================")
print("VOLUME-SUBSET PER ASSETKLASSE (RR 1:2)")
print("===================================")

per_class_stats = []
for cls in ["forex", "crypto", "metals", "indices", "commodities"]:
    class_trades = [t for t in with_vol if t["asset_class"] == cls]
    stats = compute_stats(class_trades, rr_focus)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


print()
print("===================================")
print("VOLUME-SUBSET: LONG vs. SHORT (RR 1:2)")
print("===================================")

longs = [t for t in with_vol if t["direction"] == "LONG"]
shorts = [t for t in with_vol if t["direction"] == "SHORT"]

compare_dir = pd.DataFrame({
    "LONG": compute_stats(longs, rr_focus),
    "SHORT": compute_stats(shorts, rr_focus),
})
print(compare_dir.to_string())


print()
print("===================================")
print("VOLUME-SUBSET ZONDER CRYPTO (RR 1:2)")
print("===================================")

without_crypto = [t for t in with_vol if t["asset_class"] != "crypto"]
print(f"Alleen forex/metals/indices/commodities: {len(without_crypto)} trades")
for key, value in compute_stats(without_crypto, rr_focus).items():
    print(f"{key}: {value}")


# ============================================
# CSV's opslaan
# ============================================

for rr in RR_VARIANTS:
    trades_df = pd.DataFrame(all_trades_by_rr[rr])
    if not trades_df.empty:
        trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
        trades_df.to_csv(f"breakout_backtest_trades_rr{rr}.csv", index=False)

print()
print("CSV's opgeslagen: breakout_backtest_trades_rrX.csv")