import os
import yfinance as yf
import ta
from utils.indicators import (
    calculate_kst,
    add_adx,
    add_atr,
    add_stochastic,
    add_rsi,
    add_ema,
    add_bollinger_bands,
    get_ema_distance_atr,
    detect_rsi_divergence
)
import pandas as pd
import requests
from datetime import datetime
from config.settings import *
from utils.risk import (
        calculate_stop_loss,
        calculate_take_profit,
        calculate_lot_size,
        calculate_crypto_units
)
from utils.breakout_strategy import check_latest_breakout_signal


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v3.0")
print("      HOOFDSTRATEGIE + BREAKOUT/VOLUME")
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
    Positiegrootte per assetklasse - zelfde aanpak als in de backtest-
    scripts. Forex krijgt een lot-getal, crypto een aantal eenheden,
    de rest (metals/indices/commodities) een risicobedrag zonder
    specifiek aantal (contractgroottes verschillen te veel om
    betrouwbaar te berekenen zonder brokerdata).
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
    Hoofdstrategie: KST + DMI + ADX + Stochastic-cross, met RSI-
    divergentie en EMA21-afstandsfilter. Downloadt en bereidt de data
    ook voor voor de breakout-strategie (zelfde df, geen dubbele
    download) en checkt die er meteen bij.

    Geeft (main_result, breakout_result) terug - beide kunnen None zijn.
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
            return None, None


        df["KST"],df["KST Signal"]=calculate_kst(df)

        weekly=df.resample("W").agg(
            {
            "Open":"first",
            "High":"max",
            "Low":"min",
            "Close":"last"
            }
        )

        weekly["KST"],weekly["KST Signal"]=calculate_kst(weekly)

        df = add_adx(df)

        df = add_atr(df)

        df = add_stochastic(df)

        df = add_rsi(df, window=RSI_WINDOW)

        df = add_ema(df, span=EMA_SPAN, column_name="EMA21")

        df = add_bollinger_bands(df, window=20, window_dev=2)

        asset_class = get_asset_class(pair)
        clean_name = clean_pair_name(pair)

        d=df.iloc[-1]
        w=weekly.iloc[-1]

        trend="BULL" if d["KST"]>d["KST Signal"] else "BEAR"
        weekly_trend="BULL" if w["KST"]>w["KST Signal"] else "BEAR"

        dmi="BULL" if d["DI+"]>d["DI-"] else "BEAR"



        if d["ADX"]>=ADX_MIN:

            adx_status="STRONG"

        elif df["ADX"].tail(5).max()>=25:

            adx_status="RECENT"

        else:

            adx_status="WEAK"


        # =====================================
        # RSI-DIVERGENTIE
        # =====================================
        bullish_div, bearish_div = detect_rsi_divergence(
            df,
            lookback=DIVERGENCE_LOOKBACK,
            order=DIVERGENCE_ORDER
        )

        divergence_aligned = (
            (trend == "BULL" and bullish_div)
            or (trend == "BEAR" and bearish_div)
        )


        reasons = []
        score = 0

        if trend == weekly_trend:
            score += 30
            reasons.append("✅ Weekly KST")
        else:
            reasons.append("❌ Weekly KST")

        if trend == dmi:
            score += 25
            reasons.append("✅ DMI")
        else:
            reasons.append("❌ DMI")

        if adx_status != "WEAK":
            score += 25
            reasons.append(f"✅ ADX {round(d['ADX'],1)}")
        else:
            reasons.append(f"❌ ADX {round(d['ADX'],1)}")

        if divergence_aligned:
            score += DIVERGENCE_SCORE
            reasons.append("✅ RSI Divergentie")
        else:
            reasons.append("❌ RSI Divergentie")

        confidence = round((score / MAX_SCORE) * 100)

        if confidence >= 95:
            stars = "⭐⭐⭐⭐⭐"
        elif confidence >= 85:
            stars = "⭐⭐⭐⭐"
        elif confidence >= 70:
            stars = "⭐⭐⭐"
        elif confidence >= 50:
            stars = "⭐⭐"
        else:
            stars = "⭐"

        bull_cross=(
            df["K"].iloc[-2] <= df["D"].iloc[-2]
            and df["K"].iloc[-1] > df["D"].iloc[-1]
        )

        bear_cross=(
            df["K"].iloc[-2] >= df["D"].iloc[-2]
            and df["K"].iloc[-1] < df["D"].iloc[-1]
        )

        entry="-"
        zone="-"

        if trend=="BULL" and trend==weekly_trend and bull_cross and d["K"]>d["D"]:

            entry="LONG"

            zone="OK" if d["K"]<STOCH_OVERBOUGHT else "OVERBOUGHT ⚠️"

        elif trend=="BEAR" and trend==weekly_trend and bear_cross and d["K"]<d["D"]:

            entry="SHORT"

            zone="OK" if d["K"]>STOCH_OVERSOLD else "OVERSOLD ⚠️"


        ema_distance_atr = get_ema_distance_atr(d, ema_column="EMA21")
        extended = abs(ema_distance_atr) > EMA_EXTENDED_THRESHOLD_ATR


        if entry!="-" and adx_status!="WEAK":

            status="TRADE WATCH"

            if extended:
                status="TRADE WATCH (UITGEREKT ⚠️)"

        elif trend==weekly_trend and adx_status!="WEAK":

            status="MONITOR"

        else:

            status=""

        stop_loss = calculate_stop_loss(
               d["Close"],
               d["ATR"],
               ATR_MULTIPLIER,
               entry
        )

        take_profit = calculate_take_profit(
               d["Close"],
               stop_loss,
               RR,
               entry
        )

        position_size = determine_position_size(asset_class, d["Close"], stop_loss, pair) if entry != "-" else "-"

        main_result = {

            "Datum":scan_date,
            "Pair":clean_name,
            "Asset Class": asset_class,
            "Trend":trend,
            "Score":score,
            "ADX":round(d["ADX"],1),
            "ATR": round(d["ATR"],5),
            "Close": round(d["Close"],5),
            "Stop Loss": round(stop_loss,5) if stop_loss else "-",
            "Take Profit": round(take_profit, 5) if take_profit else "-",
            "Position size": position_size,
            "ADX status":adx_status,
            "K":round(d["K"],1),
            "D":round(d["D"],1),
            "Zone":zone,
            "Entry":entry,
            "Status":status,
            "EMA21 afstand (ATR)": round(ema_distance_atr, 2),
            "Extended": extended,
            "RSI Divergentie": divergence_aligned,
            "Reason": " | ".join(reasons),
            "Confidence": confidence,
            "Stars": stars
        }


        # =====================================
        # BREAKOUT / VOLUME-STRATEGIE
        # (hergebruikt dezelfde df, geen extra download)
        # =====================================
        breakout_signal = check_latest_breakout_signal(
            df,
            atr_multiplier=ATR_MULTIPLIER,
            rr=RR,
        )

        breakout_result = None

        if breakout_signal is not None:

            bo_position_size = determine_position_size(
                asset_class, breakout_signal["entry_price"], breakout_signal["stop_loss"], pair
            )

            breakout_result = {
                "Pair": clean_name,
                "Asset Class": asset_class,
                "Direction": breakout_signal["direction"],
                "Entry": round(breakout_signal["entry_price"], 5),
                "Stop Loss": round(breakout_signal["stop_loss"], 5),
                "Take Profit": round(breakout_signal["take_profit"], 5),
                "Volume bevestigd": breakout_signal["volume_confirmed"],
                "Position size": bo_position_size,
            }


        return main_result, breakout_result


    except Exception:

        return None, None




results=[]
breakout_results=[]


print(f"Scannen van {len(ALL_PAIRS)} markten...")

for pair in ALL_PAIRS:

    if DEBUG:
        print("Scan:", pair)

    r, b = analyse(pair)

    if r:
        results.append(r)

    if b:
        breakout_results.append(b)



df=pd.DataFrame(results)

if DEBUG:
    print(df.columns.tolist())
    print(df.head())



df=df.sort_values(
    "Score",
    ascending=False
)



df.to_csv(
    "scan_resultaat.csv",
    index=False
)

if not breakout_results:
    pd.DataFrame(columns=["Pair","Asset Class","Direction","Entry","Stop Loss","Take Profit","Volume bevestigd","Position size"]).to_csv("breakout_resultaat.csv", index=False)
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


trade=df[df["Status"].str.contains("TRADE WATCH", na=False)]


if len(trade)>0:

    print()
    print("🔥 TRADE WATCH (hoofdstrategie)")
    print("-----------------------------------")

    message_lines.append("🔥 *TRADE WATCH (hoofdstrategie)*")

    for _,r in trade.iterrows():

        asset_tag = r["Asset Class"].upper()

        print()
        print(f"{r['Stars']}  [{asset_tag}] {r['Pair']} {r['Entry']}")
        print(f"Confidence : {r['Confidence']}%")
        print(f"Entry      : {r['Close']}")
        print(f"Stop Loss  : {r['Stop Loss']}")
        print(f"Take Profit: {r['Take Profit']}")
        print(f"Size       : {r['Position size']}")
        print(f"ADX        : {r['ADX']}")
        print(f"ATR        : {r['ATR']}")
        print(f"Stoch      : {r['K']}/{r['D']}")
        print(f"RSI Div.   : {'Ja' if r['RSI Divergentie'] else 'Nee'}")

        if r["Extended"]:
            print("⚠️ Uitgerekt t.o.v. EMA21, extra voorzichtig zijn")

        message_lines.append("")
        message_lines.append(f"{r['Stars']} [{asset_tag}] *{r['Pair']} {r['Entry']}*")
        message_lines.append(f"Confidence : {r['Confidence']}%")
        message_lines.append(f"Entry : {r['Close']}")
        message_lines.append(f"SL : {r['Stop Loss']}")
        message_lines.append(f"TP : {r['Take Profit']}")
        message_lines.append(f"Size : {r['Position size']}")
        message_lines.append(f"ADX : {r['ADX']}")
        message_lines.append(f"RSI Divergentie : {'Ja ✅' if r['RSI Divergentie'] else 'Nee'}")

        if r["Extended"]:
            message_lines.append("⚠️ Uitgerekt t.o.v. EMA21, extra voorzichtig zijn")


else:

    print("Geen nieuwe trades (hoofdstrategie)")
    message_lines.append("Geen nieuwe trades (hoofdstrategie)")


# =====================================
# BREAKOUT WATCH (nieuwe sectie)
# =====================================

print()
print("🚀 BREAKOUT WATCH (Bollinger Squeeze + Volume)")
print("-----------------------------------")

message_lines.append("")
message_lines.append("🚀 *BREAKOUT WATCH (Squeeze + Volume)*")

if breakout_results:

    for r in breakout_results:

        asset_tag = r["Asset Class"].upper()
        vol_tag = "✅ Volume bevestigd" if r["Volume bevestigd"] else "⚠️ Geen volumedata (check handmatig)"

        print()
        print(f"[{asset_tag}] {r['Pair']} {r['Direction']}")
        print(f"Entry      : {r['Entry']}")
        print(f"Stop Loss  : {r['Stop Loss']}")
        print(f"Take Profit: {r['Take Profit']}")
        print(f"Size       : {r['Position size']}")
        print(vol_tag)

        message_lines.append("")
        message_lines.append(f"[{asset_tag}] *{r['Pair']} {r['Direction']}*")
        message_lines.append(f"Entry : {r['Entry']}")
        message_lines.append(f"SL : {r['Stop Loss']}")
        message_lines.append(f"TP : {r['Take Profit']}")
        message_lines.append(f"Size : {r['Position size']}")
        message_lines.append(vol_tag)

else:

    print("Geen nieuwe breakouts")
    message_lines.append("Geen nieuwe breakouts")



print()
print("👀 MONITOR (hoofdstrategie)")
print("-----------------------------------")

message_lines.append("")
message_lines.append("👀 *MONITOR (hoofdstrategie)*")


monitor=df[df["Status"]=="MONITOR"].head(MONITOR_MAX_ROWS)


for _,r in monitor.iterrows():

    asset_tag = r["Asset Class"].upper()

    print(
    f"{r['Stars']} [{asset_tag}] {r['Pair']} ({r['Confidence']}%)"
    )

    message_lines.append(
    f"[{asset_tag}] {r['Pair']} {r['Trend']} | ADX {r['ADX']} | K/D {r['K']}/{r['D']}"
    )



print()
print("CSV's opgeslagen: scan_resultaat.csv, breakout_resultaat.csv")

telegram_message = "\n".join(message_lines)
send_telegram_message(telegram_message)