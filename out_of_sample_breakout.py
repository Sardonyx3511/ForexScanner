"""
Out-of-sample validatie voor de Breakout-strategie (Bollinger Squeeze +
EMA21 + volumebevestiging) - los te draaien.

Belangrijk: de strategie-parameters staan al vast (niet aangepast op
basis van deze test). We simuleren over de volledige 5 jaar data zoals
altijd, en splitsen ACHTERAF de resulterende trades in twee
niet-overlappende periodes (eerste helft vs. tweede helft) om te
checken of de strategie in BEIDE periodes apart winstgevend is - niet
alleen gemiddeld over de hele set.

Interpretatie:
- Positief in beide helften, vergelijkbare winrate  -> geruststellend,
  wijst op een structurele edge i.p.v. toeval in één periode
- Alleen positief in de eerste helft, negatief/zwak in de tweede
  -> waarschuwingssignaal, mogelijk overfitting op oudere data
- Zelfde geldt andersom

Gebruik:
    python out_of_sample_breakout.py
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


RR_FOCUS = 2.0  # beste RR uit de vorige test


print("===================================")
print("   OUT-OF-SAMPLE VALIDATIE - BREAKOUT-STRATEGIE")
print(f"   {len(ALL_PAIRS)} markten, RR 1:{RR_FOCUS}")
print("   Splitst 5 jaar data in twee niet-overlappende periodes")
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
            print("overgeslagen (te weinig data)")
            skipped.append(pair)
            continue

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        trades = simulate_breakout_trades(
            df_prepared, pair,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR_FOCUS,
            divergence_lookback=DIVERGENCE_LOOKBACK,
            divergence_order=DIVERGENCE_ORDER,
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
print(f"Totaal aantal trades verzameld: {len(all_trades)}")


# ============================================
# Splitsen in twee niet-overlappende periodes op basis van entry-datum
# ============================================

closed_trades = [t for t in all_trades if t["outcome"] in ("WIN", "LOSS")]

if not closed_trades:
    print("Geen afgeronde trades gevonden, kan niet splitsen.")
else:
    entry_dates = [t["entry_date"] for t in closed_trades]
    min_date = min(entry_dates)
    max_date = max(entry_dates)
    midpoint = min_date + (max_date - min_date) / 2

    print()
    print(f"Periode: {min_date.date()} t/m {max_date.date()}")
    print(f"Splitspunt (midden): {midpoint.date()}")

    period_1 = [t for t in closed_trades if t["entry_date"] < midpoint]
    period_2 = [t for t in closed_trades if t["entry_date"] >= midpoint]

    # Alleen volume-bevestigde trades (de sterkste subset uit de vorige test)
    period_1_vol = [t for t in period_1 if t.get("volume_used")]
    period_2_vol = [t for t in period_2 if t.get("volume_used")]

    print()
    print("===================================")
    print("ALLE TRADES: PERIODE 1 vs. PERIODE 2")
    print("===================================")
    print(f"Break-even winrate nodig bij RR 1:{RR_FOCUS}: {round(1/(1+RR_FOCUS)*100, 1)}%")
    print()

    compare_all = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1, RR_FOCUS),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2, RR_FOCUS),
    })
    print(compare_all.to_string())

    print()
    print("===================================")
    print("VOLUME-SUBSET: PERIODE 1 vs. PERIODE 2")
    print("(dit is de sterkste bevinding uit de vorige test - hier draait het om)")
    print("===================================")
    print()

    compare_vol = pd.DataFrame({
        f"Periode 1 ({min_date.date()} - {midpoint.date()})": compute_stats(period_1_vol, RR_FOCUS),
        f"Periode 2 ({midpoint.date()} - {max_date.date()})": compute_stats(period_2_vol, RR_FOCUS),
    })
    print(compare_vol.to_string())

    # CSV's opslaan voor eigen verder onderzoek
    pd.DataFrame(period_1_vol).to_csv("oos_breakout_period1_volume.csv", index=False)
    pd.DataFrame(period_2_vol).to_csv("oos_breakout_period2_volume.csv", index=False)
    print()
    print("CSV's opgeslagen: oos_breakout_period1_volume.csv, oos_breakout_period2_volume.csv")