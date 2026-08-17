"""
Multi-asset backtest voor de 'aanhoudende bias'-TDI-strategie: shark
fin zet de richting, en elke latere RSI/TSL-kruising in dezelfde
richting is ook een aparte entry - met vergelijking tussen optie A
(MBL-eis verplicht bij de kruising) en optie B (geen MBL-eis), plus
EMA-kenmerken.

Gebruik:
    python tdi_persistent_bias_backtest.py
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
    simulate_shark_fin_persistent_bias_trades,
)


print("===================================")
print("   TDI AANHOUDENDE-BIAS STRATEGIE - MULTI-ASSET BACKTEST")
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
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_backtest_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_tdi_indicators(df_prepared, rsi_period=13, band_period=34, band_dev=2)
        df_prepared = add_long_term_emas(df_prepared, fast_span=50, slow_span=200)

        trades = simulate_shark_fin_persistent_bias_trades(
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR
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


print()
print("===================================")
print("BASELINE - ALLE TRADES (optie B: elke kruising telt)")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR}: {round(1/(1+RR)*100, 1)}%")
print()

baseline_stats = compute_stats(all_trades, RR)
for key, value in baseline_stats.items():
    print(f"{key}: {value}")


print()
print("===================================")
print("ENTRY-TYPE: SHARK FIN vs. CROSS")
print("===================================")

shark_fin_entries = [t for t in all_trades if t.get("entry_type") == "shark_fin"]
cross_entries = [t for t in all_trades if t.get("entry_type") == "cross"]

compare_type = pd.DataFrame({
    "Shark fin-entries": compute_stats(shark_fin_entries, RR),
    "Cross-entries": compute_stats(cross_entries, RR),
})
print(compare_type.to_string())


print()
print("===================================")
print("CROSS-ENTRIES: OPTIE A (MBL verplicht) vs. OPTIE B (alles)")
print("===================================")

cross_option_a = [t for t in cross_entries if t.get("mbl_position_ok")]
cross_option_b_only = [t for t in cross_entries if not t.get("mbl_position_ok")]

compare_option = pd.DataFrame({
    "Optie B - alle cross-entries": compute_stats(cross_entries, RR),
    "Optie A - MBL vereist": compute_stats(cross_option_a, RR),
    "Alleen NIET-MBL (ter contrast)": compute_stats(cross_option_b_only, RR),
})
print(compare_option.to_string())


print()
print("===================================")
print("PER RICHTING")
print("===================================")

longs = [t for t in all_trades if t["direction"] == "LONG"]
shorts = [t for t in all_trades if t["direction"] == "SHORT"]

compare_dir = pd.DataFrame({
    "LONG": compute_stats(longs, RR),
    "SHORT": compute_stats(shorts, RR),
})
print(compare_dir.to_string())


print()
print("===================================")
print("EMA-KENMERKEN (prijs boven EMA200 / golden-cross-structuur)")
print("===================================")

with_price_ema = [t for t in all_trades if t.get("price_above_ema200")]
with_golden_cross = [t for t in all_trades if t.get("golden_cross_state")]
with_both = [t for t in all_trades if t.get("price_above_ema200") and t.get("golden_cross_state")]

compare_ema = pd.DataFrame({
    "Baseline (alles)": compute_stats(all_trades, RR),
    "Prijs juiste kant EMA200": compute_stats(with_price_ema, RR),
    "Golden/death-cross-structuur": compute_stats(with_golden_cross, RR),
    "Beide EMA-kenmerken": compute_stats(with_both, RR),
})
print(compare_ema.to_string())


print()
print("===================================")
print("PER ASSETKLASSE")
print("===================================")

per_class_stats = []
for cls in ["forex", "crypto", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in all_trades if t["asset_class"] == cls]
    stats = compute_stats(class_trades, RR)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))


print()
print("===================================")
print("MET vs. ZONDER CRYPTO")
print("===================================")

without_crypto = [t for t in all_trades if t["asset_class"] != "crypto"]
compare_crypto = pd.DataFrame({
    "Met crypto": compute_stats(all_trades, RR),
    "Zonder crypto": compute_stats(without_crypto, RR),
})
print(compare_crypto.to_string())


pd.DataFrame(all_trades).to_csv("tdi_persistent_bias_trades.csv", index=False)
print()
print("CSV opgeslagen: tdi_persistent_bias_trades.csv")
