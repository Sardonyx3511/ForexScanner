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
from utils.pullback_strategy import check_latest_pullback_signal
from utils.donchian_strategy import check_latest_donchian_signal
from utils.donchian_indicator import add_donchian_channels


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v5.0")
print("      BREAKOUT/VOLUME + PULLBACK (SHORT+DIV)")
print("      Beide strategieën gevalideerd: meerdere")
print("      RR's, multi-asset, out-of-sample")
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


def calc_pips(asset_class, pair, distance):
    """Indicatieve pip-omrekening voor forex, None voor andere assetklasses."""

    if asset_class != "forex" or distance is None:
        return None

    clean_pair_check = pair.replace("=X", "")
    pip_size = 0.01 if clean_pair_check.endswith("JPY") else 0.0001
    return round(distance / pip_size, 1)


def analyse(pair):
    """
    Download data één keer per paar, en checkt 'm tegen BEIDE
    gevalideerde strategieën: breakout/volume en pullback (SHORT+
    divergentie). prepare_breakout_data levert alle indicatoren die
    beide strategieën nodig hebben (superset), dus geen dubbele
    download of voorbereiding nodig.

    Geeft (breakout_result, pullback_result) terug - beide kunnen None zijn.
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
            return None, None, None


        asset_class = get_asset_class(pair)
        clean_name = clean_pair_name(pair)

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_donchian_channels(df_prepared, window=20)

        # =====================================
        # BREAKOUT / VOLUME-STRATEGIE
        # =====================================
        breakout_signal = check_latest_breakout_signal(
            df_prepared,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR,
        )

        breakout_result = None

        if breakout_signal is not None:

            bo_position_size = determine_position_size(
                asset_class, breakout_signal["entry_price"], breakout_signal["stop_loss"], pair
            )

            bo_sl_distance = round(abs(breakout_signal["entry_price"] - breakout_signal["stop_loss"]), 5)
            bo_tp_distance = round(abs(breakout_signal["take_profit"] - breakout_signal["entry_price"]), 5)

            breakout_result = {
                "Pair": clean_name,
                "Asset Class": asset_class,
                "Direction": breakout_signal["direction"],
                "Entry": round(breakout_signal["entry_price"], 5),
                "Stop Loss": round(breakout_signal["stop_loss"], 5),
                "Take Profit": round(breakout_signal["take_profit"], 5),
                "SL afstand": bo_sl_distance,
                "TP afstand": bo_tp_distance,
                "SL pips (indicatief)": calc_pips(asset_class, pair, bo_sl_distance),
                "TP pips (indicatief)": calc_pips(asset_class, pair, bo_tp_distance),
                "Volume bevestigd": breakout_signal["volume_confirmed"],
                "Volume vandaag": breakout_signal["volume_today"],
                "Volume gem. 20d": breakout_signal["avg_volume_20d"],
                "Volume ratio": breakout_signal["volume_ratio"],
                "Data datum": str(breakout_signal["data_date"])[:10],
                "Position size": bo_position_size,
            }

        # =====================================
        # PULLBACK-STRATEGIE (alleen SHORT + divergentie)
        # =====================================
        pullback_signal = check_latest_pullback_signal(
            df_prepared,
            atr_multiplier=ATR_MULTIPLIER,
            rr=PULLBACK_RR,
        )

        pullback_result = None

        if pullback_signal is not None:

            pb_position_size = determine_position_size(
                asset_class, pullback_signal["entry_price"], pullback_signal["stop_loss"], pair
            )

            pb_sl_distance = round(abs(pullback_signal["entry_price"] - pullback_signal["stop_loss"]), 5)
            pb_tp_distance = round(abs(pullback_signal["take_profit"] - pullback_signal["entry_price"]), 5)

            pullback_result = {
                "Pair": clean_name,
                "Asset Class": asset_class,
                "Direction": pullback_signal["direction"],
                "Entry": round(pullback_signal["entry_price"], 5),
                "Stop Loss": round(pullback_signal["stop_loss"], 5),
                "Take Profit": round(pullback_signal["take_profit"], 5),
                "SL afstand": pb_sl_distance,
                "TP afstand": pb_tp_distance,
                "SL pips (indicatief)": calc_pips(asset_class, pair, pb_sl_distance),
                "TP pips (indicatief)": calc_pips(asset_class, pair, pb_tp_distance),
                "Data datum": str(pullback_signal["data_date"])[:10],
                "Position size": pb_position_size,
            }

        # =====================================
        # DONCHIAN-STRATEGIE (alleen LONG, gevalideerde combinatie)
        # =====================================
        donchian_signal = check_latest_donchian_signal(
            df_prepared,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR,
        )

        donchian_result = None

        if donchian_signal is not None:

            dc_position_size = determine_position_size(
                asset_class, donchian_signal["entry_price"], donchian_signal["stop_loss"], pair
            )

            dc_sl_distance = round(abs(donchian_signal["entry_price"] - donchian_signal["stop_loss"]), 5)
            dc_tp_distance = round(abs(donchian_signal["take_profit"] - donchian_signal["entry_price"]), 5)

            donchian_result = {
                "Pair": clean_name,
                "Asset Class": asset_class,
                "Direction": donchian_signal["direction"],
                "Entry": round(donchian_signal["entry_price"], 5),
                "Stop Loss": round(donchian_signal["stop_loss"], 5),
                "Take Profit": round(donchian_signal["take_profit"], 5),
                "SL afstand": dc_sl_distance,
                "TP afstand": dc_tp_distance,
                "SL pips (indicatief)": calc_pips(asset_class, pair, dc_sl_distance),
                "TP pips (indicatief)": calc_pips(asset_class, pair, dc_tp_distance),
                "Data datum": str(donchian_signal["data_date"])[:10],
                "Position size": dc_position_size,
            }

        return breakout_result, pullback_result, donchian_result


    except Exception:

        return None, None, None




breakout_results=[]
pullback_results=[]
donchian_results=[]


print(f"Scannen van {len(ALL_PAIRS)} markten...")

for pair in ALL_PAIRS:

    if DEBUG:
        print("Scan:", pair)

    bo, pb, dc = analyse(pair)

    if bo:
        breakout_results.append(bo)

    if pb:
        pullback_results.append(pb)

    if dc:
        donchian_results.append(dc)



if not breakout_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Volume bevestigd","Volume vandaag","Volume gem. 20d","Volume ratio","Data datum","Position size"]).to_csv("breakout_resultaat.csv", index=False)
else:
    pd.DataFrame(breakout_results).to_csv("breakout_resultaat.csv", index=False)

if not pullback_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Data datum","Position size"]).to_csv("pullback_resultaat.csv", index=False)
else:
    pd.DataFrame(pullback_results).to_csv("pullback_resultaat.csv", index=False)

if not donchian_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Data datum","Position size"]).to_csv("donchian_resultaat.csv", index=False)
else:
    pd.DataFrame(donchian_results).to_csv("donchian_resultaat.csv", index=False)



print()
print("===================================")
print("📱 DAILY REPORT")
print(scan_date)
print("===================================")


message_lines = []
message_lines.append(f"📱 *DAILY REPORT*")
message_lines.append(scan_date)
message_lines.append("")


# =====================================
# 1. BREAKOUT WATCH - BOVENAAN
# =====================================

print()
print("🚀 BREAKOUT WATCH (Bollinger Squeeze + Volume) - GEVALIDEERD")
print("-----------------------------------")

message_lines.append("🚀 *BREAKOUT WATCH (Squeeze + Volume) - GEVALIDEERD*")

if breakout_results:

    for r in breakout_results:

        asset_tag = r["Asset Class"].upper()
        vol_tag = "✅ Volume bevestigd" if r["Volume bevestigd"] else "⚠️ Geen volumedata (check handmatig)"
        pip_info = f" ({r['SL pips (indicatief)']} pips)" if r['SL pips (indicatief)'] is not None else ""
        pip_info_tp = f" ({r['TP pips (indicatief)']} pips)" if r['TP pips (indicatief)'] is not None else ""

        print()
        print(f"[{asset_tag}] {r['Pair']} {r['Direction']}")
        print(f"Entry      : {r['Entry']}")
        print(f"Stop Loss  : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        print(f"Take Profit: {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        print(f"Size       : {r['Position size']}")
        print(vol_tag)
        if r["Volume ratio"] is not None:
            print(f"Volume detail: {r['Volume vandaag']} vs gem. {r['Volume gem. 20d']} = {r['Volume ratio']}x (databatum: {r['Data datum']})")

        message_lines.append("")
        message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
        message_lines.append(f"Entry : {r['Entry']}")
        message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        message_lines.append(f"Size : {r['Position size']}")
        message_lines.append(vol_tag)
        if r["Volume ratio"] is not None:
            message_lines.append(f"Vol: {r['Volume vandaag']} / gem {r['Volume gem. 20d']} = {r['Volume ratio']}x ({r['Data datum']})")

else:

    print("Geen nieuwe breakouts")
    message_lines.append("Geen nieuwe breakouts")


# =====================================
# 2. PULLBACK WATCH - ONDERAAN (SHORT + divergentie, alleen)
# =====================================

print()
print("🔻 PULLBACK WATCH (SHORT + RSI-Divergentie) - GEVALIDEERD")
print("-----------------------------------")

message_lines.append("")
message_lines.append("🔻 *PULLBACK WATCH (SHORT + Divergentie) - GEVALIDEERD*")

if pullback_results:

    for r in pullback_results:

        asset_tag = r["Asset Class"].upper()
        pip_info = f" ({r['SL pips (indicatief)']} pips)" if r['SL pips (indicatief)'] is not None else ""
        pip_info_tp = f" ({r['TP pips (indicatief)']} pips)" if r['TP pips (indicatief)'] is not None else ""

        print()
        print(f"[{asset_tag}] {r['Pair']} {r['Direction']}")
        print(f"Entry      : {r['Entry']}")
        print(f"Stop Loss  : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        print(f"Take Profit: {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        print(f"Size       : {r['Position size']}")
        print(f"Databatum  : {r['Data datum']}")

        message_lines.append("")
        message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
        message_lines.append(f"Entry : {r['Entry']}")
        message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        message_lines.append(f"Size : {r['Position size']}")

else:

    print("Geen nieuwe pullback-signalen")
    message_lines.append("Geen nieuwe pullback-signalen")


# =====================================
# 3. DONCHIAN WATCH - onderaan (LONG-only, gevalideerde combinatie)
# =====================================

print()
print("📈 DONCHIAN WATCH (Channel Breakout, LONG-only) - GEVALIDEERD")
print("-----------------------------------")

message_lines.append("")
message_lines.append("📈 *DONCHIAN WATCH (Channel Breakout, LONG-only) - GEVALIDEERD*")

if donchian_results:

    for r in donchian_results:

        asset_tag = r["Asset Class"].upper()
        pip_info = f" ({r['SL pips (indicatief)']} pips)" if r['SL pips (indicatief)'] is not None else ""
        pip_info_tp = f" ({r['TP pips (indicatief)']} pips)" if r['TP pips (indicatief)'] is not None else ""

        print()
        print(f"[{asset_tag}] {r['Pair']} {r['Direction']}")
        print(f"Entry      : {r['Entry']}")
        print(f"Stop Loss  : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        print(f"Take Profit: {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        print(f"Size       : {r['Position size']}")
        print(f"Databatum  : {r['Data datum']}")

        message_lines.append("")
        message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
        message_lines.append(f"Entry : {r['Entry']}")
        message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
        message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
        message_lines.append(f"Size : {r['Position size']}")

else:

    print("Geen nieuwe Donchian-signalen")
    message_lines.append("Geen nieuwe Donchian-signalen")


print()
print("CSV's opgeslagen: breakout_resultaat.csv, pullback_resultaat.csv, donchian_resultaat.csv")

telegram_message = "\n".join(message_lines)
send_telegram_message(telegram_message)