"""
Test verschillende filtercombinaties op de Donchian-breakout-strategie
om te zien welke de "slechte" trades daadwerkelijk eruit filtert,
i.p.v. filters blind toe te voegen.

Getest op RR 1:2 (beste uit de vorige Donchian-test), 213 markten.

Gebruik:
    python donchian_filter_compare.py
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


RR_FOCUS = 2.0
MIN_BREAKOUT_STRENGTH = 0.5  # minstens 0.5 ATR voorbij het kanaal


print("===================================")
print("   DONCHIAN FILTER-VERGELIJKING")
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
            df_prepared, pair,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR_FOCUS,
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
print(f"Totaal aantal trades: {len(all_trades)}")


# ============================================
# Losse filters, elk apart getest
# ============================================

print()
print("===================================")
print("LOSSE FILTERS (elk apart, t.o.v. baseline)")
print("===================================")
print("Break-even winrate nodig bij RR 1:2: 33.3%")
print()

baseline = all_trades
longs_only = [t for t in all_trades if t["direction"] == "LONG"]
ema_aligned_only = [t for t in all_trades if t.get("ema_aligned")]
volume_confirmed_only = [t for t in all_trades if t.get("volume_confirmed")]
strong_breakout_only = [t for t in all_trades if t.get("breakout_strength_atr", 0) >= MIN_BREAKOUT_STRENGTH]

compare_single = pd.DataFrame({
    "Baseline (alles)": compute_stats(baseline, RR_FOCUS),
    "Alleen LONG": compute_stats(longs_only, RR_FOCUS),
    "EMA-aligned": compute_stats(ema_aligned_only, RR_FOCUS),
    "Volume bevestigd": compute_stats(volume_confirmed_only, RR_FOCUS),
    f"Sterke breakout (>={MIN_BREAKOUT_STRENGTH} ATR)": compute_stats(strong_breakout_only, RR_FOCUS),
})
print(compare_single.to_string())


# ============================================
# Combinaties, opbouwend vanaf LONG-only
# ============================================

print()
print("===================================")
print("COMBINATIES (opbouwend vanaf LONG-only)")
print("===================================")
print()

long_ema = [t for t in longs_only if t.get("ema_aligned")]
long_ema_vol = [t for t in long_ema if t.get("volume_confirmed")]
long_ema_strong = [t for t in long_ema if t.get("breakout_strength_atr", 0) >= MIN_BREAKOUT_STRENGTH]
long_ema_vol_strong = [t for t in long_ema_vol if t.get("breakout_strength_atr", 0) >= MIN_BREAKOUT_STRENGTH]

compare_combo = pd.DataFrame({
    "LONG only": compute_stats(longs_only, RR_FOCUS),
    "LONG + EMA-aligned": compute_stats(long_ema, RR_FOCUS),
    "LONG + EMA + Volume": compute_stats(long_ema_vol, RR_FOCUS),
    "LONG + EMA + Sterke breakout": compute_stats(long_ema_strong, RR_FOCUS),
    "LONG + EMA + Volume + Sterk": compute_stats(long_ema_vol_strong, RR_FOCUS),
})
print(compare_combo.to_string())


# ============================================
# Beste combinatie: zonder crypto checken
# ============================================

print()
print("===================================")
print("BESTE COMBINATIE: MET vs. ZONDER CRYPTO")
print("(vul de sterkste combinatie hierboven in als 'beste_combo')")
print("===================================")

# Standaard: LONG + EMA-aligned (meestal de meest robuuste combinatie
# met voldoende trades) - pas aan als een andere combinatie sterker blijkt
beste_combo = long_ema
beste_combo_zonder_crypto = [t for t in beste_combo if t["asset_class"] != "crypto"]

compare_final = pd.DataFrame({
    "Beste combo (met crypto)": compute_stats(beste_combo, RR_FOCUS),
    "Beste combo (zonder crypto)": compute_stats(beste_combo_zonder_crypto, RR_FOCUS),
})
print(compare_final.to_string())


# ============================================
# CSV opslaan
# ============================================

trades_df = pd.DataFrame(all_trades)
if not trades_df.empty:
    trades_df["pair"] = trades_df["pair"].apply(clean_pair_name)
    trades_df.to_csv("donchian_filter_compare_trades.csv", index=False)

print()
print("CSV opgeslagen: donchian_filter_compare_trades.csv")