"""
Isoleert de sterkste combinatie uit de aanhoudende-bias-backtest:
LONG-only, zonder crypto - met en zonder de MBL-eis (optie A vs B),
en met/zonder de shark-fin-entries erbij (vs. puur cross-entries).

Leest de al opgeslagen tdi_persistent_bias_trades.csv opnieuw in -
GEEN nieuwe download nodig, draait binnen seconden.

Gebruik (nadat tdi_persistent_bias_backtest.py al eerder is gedraaid):
    python tdi_long_no_crypto_final.py
"""

import pandas as pd

from utils.backtest import compute_stats
from config.settings import RR


df = pd.read_csv("tdi_persistent_bias_trades.csv", parse_dates=["entry_date", "exit_date"])
trades = df.to_dict("records")

for t in trades:
    t["mbl_position_ok"] = str(t.get("mbl_position_ok")) == "True"


def filter_trades(trades, direction=None, no_crypto=False, entry_type=None, mbl_required=None):
    result = trades
    if direction is not None:
        result = [t for t in result if t["direction"] == direction]
    if no_crypto:
        result = [t for t in result if t["asset_class"] != "crypto"]
    if entry_type is not None:
        result = [t for t in result if t["entry_type"] == entry_type]
    if mbl_required is not None:
        result = [t for t in result if bool(t.get("mbl_position_ok")) == mbl_required]
    return result


print("===================================")
print("LONG-ONLY, ZONDER CRYPTO - VERGELIJKING VAN VARIANTEN")
print("===================================")
print(f"Break-even winrate nodig bij RR 1:{RR}: {round(1/(1+RR)*100, 1)}%")
print()

v1 = filter_trades(trades, direction="LONG", no_crypto=True)
v2 = filter_trades(trades, direction="LONG", no_crypto=True, entry_type="cross")
v3 = filter_trades(trades, direction="LONG", no_crypto=True, entry_type="cross", mbl_required=True)
v4 = filter_trades(trades, direction="LONG", no_crypto=True, entry_type="shark_fin")

compare = pd.DataFrame({
    "V1: Alles (fin+cross)": compute_stats(v1, RR),
    "V2: Alleen cross": compute_stats(v2, RR),
    "V3: Cross + MBL-eis": compute_stats(v3, RR),
    "V4: Alleen shark fin": compute_stats(v4, RR),
})
print(compare.to_string())


print()
print("===================================")
print("PER ASSETKLASSE (binnen V2: LONG, cross-only, zonder crypto)")
print("===================================")

per_class_stats = []
for cls in ["forex", "stocks", "metals", "indices", "commodities"]:
    class_trades = [t for t in v2 if t["asset_class"] == cls]
    stats = compute_stats(class_trades, RR)
    stats["Asset Class"] = cls
    per_class_stats.append(stats)

per_class_df = pd.DataFrame(per_class_stats)
cols = ["Asset Class", "Aantal trades", "Winrate (%)", "Gem. resultaat (R)",
        "Totaal resultaat (R)", "Max drawdown (R)"]
print(per_class_df[cols].to_string(index=False))