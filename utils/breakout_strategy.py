"""
Bollinger Squeeze breakout-strategie met EMA21-richtingsfilter en
(waar beschikbaar) volumebevestiging.

Kernidee: het objectieve equivalent van een ascending/descending
triangle-breakout, zonder trendlijnen te hoeven fitten (wat subjectief
en foutgevoelig is). In plaats daarvan meten we volatiliteitscompressie
via de Bollinger-bandbreedte.

LONG-voorwaarden (SHORT is het spiegelbeeld):
1. Squeeze: de Bollinger-bandbreedte was recent historisch smal
   (onderste 20e percentiel van de laatste 100 dagen) - het objectieve
   equivalent van 'de driehoek wordt smaller'
2. 21 EMA loopt omhoog (richtingsfilter, zelfde als de pullback-strategie)
3. Breakout: candle sluit boven de bovenste Bollinger Band
4. (Optioneel, alleen als er echte volumedata is - vooral crypto):
   volume op de breakout-dag > 1,5x het 20-daags gemiddelde

Bij forex/metals levert yfinance geen betrouwbare volumedata (geen
centrale beurs), dus daar wordt de volume-eis automatisch overgeslagen
- de strategie draait dan puur op de eerste drie voorwaarden. Bij
crypto/indices/commodities is vaak wel bruikbare volumedata aanwezig.
"""

import pandas as pd

from utils.risk import calculate_stop_loss, calculate_take_profit
from utils.indicators import detect_rsi_divergence, add_bollinger_bands, add_keltner_channels
from utils.backtest import prepare_backtest_data


def prepare_breakout_data(df, rsi_window=14, ema_span=21, bb_window=20, bb_dev=2,
                           kc_window=20, kc_multiplier=1.5):
    """
    Hergebruikt de bestaande prepare_backtest_data (KST/Weekly KST/ADX/
    ATR/Stochastic/RSI/EMA21) en voegt daar Bollinger Bands EN Keltner
    Channels aan toe - nodig voor beide squeeze-detectiemethodes
    (percentiel-gebaseerd vs. Squeeze Momentum/TTM-stijl).
    """

    df_prepared = prepare_backtest_data(df, rsi_window=rsi_window, ema_span=ema_span)
    df_prepared = add_bollinger_bands(df_prepared, window=bb_window, window_dev=bb_dev)
    df_prepared = add_keltner_channels(df_prepared, window=kc_window, multiplier=kc_multiplier)

    return df_prepared


def has_reliable_volume(df):
    """
    Checkt of een DataFrame bruikbare (niet overal 0/NaN) volumedata heeft.
    Forex/metals via yfinance hebben dit meestal niet.
    """

    if "Volume" not in df.columns:
        return False

    nonzero_ratio = (df["Volume"] > 0).sum() / max(len(df), 1)
    return nonzero_ratio > 0.5


def _determine_breakout_signal(df, i, squeeze_method="percentile",
                                squeeze_percentile=20, squeeze_lookback=100,
                                ema_slope_lookback=5, volume_multiplier=1.5,
                                use_volume=False):
    """
    Bepaalt of er op dag i een breakout-entry-signaal is.
    Geeft 'LONG', 'SHORT' of '-' terug.

    squeeze_method:
      'percentile' - huidige bandbreedte t.o.v. eigen historie (relatief)
      'keltner'    - Bollinger Bands binnen Keltner Channel (TTM Squeeze,
                     absolute/binaire vergelijking van twee volatiliteitsmaten)
    """

    row = df.iloc[i]

    if pd.isna(row["BB_width"]) or pd.isna(row["EMA21"]):
        return "-"

    if i < max(squeeze_lookback, ema_slope_lookback) + 1:
        return "-"

    if squeeze_method == "keltner":

        if pd.isna(row["KC_upper"]) or pd.isna(df["KC_upper"].iloc[i - 1]):
            return "-"

        was_squeezed = (
            df["BB_upper"].iloc[i - 1] < df["KC_upper"].iloc[i - 1]
            and df["BB_lower"].iloc[i - 1] > df["KC_lower"].iloc[i - 1]
        )

    else:  # 'percentile' (standaard, zoals eerder)

        width_history = df["BB_width"].iloc[i - squeeze_lookback: i]
        width_yesterday = df["BB_width"].iloc[i - 1]

        if width_history.isna().all():
            return "-"

        threshold = width_history.quantile(squeeze_percentile / 100)
        was_squeezed = width_yesterday <= threshold

    if not was_squeezed:
        return "-"

    ema_now = row["EMA21"]
    ema_prev = df["EMA21"].iloc[i - ema_slope_lookback]
    ema_slope_up = ema_now > ema_prev
    ema_slope_down = ema_now < ema_prev

    breakout_up = row["Close"] > df["BB_upper"].iloc[i - 1]
    breakout_down = row["Close"] < df["BB_lower"].iloc[i - 1]

    volume_ok = True
    if use_volume:
        avg_volume = df["Volume"].iloc[i - 20: i].mean()
        volume_ok = (not pd.isna(avg_volume)) and avg_volume > 0 and row["Volume"] > volume_multiplier * avg_volume

    if ema_slope_up and breakout_up and volume_ok:
        return "LONG"

    if ema_slope_down and breakout_down and volume_ok:
        return "SHORT"

    return "-"


def check_latest_breakout_signal(df, atr_multiplier, rr, squeeze_method="percentile",
                                  squeeze_percentile=20, squeeze_lookback=100,
                                  ema_slope_lookback=5, volume_multiplier=1.5):
    """
    Checkt ALLEEN de laatste dag van de data op een breakout-signaal.
    Voor gebruik in de live scanner (main.py) - geen backtesting/simulatie,
    puur 'is er vandaag een signaal'. Hergebruikt dezelfde, al geteste
    signaallogica als de backtest, zodat live en backtest altijd
    consistent blijven.

    Geeft een dict terug met entry/SL/TP-info, of None als er geen
    signaal is.
    """

    i = len(df) - 1

    if i < max(squeeze_lookback, ema_slope_lookback) + 1:
        return None

    use_volume = has_reliable_volume(df)

    entry = _determine_breakout_signal(
        df, i, squeeze_method, squeeze_percentile, squeeze_lookback,
        ema_slope_lookback, volume_multiplier, use_volume
    )

    if entry not in ("LONG", "SHORT"):
        return None

    row = df.iloc[i]

    if pd.isna(row["ATR"]) or row["ATR"] <= 0:
        return None

    stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
    take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

    return {
        "direction": entry,
        "entry_price": row["Close"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "volume_confirmed": use_volume,
    }
def simulate_breakout_trades(df, pair, atr_multiplier, rr,
                              squeeze_method="percentile",
                              squeeze_percentile=20, squeeze_lookback=100,
                              ema_slope_lookback=5, volume_multiplier=1.5,
                              divergence_lookback=40, divergence_order=3):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de breakout-strategie. Zelfde exit-mechanisme (SL/TP) als
    de andere strategieën, voor een eerlijke vergelijking.
    """

    use_volume = has_reliable_volume(df)

    trades = []
    position = None

    min_bars = max(squeeze_lookback, 60) + 1

    for i in range(min_bars, len(df)):

        row = df.iloc[i]
        date = df.index[i]

        if position is not None:

            exit_price = None
            outcome = None

            if position["direction"] == "LONG":
                if row["Low"] <= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["High"] >= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"
            else:
                if row["High"] >= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["Low"] <= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"

            if exit_price is not None:
                position["exit_date"] = date
                position["exit_price"] = exit_price
                position["outcome"] = outcome
                position["bars_held"] = i - position["entry_bar"]
                trades.append(position)
                position = None

            continue

        entry = _determine_breakout_signal(
            df, i, squeeze_method, squeeze_percentile, squeeze_lookback,
            ema_slope_lookback, volume_multiplier, use_volume
        )

        if entry in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

            bullish_div, bearish_div = detect_rsi_divergence(
                df.iloc[: i + 1], lookback=divergence_lookback, order=divergence_order
            )
            rsi_divergence = (
                (entry == "LONG" and bullish_div)
                or (entry == "SHORT" and bearish_div)
            )

            position = {
                "pair": pair,
                "direction": entry,
                "entry_date": date,
                "entry_price": row["Close"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "rsi_divergence": rsi_divergence,
                "volume_used": use_volume,
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades