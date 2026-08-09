"""
Multi-asset backtest voor de Pullback-naar-EMA21-strategie - los te draaien.

Test de strategie over de volledige, bijgewerkte marktenlijst (213
markten: forex + crypto + stocks + metals + indices + commodities).
Dit is de tweede volledige validatieronde, met dezelfde robuustheids-
checks die breakout+volume ook kreeg.

ADX wordt bewust NIET als filter gebruikt - bleek bij eerdere tests
averechts te werken voor deze strategie.

Gebruik:
    python pullback_backtest_multiasset.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    FOREX_PAIRS,
    CRYPTO_PAIRS,
    STOCKS_PAIRS,
    METALS_PAIRS,
    INDICES_PAIRS,
    COMMODITIES_PAIRS,
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


RR_VARIANTS = [1.0, 1.5, 2.0]
ASSET_CLASSES = ["forex", "crypto", "stocks", "metals", "indices", "commodities"]


print("===================================")
print("   PULLBACK-STRATEGIE - MULTI-ASSET BACKTEST (v2, incl. stocks)")
print(f"   {len(ALL_PAIRS)} markten totaal")
print(f"   ({len(FOREX_PAIRS)} forex, {len(CRYPTO_PAIRS)} crypto, {len(STOCKS_PAIRS)} stocks, "
      f"{len(METALS_PAIRS)} metals, {len(INDICES_PAIRS)} indices, "
      f"{len(COMMODITIES_PAIRS)} commodities)")
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

        if df.empty or len(df) < 100:
            print("overgeslagen (te weinig data)")
            skipped.append(pair)
            continue

        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        results_per_rr = []

        for rr in RR_VARIANTS:

            trades = simulate_pullback_trades(
                df_prepared, pair,
                atr_multiplier=ATR_MULTIPLIER,
                rr=rr,
                divergence_lookback=DIVERGENCE_LOOKBACK,
                divergence_order=DIVERGENCE_ORDER,
            )

            for t in trades:
                t["asset_class"] = asset_class

            all_trades_by_rr[rr].extend(trades)

            n_div = sum(1 for t in trades if t.get("rsi_divergence") and t["outcome"] in ("WIN", "LOSS"))
            results_per_rr.append(f"RR{rr}: {len(trades)}t ({n_div} div)")

        print(" | ".join(results_per_rr))

    except Exception as e:
        print(f"FOUT: {e}")
        failed.append(pair)
        continue


print()
print(f"Overgeslagen (te weinig data): {len(skipped)}")
print(f"Gefaald: {len(failed)} -> {failed}")


# ============================================
# Overzicht per RR: ALLE trades vs. RSI-divergentie-subset
# ============================================

for rr in RR_VARIANTS:

    print()
    print("===================================")
    print(f"RR 1:{rr} - ALLE MARKTEN SAMEN")
    print("===================================")

    all_stats = compute_stats(all_trades_by_rr[rr], rr)
    div_trades = [t for t in all_trades_by_rr[rr] if t.get("rsi_divergence")]
    div_stats = compute_stats(div_trades, rr)

    compare = pd.DataFrame({
        "Alle trades": all_stats,
        "Met RSI-divergentie": div_stats,
    })
    print(compare.to_string())


# ============================================
# RSI-divergentie-subset, uitgesplitst per assetklasse (RR 1:2)
# ============================================

print()
print("===================================")
print("RSI-DIVERGENTIE-SUBSET PER ASSETKLASSE (RR 1:2)")
print("===================================")

rr_focus = 2.0
div_trades_focus = [t for t in all_trades_by_rr[rr_focus] if t.get("rsi_divergence")]

per_class_stats = []
for cls in ASSET_CLASSES:
    class_trades = [t for t in div_trades_focus if t["asset_class"] == cls]
    stats = compute_stats(class_trades, rr_focus)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


# ============================================
# LONG vs. SHORT - RSI-divergentie-subset, per RR
# ============================================

print()
print("===================================")
print("LONG vs. SHORT - RSI-DIVERGENTIE-SUBSET")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

for rr in RR_VARIANTS:
    div_trades = [t for t in all_trades_by_rr[rr] if t.get("rsi_divergence")]
    longs = [t for t in div_trades if t["direction"] == "LONG"]
    shorts = [t for t in div_trades if t["direction"] == "SHORT"]

    compare_dir = pd.DataFrame({
        "LONG": compute_stats(longs, rr),
        "SHORT": compute_stats(shorts, rr),
    })
    print(f"--- RR 1:{rr} ---")
    print(compare_dir.to_string())
    print()


# ============================================
# Met crypto vs. zonder crypto - RSI-divergentie-subset, per RR
# ============================================

print("===================================")
print("MET CRYPTO vs. ZONDER CRYPTO - RSI-DIVERGENTIE-SUBSET")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

for rr in RR_VARIANTS:
    div_trades = [t for t in all_trades_by_rr[rr] if t.get("rsi_divergence")]
    with_crypto = div_trades
    without_crypto = [t for t in div_trades if t["asset_class"] != "crypto"]

    compare_crypto = pd.DataFrame({
        "Met crypto (alles)": compute_stats(with_crypto, rr),
        "Zonder crypto": compute_stats(without_crypto, rr),
    })
    print(f"--- RR 1:{rr} ---")
    print(compare_crypto.to_string())
    print()


# ============================================
# CSV's opslaan
# ============================================

for rr in RR_VARIANTS:
    trades_df = pd.DataFrame(all_trades_by_rr[rr])
    if not trades_df.empty:
        trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
        trades_df.to_csv(f"pullback_multiasset_v2_trades_rr{rr}.csv", index=False)

print()
print("CSV's opgeslagen: pullback_multiasset_v2_trades_rrX.csv")