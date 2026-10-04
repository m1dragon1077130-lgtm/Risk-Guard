"""
debug_transfer.py — اسکن اندپوینت‌های بخش Transfer و کیف‌پول‌ها
"""
import os
import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error

API_KEY = os.environ.get("TT_API_KEY")
API_SECRET = os.environ.get("TT_API_SECRET")
BASE_URL = "https://apiv2.thetruetrade.io"

if not API_KEY or not API_SECRET:
    print("خطا: کلیدهای API تنظیم نشده‌اند.")
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
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except Exception as e:
        return f"Error: {e}"

endpoints = [
    "/accounting/transfer",
    "/accounting/transfers",
    "/accounting/transfer/accounts",
    "/accounting/wallet",
    "/user/profile",
    "/futures/account"
]

for ep in endpoints:
    print(f"\n==================== {ep} ====================")
    res = request("GET", ep)
    print(json.dumps(res, indent=2) if isinstance(res, (dict, list)) else res)
