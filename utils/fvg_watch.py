"""
Fair Value Gap (FVG) Watch - puur informatief, GEEN kant-en-klare
trade-strategie. Detecteert waar recent een FVG/imbalance is ontstaan.

Bullish FVG (bij i): Low[i] > High[i-2]
Bearish FVG (bij i): High[i] < Low[i-2]

SHELF-CONFLUENCE (extra kenmerk, geen harde eis):
Kijkt terug (vóór de gap ontstond) of er een historisch punt was
(een High of Low van een eerdere candle) dat precies binnen dezelfde
prijszone lag als de huidige FVG. Als dat zo is, heeft die zone eerder
al als reactieniveau gefungeerd - een soort bevestigd 'plateau', wat de
FVG mogelijk sterker maakt. Puur getrackt, nog niet als harde filter
toegepast.
"""

import pandas as pd


def add_fvg(df):
    """
    Detecteert Fair Value Gaps op elke dag.
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


def _check_shelf_confluence(df, gap_index, zone_low, zone_high, lookback=50):
    """
    Kijkt terug vanaf VOOR de gap ontstond of er een eerdere candle-
    High of -Low precies in [zone_low, zone_high] valt.

    Geeft (heeft_shelf: bool, dagen_terug: int of None) terug.
    """

    start = max(0, gap_index - 2 - lookback)
    end = gap_index - 2

    if end <= start:
        return False, None

    match_indices = []

    for idx in range(start, end):
        h = df["High"].iloc[idx]
        l = df["Low"].iloc[idx]
        if zone_low <= h <= zone_high or zone_low <= l <= zone_high:
            match_indices.append(idx)

    if not match_indices:
        return False, None

    most_recent_match = max(match_indices)
    days_back = (gap_index - 2) - most_recent_match

    return True, days_back


def check_recent_fvg_signals(df, lookback_days=5, min_gap_size_atr=0.0, shelf_lookback=50):
    """
    Checkt de laatste 'lookback_days' dagen op nieuw ontstane FVG's.
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

        for direction, low_col, high_col in [
            ("bullish", "FVG_bullish_low", "FVG_bullish_high"),
            ("bearish", "FVG_bearish_low", "FVG_bearish_high"),
        ]:

            if pd.isna(row[low_col]):
                continue

            zone_low = row[low_col]
            zone_high = row[high_col]
            gap_size = zone_high - zone_low
            gap_size_atr = round(gap_size / atr_value, 2) if atr_value and atr_value > 0 else None

            if min_gap_size_atr > 0 and (gap_size_atr is None or gap_size_atr < min_gap_size_atr):
                continue

            has_shelf, shelf_days_back = _check_shelf_confluence(
                df, i, zone_low, zone_high, lookback=shelf_lookback
            )

            price_in_zone = zone_low <= current_close <= zone_high

            results.append({
                "direction": direction,
                "zone_low": round(zone_low, 5),
                "zone_high": round(zone_high, 5),
                "gap_size_atr": gap_size_atr,
                "data_date": df.index[i],
                "days_ago": days_ago,
                "price_in_zone": price_in_zone,
                "current_price": round(current_close, 5),
                "has_shelf": has_shelf,
                "shelf_days_back": shelf_days_back,
            })

    return results