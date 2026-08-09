"""
Multi-asset backtest voor de Mean Reversion-strategie - los te draaien.

Test over de volledige 213-markten-set. Let op: dit gebruikt een
ANDERE statistiekfunctie (compute_variable_rr_stats) dan de andere
backtest-scripts, omdat het doel (Bollinger-middenlijn) geen vast
RR-veelvoud is zoals bij breakout/pullback.

Gebruik:
    python mean_reversion_backtest_multiasset.py
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
from utils.breakout_strategy import prepare_breakout_data
from utils.mean_reversion_strategy import simulate_mean_reversion_trades, compute_variable_rr_stats


print("===================================")
print("   MEAN REVERSION-STRATEGIE - MULTI-ASSET BACKTEST")
print(f"   {len(ALL_PAIRS)} markten totaal")
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

        if df.empty or len(df) < 150:
            print("overgeslagen (te weinig data)")
            skipped.append(pair)
            continue

        # prepare_breakout_data levert alle indicatoren die mean
        # reversion nodig heeft (ADX, RSI, Bollinger Bands) - geen
        # aparte voorbereidingsfunctie nodig
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
        failed.append(pair)
        continue


print()
print(f"Overgeslagen: {len(skipped)}")
print(f"Gefaald: {len(failed)} -> {failed}")


# ============================================
# Totaaloverzicht: alle trades, LONG vs SHORT
# ============================================

print()
print("===================================")
print("TOTAALOVERZICHT - ALLE TRADES")
print("===================================")

overall_stats = compute_variable_rr_stats(all_trades)
for key, value in overall_stats.items():
    print(f"{key}: {value}")


print()
print("===================================")
print("LONG vs. SHORT")
print("===================================")

longs = [t for t in all_trades if t["direction"] == "LONG"]
shorts = [t for t in all_trades if t["direction"] == "SHORT"]

compare_dir = pd.DataFrame({
    "LONG": compute_variable_rr_stats(longs),
    "SHORT": compute_variable_rr_stats(shorts),
})
print(compare_dir.to_string())


# ============================================
# Per assetklasse
# ============================================

print()
print("===================================")
print("PER ASSETKLASSE")
print("===================================")

per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in all_trades if t["asset_class"] == cls]
    stats = compute_variable_rr_stats(class_trades)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)", "Gem. RR per trade"]
print(per_class_df[cols].to_string(index=False))


# ============================================
# Met crypto vs. zonder crypto
# ============================================

print()
print("===================================")
print("MET CRYPTO vs. ZONDER CRYPTO")
print("===================================")

without_crypto = [t for t in all_trades if t["asset_class"] != "crypto"]

compare_crypto = pd.DataFrame({
    "Met crypto (alles)": compute_variable_rr_stats(all_trades),
    "Zonder crypto": compute_variable_rr_stats(without_crypto),
})
print(compare_crypto.to_string())


# ============================================
# LONG-only, per assetklasse (LONG bleek de sterke richting)
# ============================================

print()
print("===================================")
print("LONG-ONLY PER ASSETKLASSE")
print("===================================")

longs_per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in longs if t["asset_class"] == cls]
    stats = compute_variable_rr_stats(class_trades)
    stats["Asset Class"] = cls
    longs_per_class_stats.append(stats)

longs_per_class_df = pd.DataFrame(longs_per_class_stats)
print(longs_per_class_df[cols].to_string(index=False))


# ============================================
# CSV opslaan
# ============================================

trades_df = pd.DataFrame(all_trades)
if not trades_df.empty:
    trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
    trades_df.to_csv("mean_reversion_trades.csv", index=False)

print()
print("CSV opgeslagen: mean_reversion_trades.csv")