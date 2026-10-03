
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
print("پاسخ خام GET /futures/positions:")
print("=" * 60)
positions = request("GET", "/futures/positions")
print(json.dumps(positions, indent=2, ensure_ascii=False))
print("=" * 60)

if positions:
    for p in positions:
        print("کلیدهای موجود در هر پوزیشن:", list(p.keys()))
