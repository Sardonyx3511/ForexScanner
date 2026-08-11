"""
Isoleert SHORT + TSL + EMA-trend-pullback specifiek (los van LONG),
naar aanleiding van de observatie dat verlies-trades vaak GEEN geldige
EMA-trend-pullback hadden. Leest de al opgeslagen CSV opnieuw in - geen
nieuwe download nodig.

Gebruik (nadat tdi_shark_fin_backtest.py al eerder is gedraaid):
    python tdi_short_ema_check.py
"""

import pandas as pd

from utils.backtest import compute_stats
from config.settings import RR


df = pd.read_csv("tdi_shark_fin_trades.csv")
df = df[df["outcome"].isin(["WIN", "LOSS"])].copy()

trades = df.to_dict("records")


def filter_trades(trades, direction=None, tsl=None, ema_trend=None):
    result = trades
    if direction is not None:
        result = [t for t in result if t["direction"] == direction]
    if tsl is not None:
        result = [t for t in result if bool(t.get("tsl_confirmed")) == tsl]
    if ema_trend is not None:
        result = [t for t in result if bool(t.get("ema_trend_pullback")) == ema_trend]
    return result


print("===================================")
print("SHORT-SPECIFIEKE EMA-TREND-PULLBACK CHECK")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR}: {round(1/(1+RR)*100, 1)}%")
print()

short_tsl = filter_trades(trades, direction="SHORT", tsl=True)
short_tsl_with_ema = filter_trades(trades, direction="SHORT", tsl=True, ema_trend=True)
short_tsl_without_ema = filter_trades(trades, direction="SHORT", tsl=True, ema_trend=False)

compare = pd.DataFrame({
    "SHORT + TSL (alles)": compute_stats(short_tsl, RR),
    "SHORT + TSL + EMA-trend-pullback": compute_stats(short_tsl_with_ema, RR),
    "SHORT + TSL, GEEN EMA-trend-pullback": compute_stats(short_tsl_without_ema, RR),
})
print(compare.to_string())

print()
print("===================================")
print("TER VERGELIJKING: LONG-SPECIFIEKE VERSIE")
print("===================================")
print()

long_tsl = filter_trades(trades, direction="LONG", tsl=True)
long_tsl_with_ema = filter_trades(trades, direction="LONG", tsl=True, ema_trend=True)
long_tsl_without_ema = filter_trades(trades, direction="LONG", tsl=True, ema_trend=False)

compare_long = pd.DataFrame({
    "LONG + TSL (alles)": compute_stats(long_tsl, RR),
    "LONG + TSL + EMA-trend-pullback": compute_stats(long_tsl_with_ema, RR),
    "LONG + TSL, GEEN EMA-trend-pullback": compute_stats(long_tsl_without_ema, RR),
})
print(compare_long.to_string())