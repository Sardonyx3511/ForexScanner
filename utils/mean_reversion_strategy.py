"""
Mean Reversion swingstrategie.

Kernidee: het TEGENOVERGESTELDE van breakout/pullback. Die twee
strategieën gokken op een DOORZETTENDE beweging; mean reversion gokt
op een TERUGKEER naar het gemiddelde na een statistisch overdreven
uitschieter, en werkt bewust alleen in ZWAKKE/zijwaartse markten
(precies de marktomstandigheden die breakout/pullback juist negeren).

LONG-voorwaarden (SHORT is het spiegelbeeld):
1. Prijs sluit op of onder de onderste Bollinger Band (20, 2) - de
   markt is statistisch 'te ver' gezakt
2. RSI onder 30 - onafhankelijke bevestiging dat de daling overdreven is
3. ADX onder 25 - CRUCIALE voorwaarde: geen sterke trend gaande. Dit
   voorkomt 'de dip kopen' tijdens een sterke downtrend die gewoon
   doorzet (de klassieke manier waarop mean-reversion-traders geld
   verliezen)
4. Bevestiging: een candle sluit terug BINNEN de band - bevestigt de
   afwijzing, voorkomt te vroeg instappen terwijl de daling nog doorzet

Exit-logica is FUNDAMENTEEL anders dan breakout/pullback:
- Take Profit = de Bollinger-middenlijn (SMA20) op het instapmoment -
  een terugkeer naar het gemiddelde, geen vast RR-veelvoud
- Stop Loss = ATR-gebaseerd, zelfde mechaniek als de andere strategieën

Omdat het doel geen vast RR-veelvoud is, verschilt de daadwerkelijke
risk/reward per trade - de statistiekfunctie in dit bestand houdt daar
rekening mee (zie compute_variable_rr_stats), in tegenstelling tot de
compute_stats() in utils/backtest.py die van een vaste RR uitgaat.
"""

import pandas as pd

from utils.risk import calculate_stop_loss


def _determine_mean_reversion_signal(df, i, rsi_oversold=30, rsi_overbought=70, adx_max=25):
    """
    Bepaalt of er op dag i een mean-reversion-entry-signaal is.
    Geeft 'LONG', 'SHORT' of '-' terug.
    """

    row = df.iloc[i]

    if pd.isna(row["BB_lower"]) or pd.isna(row["RSI"]) or pd.isna(row["ADX"]):
        return "-"

    if i < 1:
        return "-"

    adx_weak = row["ADX"] < adx_max

    if not adx_weak:
        return "-"

    prev_row = df.iloc[i - 1]

    # LONG: gisteren op/onder de onderband, RSI oversold, vandaag terug erboven
    touched_lower = prev_row["Close"] <= prev_row["BB_lower"]
    back_inside_up = row["Close"] > row["BB_lower"]

    if touched_lower and back_inside_up and row["RSI"] < rsi_oversold:
        return "LONG"

    # SHORT: gisteren op/boven de bovenband, RSI overbought, vandaag terug eronder
    touched_upper = prev_row["Close"] >= prev_row["BB_upper"]
    back_inside_down = row["Close"] < row["BB_upper"]

    if touched_upper and back_inside_down and row["RSI"] > rsi_overbought:
        return "SHORT"

    return "-"


def compute_variable_rr_stats(trades):
    """
    Statistieken voor trades met een VARIABELE risk/reward per trade
    (in tegenstelling tot utils.backtest.compute_stats, die van een
    vaste RR voor de hele set uitgaat). Elke trade draagt zijn eigen
    'risk_reward' veld (tp_afstand / sl_afstand) mee.
    """

    closed = [t for t in trades if t["outcome"] in ("WIN", "LOSS")]
    n = len(closed)

    if n == 0:
        return {
            "Aantal trades": 0,
            "Winrate (%)": 0,
            "Gem. resultaat (R)": 0,
            "Totaal resultaat (R)": 0,
            "Max drawdown (R)": 0,
            "Gem. trade-duur (dagen)": 0,
            "Nog open aan einde data": len(trades) - n,
        }

    wins = [t for t in closed if t["outcome"] == "WIN"]
    losses = [t for t in closed if t["outcome"] == "LOSS"]

    winrate = round(len(wins) / n * 100, 1)

    equity = []
    cum = 0
    for t in closed:
        r = t["risk_reward"] if t["outcome"] == "WIN" else -1
        cum += r
        equity.append(cum)

    total_r = round(equity[-1], 2)
    avg_r = round(total_r / n, 3)

    peak = 0
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        if dd > max_dd:
            max_dd = dd

    avg_duration = round(sum(t["bars_held"] for t in closed) / n, 1)
    avg_rr = round(sum(t["risk_reward"] for t in closed) / n, 2)

    return {
        "Aantal trades": n,
        "Winrate (%)": winrate,
        "Gem. resultaat (R)": avg_r,
        "Totaal resultaat (R)": total_r,
        "Max drawdown (R)": round(max_dd, 2),
        "Gem. trade-duur (dagen)": avg_duration,
        "Gem. RR per trade": avg_rr,
        "Nog open aan einde data": len(trades) - n,
        "Aantal wins": len(wins),
        "Aantal losses": len(losses),
    }


def simulate_mean_reversion_trades(df, pair, atr_multiplier,
                                    rsi_oversold=30, rsi_overbought=70, adx_max=25):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de mean-reversion-strategie. TP = Bollinger-middenlijn op
    het instapmoment (vast niveau voor de duur van de trade, niet
    dynamisch bijgewerkt), SL = ATR-gebaseerd.
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

        entry = _determine_mean_reversion_signal(df, i, rsi_oversold, rsi_overbought, adx_max)

        if entry in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            entry_price = row["Close"]
            stop_loss = calculate_stop_loss(entry_price, row["ATR"], atr_multiplier, entry)
            take_profit = row["BB_mid"]  # doel = terugkeer naar het gemiddelde

            # Sanity-check: het doel moet aan de juiste kant liggen
            # (voor LONG boven entry, voor SHORT eronder). Zo niet,
            # sla deze trade over (kan voorkomen bij randgevallen).
            if entry == "LONG" and take_profit <= entry_price:
                continue
            if entry == "SHORT" and take_profit >= entry_price:
                continue

            sl_distance = abs(entry_price - stop_loss)
            tp_distance = abs(take_profit - entry_price)

            if sl_distance == 0:
                continue

            risk_reward = round(tp_distance / sl_distance, 3)

            position = {
                "pair": pair,
                "direction": entry,
                "entry_date": date,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "risk_reward": risk_reward,
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades


def check_latest_mean_reversion_signal(df, atr_multiplier,
                                        rsi_oversold=30, rsi_overbought=70, adx_max=25):
    """
    Checkt ALLEEN de laatste dag van de data op een mean-reversion-
    signaal. Voor gebruik in de live scanner. Geeft None terug als er
    geen (geldig) signaal is.
    """

    i = len(df) - 1

    if i < 1:
        return None

    row = df.iloc[i]

    entry = _determine_mean_reversion_signal(df, i, rsi_oversold, rsi_overbought, adx_max)

    if entry not in ("LONG", "SHORT"):
        return None

    if pd.isna(row["ATR"]) or row["ATR"] <= 0:
        return None

    entry_price = row["Close"]
    stop_loss = calculate_stop_loss(entry_price, row["ATR"], atr_multiplier, entry)
    take_profit = row["BB_mid"]

    if entry == "LONG" and take_profit <= entry_price:
        return None
    if entry == "SHORT" and take_profit >= entry_price:
        return None

    return {
        "direction": entry,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "data_date": df.index[i],
    }