"""
Backtest-script voor de Pullback-naar-EMA21-strategie - los te draaien.

Vergelijkt dezelfde 44 forex-paren, dezelfde exit-logica (ATR-stop,
RR-target) als de hoofdstrategie, maar met een fundamenteel ander
instapmoment: een vroege pullback binnen een bevestigde trend, in
plaats van een late momentum-bevestiging (Stochastic-cross).

Test ook over de drie RR-varianten (1:1, 1:1.5, 1:2) voor een eerlijke
vergelijking met de eerdere resultaten van de hoofdstrategie.

Gebruik:
    python pullback_backtest_run.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    FOREX_PAIRS,
    ATR_MULTIPLIER,
    RSI_WINDOW,
    EMA_SPAN,
    DIVERGENCE_LOOKBACK,
    DIVERGENCE_ORDER,
    ADX_MIN,
    clean_pair_name,
)
from utils.backtest import prepare_backtest_data, compute_stats
from utils.pullback_strategy import simulate_pullback_trades


RR_VARIANTS = [1.0, 1.5, 2.0]


print("===================================")
print("   PULLBACK-STRATEGIE - BACKTEST")
print(f"   {len(FOREX_PAIRS)} forex-paren, 5 jaar historie")
print(f"   RR-varianten: {RR_VARIANTS}")
print("===================================")
print()


all_trades_by_rr = {rr: [] for rr in RR_VARIANTS}
per_pair_stats_by_rr = {rr: [] for rr in RR_VARIANTS}

for pair in FOREX_PAIRS:

    print(f"Backtesten: {pair} ...", end=" ")

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
                adx_min=ADX_MIN,
            )

            stats = compute_stats(trades, rr)
            stats["Pair"] = clean_pair_name(pair)

            per_pair_stats_by_rr[rr].append(stats)
            all_trades_by_rr[rr].extend(trades)

            results_per_rr.append(f"RR{rr}: {stats['Aantal trades']}t/{stats['Winrate (%)']}%")

        print(" | ".join(results_per_rr))

    except Exception as e:
        print(f"FOUT: {e}")
        continue


# ============================================
# Per RR-waarde: totaaloverzicht
# ============================================

overall_by_rr = {}

for rr in RR_VARIANTS:

    print()
    print("===================================")
    print(f"TOTAALOVERZICHT PULLBACK-STRATEGIE - RR 1:{rr}")
    print("===================================")

    overall_stats = compute_stats(all_trades_by_rr[rr], rr)
    overall_by_rr[rr] = overall_stats

    for key, value in overall_stats.items():
        print(f"{key}: {value}")

    stats_df = pd.DataFrame(per_pair_stats_by_rr[rr])
    if not stats_df.empty:
        stats_df = stats_df.sort_values("Totaal resultaat (R)", ascending=False)
        stats_df.to_csv(f"pullback_backtest_per_pair_rr{rr}.csv", index=False)


# ============================================
# Vergelijking RR-varianten
# ============================================

print()
print("===================================")
print("VERGELIJKING RR-VARIANTEN - PULLBACK-STRATEGIE")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

compare_rr = pd.DataFrame({
    f"RR 1:{rr}": overall_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_rr.to_string())


# ============================================
# RSI-divergentie-subset over alle drie de RR-varianten
# ============================================

print()
print("===================================")
print("RSI-DIVERGENTIE-SUBSET - PULLBACK-STRATEGIE")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

divergence_stats_by_rr = {}

for rr in RR_VARIANTS:
    trades_with_div = [t for t in all_trades_by_rr[rr] if t.get("rsi_divergence")]
    divergence_stats_by_rr[rr] = compute_stats(trades_with_div, rr)

compare_divergence_rr = pd.DataFrame({
    f"RR 1:{rr}": divergence_stats_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_divergence_rr.to_string())


# ============================================
# ADX-sterkte-subset over alle drie de RR-varianten
# ============================================

print()
print("===================================")
print("ADX-STERKTE-SUBSET - PULLBACK-STRATEGIE")
print("===================================")
print(f"ADX >= {ADX_MIN} beschouwd als 'sterke trend'")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

adx_stats_by_rr = {}

for rr in RR_VARIANTS:
    trades_strong_adx = [t for t in all_trades_by_rr[rr] if t.get("adx_strong")]
    adx_stats_by_rr[rr] = compute_stats(trades_strong_adx, rr)

compare_adx_rr = pd.DataFrame({
    f"RR 1:{rr}": adx_stats_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_adx_rr.to_string())


# ============================================
# Combinatie: RSI-divergentie EN sterke ADX tegelijk
# ============================================

print()
print("===================================")
print("GECOMBINEERD: RSI-DIVERGENTIE + STERKE ADX - PULLBACK-STRATEGIE")
print("===================================")
print("Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
print()

combined_stats_by_rr = {}

for rr in RR_VARIANTS:
    trades_combined = [
        t for t in all_trades_by_rr[rr]
        if t.get("rsi_divergence") and t.get("adx_strong")
    ]
    combined_stats_by_rr[rr] = compute_stats(trades_combined, rr)

compare_combined_rr = pd.DataFrame({
    f"RR 1:{rr}": combined_stats_by_rr[rr] for rr in RR_VARIANTS
})
print(compare_combined_rr.to_string())


# ============================================
# CSV's opslaan
# ============================================

for rr in RR_VARIANTS:
    trades_df = pd.DataFrame(all_trades_by_rr[rr])
    if not trades_df.empty:
        trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
        trades_df.to_csv(f"pullback_backtest_trades_detail_rr{rr}.csv", index=False)

print()
print("CSV's opgeslagen: pullback_backtest_per_pair_rrX.csv, pullback_backtest_trades_detail_rrX.csv")