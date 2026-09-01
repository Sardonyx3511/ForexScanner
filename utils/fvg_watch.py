"""
Fair Value Gap (FVG) Watch - puur informatief, GEEN kant-en-klare
trade-strategie. Detecteert waar recent een FVG/imbalance is ontstaan,
zodat je zelf kunt monitoren hoe de prijs zich daarna gedraagt.

Bullish FVG (bij i): Low[i] > High[i-2]
Bearish FVG (bij i): High[i] < Low[i-2]
"""

import pandas as pd


def add_fvg(df):
    """
    Detecteert Fair Value Gaps op elke dag. Voegt kolommen toe met de
    FVG-zone (boven/ondergrens), NaN als er geen FVG is op die dag.
    """

    df["FVG_bullish_low"] = float("nan")
    df["FVG_bullish_high"] = float("nan")
    df["FVG_bearish_low"] = float("nan")
    df["FVG_bearish_high"] = float("nan")

    for i in range(2, len(df)):

        high_2ago = df["High"].iloc[i - 2]
        low_2ago = df["Low"].iloc[i - 2]
        high_now = df["High"].iloc[i]
        low_now = df["Low"].iloc[i]

        if low_now > high_2ago:
            df.iloc[i, df.columns.get_loc("FVG_bullish_low")] = high_2ago
            df.iloc[i, df.columns.get_loc("FVG_bullish_high")] = low_now

        if high_now < low_2ago:
            df.iloc[i, df.columns.get_loc("FVG_bearish_low")] = high_now
            df.iloc[i, df.columns.get_loc("FVG_bearish_high")] = low_2ago

    return df


def check_recent_fvg_signals(df, lookback_days=5, min_gap_size_atr=0.0):
    """
    Checkt de laatste 'lookback_days' dagen op nieuw ontstane FVG's.

    min_gap_size_atr: filtert kleine, waarschijnlijk onbeduidende gaps
    eruit - een gap moet minstens dit veelvoud van de ATR groot zijn
    om meegenomen te worden. 0.0 = geen filter (alles tonen). Vereist
    een 'ATR'-kolom in df.

    Geeft een lijst terug (kan leeg zijn), met per FVG: richting,
    zone-grenzen, hoeveel dagen geleden, en of de huidige prijs al
    (deels) in de zone is teruggekeerd.
    """

    results = []

    last_index = len(df) - 1

    if last_index < 2:
        return results

    start_index = max(2, last_index - lookback_days + 1)
    current_close = df["Close"].iloc[last_index]

    for i in range(start_index, last_index + 1):

        row = df.iloc[i]
        days_ago = last_index - i

        atr_value = row["ATR"] if "ATR" in df.columns and not pd.isna(row["ATR"]) else None

        if not pd.isna(row["FVG_bullish_low"]):

            zone_low = row["FVG_bullish_low"]
            zone_high = row["FVG_bullish_high"]
            gap_size = zone_high - zone_low
            gap_size_atr = round(gap_size / atr_value, 2) if atr_value and atr_value > 0 else None

            if min_gap_size_atr <= 0 or (gap_size_atr is not None and gap_size_atr >= min_gap_size_atr):

                price_in_zone = zone_low <= current_close <= zone_high

                results.append({
                    "direction": "bullish",
                    "zone_low": round(zone_low, 5),
                    "zone_high": round(zone_high, 5),
                    "gap_size_atr": gap_size_atr,
                    "data_date": df.index[i],
                    "days_ago": days_ago,
                    "price_in_zone": price_in_zone,
                    "current_price": round(current_close, 5),
                })

        if not pd.isna(row["FVG_bearish_low"]):

            zone_low = row["FVG_bearish_low"]
            zone_high = row["FVG_bearish_high"]
            gap_size = zone_high - zone_low
            gap_size_atr = round(gap_size / atr_value, 2) if atr_value and atr_value > 0 else None

            if min_gap_size_atr <= 0 or (gap_size_atr is not None and gap_size_atr >= min_gap_size_atr):

                price_in_zone = zone_low <= current_close <= zone_high

                results.append({
                    "direction": "bearish",
                    "zone_low": round(zone_low, 5),
                    "zone_high": round(zone_high, 5),
                    "gap_size_atr": gap_size_atr,
                    "data_date": df.index[i],
                    "days_ago": days_ago,
                    "price_in_zone": price_in_zone,
                    "current_price": round(current_close, 5),
                })

    return results