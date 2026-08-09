"""
Donchian Channel breakout-strategie (basis van het originele Turtle
Trading-systeem).

Kernidee: puur objectief, geen trendlijnen of subjectieve interpretatie.
Koop zodra de slotkoers het hoogste punt van de afgelopen N dagen
doorbreekt; verkoop bij het laagste punt.

Uit eerste backtest bleek de PURE, ongefilterde versie zonder crypto
verlieslatend en LONG-gedomineerd - dit bestand voegt drie meetbare
kenmerken per trade toe (EMA-richting, volumebevestiging, uitbraak-
sterkte in ATR's) zodat objectief getest kan worden welke combinatie
daadwerkelijk helpt, i.p.v. filters blind toe te voegen.

Exit-logica identiek aan breakout/pullback (ATR-based SL, RR-based TP).
"""

import pandas as pd

from utils.risk import calculate_stop_loss, calculate_take_profit
from utils.donchian_indicator import add_donchian_channels
from utils.backtest import prepare_backtest_data
from utils.breakout_strategy import has_reliable_volume


def prepare_donchian_data(df, rsi_window=14, ema_span=21, channel_window=20):
    """
    Hergebruikt prepare_backtest_data (o.a. ATR, EMA21) en voegt de
    Donchian Channels toe.
    """

    df_prepared = prepare_backtest_data(df, rsi_window=rsi_window, ema_span=ema_span)
    df_prepared = add_donchian_channels(df_prepared, window=channel_window)

    return df_prepared


def _determine_donchian_signal(df, i):
    """
    Bepaalt of er op dag i een Donchian-breakout-signaal is.
    Geeft 'LONG', 'SHORT' of '-' terug.
    """

    row = df.iloc[i]

    if pd.isna(row["Donchian_upper"]) or pd.isna(row["Donchian_lower"]):
        return "-"

    if row["Close"] > row["Donchian_upper"]:
        return "LONG"

    if row["Close"] < row["Donchian_lower"]:
        return "SHORT"

    return "-"


def simulate_donchian_trades(df, pair, atr_multiplier, rr,
                              ema_slope_lookback=5, volume_multiplier=1.5):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de Donchian-breakout-strategie. Elke trade krijgt drie
    filterbare kenmerken mee: ema_aligned, volume_confirmed,
    breakout_strength_atr - voor achteraf objectief testen welke
    combinatie helpt.
    """

    use_volume = has_reliable_volume(df)

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

        entry = _determine_donchian_signal(df, i)

        if entry in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

            # Kenmerk 1: EMA21-richting sluit aan bij de breakout-richting?
            if i >= ema_slope_lookback and not pd.isna(row["EMA21"]):
                ema_prev = df["EMA21"].iloc[i - ema_slope_lookback]
                ema_now = row["EMA21"]
                if entry == "LONG":
                    ema_aligned = ema_now > ema_prev
                else:
                    ema_aligned = ema_now < ema_prev
            else:
                ema_aligned = False

            # Kenmerk 2: volumebevestiging (waar beschikbaar)
            volume_confirmed = False
            if use_volume and "Volume" in df.columns:
                avg_volume = df["Volume"].iloc[i - 20: i].mean()
                if not pd.isna(avg_volume) and avg_volume > 0:
                    volume_confirmed = row["Volume"] > volume_multiplier * avg_volume

            # Kenmerk 3: hoe overtuigend is de uitbraak (in ATR's voorbij het kanaal)?
            if entry == "LONG":
                breakout_strength_atr = round((row["Close"] - row["Donchian_upper"]) / row["ATR"], 3)
            else:
                breakout_strength_atr = round((row["Donchian_lower"] - row["Close"]) / row["ATR"], 3)

            position = {
                "pair": pair,
                "direction": entry,
                "entry_date": date,
                "entry_price": row["Close"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "ema_aligned": ema_aligned,
                "volume_confirmed": volume_confirmed,
                "volume_used": use_volume,
                "breakout_strength_atr": breakout_strength_atr,
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades


def check_latest_donchian_signal(df, atr_multiplier, rr, ema_slope_lookback=5, volume_multiplier=1.5):
    """
    Checkt ALLEEN de laatste dag van de data op een Donchian-signaal.
    Voor gebruik in de live scanner.

    Geeft UITSLUITEND LONG-signalen terug - uit uitgebreid backtesten
    (213 markten, meerdere filters, out-of-sample over twee periodes)
    bleek LONG-only de sterkste en meest stabiele combinatie, terwijl
    SHORT structureel verlieslatend was. Dit is een bewuste, data-
    gedreven keuze.
    """

    i = len(df) - 1

    if i < max(60, ema_slope_lookback):
        return None

    row = df.iloc[i]

    entry = _determine_donchian_signal(df, i)

    if entry != "LONG":
        return None

    if pd.isna(row["ATR"]) or row["ATR"] <= 0:
        return None

    stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
    take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

    use_volume = has_reliable_volume(df)
    volume_confirmed = False
    if use_volume and "Volume" in df.columns:
        avg_volume = df["Volume"].iloc[i - 20: i].mean()
        if not pd.isna(avg_volume) and avg_volume > 0:
            volume_confirmed = row["Volume"] > volume_multiplier * avg_volume

    ema_prev = df["EMA21"].iloc[i - ema_slope_lookback]
    ema_now = row["EMA21"]
    ema_aligned = ema_now > ema_prev

    return {
        "direction": entry,
        "entry_price": row["Close"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "ema_aligned": ema_aligned,
        "volume_confirmed": volume_confirmed,
        "data_date": df.index[i],
    }