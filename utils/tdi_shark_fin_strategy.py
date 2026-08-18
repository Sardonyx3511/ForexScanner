"""
TDI (Traders Dynamic Index) Shark Fin-strategie.

Kernidee: TDI bouwt Bollinger Bands NIET om de prijs, maar om de RSI-
lijn zelf. Een 'shark fin' is een scherpe piek: de RSI schiet buiten
zijn eigen band uit, en keert BINNEN ÉÉN CANDLE scherp terug naar
binnen - een momentum-omkeersignaal.

TWEE EXTRA, MEETBARE BEVESTIGINGEN (getrackt per trade, geen harde
filters totdat objectief getest - zelfde aanpak als bij breakout/
Donchian):

1. TSL vs. RSI Price Line momentum-bevestiging:
   - RSI Price Line (PL) = SMA(RSI, 2) - snelle gladstrijking
   - Trade Signal Line (TSL) = SMA(RSI, 7) - tragere gladstrijking
   - Bij een SHORT-fin: bevestigd als TSL boven de PL zit (momentum
     draait al merkbaar omlaag)
   - Bij een LONG-fin: bevestigd als TSL onder de PL zit

2. EMA50/EMA200-confluence: prijs bevindt zich TUSSEN de 50- en
   200-daagse EMA op het instapmoment.

Exit: vast RR-veelvoud (ATR-based SL), zoals breakout/pullback/Donchian.
"""

import pandas as pd

from utils.risk import calculate_stop_loss, calculate_take_profit


def add_tdi_indicators(df, rsi_period=13, band_period=34, band_dev=2):
    """
    Voegt de RSI, de Bollinger Bands OM DE RSI, en de TDI Price
    Line/Trade Signal Line toe (standaard TDI-instellingen).
    """

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["TDI_RSI"] = 100 - (100 / (1 + rs))

    rsi_sma = df["TDI_RSI"].rolling(band_period).mean()
    rsi_std = df["TDI_RSI"].rolling(band_period).std()

    df["TDI_RSI_upper"] = rsi_sma + band_dev * rsi_std
    df["TDI_RSI_lower"] = rsi_sma - band_dev * rsi_std

    # Market Base Line (MBL) - de 34-periode SMA van de RSI, dezelfde
    # middenlijn die de volatiliteitsbanden gebruiken
    df["TDI_MBL"] = rsi_sma

    df["TDI_PL"] = df["TDI_RSI"].rolling(2).mean()
    df["TDI_TSL"] = df["TDI_RSI"].rolling(7).mean()

    return df


def add_long_term_emas(df, fast_span=50, slow_span=200):
    """Voegt EMA50 en EMA200 toe, voor de trend-confluence-check."""

    df["EMA50"] = df["Close"].ewm(span=fast_span, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=slow_span, adjust=False).mean()

    return df


def _determine_shark_fin_signal(df, i):
    """
    Bepaalt of er op dag i een TDI shark-fin-signaal is.
    Geeft 'LONG', 'SHORT' of '-' terug.
    """

    if i < 1:
        return "-"

    row = df.iloc[i]
    prev_row = df.iloc[i - 1]

    if pd.isna(row["TDI_RSI"]) or pd.isna(row["TDI_RSI_upper"]) or pd.isna(row["TDI_RSI_lower"]):
        return "-"

    pierced_lower = prev_row["TDI_RSI"] < prev_row["TDI_RSI_lower"]
    back_above_lower = row["TDI_RSI"] > row["TDI_RSI_lower"]

    if pierced_lower and back_above_lower:
        return "LONG"

    pierced_upper = prev_row["TDI_RSI"] > prev_row["TDI_RSI_upper"]
    back_below_upper = row["TDI_RSI"] < row["TDI_RSI_upper"]

    if pierced_upper and back_below_upper:
        return "SHORT"

    return "-"


def simulate_shark_fin_trades(df, pair, atr_multiplier, rr):
    """
    Loopt dag voor dag door de historische data en simuleert trades
    volgens de TDI Shark Fin-strategie. Elke trade krijgt twee
    filterbare kenmerken mee: tsl_confirmed en ema_confluence.
    """

    trades = []
    position = None

    min_bars = 200  # EMA200 heeft de langste opwarmperiode nodig

    for i in range(min_bars, len(df)):

        row = df.iloc[i]
        date = df.index[i]

        if position is not None:

            exit_price = None
            outcome = None

            if position["direction"] == "LONG":
                if row["Low"] <= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["High"] >= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"
            else:
                if row["High"] >= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["Low"] <= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"

            if exit_price is not None:
                position["exit_date"] = date
                position["exit_price"] = exit_price
                position["outcome"] = outcome
                position["bars_held"] = i - position["entry_bar"]
                trades.append(position)
                position = None

            continue

        entry = _determine_shark_fin_signal(df, i)

        if entry in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            prev_row = df.iloc[i - 1]

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

            tsl_confirmed = False
            if not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_PL"]):
                if entry == "SHORT":
                    tsl_confirmed = row["TDI_TSL"] > row["TDI_PL"]
                else:
                    tsl_confirmed = row["TDI_TSL"] < row["TDI_PL"]

            ema_confluence = False
            ema_trend_pullback = False
            if not pd.isna(row["EMA50"]) and not pd.isna(row["EMA200"]):
                low_ema = min(row["EMA50"], row["EMA200"])
                high_ema = max(row["EMA50"], row["EMA200"])
                ema_confluence = low_ema <= row["Close"] <= high_ema

                # Verfijnde versie: prijs tussen de EMA's, MAAR ALLEEN als
                # de EMA's ook de juiste trendrichting hebben - dit is een
                # 'pullback in de trend', niet zomaar 'ergens tussenin'
                if entry == "SHORT":
                    # Bearish structuur: EMA50 onder EMA200
                    ema_trend_pullback = ema_confluence and row["EMA50"] < row["EMA200"]
                else:
                    # Bullish structuur: EMA50 boven EMA200
                    ema_trend_pullback = ema_confluence and row["EMA50"] > row["EMA200"]

            # Kenmerk 3: hoe extreem was de RSI-piek/dal die de band doorbrak?
            trigger_rsi_level = prev_row["TDI_RSI"]

            # Kenmerk 4: MBL-conditie (Market Base Line) - voor SHORT:
            # TSL EN RSI zitten allebei onder de MBL, ÉN TSL heeft de
            # RSI zojuist van onder naar boven gekruist (bearish
            # kruising, niet alleen een statische positie). Voor LONG
            # (spiegelbeeld): allebei boven de MBL, TSL kruist RSI van
            # boven naar onder.
            mbl_aligned = False
            if (not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_MBL"])
                    and not pd.isna(row["TDI_RSI"]) and not pd.isna(prev_row["TDI_TSL"])
                    and not pd.isna(prev_row["TDI_RSI"])):

                if entry == "SHORT":
                    below_mbl = row["TDI_TSL"] < row["TDI_MBL"] and row["TDI_RSI"] < row["TDI_MBL"]
                    crossed_up = prev_row["TDI_TSL"] <= prev_row["TDI_RSI"] and row["TDI_TSL"] > row["TDI_RSI"]
                    mbl_aligned = below_mbl and crossed_up
                else:
                    above_mbl = row["TDI_TSL"] > row["TDI_MBL"] and row["TDI_RSI"] > row["TDI_MBL"]
                    crossed_down = prev_row["TDI_TSL"] >= prev_row["TDI_RSI"] and row["TDI_TSL"] < row["TDI_RSI"]
                    mbl_aligned = above_mbl and crossed_down

            position = {
                "pair": pair,
                "direction": entry,
                "entry_date": date,
                "entry_price": row["Close"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "tsl_confirmed": tsl_confirmed,
                "mbl_aligned": mbl_aligned,
                "ema_confluence": ema_confluence,
                "ema_trend_pullback": ema_trend_pullback,
                "trigger_rsi_level": round(trigger_rsi_level, 2),
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades


def check_recent_shark_fin_signals(df, atr_multiplier, rr, lookback_days=5):
    """
    Checkt de laatste 'lookback_days' dagen (standaard 5 handelsdagen,
    ongeveer een week) op shark-fin-signalen, in plaats van alleen de
    allerlaatste candle. Nodig omdat dit signaal zeldzaam is (~0,2
    trades/week over alle markten) - een signaal dat een paar dagen
    geleden compleet werd, mag je niet missen als de scan die
    specifieke dag niet gecheckt is.

    Geeft een LIJST van signalen terug (kan leeg zijn, kan meerdere
    bevatten als er toevallig meerdere in het venster vallen). Elk
    signaal krijgt een 'days_ago' veld mee.
    """

    results = []

    last_index = len(df) - 1

    if last_index < 200:
        return results

    start_index = max(200, last_index - lookback_days + 1)

    for i in range(start_index, last_index + 1):

        row = df.iloc[i]
        prev_row = df.iloc[i - 1]

        entry = _determine_shark_fin_signal(df, i)

        if entry not in ("LONG", "SHORT"):
            continue

        if pd.isna(row["ATR"]) or row["ATR"] <= 0:
            continue

        stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
        take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

        tsl_confirmed = False
        if not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_PL"]):
            if entry == "SHORT":
                tsl_confirmed = row["TDI_TSL"] > row["TDI_PL"]
            else:
                tsl_confirmed = row["TDI_TSL"] < row["TDI_PL"]

        ema_confluence = False
        ema_trend_pullback = False
        if not pd.isna(row["EMA50"]) and not pd.isna(row["EMA200"]):
            low_ema = min(row["EMA50"], row["EMA200"])
            high_ema = max(row["EMA50"], row["EMA200"])
            ema_confluence = low_ema <= row["Close"] <= high_ema
            if entry == "SHORT":
                ema_trend_pullback = ema_confluence and row["EMA50"] < row["EMA200"]
            else:
                ema_trend_pullback = ema_confluence and row["EMA50"] > row["EMA200"]

        mbl_aligned = False
        if (not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_MBL"])
                and not pd.isna(row["TDI_RSI"]) and not pd.isna(prev_row["TDI_TSL"])
                and not pd.isna(prev_row["TDI_RSI"])):

            if entry == "SHORT":
                below_mbl = row["TDI_TSL"] < row["TDI_MBL"] and row["TDI_RSI"] < row["TDI_MBL"]
                crossed_up = prev_row["TDI_TSL"] <= prev_row["TDI_RSI"] and row["TDI_TSL"] > row["TDI_RSI"]
                mbl_aligned = below_mbl and crossed_up
            else:
                above_mbl = row["TDI_TSL"] > row["TDI_MBL"] and row["TDI_RSI"] > row["TDI_MBL"]
                crossed_down = prev_row["TDI_TSL"] >= prev_row["TDI_RSI"] and row["TDI_TSL"] < row["TDI_RSI"]
                mbl_aligned = above_mbl and crossed_down

        results.append({
            "direction": entry,
            "entry_price": row["Close"],
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "tsl_confirmed": tsl_confirmed,
            "mbl_aligned": mbl_aligned,
            "ema_confluence": ema_confluence,
            "ema_trend_pullback": ema_trend_pullback,
            "trigger_rsi_level": round(prev_row["TDI_RSI"], 2),
            "data_date": df.index[i],
            "days_ago": last_index - i,
        })

    return results


def check_latest_shark_fin_signal(df, atr_multiplier, rr):
    """Checkt ALLEEN de laatste dag op een TDI shark-fin-signaal."""

    i = len(df) - 1

    if i < 200:
        return None

    row = df.iloc[i]
    prev_row = df.iloc[i - 1]

    entry = _determine_shark_fin_signal(df, i)

    if entry not in ("LONG", "SHORT"):
        return None

    if pd.isna(row["ATR"]) or row["ATR"] <= 0:
        return None

    stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry)
    take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry)

    tsl_confirmed = False
    if not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_PL"]):
        if entry == "SHORT":
            tsl_confirmed = row["TDI_TSL"] > row["TDI_PL"]
        else:
            tsl_confirmed = row["TDI_TSL"] < row["TDI_PL"]

    ema_confluence = False
    ema_trend_pullback = False
    if not pd.isna(row["EMA50"]) and not pd.isna(row["EMA200"]):
        low_ema = min(row["EMA50"], row["EMA200"])
        high_ema = max(row["EMA50"], row["EMA200"])
        ema_confluence = low_ema <= row["Close"] <= high_ema

        if entry == "SHORT":
            ema_trend_pullback = ema_confluence and row["EMA50"] < row["EMA200"]
        else:
            ema_trend_pullback = ema_confluence and row["EMA50"] > row["EMA200"]

    mbl_aligned = False
    if (not pd.isna(row["TDI_TSL"]) and not pd.isna(row["TDI_MBL"])
            and not pd.isna(row["TDI_RSI"]) and not pd.isna(prev_row["TDI_TSL"])
            and not pd.isna(prev_row["TDI_RSI"])):

        if entry == "SHORT":
            below_mbl = row["TDI_TSL"] < row["TDI_MBL"] and row["TDI_RSI"] < row["TDI_MBL"]
            crossed_up = prev_row["TDI_TSL"] <= prev_row["TDI_RSI"] and row["TDI_TSL"] > row["TDI_RSI"]
            mbl_aligned = below_mbl and crossed_up
        else:
            above_mbl = row["TDI_TSL"] > row["TDI_MBL"] and row["TDI_RSI"] > row["TDI_MBL"]
            crossed_down = prev_row["TDI_TSL"] >= prev_row["TDI_RSI"] and row["TDI_TSL"] < row["TDI_RSI"]
            mbl_aligned = above_mbl and crossed_down

    return {
        "direction": entry,
        "entry_price": row["Close"],
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "tsl_confirmed": tsl_confirmed,
        "mbl_aligned": mbl_aligned,
        "ema_confluence": ema_confluence,
        "ema_trend_pullback": ema_trend_pullback,
        "trigger_rsi_level": round(prev_row["TDI_RSI"], 2),
        "data_date": df.index[i],
    }


def _cross_signal(df, i):
    """
    Bepaalt of er op dag i een RSI/TSL-kruising is (RSI kruist boven
    TSL = LONG-kruising, TSL kruist boven RSI = SHORT-kruising) - GEEN
    MBL-eis hier, dat is optie B (breed).

    Geeft (richting, mbl_position_ok) terug:
    - richting: 'LONG', 'SHORT' of '-'
    - mbl_position_ok: of TSL/RSI op dat moment OOK aan de juiste kant
      van de MBL zaten (optie A, als los, filterbaar label)
    """

    row = df.iloc[i]
    prev_row = df.iloc[i - 1]

    if (pd.isna(row["TDI_TSL"]) or pd.isna(row["TDI_RSI"])
            or pd.isna(prev_row["TDI_TSL"]) or pd.isna(prev_row["TDI_RSI"])):
        return "-", False

    crossed_down = prev_row["TDI_TSL"] >= prev_row["TDI_RSI"] and row["TDI_TSL"] < row["TDI_RSI"]
    crossed_up = prev_row["TDI_TSL"] <= prev_row["TDI_RSI"] and row["TDI_TSL"] > row["TDI_RSI"]

    mbl_known = not pd.isna(row["TDI_MBL"])

    if crossed_down:
        # RSI kruist boven TSL -> LONG-kruising
        mbl_position_ok = mbl_known and row["TDI_TSL"] > row["TDI_MBL"] and row["TDI_RSI"] > row["TDI_MBL"]
        return "LONG", mbl_position_ok

    if crossed_up:
        # TSL kruist boven RSI -> SHORT-kruising
        mbl_position_ok = mbl_known and row["TDI_TSL"] < row["TDI_MBL"] and row["TDI_RSI"] < row["TDI_MBL"]
        return "SHORT", mbl_position_ok

    return "-", False


def simulate_shark_fin_persistent_bias_trades(df, pair, atr_multiplier, rr):
    """
    'Aanhoudende bias'-strategie:
    - Een shark fin zet een richting (bias) neer, en is ZELF al een
      entry.
    - Zolang de bias actief is (dus totdat een shark fin in de
      TEGENOVERGESTELDE richting verschijnt), is ELKE latere MBL-
      kruising in dezelfde richting OOK een aparte entry.
    - Eén trade tegelijk (net als de andere strategieën) - een nieuwe
      entry wordt overgeslagen zolang de vorige nog open staat.

    Elke trade krijgt twee extra, meetbare kenmerken mee: 'price_above_ema200'
    (of eronder voor SHORT) en 'golden_cross_state' (EMA50 > EMA200,
    of 'death_cross_state' voor SHORT) - nog geen harde eis, wel te
    filteren achteraf.
    """

    trades = []
    position = None
    bias = None  # None, 'LONG' of 'SHORT'

    min_bars = 200

    for i in range(min_bars, len(df)):

        row = df.iloc[i]
        date = df.index[i]

        # --- Eerst: is er een open trade? Check exit ---
        if position is not None:

            exit_price = None
            outcome = None

            if position["direction"] == "LONG":
                if row["Low"] <= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["High"] >= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"
            else:
                if row["High"] >= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                    outcome = "LOSS"
                elif row["Low"] <= position["take_profit"]:
                    exit_price = position["take_profit"]
                    outcome = "WIN"

            if exit_price is not None:
                position["exit_date"] = date
                position["exit_price"] = exit_price
                position["outcome"] = outcome
                position["bars_held"] = i - position["entry_bar"]
                trades.append(position)
                position = None

            # Bias-update gebeurt ONAFHANKELIJK van open/gesloten
            # trades - een nieuwe shark fin kan de bias omdraaien
            # terwijl er nog een trade loopt (die trade loopt gewoon
            # af op zijn eigen SL/TP)
            fin_signal = _determine_shark_fin_signal(df, i)
            if fin_signal in ("LONG", "SHORT"):
                bias = fin_signal

            continue

        entry_signal = None

        # 1. Nieuwe shark fin? Die is zelf een entry, EN zet/bevestigt de bias.
        fin_signal = _determine_shark_fin_signal(df, i)
        mbl_position_ok = False

        if fin_signal in ("LONG", "SHORT"):
            bias = fin_signal
            entry_signal = fin_signal

        # 2. Geen nieuwe fin vandaag, maar wel een actieve bias EN een
        #    RSI/TSL-kruising in dezelfde richting? Ook een entry.
        #    (optie B: GEEN MBL-eis om mee te tellen - mbl_position_ok
        #    wordt wel apart getrackt, zodat optie A achteraf te
        #    filteren is)
        elif bias is not None:
            cross_signal, mbl_ok = _cross_signal(df, i)
            if cross_signal == bias:
                entry_signal = bias
                mbl_position_ok = mbl_ok

        if entry_signal in ("LONG", "SHORT"):

            if pd.isna(row["ATR"]) or row["ATR"] <= 0:
                continue

            stop_loss = calculate_stop_loss(row["Close"], row["ATR"], atr_multiplier, entry_signal)
            take_profit = calculate_take_profit(row["Close"], stop_loss, rr, entry_signal)

            price_above_ema200 = False
            golden_cross_state = False
            if not pd.isna(row["EMA50"]) and not pd.isna(row["EMA200"]):
                if entry_signal == "LONG":
                    price_above_ema200 = row["Close"] > row["EMA200"]
                    golden_cross_state = row["EMA50"] > row["EMA200"]
                else:
                    price_above_ema200 = row["Close"] < row["EMA200"]  # 'onder' voor SHORT
                    golden_cross_state = row["EMA50"] < row["EMA200"]  # 'death cross'-structuur

            position = {
                "pair": pair,
                "direction": entry_signal,
                "entry_date": date,
                "entry_price": row["Close"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_bar": i,
                "entry_type": "shark_fin" if fin_signal == entry_signal else "cross",
                "mbl_position_ok": mbl_position_ok,
                "price_above_ema200": price_above_ema200,
                "golden_cross_state": golden_cross_state,
            }

    if position is not None:
        position["exit_date"] = None
        position["exit_price"] = None
        position["outcome"] = "OPEN"
        position["bars_held"] = None
        trades.append(position)

    return trades


def check_recent_persistent_bias_signals(df, atr_multiplier, rr, lookback_days=5):
    """
    Live-check voor de aanhoudende-bias-strategie (V1: LONG-only,
    shark fin + cross-entries samen - crypto-uitsluiting gebeurt al
    op het niveau van SCAN_PAIRS in main.py, niet hier).

    Omdat de bias een status-machine is die de hele geschiedenis kent,
    draait dit de VOLLEDIGE simulatie opnieuw op de meegegeven data,
    en pikt daar de entries uit die in de laatste 'lookback_days'
    vielen - net als bij de eerdere shark-fin-lookback, om geen
    signaal te missen als je een dag niet had gecheckt.

    Geeft een lijst terug (kan leeg zijn).
    """

    trades = simulate_shark_fin_persistent_bias_trades(df, "LIVE", atr_multiplier, rr)

    if not trades:
        return []

    last_index = len(df) - 1
    date_to_index = {d: i for i, d in enumerate(df.index)}

    results = []

    for t in trades:

        if t["direction"] != "LONG":
            continue

        entry_idx = date_to_index.get(t["entry_date"])
        if entry_idx is None:
            continue

        days_ago = last_index - entry_idx

        if 0 <= days_ago < lookback_days:
            results.append({
                "direction": t["direction"],
                "entry_price": t["entry_price"],
                "stop_loss": t["stop_loss"],
                "take_profit": t["take_profit"],
                "entry_type": t["entry_type"],
                "data_date": t["entry_date"],
                "days_ago": days_ago,
            })

    return results


def check_open_persistent_bias_position(df, atr_multiplier, rr):
    """
    Checkt of er een LOPENDE (nog niet gesloten) positie is vanuit de
    aanhoudende-bias-strategie - los van check_recent_persistent_bias_signals,
    die alleen NIEUWE entries uit de laatste dagen toont. Dit maakt
    zichtbaar WAAROM er soms geen nieuw signaal verschijnt: als de
    vorige trade nog open staat, wordt er bewust geen nieuwe entry
    genomen (één trade tegelijk), ook al zou een latere kruising er
    normaal wel aan voldoen.

    Geeft None terug als er geen open LONG-positie is.
    """

    trades = simulate_shark_fin_persistent_bias_trades(df, "LIVE", atr_multiplier, rr)

    if not trades:
        return None

    last_trade = trades[-1]

    if last_trade["outcome"] != "OPEN":
        return None

    if last_trade["direction"] != "LONG":
        return None

    last_index = len(df) - 1
    date_to_index = {d: i for i, d in enumerate(df.index)}
    entry_idx = date_to_index.get(last_trade["entry_date"])
    days_open = last_index - entry_idx if entry_idx is not None else None

    return {
        "direction": last_trade["direction"],
        "entry_price": last_trade["entry_price"],
        "stop_loss": last_trade["stop_loss"],
        "take_profit": last_trade["take_profit"],
        "entry_type": last_trade["entry_type"],
        "entry_date": last_trade["entry_date"],
        "days_open": days_open,
    }