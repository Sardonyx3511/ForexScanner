"""
test_patterns.py
Backtest van Ascending Triangle + Falling Wedge breakouts op jouw eigen markten.
Staat LOS van main.py: je live scanner wordt niet aangeraakt.

Plaatsing:
    scanner-map/
        main.py
        test_patterns.py          <- dit bestand
        config/settings.py
        utils/pattern_breakout.py <- de module

Starten:
    python test_patterns.py

Data wordt de eerste keer via yfinance gedownload en bewaard in de map
backtest_data/. Een volgende run gebruikt die bestanden (veel sneller).
Wil je verse data? Verwijder de map backtest_data/.
"""
import os
import time

import pandas as pd
import yfinance as yf

from config.settings import ALL_PAIRS, get_asset_class
from utils.pattern_breakout import Config, run_backtest, summarize

CACHE_DIR = "backtest_data"
os.makedirs(CACHE_DIR, exist_ok=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df = df[[c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]]
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["high"] > 0) & (df["low"] > 0)]
    return df.sort_index()


def _download(pair: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(pair, period=period, interval=interval,
                     multi_level_index=False, progress=False, auto_adjust=True)
    return _clean(df) if df is not None and not df.empty else pd.DataFrame()


def get_data(pair: str, timeframe: str) -> pd.DataFrame:
    """Daily: 5 jaar. 4h: yfinance heeft geen 4h, dus 1h (max 730 dagen)
    en zelf omzetten naar 4h-candles."""
    safe = pair.replace("=", "_").replace("^", "_").replace("/", "_")
    path = os.path.join(CACHE_DIR, f"{safe}_{timeframe}.csv")
    if os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)

    if timeframe == "1d":
        df = _download(pair, "5y", "1d")
    else:
        h1 = _download(pair, "730d", "1h")
        if h1.empty:
            return h1
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in h1:
            agg["volume"] = "sum"
        df = h1.resample("4h").agg(agg).dropna(subset=["open", "close"])

    if df.empty:
        return df
    df = df.iloc[:-1]  # laatste candle kan nog lopen -> weglaten
    df.to_csv(path)
    return df


def main():
    cfg = Config()   # basisinstellingen; later tweaken we deze
    asset_classes = {p: get_asset_class(p) for p in ALL_PAIRS}
    summaries = []

    for tf in ["1d", "4h"]:
        print(f"\n=== Data ophalen {tf} ({len(ALL_PAIRS)} markten) ===")
        data = {}
        for i, pair in enumerate(ALL_PAIRS, 1):
            try:
                df = get_data(pair, tf)
                if len(df) >= 400:
                    data[pair] = df
                else:
                    print(f"  - {pair}: te weinig data ({len(df)} candles), overgeslagen")
            except Exception as e:
                print(f"  ⚠️ {pair}: {type(e).__name__}: {e}")
            if i % 25 == 0:
                print(f"  {i}/{len(ALL_PAIRS)} ...")

        print(f"Backtest {tf} op {len(data)} markten...")
        t0 = time.time()
        trades = run_backtest(data, cfg, asset_classes)
        print(f"Klaar in {time.time() - t0:.0f}s, {len(trades)} trades")

        if trades.empty:
            continue
        trades.to_csv(f"backtest_trades_{tf}.csv", index=False)

        s = summarize(trades, by=("asset_class", "pattern")).round(2)
        s.insert(0, "timeframe", tf)
        summaries.append(s)

        tot = summarize(trades, by=("pattern",)).round(2)
        print(f"\n----- RESULTAAT {tf} (per asset class) -----")
        print(s.drop(columns="timeframe").to_string())
        print(f"\n----- RESULTAAT {tf} (totaal) -----")
        print(tot.to_string())

    if summaries:
        out = pd.concat(summaries)
        out.to_csv("backtest_samenvatting.csv")
        print("\nOpgeslagen: backtest_samenvatting.csv, backtest_trades_1d.csv, backtest_trades_4h.csv")
        print("Stuur de RESULTAAT-tabellen (of backtest_samenvatting.csv) naar Claude.")


if __name__ == "__main__":
    main()