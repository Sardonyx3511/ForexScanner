# ============================================
# RISK MANAGEMENT
# ============================================

def calculate_stop_loss(entry, atr, multiplier, direction):
    """
    Berekent de stop loss op basis van ATR.
    """

    if direction == "LONG":
        return entry - (atr * multiplier)

    if direction == "SHORT":
        return entry + (atr * multiplier)

    return None


def calculate_take_profit(entry, stop_loss, rr, direction):
    """
    Berekent take profit op basis van Risk/Reward.
    """

    if stop_loss is None:
        return None

    risk = abs(entry - stop_loss)

    if direction == "LONG":
        return entry + (risk * rr)

    if direction == "SHORT":
        return entry - (risk * rr)

    return None

def calculate_lot_size(account_size, risk_percent, entry, stop_loss, pair):
    """
    Berekent een (indicatieve) lotgrootte op basis van je accountgrootte,
    risicopercentage en de afstand tot de stop loss.

    Exact correct voor paren waarbij USD de quote-valuta is
    (bijv. EURUSD, GBPUSD, AUDUSD). Voor overige paren (bijv. USDJPY,
    EURJPY, GBPCHF) is dit een INDICATIE - controleer de exacte
    pipwaarde bij je broker/propfirm voor je instapt.
    """

    if stop_loss is None or entry is None:
        return None, ""

    stop_distance = abs(entry - stop_loss)

    if stop_distance == 0:
        return None, ""

    risk_amount = account_size * (risk_percent / 100)

    clean_pair = pair.replace("=X", "")
    quote_currency = clean_pair[3:6]

    units = risk_amount / stop_distance
    lot_size = round(units / 100000, 2)  # 100.000 units = 1 standaardlot

    if quote_currency == "USD":
        risk_note = ""
    else:
        risk_note = " (indicatief, check pipwaarde bij broker)"

    return lot_size, risk_note