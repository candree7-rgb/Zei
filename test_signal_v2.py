#!/usr/bin/env python3
"""Test script for signal_parser_v2.py"""

from signal_parser_v2 import parse_signal, parse_signal_update, signal_hash

# Test signals from user examples
TEST_SIGNALS = [
    # Signal 1: BUY with 5 TPs (closed trade - should return None)
    """<@&1428362286581551125> 📊 NEW SIGNAL • SAPIEN • Entry $0.13236

BUY SAPIENUSDT Entry: 0.13236 CMP 25x LEVERAGE

✅ **Final P&L:** `+479.56%`

**SL:** `0.13236` ✅ *Moved to BE*

**TPs:**
✅ **TP1:** `0.13501` *HIT* (+50.00%)
✅ **TP2:** `0.13765` *HIT* (+100.00%)
✅ **TP3:** `0.14295` *HIT* (+200.00%)
✅ **TP4:** `0.15354` *HIT* (+400.00%)
🎯 **TP5:** `0.17472` **→ NEXT**

**📊 TRADE NOW:**
[ByBit](<https://www.bybit.com/trade/usdt/sapienusdt?affiliate_id=54976>)

`✅ TRADE CLOSED - 4/5 TPs hit, Final profit: +243.65%`

*Last Updated: <t:1767194633:R>*""",

    # Signal 2: BUY cancelled (should return None)
    """<@&1428362286581551125> 📊 NEW SIGNAL • LIGHT • Entry $0.92650

BUY LIGHTUSDT Entry: 0.92650 CMP 25x LEVERAGE

🚫 **Trade closed without entry**

**SL:** `0.86560` ⏳ *Active*

**TPs:**
🎯 **TP1:** `0.93762` **→ NEXT**
⏳ **TP2:** `0.94874` *Pending*
⏳ **TP3:** `0.97097` *Pending*
⏳ **TP4:** `1.00062` *Pending*

`❌ TRADE CANCELLED - Entry not triggered`

*Last Updated: <t:1767175605:R>*""",

    # Signal 3: SELL with 5 TPs (closed - should return None)
    """<@&1428362286581551125> 📊 NEW SIGNAL • LIGHT • Entry $1.16170

SELL LIGHTUSDT Entry: 1.16170 CMP 25x LEVERAGE

✅ **Final P&L:** `+158.39%`

**SL:** `1.16170` ✅ *Moved to BE*

**TPs:**
✅ **TP1:** `1.14776` *HIT* (+30.00%)
✅ **TP2:** `1.13382` *HIT* (+60.00%)
✅ **TP3:** `1.10594` *HIT* (+120.00%)
🎯 **TP4:** `1.06876` **→ NEXT**
⏳ **TP5:** `0.78996` *Pending*

`📉 TRADE CLOSED - 3/5 TPs hit`

*Last Updated: <t:1767179440:R>*""",

    # Signal 4: SELL with 4 TPs (closed - should return None)
    """<@&1428362286581551125> 📊 NEW SIGNAL • ACT • Entry $0.03426

SELL ACTUSDT Entry: 0.03426 CMP 25x LEVERAGE

✅ **Final P&L:** `+37.22%`

**SL:** `0.03426` ✅ *Moved to BE*

**TPs:**
✅ **TP1:** `0.03378` *HIT* (+35.00%)
🎯 **TP2:** `0.03289` **→ NEXT**
⏳ **TP3:** `0.03152` *Pending*
⏳ **TP4:** `0.02878` *Pending*

`⚖️ CLOSED AT BREAKEVEN - Highest profit: +37.22%`

*Last Updated: <t:1767192641:R>*""",

    # Signal 5: FRESH BUY signal (should be parsed!)
    """<@&1428362286581551125> 📊 NEW SIGNAL • BTC • Entry $95000.50

BUY BTCUSDT Entry: 95000.50 CMP 25x LEVERAGE

**SL:** `93500.00` ⏳ *Active*

**TPs:**
🎯 **TP1:** `96000.00` **→ NEXT**
⏳ **TP2:** `97500.00` *Pending*
⏳ **TP3:** `99000.00` *Pending*

*Last Updated: <t:1767192641:R>*""",

    # Signal 6: FRESH SELL signal with 5 TPs (should be parsed!)
    """<@&1428362286581551125> 📊 NEW SIGNAL • ETH • Entry $3450.25

SELL ETHUSDT Entry: 3450.25 CMP 25x LEVERAGE

**SL:** `3550.00` ⏳ *Active*

**TPs:**
🎯 **TP1:** `3400.00` **→ NEXT**
⏳ **TP2:** `3350.00` *Pending*
⏳ **TP3:** `3300.00` *Pending*
⏳ **TP4:** `3200.00` *Pending*
⏳ **TP5:** `3000.00` *Pending*

*Last Updated: <t:1767192641:R>*""",
]


def test_parser():
    print("=" * 60)
    print("Testing signal_parser_v2.py")
    print("=" * 60)

    for i, signal in enumerate(TEST_SIGNALS, 1):
        print(f"\n--- Test Signal {i} ---")
        result = parse_signal(signal, quote="USDT")

        if result:
            print(f"✅ PARSED:")
            print(f"   Symbol: {result['symbol']}")
            print(f"   Side: {result['side']}")
            print(f"   Entry: {result['trigger']}")
            print(f"   SL: {result.get('sl_price')}")
            print(f"   TPs ({len(result.get('tp_prices', []))}): {result.get('tp_prices', [])}")
            print(f"   DCAs: {result.get('dca_prices', [])}")
            print(f"   Leverage: {result.get('leverage')}x")
            print(f"   Hash: {signal_hash(result)[:12]}...")
        else:
            # Check if it was correctly rejected (closed/cancelled)
            if "TRADE CLOSED" in signal or "TRADE CANCELLED" in signal or "CLOSED AT BREAKEVEN" in signal or "Trade closed without entry" in signal:
                print("✅ Correctly rejected (closed/cancelled trade)")
            else:
                print("❌ FAILED TO PARSE (unexpected)")

    # Test parse_signal_update
    print("\n" + "=" * 60)
    print("Testing parse_signal_update")
    print("=" * 60)

    update_test = """**SL:** `0.15000` ⏳ *Active*

**TPs:**
🎯 **TP1:** `0.16000` **→ NEXT**
⏳ **TP2:** `0.17000` *Pending*
⏳ **TP3:** `0.18000` *Pending*"""

    result = parse_signal_update(update_test)
    print(f"\nUpdate result:")
    print(f"   SL: {result.get('sl_price')}")
    print(f"   TPs: {result.get('tp_prices', [])}")
    print(f"   DCAs: {result.get('dca_prices', [])}")

    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_parser()
