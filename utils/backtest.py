"""
Backtest-engine voor de Forex Scanner.

Simuleert de KST/DMI/ADX/Stochastic-strategie over historische data en
meet de daadwerkelijke prestaties: aantal trades, winrate, gemiddelde
winst/verlies, maximale drawdown en gemiddelde trade-duur.

Belangrijk ontwerpkeuze: de weekly trend gebruikt hier alleen VOLLEDIG
AFGESLOTEN weken (shift(1) + backward-merge), in tegenstelling tot de
live scanner die de nog lopende week meeneemt. Dit voorkomt lookahead
bias in de backtest. Zie de uitleg in het bijbehorende gesprek.

Vereenvoudigingen in v1 (transparant, geen slippage/gaps gemodelleerd):
- Exit gebeurt exact op de Stop Loss- of Take Profit-prijs (geen slippage).
- Bij een dag waarop zowel SL als TP binnen de High/Low-range vallen,
  wordt conservatief aangenomen dat de Stop Loss als eerste geraakt wordt.
- Eén open trade per paar tegelijk (geen pyramiding/meerdere posities
  op hetzelfde paar).
- Risico per trade is een vast bedrag (RISK_PERCENT van het originele
  ACCOUNT_SIZE), niet compounding op de groeiende/krimpende balance.
"""

import pandas as pd

from utils.indicators import (
    calculate_kst,
    add_adx,
    add_atr,
    add_stochastic,
    add_rsi,
    add_ema,
    get_ema_distance_atr,
    detect_rsi_divergence,
)
from utils.risk import calculate_stop_loss, calculate_take_profit


def prepare_backtest_data(df, rsi_window=14, ema_span=21):
    """
    Voegt alle indicatoren toe aan een daily OHLC-DataFrame, inclusief
    een lookahead-vrije 'Weekly KST' / 'Weekly KST Signal' kolom,
    RSI en EMA21.
    """

    df = df.copy()

    df["KST"], df["KST Signal"] = calculate_kst(df)

    weekly = df.resample("W").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    )
    weekly["KST"], weekly["KST Signal"] = calculate_kst(weekly)

    # Alleen volledig afgesloten weken gebruiken (voorkomt lookahead)
    weekly_shifted = weekly.shift(1)
    weekly_shifted = weekly_shifted.rename(
        columns={"KST": "Weekly KST", "KST Signal": "Weekly KST Signal"}
    )

    date_col = df.index.name or "Date"

    df_reset = df.reset_index().rename(columns={df.index.name or "index": date_col})
    weekly_reset = weekly_shifted.reset_index().rename(
        columns={weekly_shifted.index.name or "index": date_col}
    )

    merged = pd.merge_asof(
        df_reset.sort_values(date_col),
        weekly_reset[[date_col, "Weekly KST", "Weekly KST Signal"]].sort_values(date_col),
        on=date_col,
        direction="backward",
    )
    merged = merged.set_index(date_col)

    merged = add_adx(merged)
    merged = add_atr(merged)
    merged = add_stochastic(merged)
    merged = add_rsi(merged, window=rsi_window)
    merged = add_ema(merged, span=ema_span, column_name="EMA21")

    return merged


def _determine_signal(row, adx_tail_max, adx_min, stoch_oversold, stoch_overbought,
                       prev_k, prev_d):
    """
    Repliceert de entry-logica van de live scanner voor één dag.
    Geeft (entry, adx_status) terug.
    """

    if pd.isna(row["Weekly KST"]) or pd.isna(row["KST"]):
        return "-", "WEAK"

    trend = "BULL" if row["KST"] > row["KST Signal"] else "BEAR"
    weekly_trend = "BULL" if row["Weekly KST"] > row["Weekly KST Signal"] else "BEAR"
    dmi = "BULL" if row["DI+"] > row["DI-"] else "BEAR"

    if row["ADX"] >= adx_min:
        adx_status = "STRONG"
    elif adx_tail_max >= adx_min:
        adx_status = "RECENT"
    else:
        adx_status = "WEAK"

    bull_cross = (prev_k <= prev_d) and (row["K"] > row["D"])
    bear_cross = (prev_k >= prev_d) and (row["K"] < row["D"])

    entry = "-"

    if trend == "BULL" and trend == weekly_trend and bull_cross and row["K"] > row["D"]:
        entry = "LONG"

    elif trend == "BEAR" and trend == weekly_trend and bear_cross and row["K"] < row["D"]:
        entry = "SHORT"

    return entry, adx_status


def simulate_trades(df, pair, atr_multiplier, rr, adx_min, stoch_oversold, stoch_overbought,
                     divergence_lookback=40, divergence_order=3,
                     ema_extended_threshold_atr=3):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de scanner-strategie. Geeft een lijst van trade-dicts terug.

    Elke trade krijgt ook 'rsi_divergence' en 'ema_extended' mee, zodat
    achteraf te analyseren is of deze kenmerken samenhangen met betere
    of slechtere uitkomsten.
    """

    trades = []
    position = None

    min_bars = 60  # genoeg historie voor de langste indicator (KST-30)

    for i in range(min_bars, len(df)):

        row = df.iloc[i]
        date = df.index[i]

        # -----------------------------------
        # Open positie? Check eerst op exit.
        # -----------------------------------
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

            else:  # SHORT
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

            continue  # één trade tegelijk: geen nieuwe entry op dezelfde dag

        # -----------------------------------
        # Geen open positie: check op een nieuw signaal
        # -----------------------------------
        adx_tail_max = df["ADX"].iloc[max(0, i - 4): i + 1].max()
        prev_k = df["K"].iloc[i - 1]
        prev_d = df["D"].iloc[i - 1]

        entry, adx_status = _determine_signal(
            row, adx_tail_max, adx_min, stoch_oversold, stoch_overbought, prev_k, prev_d
        )

        if entry in ("LONG", "SHORT") and adx_status != "WEAK":

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

            # RSI-divergentie: alleen berekenen op entry-dagen (relatief
            # zeldzaam), dus geen performance-probleem om dit hier te doen
            # in plaats van voor elke dag in de hele backtest.
            trend = "BULL" if row["KST"] > row["KST Signal"] else "BEAR"
            bullish_div, bearish_div = detect_rsi_divergence(
                df.iloc[: i + 1], lookback=divergence_lookback, order=divergence_order
            )
            rsi_divergence = (
                (trend == "BULL" and bullish_div)
                or (trend == "BEAR" and bearish_div)
            )

            ema_distance_atr = get_ema_distance_atr(row, ema_column="EMA21")
            ema_extended = abs(ema_distance_atr) > ema_extended_threshold_atr

            position = {
                "pair": pair,
                "direction": entry,
                "entry_date": date,
                "entry_price": row["Close"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "rsi_divergence": rsi_divergence,
                "ema_extended": ema_extended,
                "ema_distance_atr": round(ema_distance_atr, 2),
            }

    # Trade die aan het einde van de data nog open staat: niet meegeteld
    # in de win/loss-statistieken (uitkomst nog onbekend), wel gelogd.
    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades


def compute_stats(trades, rr):
    """
    Berekent samenvattende statistieken over een lijst trades.
    Rendement wordt uitgedrukt in R (1R = het risicobedrag per trade).
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
        r = rr if t["outcome"] == "WIN" else -1
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

    avg_duration = round(
        sum(t["bars_held"] for t in closed) / n, 1
    )

    return {
        "Aantal trades": n,
        "Winrate (%)": winrate,
        "Gem. resultaat (R)": avg_r,
        "Totaal resultaat (R)": total_r,
        "Max drawdown (R)": round(max_dd, 2),
        "Gem. trade-duur (dagen)": avg_duration,
        "Nog open aan einde data": len(trades) - n,
        "Aantal wins": len(wins),
        "Aantal losses": len(losses),
    }