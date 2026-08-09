# ===========================
# ACCOUNT
# ===========================

ACCOUNT_SIZE = 5000
RISK_PERCENT = 1.0

# ===========================
# STRATEGY
# ===========================

ADX_MIN = 25

STOCH_OVERSOLD = 20
STOCH_OVERBOUGHT = 80

ATR_MULTIPLIER = 2.0

RR = 2.0

# RR specifiek voor de pullback-strategie (SHORT + divergentie) - dit
# kwam als beste uit de out-of-sample-validatie, apart van de RR die
# de breakout-strategie gebruikt.
PULLBACK_RR = 1.5

# RSI-divergentie
RSI_WINDOW = 14
DIVERGENCE_LOOKBACK = 40
DIVERGENCE_ORDER = 3
DIVERGENCE_SCORE = 20

# EMA-afstandsfilter
EMA_SPAN = 21
EMA_EXTENDED_THRESHOLD_ATR = 3

MAX_SCORE = 30 + 25 + 25 + DIVERGENCE_SCORE  # = 100


# ===========================
# MARKTEN
# ===========================
# Crypto is gecureerd op basis van je Cryptofundtrader-symbolenlijst:
# alleen gevestigde, bekende munten (top ~150 qua marktkapitalisatie)
# die ook in jouw broker-aanbod voorkomen. De overige ~430 obscure/
# meme-tickers uit je volledige lijst zijn bewust weggelaten - die
# hebben zeer waarschijnlijk geen data op yfinance en zouden alleen
# scantijd verspillen zonder toegevoegde waarde.
#
# Stocks is nieuw: 25 liquide Amerikaanse aandelen uit je broker-lijst -
# deze hebben altijd betrouwbare volumedata, een goede fit voor de
# breakout+volume-strategie.

FOREX_PAIRS = [
    "AUDCAD=X","AUDCHF=X","AUDJPY=X","AUDNZD=X","AUDUSD=X",
    "CADCHF=X","CADJPY=X","CHFJPY=X","EURAUD=X","EURCAD=X",
    "EURCHF=X","EURGBP=X","EURJPY=X","EURNOK=X","EURNZD=X",
    "EURSEK=X","EURUSD=X","GBPAUD=X","GBPCAD=X","GBPCHF=X",
    "GBPJPY=X","GBPNZD=X","GBPUSD=X","HKDJPY=X","MXNJPY=X",
    "NZDCAD=X","NZDCHF=X","NZDJPY=X","NZDUSD=X","PLNJPY=X",
    "SGDJPY=X","TRYJPY=X","USDCAD=X","USDCHF=X","USDHUF=X",
    "USDILS=X","USDJPY=X","USDMXN=X","USDNOK=X","USDPLN=X",
    "USDSEK=X","USDTRY=X","USDZAR=X","ZARJPY=X",
]

CRYPTO_PAIRS = [
    "1INCH-USD","AAVE-USD","ADA-USD","ALGO-USD","ANKR-USD",
    "API3-USD","APT-USD","ARB-USD","ARK-USD","ATOM-USD",
    "AVAX-USD","AXS-USD","BAND-USD","BAT-USD","BCH-USD",
    "BNB-USD","BNT-USD","BONK-USD","BTC-USD","CAKE-USD",
    "CELO-USD","CHZ-USD","COMP-USD","CRO-USD","CRV-USD",
    "CTSI-USD","CVX-USD","DASH-USD","DGB-USD","DODO-USD",
    "DOGE-USD","DOT-USD","EGLD-USD","ENJ-USD","ENS-USD",
    "ETC-USD","ETH-USD","FIL-USD","FLOW-USD","FTM-USD",
    "GALA-USD","GAS-USD","GMX-USD","GNO-USD","GRT-USD",
    "HBAR-USD","ICP-USD","ICX-USD","IMX-USD","INJ-USD",
    "IOTA-USD","JASMY-USD","JUP-USD","KAS-USD","KAVA-USD",
    "KNC-USD","LDO-USD","LINK-USD","LRC-USD","LSK-USD",
    "LTC-USD","MANA-USD","MASK-USD","MKR-USD","MNT-USD",
    "NEAR-USD","NEO-USD","NMR-USD","OKB-USD","ONE-USD",
    "ONT-USD","OP-USD","PEPE-USD","PERP-USD","POL-USD",
    "POWR-USD","PYTH-USD","QNT-USD","QTUM-USD","RENDER-USD",
    "RLC-USD","ROSE-USD","RUNE-USD","RVN-USD","SAND-USD",
    "SC-USD","SEI-USD","SHIB-USD","SKL-USD","SNX-USD",
    "SOL-USD","STEEM-USD","STORJ-USD","STX-USD","SUI-USD",
    "SYS-USD","TAO-USD","THETA-USD","TIA-USD","TON-USD",
    "TRX-USD","UMA-USD","VET-USD","WAVES-USD","WIF-USD",
    "WOO-USD","XLM-USD","XMR-USD","XRP-USD","XTZ-USD",
    "XVG-USD","YFI-USD","ZEC-USD","ZEN-USD","ZIL-USD",
    "ZRX-USD",
]

STOCKS_PAIRS = [
    "BABA","F","LMT","PEP","GOOG",
    "DIS","TSLA","APA","AAPL","SNAP",
    "BAC","GM","RACE","MSFT","C",
    "WMT","INTC","XOM","GS","NFLX",
    "EBAY","AMZN","META","BA","SBUX",
]

METALS_PAIRS = [
    "GC=F",   # Goud
    "SI=F",   # Zilver
    "PL=F",   # Platina
    "PA=F",   # Palladium
    "HG=F",   # Koper
]

INDICES_PAIRS = [
    "^NDX",        # NAS100 / US100
    "^DJI",        # US30
    "^GSPC",       # SPX500 / US500
    "^GDAXI",      # DAX40 (dekt ook 'DAX 30')
    "^FTSE",       # FTSE100 / UK100
    "^N225",       # Nikkei225 / J225
    "^FCHI",       # France 40
    "^STOXX50E",   # Europe 50
    "^HSI",        # Hang Seng
    "FTSEMIB.MI",  # FTSE MIB 40 (Italy) - check zelf of dit werkt
    "^RUT",        # Russell 2000 (US2000)
    "^IBEX",       # Spain 35 (IBEX)
    "^AXJO",       # Australia 200
]

COMMODITIES_PAIRS = [
    "CL=F",   # WTI Oil
    "BZ=F",   # Brent Oil
    "NG=F",   # Natural Gas
    "CT=F",   # Cotton
    "ZS=F",   # Soybean
    "KC=F",   # Coffee
    "SB=F",   # Sugar
    "ZW=F",   # Wheat
    "CC=F",   # Cocoa
    "ZC=F",   # Corn
]

ALL_PAIRS = FOREX_PAIRS + CRYPTO_PAIRS + STOCKS_PAIRS + METALS_PAIRS + INDICES_PAIRS + COMMODITIES_PAIRS

# Leesbare namen voor tickers die geen duidelijke naam hebben
FRIENDLY_NAMES = {
    "^NDX": "NAS100",
    "^DJI": "US30",
    "^GSPC": "SPX500",
    "^GDAXI": "DAX40",
    "^FTSE": "FTSE100",
    "^N225": "NIKKEI225",
    "^FCHI": "FRANCE40",
    "^STOXX50E": "EUROPE50",
    "^HSI": "HANGSENG",
    "FTSEMIB.MI": "ITALY40",
    "^RUT": "RUSSELL2000",
    "^IBEX": "SPAIN35",
    "^AXJO": "AUSTRALIA200",
    "CL=F": "WTI_OIL",
    "BZ=F": "BRENT_OIL",
    "NG=F": "NATGAS",
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "PL=F": "PLATINUM",
    "PA=F": "PALLADIUM",
    "HG=F": "COPPER",
    "CT=F": "COTTON",
    "ZS=F": "SOYBEAN",
    "KC=F": "COFFEE",
    "SB=F": "SUGAR",
    "ZW=F": "WHEAT",
    "CC=F": "COCOA",
    "ZC=F": "CORN",
}


def clean_pair_name(pair):
    """Geeft een leesbare naam terug voor een ticker, ongeacht het type."""
    if pair in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[pair]
    return pair.replace("=X", "").replace("-USD", "USD")


def get_asset_class(pair):
    """Bepaalt tot welke assetklasse een ticker behoort."""
    if pair in FOREX_PAIRS:
        return "forex"
    if pair in CRYPTO_PAIRS:
        return "crypto"
    if pair in STOCKS_PAIRS:
        return "stocks"
    if pair in METALS_PAIRS:
        return "metals"
    if pair in INDICES_PAIRS:
        return "indices"
    if pair in COMMODITIES_PAIRS:
        return "commodities"
    return "unknown"


# ===========================
# OUTPUT
# ===========================

DEBUG = False
MONITOR_MAX_ROWS = 15