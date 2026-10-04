"""
Node Analyzer — الگوریتم اختصاصی تشخیص گره‌های صعودی در BTC و ETH صرافی TTT
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

API_KEY = os.environ.get("TT_API_KEY")
API_SECRET = os.environ.get("TT_API_SECRET")


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


def fetch_candles(symbol: str, interval: str = "15m", limit: int = 100):
    """دریافت کندل‌های TTT برای نماد مورد نظر"""
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
    """محاسبه گره‌های صعودی و کادربندی مربع امتدادیافته به راست"""
    swings = find_swing_points(candles)
    nodes = []
    
    for i in range(2, len(swings)):
        curr = swings[i]
        prev_swings = swings[:i]
        
        # ۱. اگر سوئینگ کف جدید ایجاد شده باشد
        if curr["type"] == "LOW":
            sweep_low = curr["price"]
            sweep_index = curr["index"]
            
            # ۲. بررسی اینکه آیا زیر حداقل یکی از کف‌های قبلی را زده است؟ (سویپ نقدینگی)
            prior_lows = [s for s in prev_swings if s["type"] == "LOW"]
            swept_lows = [l for l in prior_lows if sweep_low < l["price"]]
            
            if swept_lows:
                # ۳. پیدا کردن نزدیک‌ترین کف بالاتر قبلی (Nearest Higher Low)
                nearest_higher_low = min(l["price"] for l in prior_lows if l["price"] > sweep_low)
                
                # ۴. بررسی شکست سقف بعد از سویپ (Break of Structure - BOS)
                prior_highs = [s["price"] for s in prior_lows]
                max_prior_high = max([s["price"] for s in prev_swings if s["type"] == "HIGH"], default=0)
                
                # آیا قیمت بعد از این کف، سقف قبلی را شکسته است؟
                future_candles = candles[sweep_index:]
                has_bos = any(c["close"] > max_prior_high for c in future_candles)
                
                if has_bos and max_prior_high > 0:
                    node_top = nearest_higher_low      # مرز بالای مربع
                    node_bottom = sweep_low             # مرز پایین مربع
                    
                    nodes.append({
                        "symbol": symbol,
                        "node_top": node_top,
                        "node_bottom": node_bottom,
                        "start_time": curr["time"],
                        "extended_to_right": True,
                        "status": "ACTIVE_NODE"
                    })

    return nodes


def main():
    symbols = ["BTCUSDT", "ETHUSDT"]
    print("🔍 در حال تحلیل و محاسبه گره‌های صعودی روی چارت TTT...\n")
    
    for sym in symbols:
        candles = fetch_candles(sym, interval="15m", limit=120)
        if not candles:
            continue
            
        active_nodes = detect_bullish_nodes(sym, candles)
        print(f"================== {sym} ==================")
        if not active_nodes:
            print(f"هیچ گره جدیدی در ۱۲۰ کندل اخیر پیدا نشد.")
        else:
            for idx, n in enumerate(active_nodes, 1):
                print(f"📌 گره شماره {idx}:")
                print(f"   ▫️ مرز بالای گره (Node Top / Entry Upper): {n['node_top']}")
                print(f"   ▫️ مرز پایین گره (Node Bottom / Entry Lower): {n['node_bottom']}")
                print(f"   ▫️ وضعیت باکس: مربع امتدادیافته به سمت راست (Extended Right Box)")
                print(f"   ▫️ زمان تشکیل: {n['start_time']}\n")


if __name__ == "__main__":
    main()
