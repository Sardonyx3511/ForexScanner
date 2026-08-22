"""
Donchian Channel breakout-strategie (basis van het originele Turtle
Trading-systeem).

Kernidee: puur objectief, geen trendlijnen of subjectieve interpretatie.
Koop zodra de slotkoers het hoogste punt van de afgelopen N dagen
doorbreekt; verkoop bij het laagste punt.

GEVALIDEERDE FILTERS (uit uitgebreid backtesten, 213 markten):
- Alleen LONG (SHORT bleek structureel verlieslatend, ongeacht filter)
- EMA21-uitlijning: EMA21 moet in dezelfde richting lopen als de trade
- Uitbraaksterkte >= 0.75 ATR: de slotkoers moet minstens 0.75x de ATR
  voorbij het kanaal liggen, niet slechts een marginale overschrijding.
  Dit bleek het omslagpunt: winrate en gemiddeld resultaat per trade
  bereiken hier hun piek (39,7% winrate, 0,19R/trade), en een hogere
  drempel (1.0+ ATR) verzwakt de kwaliteit juist weer en verliest de
  brede spreiding over assetklasses. Vermindert het aantal signalen
  met ~75% t.o.v. de ongefilterde versie, met een duidelijk betere
  kwaliteit (drawdown van 63R naar 18R).

Exit-logica identiek aan breakout/pullback (ATR-based SL, RR-based TP).
"""

import pandas as pd

from utils.risk import calculate_stop_loss, calculate_take_profit
from utils.donchian_indicator import add_donchian_channels
from utils.backtest import prepare_backtest_data
from utils.breakout_strategy import has_reliable_volume


# Vaste, gevalideerde drempel voor de uitbraaksterkte
MIN_BREAKOUT_STRENGTH_ATR = 0.75


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


def _compute_features(df, i, entry):
    """
    Berekent de meetbare kenmerken (EMA-uitlijning, volumebevestiging,
    uitbraaksterkte) voor een gegeven signaal op dag i.
    """

    row = df.iloc[i]

    ema_aligned = False
    if i >= 5 and not pd.isna(row["EMA21"]):
        ema_prev = df["EMA21"].iloc[i - 5]
        ema_now = row["EMA21"]
        if entry == "LONG":
            ema_aligned = ema_now > ema_prev
        else:
            ema_aligned = ema_now < ema_prev

    volume_confirmed = False
    use_volume = has_reliable_volume(df)
    if use_volume and "Volume" in df.columns:
        avg_volume = df["Volume"].iloc[i - 20: i].mean()
        if not pd.isna(avg_volume) and avg_volume > 0:
            volume_confirmed = row["Volume"] > 1.5 * avg_volume

    if entry == "LONG":
        breakout_strength_atr = round((row["Close"] - row["Donchian_upper"]) / row["ATR"], 3)
    else:
        breakout_strength_atr = round((row["Donchian_lower"] - row["Close"]) / row["ATR"], 3)

    return ema_aligned, volume_confirmed, breakout_strength_atr


def simulate_donchian_trades(df, pair, atr_multiplier, rr):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de Donchian-breakout-strategie. Elke trade krijgt de
    filterbare kenmerken mee (voor eventueel toekomstig hertesten),
    maar simuleert zelf nog ONGEFILTERD (LONG+SHORT, alle sterktes) -
    het live-gebruik in check_latest_donchian_signal past wél de
    gevalideerde filters toe. Dit scheiden houdt backtesten flexibel.
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

        entry = _determine_donchian_signal(df, i)

        if entry in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

            ema_aligned, volume_confirmed, breakout_strength_atr = _compute_features(df, i, entry)

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

    Past de VOLLEDIG GEVALIDEERDE filters toe:
    - Uitsluitend LONG (SHORT structureel verlieslatend)
    - EMA21 moet in dezelfde richting lopen (ema_aligned)
    - Uitbraaksterkte >= 0.75 ATR (MIN_BREAKOUT_STRENGTH_ATR)

    Geeft None terug als niet aan ALLE eisen wordt voldaan.
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

    ema_aligned, volume_confirmed, breakout_strength_atr = _compute_features(df, i, entry)

    if not ema_aligned:
        return None

    if breakout_strength_atr < MIN_BREAKOUT_STRENGTH_ATR:
        return None

    stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
    take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

    return {
        "direction": entry,
        "entry_price": row["Close"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "ema_aligned": ema_aligned,
        "volume_confirmed": volume_confirmed,
        "breakout_strength_atr": breakout_strength_atr,
        "data_date": df.index[i],
    }