import ta


def calculate_kst(data):

    roc1 = data["Close"].pct_change(10) * 100
    roc2 = data["Close"].pct_change(15) * 100
    roc3 = data["Close"].pct_change(20) * 100
    roc4 = data["Close"].pct_change(30) * 100

    kst = (
        roc1.rolling(10).mean()
        + 2 * roc2.rolling(10).mean()
        + 3 * roc3.rolling(10).mean()
        + 4 * roc4.rolling(15).mean()
    )

    signal = kst.rolling(9).mean()

    return kst, signal


def add_adx(data):
    """
    Voegt ADX, DI+ en DI- toe aan de DataFrame.
    """

    adx = ta.trend.ADXIndicator(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=14
    )

    data["ADX"] = adx.adx()
    data["DI+"] = adx.adx_pos()
    data["DI-"] = adx.adx_neg()

    return data


def add_atr(data):
    """
    Voegt ATR toe aan de DataFrame.
    """

    atr = ta.volatility.AverageTrueRange(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=14
    )

    data["ATR"] = atr.average_true_range()

    return data


def add_stochastic(data):
    """
    Voegt Stochastic 8,3,3 toe.
    """

    stoch = ta.momentum.StochasticOscillator(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=8,
        smooth_window=3
    )

    data["K"] = stoch.stoch()
    data["D"] = data["K"].rolling(3).mean()

    return data


def add_rsi(data, window=14):
    """
    Voegt RSI toe aan de DataFrame.
    """

    rsi = ta.momentum.RSIIndicator(
        close=data["Close"],
        window=window
    )

    data["RSI"] = rsi.rsi()

    return data


def add_ema(data, span=21, column_name="EMA21"):
    """
    Voegt een EMA toe aan de DataFrame.
    """

    data[column_name] = data["Close"].ewm(span=span, adjust=False).mean()

    return data


def add_bollinger_bands(data, window=20, window_dev=2):
    """
    Voegt Bollinger Bands toe: bovenband, onderband, middenlijn en
    de bandbreedte als percentage van de middenlijn (BB_width) - dat
    laatste is de maatstaf voor 'squeeze' (volatiliteitscompressie).
    """

    bb = ta.volatility.BollingerBands(
        close=data["Close"],
        window=window,
        window_dev=window_dev,
    )

    data["BB_upper"] = bb.bollinger_hband()
    data["BB_lower"] = bb.bollinger_lband()
    data["BB_mid"] = bb.bollinger_mavg()
    data["BB_width"] = bb.bollinger_wband()

    return data


def add_keltner_channels(data, window=20, atr_window=20, multiplier=1.5):
    """
    Voegt Keltner Channels toe: een EMA-middenlijn met ATR-gebaseerde
    bovenband/onderband. Wordt gebruikt in combinatie met Bollinger
    Bands voor de 'Squeeze Momentum'-detectie: een squeeze is 'aan'
    wanneer de Bollinger Bands volledig binnen de Keltner Channel
    vallen (John Carter's TTM Squeeze-definitie).
    """

    kc = ta.volatility.KeltnerChannel(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=window,
        window_atr=atr_window,
        multiplier=multiplier,
    )

    data["KC_upper"] = kc.keltner_channel_hband()
    data["KC_lower"] = kc.keltner_channel_lband()
    data["KC_mid"] = kc.keltner_channel_mband()

    return data


def get_ema_distance_atr(latest_row, ema_column="EMA21"):
    """
    Afstand van de prijs tot de EMA, uitgedrukt in ATR's. Robuuster dan
    een percentage omdat het meebeweegt met de volatiliteit van elk paar.
    """

    if latest_row["ATR"] and latest_row["ATR"] > 0:
        return (latest_row["Close"] - latest_row[ema_column]) / latest_row["ATR"]

    return 0


def _dedupe_swings(indices, price, order, mode):
    """
    Voegt swing points die vlak bij elkaar liggen (binnen `order` candles)
    samen tot één punt - het meest extreme punt van dat clustertje.
    Voorkomt dat een vlakke bodem/top als meerdere losse swings telt.
    """

    if not indices:
        return []

    clusters = [[indices[0]]]

    for idx in indices[1:]:
        if idx - clusters[-1][-1] <= order:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])

    result = []
    for cluster in clusters:
        if mode == "min":
            result.append(min(cluster, key=lambda i: price[i]))
        else:
            result.append(max(cluster, key=lambda i: price[i]))

    return result


def detect_rsi_divergence(data, lookback=40, order=3):
    """
    Detecteert bullish/bearish RSI-divergentie binnen de laatste
    `lookback` candles, op basis van swing highs/lows in de prijs.

    - Bullish divergentie: prijs zet een lagere low, RSI zet een hogere low
      (momentum zwakt af terwijl prijs nog daalt -> mogelijke bodem)
    - Bearish divergentie: prijs zet een hogere high, RSI zet een lagere high
      (momentum zwakt af terwijl prijs nog stijgt -> mogelijke top)

    `order` bepaalt hoeveel candles links/rechts een punt lager/hoger
    moet zijn om als swing point te tellen (hogere waarde = minder,
    maar significantere swings).

    Geeft (bullish_divergence: bool, bearish_divergence: bool) terug.
    """

    recent = data.tail(lookback).reset_index(drop=True)

    if len(recent) < (order * 2 + 2) or "RSI" not in recent.columns:
        return False, False

    price = recent["Close"]
    rsi = recent["RSI"]

    raw_lows = []
    raw_highs = []

    for i in range(order, len(recent) - order):

        window_price = price[i - order : i + order + 1]

        if price[i] == window_price.min():
            raw_lows.append(i)

        if price[i] == window_price.max():
            raw_highs.append(i)

    swing_lows = _dedupe_swings(raw_lows, price, order, mode="min")
    swing_highs = _dedupe_swings(raw_highs, price, order, mode="max")

    bullish_divergence = False
    if len(swing_lows) >= 2:
        i1, i2 = swing_lows[-2], swing_lows[-1]
        if price[i2] < price[i1] and rsi[i2] > rsi[i1]:
            bullish_divergence = True

    bearish_divergence = False
    if len(swing_highs) >= 2:
        i1, i2 = swing_highs[-2], swing_highs[-1]
        if price[i2] > price[i1] and rsi[i2] < rsi[i1]:
            bearish_divergence = True

    return bullish_divergence, bearish_divergence