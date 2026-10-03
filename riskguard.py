"""
RiskGuard — ربات مدیریت ریسک برای TrueTrade (نسخه هوشمند و دیباگ)
قوانین:
  ۱. محاسبه حد ضرر دقیق بر اساس ۳٪ از کل موجودی اکانت (Equity).
  ۲. قفل جابه‌جایی حد ضرر به سمت افزایش ریسک.
  ۳. نگه‌داشتن فقط قدیمی‌ترین پوزیشن و بستن بقیه معاملات.
"""

import os
import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error

# ---------------- تنظیمات ----------------
RISK_PERCENT = float(os.environ.get("RISK_PERCENT", "3.0"))  # ۳٪ از کل موجودی اکانت
ONLY_ONE_TRADE = os.environ.get("ONLY_ONE_TRADE", "true").lower() == "true"
LOCK_STOP_LOSS = os.environ.get("LOCK_STOP_LOSS", "true").lower() == "true"

BASE_URL = "https://apiv2.thetruetrade.io"
FUTURES_PREFIX = "/futures"

API_KEY = os.environ.get("TT_API_KEY")
API_SECRET = os.environ.get("TT_API_SECRET")

STATE_FILE = os.environ.get("STATE_FILE", "state.json")

if not API_KEY or not API_SECRET:
    print("خطا: TT_API_KEY یا TT_API_SECRET تنظیم نشده.")
    sys.exit(1)


# ---------------- امضای درخواست ----------------
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        print(f"خطای HTTP {e.code} در {method} {uri}: {err_body}")
        return None
    except Exception as e:
        print(f"خطا در {method} {uri}: {e}")
        return None


# ---------------- استخراج موجودی حساب ----------------
def get_account_balance() -> float:
    """دریافت و جستجوی خودکار فیلد موجودی کل حساب (Equity/Balance)"""
    res = request("GET", f"{FUTURES_PREFIX}/account")
    if res and isinstance(res, dict):
        print(f"[DEBUG] پاسخ API اکانت: {json.dumps(res, ensure_ascii=False)}")
        
        # جستجوی فیلدهای ممکن
        for key in ["equity", "balance", "totalWalletBalance", "totalMargin", "availableBalance", "walletBalance"]:
            if key in res and res[key] is not None:
                val = float(res[key])
                if val > 0:
                    return val
            # اگر داده در دیتای لایه دوم باشد
            if "data" in res and isinstance(res["data"], dict):
                if key in res["data"] and res["data"][key] is not None:
                    val = float(res["data"][key])
                    if val > 0:
                        return val

    print("⚠️ هشدار: فیلد موجودی حساب شناسایی نشد.")
    return 0.0


# ---------------- استخراج حجم پوزیشن ----------------
def get_position_quantity(p: dict) -> float:
    """استخراج حجم پوزیشن از فیلدهای مختلف احتمالی"""
    for key in ["quantity", "size", "contracts", "amount", "positionAmt", "volume"]:
        if key in p and p[key] is not None:
            try:
                val = abs(float(p[key]))
                if val > 0:
                    return val
            except ValueError:
                pass
    return 0.0


# ---------------- مدیریت State ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"خطا در خواندن فایل state: {e}")
            return {}
    return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"خطا در ذخیره فایل state: {e}")


# ---------------- فرمول اصلی محاسبه حد ضرر ----------------
def calc_stop_loss(entry_price: float, quantity: float, side: str, total_equity: float, risk_percent: float, leverage: float) -> float:
    """
    ۱. اگر کل موجودی و حجم دقیق خوانده شد: بر اساس ۳٪ کل موجودی
    ۲. در غیر این صورت (Fallback): بر اساس درصد ریسک تقسیم بر اهرم روی قیمت ورود
    """
    if total_equity > 0 and quantity > 0:
        # زیان مجاز به دلار
        max_loss_usd = total_equity * (risk_percent / 100.0)
        # انحراف قیمت لازم برای ایجاد این زیان
        price_distance = max_loss_usd / quantity
        print(f"-> محاسبه بر اساس Equity: ریسک دلار = ${round(max_loss_usd, 3)} | انحراف قیمت = {round(price_distance, 4)}")
    else:
        # روش رزرو در صورت عدم دریافت موجودی/حجم
        if leverage <= 0:
            leverage = 1.0
        price_risk_percent = risk_percent / leverage
        price_distance = entry_price * (price_risk_percent / 100.0)
        print(f"-> محاسبه رزرو (بر اساس اهرم {leverage}x): انحراف قیمت = {round(price_distance, 4)}")

    if side.upper() == "LONG":
        return round(entry_price - price_distance, 4)
    else:
        return round(entry_price + price_distance, 4)


def main():
    state = load_state()

    # ۱. دریافت کل موجودی حساب
    total_equity = get_account_balance()
    print(f"موجودی کل حساب شناسایی شده: {total_equity} دلار")

    # ۲. دریافت پوزیشن‌ها
    response = request("GET", f"{FUTURES_PREFIX}/positions")
    if response is None:
        print("نتونستم پوزیشن‌ها رو بخونم. خروج.")
        return

    positions = response.get("items", []) if isinstance(response, dict) else response
    open_positions = [p for p in positions if p.get("status") == "OPENED" and p.get("isActive")]
    print(f"تعداد پوزیشن‌های باز: {len(open_positions)}")

    # --- قانون ۳: فقط نگه داشتن «قدیمی‌ترین» پوزیشن و بستن بقیه ---
    if ONLY_ONE_TRADE and len(open_positions) > 1:
        open_positions.sort(key=lambda p: (p.get("createdAt", ""), p.get("id")))

        oldest_position = open_positions[0]
        oldest_id = oldest_position["id"]
        print(f"قدیمی‌ترین پوزیشن نگه داشته شد: ID {oldest_id} ({oldest_position.get('symbol')})")

        for p in open_positions[1:]:
            pid = p["id"]
            print(f"بستن پوزیشن جدیدتر {pid} ({p.get('symbol')}) طبق قانون «فقط یک معامله باز»")
            request("POST", f"{FUTURES_PREFIX}/positions/{pid}/close", {"orderType": "MARKET"})
        
        open_positions = [oldest_position]

    for p in open_positions:
        pid = str(p["id"])
        symbol = p["symbol"]
        side = p["side"]
        entry_price = float(p["entryPrice"])
        current_sl = p.get("stopLoss")
        leverage = float(p.get("leverage", 1.0))
        
        # چاپ داده‌های پوزیشن برای دیباگ دقیق
        print(f"\n[DEBUG] داده پوزیشن {symbol} (id={pid}): {json.dumps(p, ensure_ascii=False)}")

        # استخراج حجم معامله
        quantity = get_position_quantity(p)

        key = pid

        if key not in state:
            # اگر حد ضرر ندارد یا صفره
            if current_sl is None or str(current_sl).strip() == "" or float(current_sl or 0) == 0:
                new_sl = calc_stop_loss(entry_price, quantity, side, total_equity, RISK_PERCENT, leverage)
                print(f"ارسال درخواست حد ضرر جدید برای {symbol} (id={pid}) روی قیمت: {new_sl}")

                result = request(
                    "PATCH",
                    f"{FUTURES_PREFIX}/positions/{pid}/tpsl",
                    {"stopLoss": str(new_sl), "stopLossOrderType": "STOP_MARKET"},
                )
                if result is not None:
                    print(f"✅ حد ضرر با موفقیت روی {new_sl} ست شد.")
                    state[key] = {"symbol": symbol, "side": side, "sl": new_sl}
                else:
                    print(f"❌ خطا در ثبت حد ضرر از سمت صرافی.")
            else:
                state[key] = {"symbol": symbol, "side": side, "sl": float(current_sl)}
                print(f"پوزیشن {symbol} از قبل حد ضرر {current_sl} داشت؛ ذخیره در state.")
        else:
            # --- قانون ۲: قفل جابه‌جایی حد ضرر ---
            if LOCK_STOP_LOSS and current_sl:
                original_sl = float(state[key]["sl"])
                current_sl_f = float(current_sl)
                risk_increased = False

                if side.upper() == "LONG":
                    if current_sl_f < original_sl - 1e-6:
                        risk_increased = True
                else:
                    if current_sl_f > original_sl + 1e-6:
                        risk_increased = True

                if risk_increased:
                    print(f"⚠️ افزایش ریسک شناسایی شد در {symbol}. برگردوندن حد ضرر به {original_sl}")
                    request(
                        "PATCH",
                        f"{FUTURES_PREFIX}/positions/{pid}/tpsl",
                        {"stopLoss": str(original_sl), "stopLossOrderType": "STOP_MARKET"},
                    )
                elif abs(current_sl_f - original_sl) > 1e-6:
                    print(f"حد ضرر {symbol} به نفع معامله جابه‌جا شد: {original_sl} -> {current_sl_f}")
                    state[key]["sl"] = current_sl_f

    # پاک‌سازی state
    open_ids = {str(p["id"]) for p in open_positions}
    for k in list(state.keys()):
        if k not in open_ids:
            print(f"پوزیشن {k} بسته شده؛ حذف از state.")
            del state[k]

    save_state(state)
    print("\nاجرا کامل شد.")


if __name__ == "__main__":
    main()
