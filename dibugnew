"""
RiskGuard — اسکریپت عیب‌یابی و خواندن ساختار کامل API کاربر و موجودی
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

if not API_KEY or not API_SECRET:
    print("خطا: کلیدهای TT_API_KEY یا TT_API_SECRET تنظیم نشده‌اند.")
    sys.exit(1)


def sign(secret: str, timestamp: str, method: str, uri: str) -> str:
    payload = f"{timestamp}{method}{uri}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def request(method: str, uri: str):
    timestamp = str(int(time.time() * 1000))
    signature = sign(API_SECRET, timestamp, method.upper(), uri)

    url = BASE_URL + uri
    headers = {
        "X-API-Key": API_KEY,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode(errors="replace")
        return {"error_code": e.code, "message": err_msg}
    except Exception as e:
        return {"error": str(e)}


def main():
    endpoints = [
        f"{FUTURES_PREFIX}/user/me",
        f"{FUTURES_PREFIX}/user/profile",
        f"{FUTURES_PREFIX}/user",
        f"{FUTURES_PREFIX}/account",
        f"{FUTURES_PREFIX}/wallet",
        f"{FUTURES_PREFIX}/balance",
    ]

    print("============================================================")
    print("بررسی Endpointهای مختلف برای یافتن موجودی کل (Equity/Balance)")
    print("============================================================\n")

    for ep in endpoints:
        print(f"--> تست مسیر: {ep}")
        res = request("GET", ep)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        print("-" * 60)


if __name__ == "__main__":
    main()
