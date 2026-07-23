import os
import yfinance as yf
import ta
import pandas as pd
import requests
from datetime import datetime


print("\033c", end="")

print("===================================")
print("      FOREX SCANNER v1.9")
print("      TELEGRAM REPORT STYLE")
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
# Token en chat ID komen uit environment variables.
# Lokaal kun je ze zetten met (PowerShell):
#   $env:TELEGRAM_TOKEN="123456:ABC..."
#   $env:TELEGRAM_CHAT_ID="2143382141"
# In GitHub Actions komen ze uit de repository Secrets.

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


def calculate_kst(data):

    roc1=data["Close"].pct_change(10)*100
    roc2=data["Close"].pct_change(15)*100
    roc3=data["Close"].pct_change(20)*100
    roc4=data["Close"].pct_change(30)*100

    kst=(
        roc1.rolling(10).mean()
        +2*roc2.rolling(10).mean()
        +3*roc3.rolling(10).mean()
        +4*roc4.rolling(15).mean()
    )

    signal=kst.rolling(9).mean()

    return kst,signal




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



        adx=ta.trend.ADXIndicator(
            df["High"],
            df["Low"],
            df["Close"],
            window=14
        )

        df["ADX"]=adx.adx()
        df["DI+"]=adx.adx_pos()
        df["DI-"]=adx.adx_neg()



        stoch=ta.momentum.StochasticOscillator(
            df["High"],
            df["Low"],
            df["Close"],
            window=8,
            smooth_window=3
        )


        df["K"]=stoch.stoch()
        df["D"]=df["K"].rolling(3).mean()



        d=df.iloc[-1]
        w=weekly.iloc[-1]



        trend="BULL" if d["KST"]>d["KST Signal"] else "BEAR"
        weekly_trend="BULL" if w["KST"]>w["KST Signal"] else "BEAR"

        dmi="BULL" if d["DI+"]>d["DI-"] else "BEAR"



        if d["ADX"]>=25:

            adx_status="STRONG"

        elif df["ADX"].tail(5).max()>=25:

            adx_status="RECENT"

        else:

            adx_status="WEAK"



        score=0

        if trend==weekly_trend:
            score+=30

        if trend==dmi:
            score+=25

        if adx_status!="WEAK":
            score+=25



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

            zone="OK" if d["K"]<80 else "OVERBOUGHT ⚠️"



        elif trend=="BEAR" and trend==weekly_trend and bear_cross and d["K"]<d["D"]:

            entry="SHORT"

            zone="OK" if d["K"]>20 else "OVERSOLD ⚠️"



        if entry!="-" and adx_status!="WEAK":

            status="TRADE WATCH"

        elif trend==weekly_trend and adx_status!="WEAK":

            status="MONITOR"

        else:

            status=""



        return {

            "Datum":scan_date,
            "Pair":pair.replace("=X",""),
            "Trend":trend,
            "Score":score,
            "ADX":round(d["ADX"],1),
            "ADX status":adx_status,
            "K":round(d["K"],1),
            "D":round(d["D"],1),
            "Zone":zone,
            "Entry":entry,
            "Status":status
        }


    except:

        return None




results=[]


for pair in pairs:

    print("Scan:",pair)

    r=analyse(pair)

    if r:
        results.append(r)



df=pd.DataFrame(results)



df=df.sort_values(
    "Score",
    ascending=False
)



df.to_csv(
    "scan_resultaat.csv",
    index=False
)



print()
print("===================================")
print("📱 DAILY REPORT")
print(scan_date)
print("===================================")


# ============================================
# Bericht opbouwen (console + Telegram)
# ============================================

message_lines = []
message_lines.append(f"📱 *DAILY REPORT*")
message_lines.append(scan_date)
message_lines.append("")


trade=df[df["Status"]=="TRADE WATCH"]


if len(trade)>0:

    print()
    print("🔥 TRADE WATCH")
    print("-----------------------------------")

    message_lines.append("🔥 *TRADE WATCH*")

    for _,r in trade.iterrows():

        print()
        print(
            f"{r['Pair']} {r['Entry']}"
        )

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

        message_lines.append("")
        message_lines.append(f"*{r['Pair']} {r['Entry']}*")
        message_lines.append(f"ADX {r['ADX']} | Stoch {r['K']}/{r['D']} | {r['Zone']}")
        message_lines.append("✅ KST Daily/Weekly")
        message_lines.append("✅ DMI richting")
        message_lines.append("✅ ADX filter")


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
        f"{r['Pair']} {r['Trend']} | ADX {r['ADX']} | K/D {r['K']}/{r['D']}"
    )

    message_lines.append(
        f"{r['Pair']} {r['Trend']} | ADX {r['ADX']} | K/D {r['K']}/{r['D']}"
    )



print()
print("CSV opgeslagen")

telegram_message = "\n".join(message_lines)
send_telegram_message(telegram_message)
