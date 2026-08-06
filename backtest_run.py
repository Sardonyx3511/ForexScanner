"""
Backtest-script - los te draaien, NIET onderdeel van de dagelijkse
GitHub Actions-run.

Test de KST/DMI/ADX/Stochastic-strategie over 5 jaar historische data
per forex-paar, vergelijkt RSI-divergentie en de EMA21-afstandsfilter,
EN vergelijkt drie Risk/Reward-instellingen (1:1, 1:1.5, 1:2) om te
zien welke combinatie van winrate en reward het beste totaalresultaat
geeft.

Belangrijk: data wordt maar ÉÉN keer per paar gedownload en voorbereid;
daarna wordt de trade-simulatie driemaal gedraaid (één keer per RR-
waarde) op exact dezelfde entries, zodat de vergelijking eerlijk is
(alleen het exit-punt verschilt, niet de instapmomenten).

Gebruik:
    python backtest_run.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    FOREX_PAIRS,
    ATR_MULTIPLIER,
    ADX_MIN,
    STOCH_OVERSOLD,
    STOCH_OVERBOUGHT,
    RSI_WINDOW,
    EMA_SPAN,
    DIVERGENCE_LOOKBACK,
    DIVERGENCE_ORDER,
    EMA_EXTENDED_THRESHOLD_ATR,
    clean_pair_name,
)
from utils.backtest import prepare_backtest_data, simulate_trades, compute_stats


RR_VARIANTS = [1.0, 1.5, 2.0]


print("===================================")
print("      FOREX SCANNER - BACKTEST")
print(f"      {len(FOREX_PAIRS)} forex-paren, 5 jaar historie")
print(f"      RR-varianten: {RR_VARIANTS}")
print("===================================")
print()


# Per RR-waarde houden we een aparte verzameling trades + per-paar stats bij
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

        # Data + indicatoren maar ÉÉN keer voorbereiden per paar
        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        results_per_rr = []

        for rr in RR_VARIANTS:

            trades = simulate_trades(
                df_prepared, pair,
                atr_multiplier=ATR_MULTIPLIER,
                rr=rr,
                adx_min=ADX_MIN,
                stoch_oversold=STOCH_OVERSOLD,
                stoch_overbought=STOCH_OVERBOUGHT,
                divergence_lookback=DIVERGENCE_LOOKBACK,
                divergence_order=DIVERGENCE_ORDER,
                ema_extended_threshold_atr=EMA_EXTENDED_THRESHOLD_ATR,
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
# Per RR-waarde: totaaloverzicht + per-paar CSV
# ============================================

overall_by_rr = {}

for rr in RR_VARIANTS:

    print()
    print("===================================")
    print(f"TOTAALOVERZICHT - RR 1:{rr}")
    print("===================================")

    overall_stats = compute_stats(all_trades_by_rr[rr], rr)
    overall_by_rr[rr] = overall_stats

    for key, value in overall_stats.items():
        print(f"{key}: {value}")

    stats_df = pd.DataFrame(per_pair_stats_by_rr[rr])
    if not stats_df.empty:
        stats_df = stats_df.sort_values("Totaal resultaat (R)", ascending=False)
        stats_df.to_csv(f"backtest_per_pair_rr{rr}.csv", index=False)


# ============================================
# Directe vergelijking van de drie RR-varianten
# ============================================

print()
print("===================================")
print("VERGELIJKING RR-VARIANTEN (alle forex-paren samen)")
print("===================================")
print(f"Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
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
print("RSI-DIVERGENTIE-SUBSET PER RR-VARIANT")
print("===================================")
print(f"Break-even winrate nodig per RR: 1:1 -> 50.0% | 1:1.5 -> 40.0% | 1:2 -> 33.3%")
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
# Trade-detail CSV's per RR (handig voor verder onderzoek)
# ============================================

for rr in RR_VARIANTS:
    trades_df = pd.DataFrame(all_trades_by_rr[rr])
    if not trades_df.empty:
        trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
        trades_df.to_csv(f"backtest_trades_detail_rr{rr}.csv", index=False)

print()
print("CSV's opgeslagen per RR-variant: backtest_per_pair_rrX.csv, backtest_trades_detail_rrX.csv")