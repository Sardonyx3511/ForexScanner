import os
import yfinance as yf
import ta
from utils.indicators import add_bollinger_bands
import pandas as pd
import requests
from datetime import datetime
from config.settings import *
from utils.risk import calculate_lot_size, calculate_crypto_units
from utils.breakout_strategy import check_latest_breakout_signal, prepare_breakout_data


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v4.0")
print("      BREAKOUT/VOLUME (gevalideerde strategie)")
print("      KST-hoofdstrategie verwijderd - bleek")
print("      historisch niet winstgevend")
print("===================================")


scan_date = datetime.now().strftime("%d-%m-%Y %H:%M")


# ============================================
# TELEGRAM CONFIG
# ============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_message(text):
    """Stuurt een bericht naar Telegram. Print een waarschuwing als config ontbreekt."""

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  TELEGRAM_TOKEN of TELEGRAM_CHAT_ID ontbreekt, bericht wordt niet verstuurd.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, data=payload, timeout=15)

        if response.status_code == 200:
            print("✅ Telegram-bericht verstuurd.")
        else:
            print(f"⚠️  Telegram gaf een foutcode terug: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"⚠️  Versturen naar Telegram mislukt: {e}")


def determine_position_size(asset_class, entry_price, stop_loss, pair):
    """
    Positiegrootte per assetklasse - forex krijgt een lot-getal, crypto
    een aantal eenheden, de rest (stocks/metals/indices/commodities)
    een risicobedrag zonder specifiek aantal.
    """

    if entry_price is None or stop_loss is None:
        return "-"

    if asset_class == "forex":
        lot_size, risk_note = calculate_lot_size(
            ACCOUNT_SIZE, RISK_PERCENT, entry_price, stop_loss, pair
        )
        return f"{lot_size} lots{risk_note}" if lot_size else "-"

    elif asset_class == "crypto":
        units = calculate_crypto_units(
            ACCOUNT_SIZE, RISK_PERCENT, entry_price, stop_loss
        )
        return f"{units} units" if units else "-"

    else:
        risk_amount = round(ACCOUNT_SIZE * (RISK_PERCENT / 100), 2)
        return f"${risk_amount} risico (check contractgrootte bij broker)"


def analyse(pair):
    """
    Alleen de breakout/volume-strategie (Bollinger Squeeze + EMA21 +
    volumebevestiging) - de enige strategie die uitgebreid gevalideerd
    is (meerdere RR's, asset-classes, out-of-sample).

    Geeft breakout_result terug, of None.
    """

    try:

        df=yf.download(
            pair,
            period="5y",
            interval="1d",
            multi_level_index=False,
            progress=False
        )


        if df.empty or len(df) < 150:
            return None


        asset_class = get_asset_class(pair)
        clean_name = clean_pair_name(pair)

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)

        breakout_signal = check_latest_breakout_signal(
            df_prepared,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR,
        )

        if breakout_signal is None:
            return None

        bo_position_size = determine_position_size(
            asset_class, breakout_signal["entry_price"], breakout_signal["stop_loss"], pair
        )

        bo_sl_distance = round(abs(breakout_signal["entry_price"] - breakout_signal["stop_loss"]), 5)
        bo_tp_distance = round(abs(breakout_signal["take_profit"] - breakout_signal["entry_price"]), 5)

        bo_sl_pips = None
        bo_tp_pips = None
        if asset_class == "forex":
            clean_pair_check = pair.replace("=X", "")
            pip_size = 0.01 if clean_pair_check.endswith("JPY") else 0.0001
            bo_sl_pips = round(bo_sl_distance / pip_size, 1)
            bo_tp_pips = round(bo_tp_distance / pip_size, 1)

        breakout_result = {
            "Pair": clean_name,
            "Asset Class": asset_class,
            "Direction": breakout_signal["direction"],
            "Entry": round(breakout_signal["entry_price"], 5),
            "Stop Loss": round(breakout_signal["stop_loss"], 5),
            "Take Profit": round(breakout_signal["take_profit"], 5),
            "SL afstand": bo_sl_distance,
            "TP afstand": bo_tp_distance,
            "SL pips (indicatief)": bo_sl_pips,
            "TP pips (indicatief)": bo_tp_pips,
            "Volume bevestigd": breakout_signal["volume_confirmed"],
            "Volume vandaag": breakout_signal["volume_today"],
            "Volume gem. 20d": breakout_signal["avg_volume_20d"],
            "Volume ratio": breakout_signal["volume_ratio"],
            "Data datum": str(breakout_signal["data_date"])[:10],
            "Position size": bo_position_size,
        }

        return breakout_result


    except Exception:

        return None




breakout_results=[]


print(f"Scannen van {len(ALL_PAIRS)} markten...")

for pair in ALL_PAIRS:

    if DEBUG:
        print("Scan:", pair)

    b = analyse(pair)

    if b:
        breakout_results.append(b)



if not breakout_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Volume bevestigd","Volume vandaag","Volume gem. 20d","Volume ratio","Data datum","Position size"]).to_csv("breakout_resultaat.csv", index=False)
else:
    pd.DataFrame(breakout_results).to_csv("breakout_resultaat.csv", index=False)



print()
print("===================================")
print("📱 DAILY REPORT")
print(scan_date)
print("===================================")


message_lines = []
message_lines.append(f"📱 *DAILY REPORT*")
message_lines.append(scan_date)
message_lines.append("")


print()
print("🚀 BREAKOUT WATCH (Bollinger Squeeze + Volume) - GEVALIDEERD")
print("-----------------------------------")

message_lines.append("🚀 *BREAKOUT WATCH (Squeeze + Volume) - GEVALIDEERD*")

if breakout_results:

    for r in breakout_results:

        asset_tag = r["Asset Class"].upper()
        vol_tag = "✅ Volume bevestigd" if r["Volume bevestigd"] else "⚠️ Geen volumedata (check handmatig)"

        print()
        print(f"[{asset_tag}] {r['Pair']} {r['Direction']}")
        print(f"Entry      : {r['Entry']}")
        print(f"Stop Loss  : {r['Stop Loss']}")
        print(f"Take Profit: {r['Take Profit']}")
        bo_pip_info = f" ({r['SL pips (indicatief)']} pips)" if r['SL pips (indicatief)'] is not None else ""
        bo_pip_info_tp = f" ({r['TP pips (indicatief)']} pips)" if r['TP pips (indicatief)'] is not None else ""
        print(f"SL afstand : {r['SL afstand']}{bo_pip_info}")
        print(f"TP afstand : {r['TP afstand']}{bo_pip_info_tp}")
        print(f"Size       : {r['Position size']}")
        print(vol_tag)
        if r["Volume ratio"] is not None:
            print(f"Volume detail: {r['Volume vandaag']} vs gem. {r['Volume gem. 20d']} = {r['Volume ratio']}x (databatum: {r['Data datum']})")

        message_lines.append("")
        message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
        message_lines.append(f"Entry : {r['Entry']}")
        message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{bo_pip_info})")
        message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{bo_pip_info_tp})")
        message_lines.append(f"Size : {r['Position size']}")
        message_lines.append(vol_tag)
        if r["Volume ratio"] is not None:
            message_lines.append(f"Vol: {r['Volume vandaag']} / gem {r['Volume gem. 20d']} = {r['Volume ratio']}x ({r['Data datum']})")

else:

    print("Geen nieuwe breakouts")
    message_lines.append("Geen nieuwe breakouts")


print()
print("CSV opgeslagen: breakout_resultaat.csv")

telegram_message = "\n".join(message_lines)
send_telegram_message(telegram_message)