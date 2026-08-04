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

# RSI-divergentie
RSI_WINDOW = 14
DIVERGENCE_LOOKBACK = 40   # hoeveel candles terug om divergentie te zoeken
DIVERGENCE_ORDER = 3       # hoe streng een swing point gedefinieerd wordt
DIVERGENCE_SCORE = 20      # punten erbij in de confidence-score bij divergentie

# EMA-afstandsfilter (waarschuwing bij te ver uitgerekte instap)
EMA_SPAN = 21
EMA_EXTENDED_THRESHOLD_ATR = 3   # vanaf hoeveel ATR's afstand een instap "uitgerekt" is

# Maximale confidence-score (gebruikt om % te berekenen)
MAX_SCORE = 30 + 25 + 25 + DIVERGENCE_SCORE  # = 100


# ===========================
# OUTPUT
# ===========================

DEBUG = False