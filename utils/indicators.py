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