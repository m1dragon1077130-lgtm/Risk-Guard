"""
Node Analyzer — الگوریتم اختصاصی تشخیص گره‌های صعودی در صرافی TTT
منطق: سقف بالاتر + سویپ کف قبلی + شکست سقف (BOS) + محدوده بین Sweep Low و Nearest Higher Low
"""

import os
import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error

BASE_URL = "https://apiv2.thetruetrade.io"
FUTURES_PREFIX = "/futures"

API_KEY = os.environ.get("TT_API_KEY", "")
API_SECRET = os.environ.get("TT_API_SECRET", "")


def sign(secret: str, timestamp: str, method: str, uri: str) -> str:
    payload = f"{timestamp}{method}{uri}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def request(method: str, uri: str, body: dict = None):
    timestamp = str(int(time.time() * 1000))
    signature = sign(API_SECRET, timestamp, method.upper(), uri)

    url = BASE_URL + uri
    headers = {
        "X-API-Key": API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except Exception as e:
        print(f"خطا در دریافت اطلاعات: {e}")
        return None


def fetch_candles(symbol: str, interval: str = "15m", limit: int = 300):
    """دریافت کندل‌های TTT برای نماد مورد نظر (افزایش limit به ۳۰۰ برای بررسی کامل‌تر)"""
    uri = f"{FUTURES_PREFIX}/candles?symbol={symbol}&interval={interval}&limit={limit}"
    data = request("GET", uri)
    
    if not data:
        print(f"❌ عدم دریافت داده‌های کندل برای {symbol}")
        return []

    items = data.get("items", data) if isinstance(data, dict) else data
    candles = []
    
    for c in items:
        try:
            candles.append({
                "time": c.get("time") or c.get("timestamp"),
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0))
            })
        except Exception:
            continue
            
    return candles


def find_swing_points(candles, left=2, right=2):
    """پیدا کردن سوئینگ‌های سقف و کف در چارت"""
    swings = []
    n = len(candles)
    
    for i in range(left, n - right):
        current_low = candles[i]["low"]
        current_high = candles[i]["high"]
        
        # بررسی سوئینگ کف (Swing Low)
        is_low = all(candles[i - l]["low"] > current_low for l in range(1, left + 1)) and \
                 all(candles[i + r]["low"] > current_low for r in range(1, right + 1))
                 
        # بررسی سوئینگ سقف (Swing High)
        is_high = all(candles[i - l]["high"] < current_high for l in range(1, left + 1)) and \
                  all(candles[i + r]["high"] < current_high for r in range(1, right + 1))
                  
        if is_low:
            swings.append({"type": "LOW", "index": i, "price": current_low, "time": candles[i]["time"]})
        if is_high:
            swings.append({"type": "HIGH", "index": i, "price": current_high, "time": candles[i]["time"]})
            
    return swings


def detect_bullish_nodes(symbol: str, candles):
    """محاسبه گره‌های صعودی (اصلاح‌شده بدون باگ و با دقت بیشتر)"""
    swings = find_swing_points(candles, left=2, right=2)
    nodes = []
    
    for i in range(len(swings)):
        curr = swings[i]
        
        # ۱. بررسی اینکه آیا نقطه فعلی یک کف است
        if curr["type"] == "LOW":
            sweep_low = curr["price"]
            sweep_index = curr["index"]
            
            # ۲. بررسی اینکه آیا زیر حداقل یکی از کف‌های قبلی را زده است؟ (سویپ نقدینگی)
            prior_lows = [s for s in swings[:i] if s["type"] == "LOW"]
            swept_lows = [l for l in prior_lows if sweep_low < l["price"]]
            
            if swept_lows:
                # ۳. پیدا کردن نزدیک‌ترین کف بالاتر قبلی جهت تعیین مرز بالای گره
                higher_lows = [l["price"] for l in prior_lows if l["price"] > sweep_low]
                if not higher_lows:
                    continue
                nearest_higher_low = min(higher_lows)
                
                # ۴. پیدا کردن بالاترین سقف قبل از سویپ
                prior_highs = [s["price"] for s in swings[:i] if s["type"] == "HIGH"]
                if not prior_highs:
                    continue
                max_prior_high = max(prior_highs)
                
                # ۵. بررسی شکست سقف بعد از سویپ (Break of Structure - BOS)
                future_candles = candles[sweep_index:]
                has_bos = any(c["close"] > max_prior_high for c in future_candles)
                
                if has_bos:
                    nodes.append({
                        "symbol": symbol,
                        "node_top": nearest_higher_low,   # مرز بالای باکس
                        "node_bottom": sweep_low,          # مرز پایین باکس (شدوی سویپ)
                        "start_time": curr["time"],
                        "status": "ACTIVE_NODE"
                    })

    return nodes


def main():
    # نمادها (در صورت نیاز نمادهای دیگر مانند ZECUSDT را هم می‌توانید اضافه کنید)
    symbols = ["BTCUSDT", "ETHUSDT", "ZECUSDT"]
    print("🔍 در حال تحلیل و محاسبه گره‌های صعودی روی چارت TTT...\n")
    
    for sym in symbols:
        candles = fetch_candles(sym, interval="15m", limit=300)
        if not candles:
            continue
            
        active_nodes = detect_bullish_nodes(sym, candles)
        print(f"================== {sym} ==================")
        if not active_nodes:
            print(f"هیچ گره جدیدی پیدا نشد.")
        else:
            for idx, n in enumerate(active_nodes, 1):
                print(f"📌 گره شماره {idx}:")
                print(f"    ▫️ مرز بالای گره (Node Top / Entry Upper): {n['node_top']}")
                print(f"    ▫️ مرز پایین گره (Node Bottom / Entry Lower): {n['node_bottom']}")
                print(f"    ▫️ وضعیت باکس: مربع امتدادیافته به سمت راست (Extended Right Box)")
                print(f"    ▫️ زمان تشکیل: {n['start_time']}\n")


if __name__ == "__main__":
    main()
