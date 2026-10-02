import os
import time
import requests
from datetime import datetime, timezone

# ============================================================
# BALA BTC BOT
# Binance live BTCUSDT + Telegram alerts
# ALERT ONLY — NO REAL ORDERS
# ============================================================

BINANCE_URL = "https://api.binance.com/api/v3/klines"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"

SYMBOL = "BTCUSDT"

# Telegram credentials must be added as environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_SECONDS = 20

# BALA settings
EMA_FAST = 9
EMA_SLOW = 21
ATR_LENGTH = 14
VOLUME_LENGTH = 20

last_signal = None
last_signal_time = 0


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured.")
        print(message)
        return False

    try:
        url = TELEGRAM_URL.format(TELEGRAM_TOKEN)

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


# ============================================================
# BINANCE DATA
# ============================================================

def get_klines(interval, limit=100):
    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "limit": limit
    }

    response = requests.get(
        BINANCE_URL,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    candles = []

    for x in data:
        candles.append({
            "time": int(x[0]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "volume": float(x[5])
        })

    return candles


# ============================================================
# INDICATORS
# ============================================================

def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = sum(values[:period]) / period

    for price in values[period:]:
        result = (price - result) * multiplier + result

    return result


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    return sum(true_ranges[-period:]) / period


def average_volume(candles, period=20):
    if len(candles) < period:
        return None

    volumes = [x["volume"] for x in candles[-period:]]

    return sum(volumes) / len(volumes)


# ============================================================
# BALA STRUCTURE
# ============================================================

def get_structure(candles):
    if len(candles) < 10:
        return "NEUTRAL"

    recent = candles[-6:]

    previous_high = max(x["high"] for x in candles[-10:-3])
    previous_low = min(x["low"] for x in candles[-10:-3])

    current_high = max(x["high"] for x in recent)
    current_low = min(x["low"] for x in recent)

    if current_high > previous_high and current_low > previous_low:
        return "BULLISH"

    if current_high < previous_high and current_low < previous_low:
        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# LIQUIDITY SWEEP
# ============================================================

def liquidity_sweep(candles):
    if len(candles) < 8:
        return None

    previous = candles[-2]
    current = candles[-1]

    recent_high = max(
        x["high"] for x in candles[-7:-2]
    )

    recent_low = min(
        x["low"] for x in candles[-7:-2]
    )

    # Sell-side liquidity sweep followed by bullish close
    if current["low"] < recent_low and current["close"] > previous["high"]:
        return "BUY_SWEEP"

    # Buy-side liquidity sweep followed by bearish close
    if current["high"] > recent_high and current["close"] < previous["low"]:
        return "SELL_SWEEP"

    return None


# ============================================================
# DISPLACEMENT
# ============================================================

def displacement(candles):
    if len(candles) < 10:
        return None

    current = candles[-1]

    current_range = current["high"] - current["low"]

    previous_ranges = [
        x["high"] - x["low"]
        for x in candles[-8:-1]
    ]

    average_range = sum(previous_ranges) / len(previous_ranges)

    if average_range <= 0:
        return None

    # Strong bullish displacement
    if (
        current_range > average_range * 1.5
        and current["close"] > current["open"]
    ):
        return "BULLISH"

    # Strong bearish displacement
    if (
        current_range > average_range * 1.5
        and current["close"] < current["open"]
    ):
        return "BEARISH"

    return None


# ============================================================
# 1 MINUTE BALA SIGNAL
# ============================================================

def analyze_1m(candles):

    closes = [x["close"] for x in candles]

    fast = ema(closes, EMA_FAST)
    slow = ema(closes, EMA_SLOW)

    current = candles[-1]

    volume_avg = average_volume(
        candles,
        VOLUME_LENGTH
    )

    current_volume = current["volume"]

    structure = get_structure(candles)

    sweep = liquidity_sweep(candles)

    move = displacement(candles)

    buy_score = 0
    sell_score = 0

    reasons_buy = []
    reasons_sell = []

    # EMA
    if fast and slow:

        if fast > slow:
            buy_score += 1
            reasons_buy.append("EMA bullish")

        if fast < slow:
            sell_score += 1
            reasons_sell.append("EMA bearish")

    # Structure
    if structure == "BULLISH":
        buy_score += 1
        reasons_buy.append("BOS/structure bullish")

    elif structure == "BEARISH":
        sell_score += 1
        reasons_sell.append("BOS/structure bearish")

    # Liquidity
    if sweep == "BUY_SWEEP":
        buy_score += 2
        reasons_buy.append("sell-side liquidity sweep")

    elif sweep == "SELL_SWEEP":
        sell_score += 2
        reasons_sell.append("buy-side liquidity sweep")

    # Displacement
    if move == "BULLISH":
        buy_score += 1
        reasons_buy.append("bullish displacement")

    elif move == "BEARISH":
        sell_score += 1
        reasons_sell.append("bearish displacement")

    # Volume
    if volume_avg and current_volume > volume_avg * 1.5:

        if current["close"] > current["open"]:
            buy_score += 1
            reasons_buy.append("high volume")

        elif current["close"] < current["open"]:
            sell_score += 1
            reasons_sell.append("high volume")

    # Final signal
    if buy_score >= 4 and buy_score > sell_score:
        return {
            "signal": "BUY",
            "score": buy_score,
            "reasons": reasons_buy,
            "price": current["close"]
        }

    if sell_score >= 4 and sell_score > buy_score:
        return {
            "signal": "SELL",
            "score": sell_score,
            "reasons": reasons_sell,
            "price": current["close"]
        }

    return {
        "signal": "NO TRADE",
        "score": max(buy_score, sell_score),
        "reasons": [],
        "price": current["close"]
    }


# ============================================================
# MULTI-TIMEFRAME BALA ANALYSIS
# ============================================================

def analyze_market():

    candles_15m = get_klines("15m", 100)
    candles_5m = get_klines("5m", 100)
    candles_1m = get_klines("1m", 100)

    trend_15m = get_structure(candles_15m)
    trend_5m = get_structure(candles_5m)

    signal_1m = analyze_1m(candles_1m)

    return {
        "trend_15m": trend_15m,
        "trend_5m": trend_5m,
        "signal_1m": signal_1m
    }


# ============================================================
# FINAL BALA DECISION
# ============================================================

def bala_decision():

    market = analyze_market()

    trend_15m = market["trend_15m"]
    trend_5m = market["trend_5m"]
    signal = market["signal_1m"]

    price = signal["price"]

    # ----------------------------------------
    # BUY
    # ----------------------------------------

    if (
        trend_15m == "BULLISH"
        and trend_5m == "BULLISH"
        and signal["signal"] == "BUY"
    ):
        return {
            "signal": "A+ BUY",
            "price": price,
            "trend15": trend_15m,
            "trend5": trend_5m,
            "score": signal["score"],
            "reasons": signal["reasons"]
        }

    # ----------------------------------------
    # SELL
    # ----------------------------------------

    if (
        trend_15m == "BEARISH"
        and trend_5m == "BEARISH"
        and signal["signal"] == "SELL"
    ):
        return {
            "signal": "A+ SELL",
            "price": price,
            "trend15": trend_15m,
            "trend5": trend_5m,
            "score": signal["score"],
            "reasons": signal["reasons"]
        }

    # ----------------------------------------
    # NO TRADE
    # ----------------------------------------

    return {
        "signal": "NO TRADE",
        "price": price,
        "trend15": trend_15m,
        "trend5": trend_5m,
        "score": signal["score"],
        "reasons": []
    }


# ============================================================
# MESSAGE
# ============================================================

def build_message(result):

    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    if result["signal"] == "A+ BUY":

        emoji = "🟢"

    elif result["signal"] == "A+ SELL":

        emoji = "🔴"

    else:

        emoji = "⚪"

    message = f"""
{emoji} BALA BTC SIGNAL

Symbol: BTCUSDT
Signal: {result["signal"]}

Price: {result["price"]:.2f}

15M Structure: {result["trend15"]}
5M Structure: {result["trend5"]}

1M Score: {result["score"]}/6
"""

    if result["reasons"]:

        message += "\nConfirmations:\n"

        for reason in result["reasons"]:
            message += f"• {reason}\n"

    message += f"""
Time: {now}

⚠️ ALERT ONLY
No automatic order placed.
"""

    return message


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    global last_signal
    global last_signal_time

    print("===================================")
    print("BALA BTC BOT - STARTING")
    print("Symbol:", SYMBOL)
    print("Mode: ALERT ONLY")
    print("===================================")

    send_telegram(
        "🟢 BALA BTC BOT started.\n"
        "Live BTCUSDT monitoring is active.\n"
        "Mode: ALERT ONLY"
    )

    while True:

        try:

            result = bala_decision()

            print(
                datetime.now().strftime("%H:%M:%S"),
                "|",
                result["signal"],
                "|",
                result["price"]
            )

            current_time = time.time()

            # Send only when a new A+ signal appears
            if result["signal"] in ["A+ BUY", "A+ SELL"]:

                signal_changed = (
                    result["signal"] != last_signal
                )

                cooldown_finished = (
                    current_time - last_signal_time > 300
                )

                if signal_changed or cooldown_finished:

                    message = build_message(result)

                    send_telegram(message)

                    last_signal = result["signal"]
                    last_signal_time = current_time

            else:

                last_signal = None

            time.sleep(CHECK_SECONDS)

        except Exception as e:

            print("BOT ERROR:", e)

            time.sleep(30)


if __name__ == "__main__":
    main()
