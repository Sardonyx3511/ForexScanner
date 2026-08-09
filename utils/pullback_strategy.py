"""
Pullback-naar-EMA21 swingstrategie.

Kernidee: in plaats van te wachten op een laat momentum-bevestigingssignaal
(zoals de Stochastic-cross in de oude hoofdstrategie), stap je in tijdens
een gezonde terugval binnen een al bestaande trend - vroeger in de
beweging, tegen een betere prijs.

LONG-voorwaarden (SHORT is het spiegelbeeld):
1. Weekly trend is bullish (herbruik van de KST-logica, lookahead-vrij)
2. 21 EMA loopt omhoog op daily (bevestigt de trend ook op korte termijn)
3. Prijs raakt of doorbreekt de 21 EMA (vandaag of gisteren) - de pullback
4. Bullish candle sluit terug boven de EMA - bevestigt de afwijzing/bounce
5. RSI tussen 35-60 - bevestigt een normale terugval, geen scherpe crash

Exit-logica (SL/TP) is identiek aan de hoofdstrategie (ATR-based stop,
RR-based target), zodat de vergelijking eerlijk is: alleen het
instapmoment verschilt, niet hoe de trade wordt afgesloten.

BELANGRIJK - gevalideerde bevinding uit uitgebreid backtesten (213
markten, meerdere RR's, out-of-sample gevalideerd over twee periodes):
alleen de combinatie SHORT + RSI-divergentie bleek consistent
winstgevend. LONG-signalen (met of zonder divergentie) waren
verlieslatend. De live-functie hieronder geeft daarom UITSLUITEND
SHORT-signalen met divergentie terug - dit is een bewuste, data-
gedreven keuze, geen omissie.
"""

import pandas as pd

from utils.risk import calculate_stop_loss, calculate_take_profit
from utils.indicators import detect_rsi_divergence


def _determine_pullback_signal(df, i, ema_slope_lookback=5, rsi_low=35, rsi_high=60):
    """
    Bepaalt of er op dag i een pullback-entry-signaal is.
    Geeft 'LONG', 'SHORT' of '-' terug.
    """

    row = df.iloc[i]

    if pd.isna(row["Weekly KST"]) or pd.isna(row["EMA21"]) or pd.isna(row["RSI"]):
        return "-"

    if i < ema_slope_lookback:
        return "-"

    weekly_trend = "BULL" if row["Weekly KST"] > row["Weekly KST Signal"] else "BEAR"

    ema_now = row["EMA21"]
    ema_prev = df["EMA21"].iloc[i - ema_slope_lookback]
    ema_slope_up = ema_now > ema_prev
    ema_slope_down = ema_now < ema_prev

    low_today = row["Low"]
    low_yesterday = df["Low"].iloc[i - 1]
    high_today = row["High"]
    high_yesterday = df["High"].iloc[i - 1]

    touched_ema_from_above = (low_today <= ema_now) or (low_yesterday <= df["EMA21"].iloc[i - 1])
    touched_ema_from_below = (high_today >= ema_now) or (high_yesterday >= df["EMA21"].iloc[i - 1])

    bullish_candle = row["Close"] > row["Open"] and row["Close"] > ema_now
    bearish_candle = row["Close"] < row["Open"] and row["Close"] < ema_now

    rsi = row["RSI"]

    if (weekly_trend == "BULL" and ema_slope_up and touched_ema_from_above
            and bullish_candle and rsi_low <= rsi <= rsi_high):
        return "LONG"

    if (weekly_trend == "BEAR" and ema_slope_down and touched_ema_from_below
            and bearish_candle and (100 - rsi_high) <= rsi <= (100 - rsi_low)):
        return "SHORT"

    return "-"


def check_latest_pullback_signal(df, atr_multiplier, rr,
                                  ema_slope_lookback=5, rsi_low=35, rsi_high=60,
                                  divergence_lookback=40, divergence_order=3):
    """
    Checkt ALLEEN de laatste dag van de data op een pullback-signaal.
    Voor gebruik in de live scanner (main.py).

    Geeft UITSLUITEND SHORT-signalen terug die ook RSI-divergentie
    hebben - dit is de enige combinatie die in uitgebreid backtesten
    (213 markten, out-of-sample gevalideerd) consistent winstgevend
    bleek. LONG-signalen worden bewust genegeerd.

    Geeft None terug als er geen (geldig) signaal is.
    """

    i = len(df) - 1

    if i < max(divergence_lookback, ema_slope_lookback) + 1:
        return None

    row = df.iloc[i]

    entry = _determine_pullback_signal(df, i, ema_slope_lookback, rsi_low, rsi_high)

    if entry != "SHORT":
        return None

    bullish_div, bearish_div = detect_rsi_divergence(
        df.iloc[: i + 1], lookback=divergence_lookback, order=divergence_order
    )

    if not bearish_div:
        return None

    if pd.isna(row["ATR"]) or row["ATR"] <= 0:
        return None

    stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
    take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

    return {
        "direction": entry,
        "entry_price": row["Close"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rsi_divergence": True,
        "data_date": df.index[i],
    }


def simulate_pullback_trades(df, pair, atr_multiplier, rr,
                              ema_slope_lookback=5, rsi_low=35, rsi_high=60,
                              divergence_lookback=40, divergence_order=3):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de pullback-strategie (voor backtesting - LONG en SHORT
    worden allebei gesimuleerd zodat je ze kunt vergelijken, in
    tegenstelling tot check_latest_pullback_signal die alleen SHORT
    teruggeeft voor live gebruik).
    """

    trades = []
    position = None

    min_bars = 60

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

        entry = _determine_pullback_signal(df, i, ema_slope_lookback, rsi_low, rsi_high)

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
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades