"""
اسکریپت موقت برای دیدن دقیق فیلدهای واقعی پاسخ GET /futures/positions
فقط یه‌بار اجرا کن و خروجی کنسول (Actions log) رو کپی کن و بفرست.
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
API_KEY = os.environ.get("TT_API_KEY")
API_SECRET = os.environ.get("TT_API_SECRET")

if not API_KEY or not API_SECRET:
    print("خطا: TT_API_KEY یا TT_API_SECRET تنظیم نشده.")
    sys.exit(1)


def sign(secret, timestamp, method, uri):
    payload = f"{timestamp}{method}{uri}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def request(method, uri):
    timestamp = str(int(time.time() * 1000))
    signature = sign(API_SECRET, timestamp, method.upper(), uri)
    url = BASE_URL + uri
    headers = {
        "X-API-Key": API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"خطای HTTP {e.code}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        print(f"خطا: {e}")
        return None


print("=" * 60)
print("بررسی ساختار پاسخ GET /futures/positions:")
print("=" * 60)
positions = request("GET", "/futures/positions")

print("نوع داده (type):", type(positions))

if isinstance(positions, dict):
    print("این یک dict است. کلیدهای سطح بالا:", list(positions.keys()))
    for k, v in positions.items():
        print(f"  کلید '{k}' -> نوع: {type(v)}", end="")
        if isinstance(v, list):
            print(f", تعداد عضو: {len(v)}")
            if len(v) > 0:
                print(f"    نوع عضو اول: {type(v[0])}")
                if isinstance(v[0], dict):
                    print(f"    کلیدهای عضو اول: {list(v[0].keys())}")
        else:
            print()
elif isinstance(positions, list):
    print("این یک list است. تعداد عضو:", len(positions))
    if len(positions) > 0:
        print("نوع عضو اول:", type(positions[0]))
        if isinstance(positions[0], dict):
            print("کلیدهای عضو اول:", list(positions[0].keys()))
        else:
            print("مقدار عضو اول:", positions[0])
else:
    print("مقدار:", positions)

print("=" * 60)
print("JSON کامل (برای اطمینان):")
print("=" * 60)
print(json.dumps(positions, indent=2, ensure_ascii=False)[:3000])
