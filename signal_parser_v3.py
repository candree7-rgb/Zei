import re
import hashlib
from typing import Any, Dict, Optional, List

from config import ALLOWED_TIMEFRAMES

NUM = r"([0-9]+(?:\.[0-9]+)?)"

# ============================================================
# CRYPTO SIGNALS V3 FORMAT (Plain text, emoji-based)
# ============================================================
# Example Signal:
# @Crypto Signal H1
# 🎯 Trading Signals 🎯
# BUY 📈 on ATOM/USD at Price: 2.576
# ✅ TP 1: 2.657
# ✅ TP 2: 2.676
# ❌ SL : 2.477
# Timeframe: H1
#
# --- OR ---
#
# @Crypto Signal M15
# 🎯 Trading Signals 🎯
# SELL 📉 on AVAX/USD at Price: 13.92
# ✅ TP 1: 13.79
# ✅ TP 2: 13.79
# ❌ SL : 14.07
# Timeframe: M15
# ============================================================

# ALLOWED_TIMEFRAMES is imported from config.py (set via ENV)

# ALLOWED QUOTE CURRENCIES (skip BTC, ETH pairs etc.)
ALLOWED_QUOTES = ["USD", "USDT"]

# SYMBOL MAPPING for Bybit (some coins have different names)
SYMBOL_MAP = {
    "LUNA": "LUNA2",  # Terra Luna Classic is LUNA2 on Bybit
}

# Signal header: "🎯 Trading Signals 🎯"
RE_HEADER = re.compile(
    r"🎯\s*Trading\s+Signals\s*🎯",
    re.I
)

# Side and Symbol: "BUY 📈 on ATOM/USD at Price: 2.576"
# or: "SELL 📉 on AVAX/USD at Price: 13.92"
# Note: Use (?:📈|📉)? instead of [📈📉]? because emojis are multi-byte
RE_SIDE_SYMBOL = re.compile(
    r"(BUY|SELL)\s*(?:📈|📉)?\s*on\s+([A-Z0-9]+)/([A-Z]+)\s+at\s+Price\s*:\s*" + NUM,
    re.I
)

# TP: "✅ TP 1: 2.657" or "TP 1: 2.657"
RE_TP = re.compile(
    r"(?:✅\s*)?TP\s*(\d+)\s*:\s*" + NUM,
    re.I
)

# Stop Loss: "❌ SL : 2.477" or "SL : 2.477"
RE_SL = re.compile(
    r"(?:❌\s*)?SL\s*:\s*" + NUM,
    re.I
)

# Timeframe: "Timeframe: H1" or "Timeframe: M15"
RE_TIMEFRAME = re.compile(
    r"Timeframe\s*:\s*([A-Z0-9]+)",
    re.I
)


def parse_single_signal_block(block: str, timeframe: str, quote: str = "USDT") -> Optional[Dict[str, Any]]:
    """Parse a single signal block (one BUY/SELL with its TPs and SL)."""
    # Parse side and symbol: "BUY 📈 on ATOM/USD at Price: 2.576"
    ms = RE_SIDE_SYMBOL.search(block)
    if not ms:
        return None

    side_word = ms.group(1).upper()
    base = ms.group(2).upper()
    quote_from_signal = ms.group(3).upper()  # USD or USDT from signal
    trigger = float(ms.group(4))

    # Only allow USD and USDT pairs (skip BTC, ETH pairs etc.)
    if quote_from_signal not in ALLOWED_QUOTES:
        return None

    side = "sell" if side_word == "SELL" else "buy"

    # Apply symbol mapping (e.g., LUNA → LUNA2 for Bybit)
    base = SYMBOL_MAP.get(base, base)

    # Convert to Bybit symbol (always USDT perpetual)
    symbol = f"{base}{quote}"

    # Parse TP prices (only in this block)
    tps: List[float] = []
    for m in RE_TP.finditer(block):
        idx = int(m.group(1))
        price = float(m.group(2))
        while len(tps) < idx:
            tps.append(0.0)
        tps[idx-1] = price
    tps = [p for p in tps if p > 0]

    # Parse Stop Loss (only in this block)
    sl = None
    msl = RE_SL.search(block)
    if msl:
        sl = float(msl.group(1))

    return {
        "base": base,
        "symbol": symbol,
        "side": side,
        "trigger": trigger,
        "tp_prices": tps,
        "dca_prices": [],
        "sl_price": sl,
        "leverage": None,
        "timeframe": timeframe,
        "raw": block,
    }


def parse_signal(text: str, quote: str = "USDT") -> Optional[Dict[str, Any]]:
    """
    Parse Crypto Signals V3 format (emoji-based plain text).

    If multiple signals in one message, returns the FIRST valid one.
    Use parse_all_signals() to get all signals.

    Returns None if:
    - Not a Trading Signals message
    - Timeframe not in ALLOWED_TIMEFRAMES (H1, M15, H4)
    - Cannot parse symbol/side or entry price
    """
    signals = parse_all_signals(text, quote)
    return signals[0] if signals else None


def parse_all_signals(text: str, quote: str = "USDT") -> List[Dict[str, Any]]:
    """
    Parse ALL signals from a message (handles multi-signal messages).

    Returns list of parsed signals (may be empty).
    """
    # Check for header
    if not RE_HEADER.search(text):
        return []

    # Check timeframe - only allow configured timeframes
    mtf = RE_TIMEFRAME.search(text)
    if not mtf:
        return []

    timeframe = mtf.group(1).upper()
    if timeframe not in ALLOWED_TIMEFRAMES:
        return []

    # Find all BUY/SELL occurrences to split multi-signal messages
    signal_matches = list(RE_SIDE_SYMBOL.finditer(text))

    if not signal_matches:
        return []

    results = []

    for i, match in enumerate(signal_matches):
        # Extract block for this signal (from this match to next match or end)
        start = match.start()
        end = signal_matches[i + 1].start() if i + 1 < len(signal_matches) else len(text)
        block = text[start:end]

        sig = parse_single_signal_block(block, timeframe, quote)
        if sig:
            sig["raw"] = text  # Keep full message as raw
            results.append(sig)

    return results


def parse_signal_update(text: str) -> Dict[str, Any]:
    """
    Parse signal for SL/TP updates only.

    Unlike parse_signal(), this does NOT require specific header.
    Used for checking if an existing signal was updated with new SL/TP values.

    Returns dict with sl_price and tp_prices (may be None/empty if not found).
    """
    result = {
        "sl_price": None,
        "dca_prices": [],
        "tp_prices": [],
    }

    # Parse Stop Loss
    msl = RE_SL.search(text)
    if msl:
        result["sl_price"] = float(msl.group(1))

    # Parse TP prices
    tps: List[float] = []
    for m in RE_TP.finditer(text):
        idx = int(m.group(1))
        price = float(m.group(2))
        while len(tps) < idx:
            tps.append(0.0)
        tps[idx-1] = price
    result["tp_prices"] = [p for p in tps if p > 0]

    return result


def signal_hash(sig: Dict[str, Any]) -> str:
    """Generate unique hash for signal deduplication."""
    core = f"{sig.get('symbol')}|{sig.get('side')}|{sig.get('trigger')}|{sig.get('tp_prices')}"
    return hashlib.md5(core.encode("utf-8")).hexdigest()
