"""
Weex perpetual futures - datacheck (alleen testen, raakt de scanner niet aan).

Doel: uitzoeken
  1. welke perpetual-paren (USDT) Weex via CCXT aanbiedt,
  2. hoeveel dagcandles (1d) er per paar beschikbaar zijn,
  3. of de ruwe contract-API bereikbaar is (diagnostiek).

Installeren (eenmalig):
    pip install ccxt requests

Gebruik:
    python weex_data_check.py          -> steekproef van ~15 paren
    python weex_data_check.py --all    -> alle perpetual-paren (duurt langer)
"""

import sys
import time
import random

import requests

try:
    import ccxt
except ImportError:
    print("ccxt is niet geinstalleerd. Draai eerst:  pip install ccxt")
    sys.exit(1)


MIN_DAYS_NEEDED = 220      # ruim genoeg voor EMA200 + opwarming
CANDLE_LIMIT = 1000
SLEEP_BETWEEN_CALLS = 0.3  # rustig aan, om rate limits te vermijden
SAMPLE_SIZE = 15
ALWAYS_INCLUDE = ["BTC", "ETH", "SOL"]


def summarize_candles(candles):
    """
    Vat een lijst CCXT-candles samen: [timestamp_ms, open, high, low, close, volume].
    Geeft (aantal, eerste_datum, laatste_datum) terug, of (0, None, None).
    """
    if not candles:
        return 0, None, None

    first = time.strftime("%Y-%m-%d", time.gmtime(candles[0][0] / 1000))
    last = time.strftime("%Y-%m-%d", time.gmtime(candles[-1][0] / 1000))
    return len(candles), first, last


def probe_raw_contract_api():
    """
    Diagnostiek: probeert de ruwe contract-API direct aan te roepen.
    De exacte parameternamen zijn een aanname - de uitvoer laat zien
    wat de API daadwerkelijk teruggeeft.
    """
    print()
    print("=== Ruwe contract-API probe ===")

    base = "https://api-contract.weex.com"

    for path, params in [
        ("/capi/v3/market/time", {}),
        ("/capi/v3/market/exchangeInfo", {}),
        ("/capi/v3/market/klines", {"symbol": "BTCUSDT", "interval": "1d", "limit": 5}),
    ]:
        try:
            r = requests.get(base + path, params=params, timeout=15)
            print(f"GET {path} -> HTTP {r.status_code}")
            print(f"   {r.text[:300]}")
        except Exception as e:
            print(f"GET {path} -> FOUT: {type(e).__name__}: {e}")


def main():
    check_all = "--all" in sys.argv

    print("=== Weex perpetual futures - datacheck ===")
    print()

    exchange = ccxt.weex({"options": {"defaultType": "swap"}})

    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"Markten laden mislukt: {type(e).__name__}: {e}")
        probe_raw_contract_api()
        return

    swaps = [
        m for m in markets.values()
        if m.get("swap") and m.get("quote") == "USDT" and m.get("active", True) is not False
    ]

    print(f"Totaal markten geladen: {len(markets)}")
    print(f"Perpetual USDT-paren:   {len(swaps)}")

    if not swaps:
        print("Geen perpetual-paren gevonden via CCXT - zie de ruwe API-probe hieronder.")
        probe_raw_contract_api()
        return

    if check_all:
        sample = swaps
    else:
        wanted = [m for m in swaps if m.get("base") in ALWAYS_INCLUDE]
        others = [m for m in swaps if m.get("base") not in ALWAYS_INCLUDE]
        random.seed(1)
        extra = random.sample(others, min(SAMPLE_SIZE - len(wanted), len(others)))
        sample = wanted + extra

    print(f"Paren die nu gecheckt worden: {len(sample)}")
    print()

    enough = 0
    failed = 0

    for m in sample:
        symbol = m["symbol"]
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=CANDLE_LIMIT)
            n, first, last = summarize_candles(candles)
            flag = "OK " if n >= MIN_DAYS_NEEDED else "TE KORT"
            if n >= MIN_DAYS_NEEDED:
                enough += 1
            print(f"{flag:8} {symbol:28} {n:5} dagen  ({first} t/m {last})")
        except Exception as e:
            failed += 1
            print(f"FOUT     {symbol:28} {type(e).__name__}: {str(e)[:100]}")

        time.sleep(SLEEP_BETWEEN_CALLS)

    print()
    print("=== Samenvatting ===")
    print(f"Gecheckt:                          {len(sample)}")
    print(f"Genoeg geschiedenis (>= {MIN_DAYS_NEEDED} dagen): {enough}")
    print(f"Te kort:                           {len(sample) - enough - failed}")
    print(f"Fout bij ophalen:                  {failed}")

    if failed == len(sample):
        print()
        print("Alle candle-calls mislukten - de ruwe API-probe hieronder laat zien waarom.")
        probe_raw_contract_api()


if __name__ == "__main__":
    main()