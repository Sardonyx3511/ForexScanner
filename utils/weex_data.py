"""
Weex perpetual futures als databron voor crypto.

Haalt de top N crypto-perpetuals (USDT) op, gerangschikt op 24-uurs
handelsvolume, met dagcandles in hetzelfde formaat als yfinance
(index = datum; kolommen Open, High, Low, Close, Volume).

Alleen ECHTE crypto: Weex lijst ook aandelen, ETF's en metalen als
perpetual. Die zijn te herkennen aan de marktinfo:
    contractType  == "PERPETUAL"   (crypto)   vs "TRADIFI_PERPETUAL"
    underlyingType == "COIN"       (crypto)   vs "Stocks" / "Metals"
Beide moeten kloppen, zodat een nieuw soort contract er vanzelf uit valt.

ccxt wordt pas bij gebruik geimporteerd: als ccxt ontbreekt, geeft de
functie een duidelijke fout en kan de scanner terugvallen op yfinance.
"""

import time

import pandas as pd


CRYPTO_CONTRACT_TYPE = "PERPETUAL"
CRYPTO_UNDERLYING_TYPE = "COIN"


def is_crypto_perpetual(market):
    """
    True als dit een actieve USDT-perpetual op echte crypto is
    (dus geen aandeel, ETF of metaal).
    """
    if not market.get("swap"):
        return False

    if market.get("quote") != "USDT":
        return False

    if market.get("active", True) is False:
        return False

    info = market.get("info") or {}

    return (
        info.get("contractType") == CRYPTO_CONTRACT_TYPE
        and info.get("underlyingType") == CRYPTO_UNDERLYING_TYPE
    )


def get_quote_volume(ticker):
    """
    24-uurs volume in USDT uit een CCXT-ticker: quoteVolume, of anders
    baseVolume x laatste koers. 0.0 als er niets bruikbaars is.
    """
    if not ticker:
        return 0.0

    quote_volume = ticker.get("quoteVolume")
    if quote_volume:
        return float(quote_volume)

    base_volume = ticker.get("baseVolume")
    last = ticker.get("last") or ticker.get("close")
    if base_volume and last:
        return float(base_volume) * float(last)

    return 0.0


def candles_to_dataframe(candles):
    """
    Zet CCXT-candles [timestamp_ms, open, high, low, close, volume] om
    naar een DataFrame in yfinance-formaat. Dubbele datums worden
    ontdubbeld, rijen met ontbrekende prijzen verwijderd.
    """
    df = pd.DataFrame(
        candles,
        columns=["timestamp", "Open", "High", "Low", "Close", "Volume"],
    )

    df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop(columns="timestamp").set_index("Date")

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    return df.astype(float)


def fetch_weex_crypto_data(
    top_n=100,
    min_days=150,
    candle_limit=1000,
    max_attempts=300,
    sleep_between_calls=0.25,
    exchange=None,
):
    """
    Haalt de top_n crypto-perpetuals op volume op, met dagcandles.

    Paren met minder dan min_days dagen geschiedenis worden overgeslagen
    en vervangen door het volgende paar op de ranglijst, zodat je tot
    top_n bruikbare paren komt (zolang er genoeg zijn).

    Geeft (data, stats) terug:
      data  = {symbool: (naam, DataFrame)}
      stats = dict met tellingen, om in de console te tonen

    Gooit een exception als Weex niet bereikbaar is - de aanroeper kan
    dan terugvallen op een andere bron.
    """

    if exchange is None:
        try:
            import ccxt
        except ImportError as e:
            raise RuntimeError("ccxt is niet geinstalleerd (pip install ccxt)") from e

        exchange = ccxt.weex({"options": {"defaultType": "swap"}})

    markets = exchange.load_markets()

    swaps = [
        m for m in markets.values()
        if m.get("swap") and m.get("quote") == "USDT" and m.get("active", True) is not False
    ]
    crypto = [m for m in swaps if is_crypto_perpetual(m)]

    stats = {
        "perpetuals_totaal": len(swaps),
        "crypto": len(crypto),
        "niet_crypto_uitgesloten": len(swaps) - len(crypto),
        "te_kort": 0,
        "fout": 0,
        "geladen": 0,
    }

    if not crypto:
        return {}, stats

    symbols = [m["symbol"] for m in crypto]

    try:
        tickers = exchange.fetch_tickers(symbols)
    except Exception:
        tickers = exchange.fetch_tickers()

    ranked = sorted(
        crypto,
        key=lambda m: get_quote_volume(tickers.get(m["symbol"])),
        reverse=True,
    )

    data = {}
    attempts = 0

    for m in ranked:

        if len(data) >= top_n or attempts >= max_attempts:
            break

        attempts += 1
        symbol = m["symbol"]

        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=candle_limit)
            df = candles_to_dataframe(candles)
        except Exception:
            stats["fout"] += 1
            time.sleep(sleep_between_calls)
            continue

        if len(df) < min_days:
            stats["te_kort"] += 1
        else:
            data[symbol] = (m.get("base") or symbol, df)

        time.sleep(sleep_between_calls)

    stats["geladen"] = len(data)

    return data, stats