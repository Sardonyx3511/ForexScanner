"""
pattern_breakout.py
Detectie + backtest van Ascending Triangle en Falling Wedge breakouts (LONG).
Bedoeld voor 4h en daily, multi-asset. Geen lookahead: een pivot telt pas
mee zodra hij bevestigd is (pivot_right bars later).

Verwacht per markt een DataFrame met kolommen: open, high, low, close, (volume)
en een DatetimeIndex, oplopend gesorteerd.

Gebruik:
    from pattern_breakout import Config, scan, run_backtest, summarize
    signals = scan(df, "BTCUSDT", "4h", Config())            # live scan
    trades  = run_backtest({"BTCUSDT": df, ...}, Config())   # backtest
    print(summarize(trades))
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product
from typing import Optional

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Configuratie
# ----------------------------------------------------------------------------
@dataclass
class Config:
    # Pivots
    pivot_left: int = 3
    pivot_right: int = 3
    # Patroonvenster
    lookback: int = 100            # max patroonlengte in bars
    min_bars: int = 15             # min patroonlengte in bars
    max_pivots: int = 4            # max pivots per lijn om te fitten
    # Toleranties (in ATR-eenheden)
    atr_len: int = 14
    touch_tol_atr: float = 0.4     # pivot moet zo dicht bij lijn liggen
    flat_slope_atr: float = 0.03   # |helling| per bar voor "vlakke" lijn
    rising_slope_atr: float = 0.02 # min stijging per bar onderlijn triangle
    violation_atr: float = 0.25    # close voorbij lijn binnen patroon = ongeldig
    # Breakout
    breakout_buffer_atr: float = 0.2
    near_line_atr: float = 0.5     # "setup in vorming" melding
    # Filters
    ema_len: int = 200
    trend_filter_triangle: bool = True   # close > EMA200 vereist
    trend_filter_wedge: bool = False
    require_contraction: bool = True     # ATR nu < ATR bij patroonstart
    use_volume: bool = False             # alleen zinvol voor crypto/aandelen
    volume_mult: float = 1.3             # volume breakout-bar vs gem. 20
    min_wedge_convergence: float = 0.75  # breedte eind / breedte start <= dit
    # Trade management (backtest)
    stop_buffer_atr: float = 0.5
    target_mult: float = 1.0             # x patroonhoogte (measured move)
    max_hold_bars: int = 40
    min_rr: float = 1.0                  # skip trades met slechtere R:R


# ----------------------------------------------------------------------------
# Indicatoren
# ----------------------------------------------------------------------------
def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def pivots(series: np.ndarray, left: int, right: int, kind: str) -> np.ndarray:
    """Boolean array: True op index i als i een pivot high/low is.
    Let op: pas bekend op bar i + right."""
    n = len(series)
    out = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        window = series[i - left: i + right + 1]
        if kind == "high":
            if series[i] == window.max() and np.argmax(window) == left:
                out[i] = True
        else:
            if series[i] == window.min() and np.argmin(window) == left:
                out[i] = True
    return out


def fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Kleinste-kwadraten lijn y = slope * x + intercept."""
    if len(x) == 2:
        slope = (y[1] - y[0]) / (x[1] - x[0])
        return slope, y[0] - slope * x[0]
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


# ----------------------------------------------------------------------------
# Patroondetectie op één bar
# ----------------------------------------------------------------------------
@dataclass
class Pattern:
    kind: str            # "ascending_triangle" | "falling_wedge"
    start: int           # index eerste pivot
    upper_slope: float
    upper_icpt: float
    lower_slope: float
    lower_icpt: float
    touches_upper: int
    touches_lower: int

    def upper(self, i: float) -> float:
        return self.upper_slope * i + self.upper_icpt

    def lower(self, i: float) -> float:
        return self.lower_slope * i + self.lower_icpt

    def height(self) -> float:
        # Breedste punt = start van het patroon
        return self.upper(self.start) - self.lower(self.start)


class Detector:
    """Precompute alles per markt, dan per bar goedkoop detecteren."""

    def __init__(self, df: pd.DataFrame, cfg: Config):
        self.df = df
        self.cfg = cfg
        self.o = df["open"].to_numpy(float)
        self.h = df["high"].to_numpy(float)
        self.l = df["low"].to_numpy(float)
        self.c = df["close"].to_numpy(float)
        self.v = df["volume"].to_numpy(float) if "volume" in df else None
        self.atr = atr(df, cfg.atr_len).to_numpy(float)
        self.ema = df["close"].ewm(span=cfg.ema_len, adjust=False).mean().to_numpy(float)
        self.vol_ma = (pd.Series(self.v).rolling(20).mean().to_numpy(float)
                       if self.v is not None else None)
        self.ph = np.flatnonzero(pivots(self.h, cfg.pivot_left, cfg.pivot_right, "high"))
        self.pl = np.flatnonzero(pivots(self.l, cfg.pivot_left, cfg.pivot_right, "low"))

    def _known(self, piv: np.ndarray, t: int) -> np.ndarray:
        """Pivots die op bar t al bevestigd zijn en binnen lookback vallen."""
        cfg = self.cfg
        mask = (piv <= t - cfg.pivot_right) & (piv >= t - cfg.lookback)
        return piv[mask]

    def detect(self, t: int) -> Optional[Pattern]:
        cfg = self.cfg
        a = self.atr[t]
        if not np.isfinite(a) or a <= 0:
            return None
        highs = self._known(self.ph, t)
        lows = self._known(self.pl, t)
        if len(highs) < 2 or len(lows) < 2:
            return None

        best: Optional[Pattern] = None
        best_score = -1
        k_range = range(min(cfg.max_pivots, len(highs)), 1, -1)
        j_range = range(min(cfg.max_pivots, len(lows)), 1, -1)
        for k_hi, k_lo in product(k_range, j_range):
            hx = highs[-k_hi:]
            lx = lows[-k_lo:]
            pat = self._evaluate(t, hx, lx, a)
            if pat is not None:
                score = pat.touches_upper + pat.touches_lower
                if score > best_score:
                    best, best_score = pat, score
        return best

    def _evaluate(self, t: int, hx: np.ndarray, lx: np.ndarray, a: float) -> Optional[Pattern]:
        cfg = self.cfg
        hy, ly = self.h[hx], self.l[lx]
        us, ui = fit_line(hx.astype(float), hy)
        ls, li = fit_line(lx.astype(float), ly)
        start = int(min(hx[0], lx[0]))
        if t - start < cfg.min_bars:
            return None

        # Alle gebruikte pivots moeten dicht bij hun lijn liggen
        tol = cfg.touch_tol_atr * a
        if np.any(np.abs(hy - (us * hx + ui)) > tol):
            return None
        if np.any(np.abs(ly - (ls * lx + li)) > tol):
            return None

        # Lijnen mogen niet gekruist zijn (apex niet voorbij)
        width_start = (us * start + ui) - (ls * start + li)
        width_now = (us * t + ui) - (ls * t + li)
        if width_start <= 0 or width_now <= 0:
            return None

        # Classificatie (hellingen in ATR per bar)
        us_n, ls_n = us / a, ls / a
        kind = None
        if abs(us_n) <= cfg.flat_slope_atr and ls_n >= cfg.rising_slope_atr:
            kind = "ascending_triangle"
        elif us_n < 0 and ls_n < 0 and us < ls \
                and width_now / width_start <= cfg.min_wedge_convergence:
            kind = "falling_wedge"
        if kind is None:
            return None

        # Prijs moet de lijnen gerespecteerd hebben binnen het patroon (t-1)
        idx = np.arange(start, t)
        if len(idx):
            upper_vals = us * idx + ui
            lower_vals = ls * idx + li
            viol = cfg.violation_atr * a
            if np.any(self.c[idx] > upper_vals + viol):
                return None
            if np.any(self.c[idx] < lower_vals - viol):
                return None

        return Pattern(kind, start, us, ui, ls, li, len(hx), len(lx))

    # --- filters -------------------------------------------------------------
    def passes_filters(self, t: int, pat: Pattern) -> tuple[bool, list[str]]:
        cfg = self.cfg
        notes = []
        trend_req = (cfg.trend_filter_triangle if pat.kind == "ascending_triangle"
                     else cfg.trend_filter_wedge)
        above_ema = self.c[t] > self.ema[t]
        notes.append("boven EMA200" if above_ema else "onder EMA200")
        if trend_req and not above_ema:
            return False, notes
        if cfg.require_contraction:
            contracted = self.atr[t - 1] < self.atr[pat.start]
            if not contracted:
                return False, notes
            notes.append("ATR-contractie")
        if cfg.use_volume and self.v is not None:
            if not (self.v[t] > cfg.volume_mult * self.vol_ma[t]):
                return False, notes
            notes.append("volume bevestigd")
        return True, notes


# ----------------------------------------------------------------------------
# Signalen
# ----------------------------------------------------------------------------
def _signal_at(det: Detector, t: int) -> Optional[dict]:
    """Geeft 'breakout' of 'forming' signaal op bar t, anders None."""
    cfg = det.cfg
    pat = det.detect(t)
    if pat is None:
        return None
    a = det.atr[t]
    line_now = pat.upper(t)
    line_prev = pat.upper(t - 1)
    buf = cfg.breakout_buffer_atr

    is_break = (det.c[t] > line_now + buf * a and
                det.c[t - 1] <= line_prev + buf * det.atr[t - 1])
    is_near = (not is_break and det.c[t] <= line_now and
               line_now - det.c[t] <= cfg.near_line_atr * a)
    if not (is_break or is_near):
        return None

    ok, notes = det.passes_filters(t, pat)
    if not ok:
        return None

    last_low = det.l[det.pl[det.pl <= t - cfg.pivot_right][-1]]
    stop = min(last_low, pat.lower(t)) - cfg.stop_buffer_atr * a
    entry_ref = max(det.c[t], line_now)  # referentie; echte entry = open volgende bar
    target = line_now + cfg.target_mult * pat.height()
    risk = entry_ref - stop
    rr = (target - entry_ref) / risk if risk > 0 else np.nan

    return {
        "status": "breakout" if is_break else "forming",
        "pattern": pat.kind,
        "bar": t,
        "time": det.df.index[t],
        "close": det.c[t],
        "line": line_now,
        "stop": stop,
        "target": target,
        "rr": rr,
        "height": pat.height(),
        "bars_in_pattern": t - pat.start,
        "touches": f"{pat.touches_upper}/{pat.touches_lower}",
        "notes": ", ".join(notes),
    }


def scan(df: pd.DataFrame, symbol: str, timeframe: str, cfg: Config = Config()) -> list[dict]:
    """Live scan: kijkt alleen naar de laatste GESLOTEN candle.
    Zorg dat df geen lopende (onvolledige) candle bevat."""
    if len(df) < max(cfg.ema_len, cfg.lookback) + 5:
        return []
    det = Detector(df, cfg)
    sig = _signal_at(det, len(df) - 1)
    if sig is None:
        return []
    sig.update(symbol=symbol, timeframe=timeframe)
    return [sig]


def format_telegram(sig: dict) -> str:
    icon = "🚀" if sig["status"] == "breakout" else "👀"
    name = "Ascending Triangle" if sig["pattern"] == "ascending_triangle" else "Falling Wedge"
    status = "BREAKOUT" if sig["status"] == "breakout" else "Setup in vorming"
    return (
        f"{icon} {status} | {sig['symbol']} {sig['timeframe']}\n"
        f"Patroon: {name} ({sig['bars_in_pattern']} bars, touches {sig['touches']})\n"
        f"Close: {sig['close']:.5g} | Lijn: {sig['line']:.5g}\n"
        f"Stop: {sig['stop']:.5g} | Target: {sig['target']:.5g} | R:R {sig['rr']:.2f}\n"
        f"{sig['notes']}"
    )


# ----------------------------------------------------------------------------
# Backtest
# ----------------------------------------------------------------------------
def backtest_symbol(df: pd.DataFrame, symbol: str, cfg: Config = Config(),
                    asset_class: str = "") -> list[dict]:
    """Entry op open van de bar NA de breakout-close. Stop en target vast.
    Als stop en target in dezelfde bar geraakt worden: telt als stop (conservatief).
    Eén trade tegelijk per markt."""
    det = Detector(df, cfg)
    n = len(df)
    start_t = max(cfg.ema_len, cfg.lookback) + 1
    trades = []
    t = start_t
    while t < n - 1:
        sig = _signal_at(det, t)
        if sig is None or sig["status"] != "breakout":
            t += 1
            continue
        entry = det.o[t + 1]
        stop, target = sig["stop"], sig["target"]
        risk = entry - stop
        if risk <= 0 or (target - entry) / risk < cfg.min_rr:
            t += 1
            continue

        exit_price, exit_reason, j = None, None, t + 1
        last = min(n - 1, t + cfg.max_hold_bars)
        for j in range(t + 1, last + 1):
            if det.l[j] <= stop:
                exit_price, exit_reason = min(stop, det.o[j]), "stop"  # gap-proof
                break
            if det.h[j] >= target:
                exit_price, exit_reason = max(target, det.o[j]), "target"
                break
        if exit_price is None:
            exit_price, exit_reason = det.c[last], "time"
            j = last

        trades.append({
            "symbol": symbol,
            "asset_class": asset_class,
            "pattern": sig["pattern"],
            "entry_time": df.index[t + 1],
            "exit_time": df.index[j],
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "exit_reason": exit_reason,
            "R": (exit_price - entry) / risk,
            "bars_held": j - (t + 1) + 1,
            "planned_rr": (target - entry) / risk,
        })
        t = j + 1  # geen overlappende trades
    return trades


def run_backtest(data: dict[str, pd.DataFrame], cfg: Config = Config(),
                 asset_classes: Optional[dict[str, str]] = None) -> pd.DataFrame:
    asset_classes = asset_classes or {}
    all_trades = []
    for sym, df in data.items():
        if len(df) < max(cfg.ema_len, cfg.lookback) + 50:
            continue
        all_trades += backtest_symbol(df, sym, cfg, asset_classes.get(sym, ""))
    return pd.DataFrame(all_trades)


def summarize(trades: pd.DataFrame, by: tuple[str, ...] = ("pattern",)) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    def stats(g: pd.DataFrame) -> pd.Series:
        wins = g.loc[g["R"] > 0, "R"].sum()
        losses = -g.loc[g["R"] < 0, "R"].sum()
        eq = g["R"].cumsum()
        return pd.Series({
            "trades": len(g),
            "winrate_%": 100 * (g["R"] > 0).mean(),
            "avg_R": g["R"].mean(),
            "total_R": g["R"].sum(),
            "profit_factor": wins / losses if losses > 0 else np.inf,
            "max_dd_R": (eq.cummax() - eq).max(),
            "avg_bars": g["bars_held"].mean(),
            "pct_target": 100 * (g["exit_reason"] == "target").mean(),
            "pct_time": 100 * (g["exit_reason"] == "time").mean(),
        })

    cols = [c for c in by if c in trades.columns and trades[c].astype(str).str.len().gt(0).any()]
    if not cols:
        return stats(trades).to_frame("all").T
    return trades.groupby(cols).apply(stats, include_groups=False)


# ----------------------------------------------------------------------------
# Parameter-sweep (optioneel) — gebruik met beleid i.v.m. overfitting
# ----------------------------------------------------------------------------
def sweep(data: dict[str, pd.DataFrame], grid: dict[str, list],
          base: Config = Config()) -> pd.DataFrame:
    keys = list(grid)
    rows = []
    for values in product(*grid.values()):
        cfg = Config(**{**asdict(base), **dict(zip(keys, values))})
        tr = run_backtest(data, cfg)
        if tr.empty:
            continue
        row = dict(zip(keys, values))
        row.update(trades=len(tr), winrate=(tr["R"] > 0).mean() * 100,
                   avg_R=tr["R"].mean(), total_R=tr["R"].sum())
        rows.append(row)
    return pd.DataFrame(rows).sort_values("avg_R", ascending=False)


# ----------------------------------------------------------------------------
# CLI: backtest op een map met CSV's (kolommen: time,open,high,low,close[,volume])
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import glob
    import os

    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="map met CSV's, bestandsnaam = symbool")
    ap.add_argument("--timecol", default="time")
    args = ap.parse_args()

    data = {}
    for f in glob.glob(os.path.join(args.folder, "*.csv")):
        d = pd.read_csv(f, parse_dates=[args.timecol], index_col=args.timecol)
        d.columns = [c.lower() for c in d.columns]
        data[os.path.splitext(os.path.basename(f))[0]] = d.sort_index()

    trades = run_backtest(data)
    print(f"{len(trades)} trades over {len(data)} markten\n")
    print(summarize(trades).round(2).to_string())