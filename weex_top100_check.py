"""
Weex perpetual futures - top 100 op 24-uurs volume (alleen testen).

Doel:
  1. De top N paren op handelsvolume bepalen.
  2. De ruwe marktinfo van een paar paren tonen, om te zien welk veld
     echte crypto onderscheidt van aandelen/grondstoffen (TOYOTA, XPT, ...).
  3. Per paar controleren of er genoeg dagcandles zijn (>= 150).
  4. Alles opslaan in weex_top_pairs.csv.

Gebruik:
    python weex_top100_check.py
"""

import sys
import csv
import json
import time

try:
    import ccxt
except ImportError:
    print("ccxt is niet geinstalleerd. Draai eerst:  pip install ccxt")
    sys.exit(1)


TOP_N = 100
MIN_DAYS_NEEDED = 150
SLEEP_BETWEEN_CALLS = 0.3
INSPECT_BASES = ["BTC", "CELR", "TOYOTA", "XPT", "TTWO"]


def get_quote_volume(ticker):
    """
    Haalt het 24-uurs volume in USDT uit een CCXT-ticker.
    Gebruikt quoteVolume, en valt terug op baseVolume x laatste koers.
    Geeft 0.0 terug als niets bruikbaars aanwezig is.
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


def rank_by_volume(swaps, tickers):
    """
    Sorteert markten van hoog naar laag volume.
    Geeft een lijst (markt, volume) terug.
    """
    ranked = []
    for m in swaps:
        volume = get_quote_volume(tickers.get(m["symbol"]))
        ranked.append((m, volume))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def main():
    print("=== Weex perpetual futures - top 100 op volume ===")
    print()

    exchange = ccxt.weex({"options": {"defaultType": "swap"}})
    markets = exchange.load_markets()

    swaps = [
        m for m in markets.values()
        if m.get("swap") and m.get("quote") == "USDT" and m.get("active", True) is not False
    ]
    print(f"Perpetual USDT-paren: {len(swaps)}")

    # --- Ruwe marktinfo van een paar paren ---
    print()
    print("=== Ruwe marktinfo (zoek een veld dat crypto van aandelen scheidt) ===")
    for base in INSPECT_BASES:
        match = [m for m in swaps if m.get("base") == base]
        if not match:
            print(f"\n{base}: niet gevonden")
            continue
        m = match[0]
        print(f"\n--- {m['symbol']} ---")
        print(f"CCXT-velden: type={m.get('type')} swap={m.get('swap')} "
              f"linear={m.get('linear')} contractSize={m.get('contractSize')}")
        print("info:")
        print(json.dumps(m.get("info"), indent=1, default=str)[:900])

    # --- Volumes ophalen ---
    print()
    print("Volumes ophalen...")
    try:
        tickers = exchange.fetch_tickers([m["symbol"] for m in swaps])
    except Exception as e:
        print(f"fetch_tickers mislukt: {type(e).__name__}: {e}")
        print("Probeer zonder lijst...")
        try:
            tickers = exchange.fetch_tickers()
        except Exception as e2:
            print(f"Ook dat mislukt: {type(e2).__name__}: {e2}")
            return

    ranked = rank_by_volume(swaps, tickers)
    with_volume = sum(1 for _, v in ranked if v > 0)
    print(f"Paren met bekend volume: {with_volume} van {len(ranked)}")

    if with_volume == 0:
        print("Geen enkel volume gevonden - de tickers bevatten geen quoteVolume/baseVolume.")
        sample_symbol = swaps[0]["symbol"]
        print(f"Voorbeeld-ticker {sample_symbol}:")
        print(json.dumps(tickers.get(sample_symbol), indent=1, default=str)[:900])
        return

    top = ranked[:TOP_N]

    # --- Geschiedenis checken per paar ---
    print()
    print(f"Geschiedenis checken voor de top {len(top)} (duurt even)...")
    print()

    rows = []
    enough = 0

    for rank, (m, volume) in enumerate(top, start=1):
        symbol = m["symbol"]
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=200)
            days = len(candles)
        except Exception as e:
            days = -1
            print(f"FOUT {symbol}: {type(e).__name__}: {str(e)[:80]}")

        ok = days >= MIN_DAYS_NEEDED
        if ok:
            enough += 1

        flag = "OK " if ok else "KORT"
        print(f"{rank:3}. {flag} {symbol:26} vol={volume:>16,.0f} USDT  dagen={days}")
        rows.append([rank, symbol, m.get("base"), round(volume, 2), days, ok])

        time.sleep(SLEEP_BETWEEN_CALLS)

    with open("weex_top_pairs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "symbol", "base", "quote_volume_usdt", "days_available", "enough_history"])
        writer.writerows(rows)

    print()
    print("=== Samenvatting ===")
    print(f"Top {len(top)} op volume: {enough} hebben >= {MIN_DAYS_NEEDED} dagen geschiedenis")
    print("Opgeslagen in: weex_top_pairs.csv")


if __name__ == "__main__":
    main()