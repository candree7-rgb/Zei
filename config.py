import os
from dotenv import load_dotenv

load_dotenv()

def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def _get_bool(name: str, default: str = "false") -> bool:
    return _get(name, default).lower() in ("1","true","yes","y","on")

def _get_int(name: str, default: str) -> int:
    return int(_get(name, default))

def _get_float(name: str, default: str) -> float:
    return float(_get(name, default))

# Discord
DISCORD_TOKEN = _get("DISCORD_TOKEN")
CHANNEL_ID    = _get("CHANNEL_ID")

# Bybit
BYBIT_API_KEY    = _get("BYBIT_API_KEY")
BYBIT_API_SECRET = _get("BYBIT_API_SECRET")
BYBIT_TESTNET    = _get_bool("BYBIT_TESTNET","false")
BYBIT_DEMO       = _get_bool("BYBIT_DEMO","false")  # Demo trading (paper trading)
ACCOUNT_TYPE     = _get("ACCOUNT_TYPE","UNIFIED")  # UNIFIED / CONTRACT etc (depends on your Bybit account)

# Bot identification (for multi-bot dashboard support)
BOT_ID = _get("BOT_ID", "ao")  # Unique identifier for this bot instance

# Signal Parser Version: "v1" = original embed format, "v2" = AO plain text, "v3" = Crypto Signals (H1/M15)
SIGNAL_PARSER_VERSION = _get("SIGNAL_PARSER_VERSION", "v3").lower()

# Allowed timeframes for V3 signals (comma-separated)
# Example: "H1,M15,H4" or just "H1,M15"
ALLOWED_TIMEFRAMES = [x.strip().upper() for x in _get("ALLOWED_TIMEFRAMES", "H1,M15,H4").split(",") if x.strip()]

RECV_WINDOW = _get("RECV_WINDOW","5000")

# Trading
CATEGORY = _get("CATEGORY","linear")   # linear for USDT perpetual
QUOTE    = _get("QUOTE","USDT").upper()

LEVERAGE = _get_int("LEVERAGE","5")
RISK_PCT = _get_float("RISK_PCT","5")

# ============================================================
# DYNAMIC POSITION SIZING (Risk-Based)
# ============================================================
# Calculate position size based on SL distance for consistent risk per trade
# This is the mathematically optimal approach (Fixed Fractional / Kelly-lite)

# Enable dynamic sizing (position size based on SL distance)
DYNAMIC_SIZING_ENABLED = _get_bool("DYNAMIC_SIZING_ENABLED", "true")

# Risk per trade as % of equity (how much you lose if SL hits)
# 2% is conservative, 5% is aggressive
RISK_PER_TRADE_PCT = _get_float("RISK_PER_TRADE_PCT", "2.0")

# Maximum leverage to use (safety cap)
MAX_LEVERAGE = _get_int("MAX_LEVERAGE", "50")

# Minimum leverage (for very tight SL)
MIN_LEVERAGE = _get_int("MIN_LEVERAGE", "5")

# Limits / Safety
MAX_CONCURRENT_TRADES = _get_int("MAX_CONCURRENT_TRADES","3")
MAX_TRADES_PER_DAY    = _get_int("MAX_TRADES_PER_DAY","20")
TC_MAX_LAG_SEC        = _get_int("TC_MAX_LAG_SEC","300")

# Entry rules
# Timeframe-based entry expiration (in minutes)
# If specific timeframe not set, falls back to ENTRY_EXPIRATION_MIN
ENTRY_EXPIRATION_M15 = _get_int("ENTRY_EXPIRATION_M15", "30")   # ~2 candles
ENTRY_EXPIRATION_H1  = _get_int("ENTRY_EXPIRATION_H1", "120")   # ~2 candles
ENTRY_EXPIRATION_H4  = _get_int("ENTRY_EXPIRATION_H4", "480")   # ~2 candles
ENTRY_EXPIRATION_MIN = _get_int("ENTRY_EXPIRATION_MIN", "180")  # Fallback default

def get_entry_expiration(timeframe: str) -> int:
    """Get entry expiration in minutes based on signal timeframe."""
    tf = timeframe.upper() if timeframe else ""
    if tf == "M15":
        return ENTRY_EXPIRATION_M15
    elif tf == "H1":
        return ENTRY_EXPIRATION_H1
    elif tf == "H4":
        return ENTRY_EXPIRATION_H4
    return ENTRY_EXPIRATION_MIN

ENTRY_TOO_FAR_PCT            = _get_float("ENTRY_TOO_FAR_PCT","0.5")
ENTRY_TOO_FAR_NO_TP_PCT      = _get_float("ENTRY_TOO_FAR_NO_TP_PCT","15.0")  # Fallback when TP1 unknown (more lenient)
ENTRY_TRIGGER_BUFFER_PCT     = _get_float("ENTRY_TRIGGER_BUFFER_PCT","0.0")
ENTRY_LIMIT_PRICE_OFFSET_PCT = _get_float("ENTRY_LIMIT_PRICE_OFFSET_PCT","0.0")
ENTRY_EXPIRATION_PRICE_PCT   = _get_float("ENTRY_EXPIRATION_PRICE_PCT","0.6")

# TP/SL
MOVE_SL_TO_BE_ON_TP1 = _get_bool("MOVE_SL_TO_BE_ON_TP1","true")
BE_BUFFER_PCT = _get_float("BE_BUFFER_PCT","0.15")  # Buffer for BE SL (0.15% = slight profit instead of exact entry)
INITIAL_SL_PCT = _get_float("INITIAL_SL_PCT","19.0")  # SL distance from entry in %

# Follow-TP: Move SL to previous TP level after each TP hit
# Example: TP1 hit → SL to BE, TP2 hit → SL to TP1, TP3 hit → SL to TP2
FOLLOW_TP_ENABLED = _get_bool("FOLLOW_TP_ENABLED", "false")
FOLLOW_TP_BUFFER_PCT = _get_float("FOLLOW_TP_BUFFER_PCT", "0.1")  # Buffer above/below TP level

# Max SL distance filter: Skip signals where SL is more than X% from entry
# Set to 0 to disable this filter
MAX_SL_DISTANCE_PCT = _get_float("MAX_SL_DISTANCE_PCT", "0")

# Cap SL distance: If signal SL is further than X%, cap it at X%
# Unlike MAX_SL_DISTANCE_PCT (which skips), this ADJUSTS the SL to be closer
# Set to 0 to disable (use signal's SL as-is)
CAP_SL_DISTANCE_PCT = _get_float("CAP_SL_DISTANCE_PCT", "0")

# Min signal leverage filter: Skip signals where leverage in signal text is below this
# AO Trading uses 25x for normal signals, 5x for risky ones (wider SL)
# Set to 0 to disable this filter (V3 signals have no leverage info)
MIN_SIGNAL_LEVERAGE = _get_int("MIN_SIGNAL_LEVERAGE", "0")

# ============================================================
# TREND LEG FILTER (Zeiierman Strategy)
# ============================================================
# Analyzes price action to determine trend leg and skip late entries
# Best entries: Leg 1-3 (early trend, after pullbacks #1-#2)
# Skip: Leg 4-5 (late trend, higher reversal risk)

# Enable/disable leg filter
LEG_FILTER_ENABLED = _get_bool("LEG_FILTER_ENABLED", "true")

# Maximum allowed leg for entry (1-3 recommended, 0 = disabled)
# Leg 1-2: Best R:R, fresh momentum
# Leg 3: Still good, but watch for exhaustion
# Leg 4-5: Skip (late trend, "last flush" risk)
MAX_ALLOWED_LEG = _get_int("MAX_ALLOWED_LEG", "3")

# Swing detection lookback (how many candles to look on each side)
# Higher = fewer swing points, more reliable but less sensitive
# Lower = more swing points, more sensitive but more noise
SWING_LOOKBACK = _get_int("SWING_LOOKBACK", "5")

# Number of candles to fetch for trend analysis
# More candles = better trend context, but slower
TREND_CANDLES = _get_int("TREND_CANDLES", "200")

# Skip signals where trend direction doesn't match signal side
# BUY should be in uptrend, SELL should be in downtrend
REQUIRE_TREND_ALIGNMENT = _get_bool("REQUIRE_TREND_ALIGNMENT", "true")

# ============================================================
# SIGNAL BATCHING (Multiple signals at same time)
# ============================================================
# When multiple signals arrive at the same time (e.g., every 15 min),
# collect them, analyze all, and pick the BEST one based on score.

# Enable signal batching (analyze all, pick best)
SIGNAL_BATCH_ENABLED = _get_bool("SIGNAL_BATCH_ENABLED", "true")

# Time window to collect signals (seconds)
# Signals within this window are batched together
SIGNAL_BATCH_WINDOW_SEC = _get_int("SIGNAL_BATCH_WINDOW_SEC", "30")

# Maximum signals to trade per batch (usually 1)
# Set to 1 to only trade the best signal per batch
MAX_SIGNALS_PER_BATCH = _get_int("MAX_SIGNALS_PER_BATCH", "1")

# TP_SPLITS: percentage of position to close at each TP level
# Example: 50,50 means 100% total (50% at TP1, 50% at TP2)
# For V3 signals with 2 TPs, use: 50,50
# DO NOT normalize - allow sum < 100% for runner positions
TP_SPLITS = [float(x) for x in _get("TP_SPLITS","50,50").split(",") if x.strip()]
if sum(TP_SPLITS) > 100.0:
    # Only normalize if over 100% (user error)
    s = sum(TP_SPLITS)
    TP_SPLITS = [x * 100.0 / s for x in TP_SPLITS]

# TP_SPLITS_AUTO: if true, automatically calculate equal splits based on number of TPs
# Example: 5 TPs = 20% each, 4 TPs = 25% each, 3 TPs = 33% each
TP_SPLITS_AUTO = _get_bool("TP_SPLITS_AUTO", "false")

# Fallback TP distances (% from entry) if signal has no TPs
FALLBACK_TP_PCT = [float(x) for x in _get("FALLBACK_TP_PCT","0.85,1.65,4.0").split(",") if x.strip()]

TRAIL_AFTER_TP_INDEX = _get_int("TRAIL_AFTER_TP_INDEX","3")  # start trailing when TPn filled
TRAIL_DISTANCE_PCT   = _get_float("TRAIL_DISTANCE_PCT","2.0")
TRAIL_ACTIVATE_ON_TP = _get_bool("TRAIL_ACTIVATE_ON_TP","true")

# DCA sizing multipliers vs BASE qty
# Example: 1.5 means DCA1 = 1.5x base qty
# Only places as many DCAs as there are multipliers (ignores extra DCA prices from signal)
# AO Trading typically has only 1 DCA or none
DCA_QTY_MULTS = [float(x) for x in _get("DCA_QTY_MULTS","1.5").split(",") if x.strip()]

# Timing
POLL_SECONDS    = _get_int("POLL_SECONDS","15")
POLL_JITTER_MAX = _get_int("POLL_JITTER_MAX","5")
SIGNAL_UPDATE_INTERVAL_SEC = _get_int("SIGNAL_UPDATE_INTERVAL_SEC", "15")  # How often to re-check signals for SL/TP/DCA updates

# Quarter-hour polling mode (for signal providers that only send at XX:00, XX:15, XX:30, XX:45)
# When enabled, bot sleeps until next quarter-hour + buffer instead of polling every POLL_SECONDS
POLL_QUARTER_HOUR = _get_bool("POLL_QUARTER_HOUR", "true")  # Enable quarter-hour polling
POLL_QUARTER_BUFFER_SEC = _get_int("POLL_QUARTER_BUFFER_SEC", "3")  # Seconds after quarter-hour to poll (e.g., 3 = poll at XX:00:03)

# Misc
DRY_RUN     = _get_bool("DRY_RUN","true")
STATE_FILE  = _get("STATE_FILE","state.json")
LOG_LEVEL   = _get("LOG_LEVEL","INFO").upper()

# Telegram Alerts
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = _get("TELEGRAM_CHAT_ID")
# Position P&L thresholds to trigger alerts (e.g., 25,35,50 = alert at -25%, -35%, -50%)
POSITION_ALERT_THRESHOLDS = [float(x) for x in _get("POSITION_ALERT_THRESHOLDS", "25,35,50").split(",") if x.strip()]
