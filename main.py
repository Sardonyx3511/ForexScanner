import os
import yfinance as yf
import ta
from utils.indicators import add_bollinger_bands
import pandas as pd
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from config.settings import *
from utils.risk import calculate_lot_size, calculate_crypto_units
from utils.breakout_strategy import check_latest_breakout_signal, prepare_breakout_data
from utils.pullback_strategy import check_latest_pullback_signal
from utils.donchian_strategy import check_latest_donchian_signal
from utils.donchian_indicator import add_donchian_channels
from utils.tdi_shark_fin_strategy import check_recent_persistent_bias_signals, check_open_persistent_bias_position, add_tdi_indicators, add_long_term_emas
from utils.fvg_watch import add_fvg, check_recent_fvg_signals
from utils.weex_data import fetch_weex_crypto_data


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v9.3")
print("      3 STRATEGIEËN ACTIEF")
print("      Breakout + Pullback + Donchian")
print("      Crypto: Weex perpetuals (top 100 op volume)")
print("      (TDI Bias en FVG Watch tijdelijk uit)")
print("===================================")


scan_date = datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%d-%m-%Y %H:%M")

SHARK_FIN_LOOKBACK_DAYS = 5

ENABLE_BREAKOUT_WATCH = True
ENABLE_PULLBACK_WATCH = True
ENABLE_DONCHIAN_WATCH = True
ENABLE_SHARK_FIN_WATCH = False
ENABLE_FVG_WATCH = False

FVG_LOOKBACK_DAYS = 5
FVG_MIN_GAP_SIZE_ATR = 0.5
FVG_EXCLUDE_CRYPTO = True
FVG_SHELF_LOOKBACK = 50

TDI_EXCLUDE_CRYPTO = True

# Crypto alleen downloaden als minstens één ACTIEVE strategie het ook
# daadwerkelijk gebruikt (breakout/pullback/Donchian gebruiken crypto
# wél als ze aanstaan; TDI en FVG sluiten crypto altijd uit) - zo
# voorkomt je nodeloze downloads (en 'delisted'-foutmeldingen) van
# crypto-paren terwijl geen enkele actieve strategie ze gebruikt.
_needs_crypto = ENABLE_BREAKOUT_WATCH or ENABLE_PULLBACK_WATCH or ENABLE_DONCHIAN_WATCH

# ============================================
# CRYPTO-BRON
# Crypto komt van Weex (perpetual futures, waar je ook daadwerkelijk
# handelt): de top WEEX_TOP_N echte crypto-paren op 24-uurs volume.
# Aandelen/ETF's/metalen die Weex ook als perpetual lijst worden
# eruit gefilterd (zie utils/weex_data.py). Als Weex niet bereikbaar
# is, valt de scan terug op de oude yfinance-cryptolijst.
# Zet USE_WEEX_FOR_CRYPTO op False om altijd yfinance te gebruiken.
# ============================================
USE_WEEX_FOR_CRYPTO = True
WEEX_TOP_N = 100
WEEX_MIN_DAYS = 150

_non_crypto_pairs = [p for p in ALL_PAIRS if get_asset_class(p) != "crypto"]
_yf_crypto_pairs = [p for p in ALL_PAIRS if get_asset_class(p) == "crypto"]

weex_crypto_data = {}
_crypto_note = ""

if _needs_crypto and USE_WEEX_FOR_CRYPTO:

    try:
        weex_crypto_data, _weex_stats = fetch_weex_crypto_data(
            top_n=WEEX_TOP_N,
            min_days=WEEX_MIN_DAYS,
        )

        print(
            f"Weex crypto: {_weex_stats['geladen']} paren geladen "
            f"(van {_weex_stats['crypto']} crypto-perpetuals; "
            f"{_weex_stats['niet_crypto_uitgesloten']} aandelen/ETF's/metalen uitgesloten, "
            f"{_weex_stats['te_kort']} te weinig geschiedenis, "
            f"{_weex_stats['fout']} ophaalfouten)"
        )

        if not weex_crypto_data:
            print("⚠️  Weex gaf geen bruikbare crypto-paren terug - terugval op yfinance-cryptolijst.")

    except Exception as e:
        print(f"⚠️  Weex niet bereikbaar ({type(e).__name__}: {e}) - terugval op yfinance-cryptolijst.")
        weex_crypto_data = {}

SCAN_PAIRS = list(_non_crypto_pairs)

if _needs_crypto and not weex_crypto_data:
    SCAN_PAIRS += _yf_crypto_pairs
    _crypto_note = " (crypto via yfinance)"
elif _needs_crypto:
    _crypto_note = f" + {len(weex_crypto_data)} crypto-perpetuals via Weex"
else:
    _crypto_note = " (crypto niet gedownload - geen actieve strategie gebruikt het)"


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


TELEGRAM_MAX_LENGTH = 4000


def split_message(text, max_length=TELEGRAM_MAX_LENGTH):
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1

        if current_length + line_length > max_length and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(line)
        current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def send_telegram_message(text):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  TELEGRAM_TOKEN of TELEGRAM_CHAT_ID ontbreekt, bericht wordt niet verstuurd.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    chunks = split_message(text)

    if len(chunks) > 1:
        print(f"ℹ️  Bericht is {len(text)} tekens, wordt opgesplitst in {len(chunks)} delen.")

    for idx, chunk in enumerate(chunks):

        if len(chunks) > 1:
            chunk = f"*(deel {idx + 1}/{len(chunks)})*\n\n{chunk}"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(url, data=payload, timeout=15)

            if response.status_code == 200:
                print(f"✅ Telegram-bericht verstuurd (deel {idx + 1}/{len(chunks)}).")
            else:
                print(f"⚠️  Telegram gaf een foutcode terug (deel {idx + 1}/{len(chunks)}): {response.status_code}")
                print(response.text)

        except Exception as e:
            print(f"⚠️  Versturen naar Telegram mislukt (deel {idx + 1}/{len(chunks)}): {e}")


def determine_position_size(asset_class, entry_price, stop_loss, pair):

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

    if asset_class != "forex" or distance is None:
        return None

    clean_pair_check = pair.replace("=X", "")
    pip_size = 0.01 if clean_pair_check.endswith("JPY") else 0.0001
    return round(distance / pip_size, 1)


def analyse(pair, df_override=None, asset_class_override=None, name_override=None):
    """
    Normaal haalt analyse() de data zelf op via yfinance. Voor Weex-crypto
    wordt de data al eerder opgehaald en meegegeven via df_override (met
    asset_class_override en name_override, omdat Weex-symbolen niet in de
    config-lijsten staan).
    """

    try:

        if df_override is not None:
            df = df_override.copy()
        else:
            df=yf.download(
                pair,
                period="5y",
                interval="1d",
                multi_level_index=False,
                progress=False
            )


        if df.empty or len(df) < 150:
            return None, None, None, None, None, None


        asset_class = asset_class_override or get_asset_class(pair)
        clean_name = name_override or clean_pair_name(pair)

        df_prepared = prepare_breakout_data(df, rsi_window=RSI_WINDOW, ema_span=EMA_SPAN)
        df_prepared = add_donchian_channels(df_prepared, window=20)
        df_prepared = add_tdi_indicators(df_prepared, rsi_period=13, band_period=34, band_dev=2)
        df_prepared = add_long_term_emas(df_prepared, fast_span=50, slow_span=200)

        breakout_result = None

        if ENABLE_BREAKOUT_WATCH:

            breakout_signal = check_latest_breakout_signal(
                df_prepared,
                atr_multiplier=ATR_MULTIPLIER,
                rr=RR,
            )

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
                    # .get(): een signaal zonder volumegegevens (bv. forex, of
                    # een paar zonder betrouwbaar volume) mag de verwerking niet
                    # laten crashen - het wordt dan getoond als 'geen volumedata'
                    "Volume bevestigd": breakout_signal.get("volume_confirmed", False),
                    "Volume vandaag": breakout_signal.get("volume_today"),
                    "Volume gem. 20d": breakout_signal.get("avg_volume_20d"),
                    "Volume ratio": breakout_signal.get("volume_ratio"),
                    "Data datum": str(breakout_signal["data_date"])[:10],
                    "Position size": bo_position_size,
                }

        pullback_result = None

        if ENABLE_PULLBACK_WATCH:

            pullback_signal = check_latest_pullback_signal(
                df_prepared,
                atr_multiplier=ATR_MULTIPLIER,
                rr=PULLBACK_RR,
            )

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

        donchian_result = None

        if ENABLE_DONCHIAN_WATCH:

            donchian_signal = check_latest_donchian_signal(
                df_prepared,
                atr_multiplier=ATR_MULTIPLIER,
                rr=RR,
            )

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

        shark_signals = []

        if ENABLE_SHARK_FIN_WATCH and not (TDI_EXCLUDE_CRYPTO and asset_class == "crypto"):

            shark_signals = check_recent_persistent_bias_signals(
                df_prepared,
                atr_multiplier=ATR_MULTIPLIER,
                rr=RR,
                lookback_days=SHARK_FIN_LOOKBACK_DAYS,
            )

        shark_results_for_pair = []

        for shark_signal in shark_signals:

            sf_position_size = determine_position_size(
                asset_class, shark_signal["entry_price"], shark_signal["stop_loss"], pair
            )

            sf_sl_distance = round(abs(shark_signal["entry_price"] - shark_signal["stop_loss"]), 5)
            sf_tp_distance = round(abs(shark_signal["take_profit"] - shark_signal["entry_price"]), 5)

            shark_results_for_pair.append({
                "Pair": clean_name,
                "Asset Class": asset_class,
                "Direction": shark_signal["direction"],
                "Entry": round(shark_signal["entry_price"], 5),
                "Stop Loss": round(shark_signal["stop_loss"], 5),
                "Take Profit": round(shark_signal["take_profit"], 5),
                "SL afstand": sf_sl_distance,
                "TP afstand": sf_tp_distance,
                "SL pips (indicatief)": calc_pips(asset_class, pair, sf_sl_distance),
                "TP pips (indicatief)": calc_pips(asset_class, pair, sf_tp_distance),
                "Entry type": shark_signal["entry_type"],
                "Dagen geleden": shark_signal["days_ago"],
                "Data datum": str(shark_signal["data_date"])[:10],
                "Position size": sf_position_size,
            })

        open_position_result = None

        if ENABLE_SHARK_FIN_WATCH and not (TDI_EXCLUDE_CRYPTO and asset_class == "crypto"):

            open_pos = check_open_persistent_bias_position(
                df_prepared,
                atr_multiplier=ATR_MULTIPLIER,
                rr=RR,
            )

            if open_pos is not None:
                open_position_result = {
                    "Pair": clean_name,
                    "Asset Class": asset_class,
                    "Direction": open_pos["direction"],
                    "Entry": round(open_pos["entry_price"], 5),
                    "Stop Loss": round(open_pos["stop_loss"], 5),
                    "Take Profit": round(open_pos["take_profit"], 5),
                    "Entry type": open_pos["entry_type"],
                    "Entry datum": str(open_pos["entry_date"])[:10],
                    "Dagen open": open_pos["days_open"],
                }

        fvg_results_for_pair = []

        if ENABLE_FVG_WATCH and not (FVG_EXCLUDE_CRYPTO and asset_class == "crypto"):

            df_prepared = add_fvg(df_prepared)

            fvg_signals = check_recent_fvg_signals(
                df_prepared,
                lookback_days=FVG_LOOKBACK_DAYS,
                min_gap_size_atr=FVG_MIN_GAP_SIZE_ATR,
                shelf_lookback=FVG_SHELF_LOOKBACK,
            )

            for fvg in fvg_signals:
                fvg_results_for_pair.append({
                    "Pair": clean_name,
                    "Asset Class": asset_class,
                    "Direction": fvg["direction"],
                    "Zone laag": fvg["zone_low"],
                    "Zone hoog": fvg["zone_high"],
                    "Huidige prijs": fvg["current_price"],
                    "Prijs in zone": fvg["price_in_zone"],
                    "Gap grootte (ATR)": fvg.get("gap_size_atr"),
                    "Heeft shelf": fvg.get("has_shelf", False),
                    "Shelf dagen terug": fvg.get("shelf_days_back"),
                    "Dagen geleden": fvg["days_ago"],
                    "Data datum": str(fvg["data_date"])[:10],
                })

        return breakout_result, pullback_result, donchian_result, shark_results_for_pair, open_position_result, fvg_results_for_pair


    except Exception as e:

        print(f"  ⚠️ FOUT bij {pair}: {type(e).__name__}: {e}")
        return None, None, None, None, None, None




breakout_results=[]
pullback_results=[]
donchian_results=[]
shark_results=[]
open_positions=[]
fvg_results=[]


def collect_results(bo, pb, dc, sf, op, fvg):
    """Voegt de uitkomst van analyse() toe aan de resultaatlijsten."""

    if bo:
        breakout_results.append(bo)

    if pb:
        pullback_results.append(pb)

    if dc:
        donchian_results.append(dc)

    if sf:
        shark_results.extend(sf)

    if op:
        open_positions.append(op)

    if fvg:
        fvg_results.extend(fvg)


print(f"Scannen van {len(SCAN_PAIRS)} markten{_crypto_note}...")

for pair in SCAN_PAIRS:

    if DEBUG:
        print("Scan:", pair)

    collect_results(*analyse(pair))


# Weex-crypto: data is al opgehaald, dus geen download per paar
for symbol, (base_name, weex_df) in weex_crypto_data.items():

    if DEBUG:
        print("Scan (Weex):", symbol)

    collect_results(*analyse(
        symbol,
        df_override=weex_df,
        asset_class_override="crypto",
        name_override=f"{base_name}-PERP",
    ))



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

if not shark_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Entry type","Dagen geleden","Data datum","Position size"]).to_csv("shark_fin_resultaat.csv", index=False)
else:
    pd.DataFrame(shark_results).to_csv("shark_fin_resultaat.csv", index=False)



print()
print("===================================")
print("📱 DAILY REPORT")
print(scan_date)
print("===================================")


header_line = f"📱 *DAILY REPORT* - {scan_date}"


if ENABLE_BREAKOUT_WATCH:

    print()
    print("🚀 BREAKOUT WATCH (Bollinger Squeeze + Volume) - GEVALIDEERD")
    print("-----------------------------------")

    breakout_message_lines = [header_line, "", "🚀 *BREAKOUT WATCH (Squeeze + Volume) - GEVALIDEERD*"]

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

            breakout_message_lines.append("")
            breakout_message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
            breakout_message_lines.append(f"Entry : {r['Entry']}")
            breakout_message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
            breakout_message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
            breakout_message_lines.append(f"Size : {r['Position size']}")
            breakout_message_lines.append(vol_tag)
            if r["Volume ratio"] is not None:
                breakout_message_lines.append(f"Vol: {r['Volume vandaag']} / gem {r['Volume gem. 20d']} = {r['Volume ratio']}x ({r['Data datum']})")

    else:

        print("Geen nieuwe breakouts")
        breakout_message_lines.append("Geen nieuwe breakouts")

    send_telegram_message("\n".join(breakout_message_lines))

else:
    print()
    print("🚀 BREAKOUT WATCH - uitgeschakeld (ENABLE_BREAKOUT_WATCH=False)")


if ENABLE_PULLBACK_WATCH:

    print()
    print("🔻 PULLBACK WATCH (SHORT + RSI-Divergentie) - GEVALIDEERD")
    print("-----------------------------------")

    pullback_message_lines = [header_line, "", "🔻 *PULLBACK WATCH (SHORT + Divergentie) - GEVALIDEERD*"]

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

            pullback_message_lines.append("")
            pullback_message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
            pullback_message_lines.append(f"Entry : {r['Entry']}")
            pullback_message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
            pullback_message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
            pullback_message_lines.append(f"Size : {r['Position size']}")

    else:

        print("Geen nieuwe pullback-signalen")
        pullback_message_lines.append("Geen nieuwe pullback-signalen")

    send_telegram_message("\n".join(pullback_message_lines))

else:
    print()
    print("🔻 PULLBACK WATCH - uitgeschakeld (ENABLE_PULLBACK_WATCH=False)")


if ENABLE_SHARK_FIN_WATCH:

    print()
    print("🦈 TDI AANHOUDENDE BIAS WATCH (LONG-only) - GEVALIDEERD")
    print("-----------------------------------")

    shark_message_lines = [header_line, "", "🦈 *TDI AANHOUDENDE BIAS WATCH (LONG-only) - GEVALIDEERD*"]

    if shark_results:

        for r in shark_results:

            asset_tag = r["Asset Class"].upper()
            pip_info = f" ({r['SL pips (indicatief)']} pips)" if r['SL pips (indicatief)'] is not None else ""
            pip_info_tp = f" ({r['TP pips (indicatief)']} pips)" if r['TP pips (indicatief)'] is not None else ""
            dagen_tag = "vandaag" if r["Dagen geleden"] == 0 else f"{r['Dagen geleden']} dagen geleden"
            type_tag = "🦈 Shark fin (nieuwe bias)" if r["Entry type"] == "shark_fin" else "✖️ MBL-kruising (binnen bestaande bias)"

            print()
            print(f"[{asset_tag}] {r['Pair']} {r['Direction']} ({dagen_tag})")
            print(f"Entry      : {r['Entry']}")
            print(f"Stop Loss  : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
            print(f"Take Profit: {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
            print(f"Size       : {r['Position size']}")
            print(type_tag)

            shark_message_lines.append("")
            shark_message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}* ({dagen_tag})")
            shark_message_lines.append(f"Entry : {r['Entry']}")
            shark_message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
            shark_message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
            shark_message_lines.append(f"Size : {r['Position size']}")
            shark_message_lines.append(type_tag)

    else:

        print("Geen nieuwe signalen")
        shark_message_lines.append("Geen nieuwe signalen")

    if open_positions:

        open_positions_sorted = sorted(
            open_positions, key=lambda op: op["Entry datum"], reverse=True
        )

        print()
        print(f"--- {len(open_positions_sorted)} lopende positie(s) uit eerdere bias (nog niet gesloten, nieuwste eerst) ---")
        shark_message_lines.append("")
        shark_message_lines.append(f"_{len(open_positions_sorted)} lopende positie(s), nog niet gesloten (nieuwste eerst):_")

        for op in open_positions_sorted:
            asset_tag = op["Asset Class"].upper()
            print(f"[{asset_tag}] {op['Pair']} {op['Direction']} | Entry: {op['Entry']} ({op['Entry datum']}) | {op['Dagen open']} dagen open | type={op['Entry type']}")
            shark_message_lines.append(f"[{asset_tag}] {op['Pair']} {op['Direction']} - entry {op['Entry']} ({op['Entry datum']}, {op['Dagen open']}d open)")

    send_telegram_message("\n".join(shark_message_lines))

else:
    print()
    print("🦈 TDI AANHOUDENDE BIAS WATCH - uitgeschakeld (ENABLE_SHARK_FIN_WATCH=False)")


if ENABLE_DONCHIAN_WATCH:

    print()
    print("📈 DONCHIAN WATCH (Channel Breakout, LONG-only) - GEVALIDEERD")
    print("-----------------------------------")

    donchian_message_lines = [header_line, "", "📈 *DONCHIAN WATCH (Channel Breakout, LONG-only) - GEVALIDEERD*"]

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

            donchian_message_lines.append("")
            donchian_message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
            donchian_message_lines.append(f"Entry : {r['Entry']}")
            donchian_message_lines.append(f"SL : {r['Stop Loss']} (afstand: {r['SL afstand']}{pip_info})")
            donchian_message_lines.append(f"TP : {r['Take Profit']} (afstand: {r['TP afstand']}{pip_info_tp})")
            donchian_message_lines.append(f"Size : {r['Position size']}")

    else:

        print("Geen nieuwe Donchian-signalen")
        donchian_message_lines.append("Geen nieuwe Donchian-signalen")

    send_telegram_message("\n".join(donchian_message_lines))

else:
    print()
    print("📈 DONCHIAN WATCH - uitgeschakeld (ENABLE_DONCHIAN_WATCH=False)")


if ENABLE_FVG_WATCH:

    print()
    print("🔲 FVG WATCH (Fair Value Gaps - zelf monitoren, geen strategie)")
    print("-----------------------------------")

    fvg_message_lines = [header_line, "", "🔲 *FVG WATCH (zelf monitoren, geen kant-en-klare strategie)*"]

    if fvg_results:

        for r in fvg_results:

            asset_tag = r["Asset Class"].upper()
            richting_tag = "📈 Bullish gap" if r["Direction"] == "bullish" else "📉 Bearish gap"
            dagen_tag = "vandaag" if r["Dagen geleden"] == 0 else f"{r['Dagen geleden']} dagen geleden"
            zone_tag = "✅ Prijs is terug in de zone" if r["Prijs in zone"] else "⚪ Prijs nog niet terug in de zone"

            print()
            print(f"[{asset_tag}] {r['Pair']} - {richting_tag} ({dagen_tag})")
            print(f"Zone       : {r['Zone laag']} - {r['Zone hoog']} ({r['Gap grootte (ATR)']} ATR)")
            print(f"Huidige prijs: {r['Huidige prijs']}")
            if r["Heeft shelf"]:
                print(f"🟨 Shelf-confluence: historisch reactieniveau {r['Shelf dagen terug']} dagen eerder op dezelfde zone")
            print(zone_tag)

            fvg_message_lines.append("")
            fvg_message_lines.append(f"[{asset_tag}] *{r['Pair']}* - {richting_tag} ({dagen_tag})")
            fvg_message_lines.append(f"Zone : {r['Zone laag']} - {r['Zone hoog']} ({r['Gap grootte (ATR)']} ATR)")
            fvg_message_lines.append(f"Huidige prijs : {r['Huidige prijs']}")
            if r["Heeft shelf"]:
                fvg_message_lines.append(f"🟨 Shelf: {r['Shelf dagen terug']}d eerder al reactieniveau op deze zone")
            fvg_message_lines.append(zone_tag)

    else:

        print("Geen nieuwe FVG's")
        fvg_message_lines.append("Geen nieuwe FVG's")

    send_telegram_message("\n".join(fvg_message_lines))

else:
    print()
    print("🔲 FVG WATCH - uitgeschakeld (ENABLE_FVG_WATCH=False)")


print()
print("CSV's opgeslagen: breakout_resultaat.csv, pullback_resultaat.csv, donchian_resultaat.csv, shark_fin_resultaat.csv")