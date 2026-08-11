"""
Toont een aantal concrete voorbeeldtrades uit tdi_shark_fin_trades.csv,
zodat je ze zelf kunt opzoeken op TradingView (paar + datum) om te
verifiëren of de TSL/PL-crossover visueel klopt met wat de code claimt.

Gebruik (nadat tdi_shark_fin_backtest.py al eerder is gedraaid):
    python tdi_shark_fin_examples.py
"""

import pandas as pd


df = pd.read_csv("tdi_shark_fin_trades.csv", parse_dates=["entry_date", "exit_date"])
df = df[df["outcome"].isin(["WIN", "LOSS"])].copy()


def print_examples(subset, title, n=5, seed=42):
    print(f"\n--- {title} ({len(subset)} beschikbaar, {min(n, len(subset))} getoond) ---")
    if subset.empty:
        print("  (geen trades in deze categorie)")
        return
    sample = subset.sample(n=min(n, len(subset)), random_state=seed)
    for _, r in sample.sort_values("entry_date").iterrows():
        print(f"  {r['pair']:12s} | {r['direction']:5s} | Entry: {r['entry_date'].date()} "
              f"| Prijs: {round(r['entry_price'], 5)} | Uitkomst: {r['outcome']} "
              f"| Duur: {r['bars_held']} dagen")


print("===================================")
print("VOORBEELDTRADES VOOR HANDMATIGE VERIFICATIE")
print("Zoek deze op TradingView op: paar + entry-datum, en check de")
print("TDI-indicator (TSL vs. RSI Price Line) op die specifieke dag.")
print("===================================")

short_tsl = df[(df["direction"] == "SHORT") & (df["tsl_confirmed"] == True)]
long_tsl = df[(df["direction"] == "LONG") & (df["tsl_confirmed"] == True)]

print_examples(short_tsl[short_tsl["outcome"] == "LOSS"], "SHORT + TSL-bevestigd, LOSS (het onverwachte resultaat)")
print_examples(short_tsl[short_tsl["outcome"] == "WIN"], "SHORT + TSL-bevestigd, WIN (ter vergelijking)")
print_examples(long_tsl[long_tsl["outcome"] == "WIN"], "LONG + TSL-bevestigd, WIN (het sterke patroon)")
print_examples(long_tsl[long_tsl["outcome"] == "LOSS"], "LONG + TSL-bevestigd, LOSS (ter vergelijking)")

print()
print("===================================")
print("TIP")
print("===================================")
print("Zet op TradingView de TDI-indicator op de daily-chart van elk paar,")
print("ga naar de vermelde entry-datum, en check of:")
print("  - Bij SHORT: de TSL-lijn daadwerkelijk boven de RSI Price Line zat")
print("  - Bij LONG: de TSL-lijn daadwerkelijk onder de RSI Price Line zat")
print("Als dat niet klopt met wat je op TradingView ziet, is er mogelijk")
print("een verschil in TDI-instellingen (periodes) tussen de code en de")
print("TradingView-indicator die je gebruikt - laat het weten, dan checken")
print("we de exacte instellingen.")