"""
Propfirm-simulatie: test alle drie de live-strategieën (breakout,
pullback SHORT+divergentie, Donchian LONG) samen op een virtueel
$5.000-account, met jouw specifieke regels:

- Risico per trade: 1% ($50)
- Daily drawdown-limiet: 4% ($200) - dag wordt geflagged als het
  gerealiseerde verlies op een dag deze limiet overschrijdt
- Max drawdown: $500 (naar $4.500) - simulatie stopt zodra dit geraakt wordt
- Profit target: $5.500 (+$500, +10%)

BELANGRIJKE AANNAMES (dit is een benadering, geen exacte reconstructie):
- Dagresultaat = som van R-multiples van trades die DIE DAG sluiten
  (geen intraday mark-to-market van nog open posities - die data
  hebben we niet)
- Meerdere scenario's voor max. gelijktijdig open trades (2/3/4/
  onbeperkt) worden getest, chronologisch first-come-first-served
- Vast risicobedrag van $50 per trade, niet meegroeiend met het saldo

Gebruik:
    python propfirm_simulation.py
"""

import yfinance as yf
import pandas as pd

from config.settings import (
    ALL_PAIRS,
    ATR_MULTIPLIER,
    RR,
    PULLBACK_RR,
    RSI_WINDOW,
    EMA_SPAN,
    DIVERGENCE_LOOKBACK,
    DIVERGENCE_ORDER,
    get_asset_class,
)
from utils.breakout_strategy import prepare_breakout_data, simulate_breakout_trades
from utils.pullback_strategy import simulate_pullback_trades
from utils.donchian_strategy import prepare_donchian_data, simulate_donchian_trades
from utils.donchian_indicator import add_donchian_channels


# ============================================
# PROPFIRM-REGELS
# ============================================
ACCOUNT_START = 5000
RISK_PER_TRADE = 50          # 1%
DAILY_DD_LIMIT = 200         # 4%
MAX_DD_FLOOR = 4500          # account stopt hieronder (max drawdown $500)
PROFIT_TARGET = 5500         # +$500

CONCURRENT_SCENARIOS = [2, 3, 4, 999]  # 999 = ongelimiteerd


print("===================================")
print("   DATA VERZAMELEN VOOR PROPFIRM-SIMULATIE")
print(f"   {len(ALL_PAIRS)} markten, 3 strategieën")
print("===================================")
print()


all_trades = []
skipped = []

for pair in ALL_PAIRS:

    asset_class = get_asset_class(pair)
    print(f"Verwerken: {pair} [{asset_class}] ...", end=" ")

    try:
        df = yf.download(
            pair,
            period="5y",
            interval="1d",
            multi_level_index=False,
            progress=False
        )

        if df.empty or len(df) < 150:
            print("overgeslagen")
            skipped.append(pair)
            continue

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_donchian_channels(df_prepared, window=20)

        # --- Breakout (LONG+SHORT, volume waar beschikbaar - exact zoals live) ---
        bo_trades = simulate_breakout_trades(
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR
        )
        for t in bo_trades:
            t["strategy"] = "breakout"
            t["asset_class"] = asset_class

        # --- Pullback (alleen SHORT + divergentie - exact zoals live) ---
        pb_trades_all = simulate_pullback_trades(
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=PULLBACK_RR,
            divergence_lookback=DIVERGENCE_LOOKBACK, divergence_order=DIVERGENCE_ORDER
        )
        pb_trades = [t for t in pb_trades_all if t["direction"] == "SHORT" and t.get("rsi_divergence")]
        for t in pb_trades:
            t["strategy"] = "pullback"
            t["asset_class"] = asset_class

        # --- Donchian (alleen LONG - exact zoals live) ---
        dc_trades_all = simulate_donchian_trades(
            df_prepared, pair, atr_multiplier=ATR_MULTIPLIER, rr=RR
        )
        dc_trades = [t for t in dc_trades_all if t["direction"] == "LONG"]
        for t in dc_trades:
            t["strategy"] = "donchian"
            t["asset_class"] = asset_class

        all_trades.extend(bo_trades)
        all_trades.extend(pb_trades)
        all_trades.extend(dc_trades)

        print(f"BO:{len(bo_trades)} PB:{len(pb_trades)} DC:{len(dc_trades)}")

    except Exception as e:
        print(f"FOUT: {e}")
        continue


print()
print(f"Overgeslagen: {len(skipped)}")

closed_trades = [t for t in all_trades if t["outcome"] in ("WIN", "LOSS")]
print(f"Totaal aantal afgeronde trades (alle strategieën, alle markten): {len(closed_trades)}")

# Sorteer chronologisch op entry-datum - nodig voor de portfolio-simulatie
closed_trades.sort(key=lambda t: t["entry_date"])


# ============================================
# PORTFOLIO-SIMULATIE
# ============================================

def simulate_portfolio(trades, max_concurrent):
    """
    Loopt chronologisch door de trades heen, met een limiet op het
    aantal gelijktijdig open posities (first-come-first-served).
    Geeft een dict terug met de belangrijkste uitkomsten.
    """

    balance = ACCOUNT_START
    peak_balance = ACCOUNT_START
    open_until = []  # lijst van exit_dates van nu 'open' geachte trades

    daily_pnl = {}  # datum -> som van R * RISK_PER_TRADE die dag

    target_reached_date = None
    target_reached_trades = None
    dd_breached_date = None
    dd_breached_trades = None
    daily_breach_count = 0
    daily_breach_dates = []

    trades_taken = 0
    trades_skipped_limit = 0

    for t in trades:

        entry_date = t["entry_date"]
        open_until = [d for d in open_until if d > entry_date]
        open_count = len(open_until)

        if open_count >= max_concurrent:
            trades_skipped_limit += 1
            continue

        trades_taken += 1
        open_until.append(t["exit_date"])

        if t["strategy"] == "pullback":
            r_multiple = PULLBACK_RR if t["outcome"] == "WIN" else -1
        else:
            r_multiple = RR if t["outcome"] == "WIN" else -1

        pnl = r_multiple * RISK_PER_TRADE

        balance += pnl
        peak_balance = max(peak_balance, balance)

        exit_day = t["exit_date"]
        daily_pnl[exit_day] = daily_pnl.get(exit_day, 0) + pnl

        if daily_pnl[exit_day] <= -DAILY_DD_LIMIT and exit_day not in daily_breach_dates:
            daily_breach_count += 1
            daily_breach_dates.append(exit_day)

        if balance >= PROFIT_TARGET and target_reached_date is None:
            target_reached_date = exit_day
            target_reached_trades = trades_taken

        if balance <= MAX_DD_FLOOR:
            # Account is 'gesloten' - een echt propfirm-account stopt hier.
            # We breken de simulatie af, in plaats van door te blijven
            # rekenen alsof er niets gebeurd is.
            dd_breached_date = exit_day
            dd_breached_trades = trades_taken
            break

    return {
        "Eindsaldo": round(balance, 2),
        "Trades genomen": trades_taken,
        "Trades overgeslagen (limiet)": trades_skipped_limit,
        "Target ($5.500) gehaald op": target_reached_date,
        "Target gehaald na X trades": target_reached_trades,
        "Max drawdown ($4.500) geraakt op": dd_breached_date,
        "Max drawdown geraakt na X trades": dd_breached_trades,
        "Aantal dagen met daily-limiet-breach": daily_breach_count,
    }


# ============================================
# GECOMBINEERD: alle 3 strategieën samen, per concurrent-scenario
# ============================================

print()
print("===================================")
print("GECOMBINEERD (alle 3 strategieën samen)")
print("===================================")
print()

for max_c in CONCURRENT_SCENARIOS:
    label = "Onbeperkt" if max_c == 999 else f"Max {max_c} tegelijk"
    result = simulate_portfolio(closed_trades, max_c)
    print(f"--- {label} ---")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print()


# ============================================
# PER STRATEGIE APART (elk op een eigen $5.000-account,
# zelfde concurrent-limiet-logica toegepast op alleen die strategie)
# ============================================

print("===================================")
print("PER STRATEGIE APART (max 3 tegelijk, ter vergelijking)")
print("===================================")
print()

for strategy in ["breakout", "pullback", "donchian"]:
    strategy_trades = [t for t in closed_trades if t["strategy"] == strategy]
    result = simulate_portfolio(strategy_trades, 3)
    print(f"--- {strategy.upper()} (n={len(strategy_trades)} trades beschikbaar) ---")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print()


# ============================================
# CSV opslaan
# ============================================

trades_df = pd.DataFrame(closed_trades)
if not trades_df.empty:
    trades_df.to_csv("propfirm_simulation_trades.csv", index=False)
print("CSV opgeslagen: propfirm_simulation_trades.csv")