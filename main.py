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
        calculate_lot_size
)


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v2.7")
print("      RSI DIVERGENCE + EMA FILTER")
print("===================================")


scan_date = datetime.now().strftime("%d-%m-%Y %H:%M")


pairs = [
"EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X",
"AUDUSD=X","USDCAD=X","NZDUSD=X",
"EURJPY=X","EURGBP=X","EURAUD=X",
"EURCAD=X","EURCHF=X","EURNZD=X",
"GBPJPY=X","GBPAUD=X","GBPCAD=X",
"GBPCHF=X","GBPNZD=X",
"AUDJPY=X","CADJPY=X","CHFJPY=X",
"NZDJPY=X",
"AUDCAD=X","AUDCHF=X","AUDNZD=X",
"NZDCAD=X","NZDCHF=X",
"CADCHF=X",
"USDSEK=X","USDNOK=X",
"EURSEK=X","EURNOK=X",
"USDMXN=X","USDZAR=X",
"USDTRY=X","USDPLN=X",
"USDHUF=X","USDILS=X",
"SGDJPY=X","HKDJPY=X",
"ZARJPY=X","MXNJPY=X",
"TRYJPY=X","PLNJPY=X"
]


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


def analyse(pair):

    try:

        df=yf.download(
            pair,
            period="5y",
            interval="1d",
            multi_level_index=False,
            progress=False
        )


        if df.empty:
            return None


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

        # Weekly trend
        if trend == weekly_trend:
            score += 30
            reasons.append("✅ Weekly KST")
        else:
            reasons.append("❌ Weekly KST")

        # DMI
        if trend == dmi:
            score += 25
            reasons.append("✅ DMI")
        else:
            reasons.append("❌ DMI")

        # ADX
        if adx_status != "WEAK":
            score += 25
            reasons.append(f"✅ ADX {round(d['ADX'],1)}")
        else:
            reasons.append(f"❌ ADX {round(d['ADX'],1)}")

        # RSI-divergentie
        if divergence_aligned:
            score += DIVERGENCE_SCORE
            reasons.append("✅ RSI Divergentie")
        else:
            reasons.append("❌ RSI Divergentie")

        # =====================================
        # CONFIDENCE SCORE
        # =====================================

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


        # =====================================
        # EMA21-AFSTANDSFILTER (waarschuwing, geen scoring)
        # =====================================
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

        # =====================================
        # STOP LOSS / TAKE PROFIT / LOT SIZE
        # =====================================

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

        lot_size, risk_note = calculate_lot_size(
               ACCOUNT_SIZE,
               RISK_PERCENT,
               d["Close"],
               stop_loss,
               pair
        )

        return {

            "Datum":scan_date,
            "Pair":pair.replace("=X",""),
            "Trend":trend,
            "Score":score,
            "ADX":round(d["ADX"],1),
            "ATR": round(d["ATR"],5),
            "Close": round(d["Close"],5),
            "Stop Loss": round(stop_loss,5) if stop_loss else "-",
            "Take Profit": round(take_profit, 5) if take_profit else "-",
            "Lot size": lot_size if lot_size else "-",
            "Risk note": risk_note,
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


    except:

        return None




results=[]


print(f"Scannen van {len(pairs)} markten...")

for pair in pairs:

    if DEBUG:
        print("Scan:", pair)

    r = analyse(pair)

    if r:
        results.append(r)



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

if DEBUG:
    print(df[["Pair", "Entry", "Close", "Stop Loss", "Take Profit"]].head())



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
    print("🔥 TRADE WATCH")
    print("-----------------------------------")

    message_lines.append("🔥 *TRADE WATCH*")

    for _,r in trade.iterrows():

        print()
        print(f"{r['Stars']}  {r['Pair']} {r['Entry']}")
        print(f"Confidence : {r['Confidence']}%")
        print(f"Entry      : {r['Close']}")
        print(f"Stop Loss  : {r['Stop Loss']}")
        print(f"Take Profit: {r['Take Profit']}")
        print(f"Lots       : {r['Lot size']}{r['Risk note']}")
        print(f"ADX        : {r['ADX']}")
        print(f"ATR        : {r['ATR']}")
        print(f"Stoch      : {r['K']}/{r['D']}")
        print(f"RSI Div.   : {'Ja' if r['RSI Divergentie'] else 'Nee'}")

        print(
            f"ADX {r['ADX']} | Stoch {r['K']}/{r['D']} | {r['Zone']}"
        )

        print(
            "✅ KST Daily/Weekly"
        )

        print(
            "✅ DMI richting"
        )

        print(
            "✅ ADX filter"
        )

        if r["Extended"]:
            print("⚠️ Uitgerekt t.o.v. EMA21, extra voorzichtig zijn")

        message_lines.append("")
        message_lines.append(f"{r['Stars']} *{r['Pair']} {r['Entry']}*")
        message_lines.append(f"Confidence : {r['Confidence']}%")
        message_lines.append(f"Entry : {r['Close']}")
        message_lines.append(f"SL : {r['Stop Loss']}")
        message_lines.append(f"TP : {r['Take Profit']}")
        message_lines.append(f"Lots : {r['Lot size']}{r['Risk note']}")
        message_lines.append(f"ADX : {r['ADX']}")
        message_lines.append(f"ATR : {r['ATR']}")
        message_lines.append(f"RSI Divergentie : {'Ja ✅' if r['RSI Divergentie'] else 'Nee'}")

        if r["Extended"]:
            message_lines.append("⚠️ Uitgerekt t.o.v. EMA21, extra voorzichtig zijn")


else:

    print("Geen nieuwe trades")
    message_lines.append("Geen nieuwe trades")



print()
print("👀 MONITOR")
print("-----------------------------------")

message_lines.append("")
message_lines.append("👀 *MONITOR*")


monitor=df[df["Status"]=="MONITOR"].head(10)


for _,r in monitor.iterrows():

    print(
    f"{r['Stars']} {r['Pair']} ({r['Confidence']}%)"
    )

    message_lines.append(
    f"{r['Pair']} {r['Trend']} | ADX {r['ADX']} | ATR {r['ATR']} | K/D {r['K']}/{r['D']}"
    )



print()
print("CSV opgeslagen")

telegram_message = "\n".join(message_lines)
send_telegram_message(telegram_message)