"""
RiskGuard — ربات مدیریت ریسک برای TrueTrade
قوانین:
  ۱. هر پوزیشن بدون حد ضرر، خودکار حد ضرر ۳٪ (قابل‌تغییر) می‌گیره
  ۲. اگه حد ضرر در جهت افزایش ریسک جابه‌جا بشه، برمی‌گرده سر جاش
  ۳. فقط یک پوزیشن باز مجازه؛ بقیه بسته می‌شن

این اسکریپت یک‌بار اجرا می‌شه و خارج می‌شه (برای اجرا با GitHub Actions
هر چند دقیقه). حالت state (حد ضرر اصلی هر پوزیشن) در یک فایل JSON
در همین ریپازیتوری ذخیره می‌شه تا بین اجراها حفظ بشه.
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
RISK_PERCENT = float(os.environ.get("RISK_PERCENT", "3.0"))
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
    """uri باید با / شروع بشه، شامل querystring اگه لازم بود (مثلا /futures/positions)."""
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


# ---------------- state ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------- منطق اصلی ----------------
def get_futures_balance() -> float:
    """
    موجودی کل حساب فیوچرز رو می‌خونه. چون /accounting/assets بدون پارامتر
    انگار کیف‌پول «funding» رو برمی‌گردونه (نه futures)، اول با
    accountType=futures امتحان می‌کنیم؛ اگه نشد، از خود پوزیشن‌های باز
    (initialMargin ها) به‌عنوان جایگزین استفاده می‌کنیم.
    """
    # تلاش ۱: با پارامتر accountType=futures
    assets = request("GET", "/accounting/assets?accountType=futures")
    bal = _extract_usdt_balance(assets)
    if bal is not None and bal > 0:
        print(f"موجودی از /accounting/assets?accountType=futures: {bal}")
        return bal

    # تلاش ۲: بدون پارامتر (fallback)، چاپ کامل برای دیباگ
    assets = request("GET", "/accounting/assets")
    print("پاسخ خام /accounting/assets (بدون پارامتر):", json.dumps(assets, ensure_ascii=False))
    bal = _extract_usdt_balance(assets)
    if bal is not None and bal > 0:
        print(f"موجودی از /accounting/assets (بدون پارامتر): {bal}")
        return bal

    print("نتونستیم موجودی USDT فیوچرز معتبر (بزرگ‌تر از صفر) پیدا کنیم.")
    return None


def _extract_usdt_balance(assets):
    if assets is None:
        return None
    items = assets.get("items", assets) if isinstance(assets, dict) else assets
    if not isinstance(items, list):
        return None
    for a in items:
        if a.get("asset") == "USDT":
            try:
                return float(a.get("availableBalance", a.get("balance", 0)))
            except (TypeError, ValueError):
                return None
    return None


def calc_stop_loss(entry_price: float, side: str, size: float, balance: float, risk_percent: float) -> float:
    """
    حد ضرر بر اساس درصدی از کل موجودی حساب (نه حجم یا قیمت معامله) محاسبه می‌شه:
      ۱) مبلغ مجاز ریسک = موجودی کل × درصد ریسک
      ۲) فاصله‌ی قیمتی حد ضرر = مبلغ مجاز ریسک ÷ حجم پوزیشن (size)
    یعنی هر معامله، صرف‌نظر از لوریج یا حجمش، دقیقاً همون درصد از
    کل حسابت رو به خطر می‌ندازه.
    """
    risk_money = balance * (risk_percent / 100.0)
    if size <= 0:
        return None
    distance = risk_money / size
    if side == "LONG":
        return round(entry_price - distance, 8)
    else:
        return round(entry_price + distance, 8)


def main():
    state = load_state()

    account_balance = get_futures_balance()
    if account_balance is None:
        print("نتونستم موجودی حساب رو بخونم. خروج.")
        return
    print(f"موجودی کل حساب فیوچرز: {account_balance}")

    response = request("GET", f"{FUTURES_PREFIX}/positions")
    if response is None:
        print("نتونستم پوزیشن‌ها رو بخونم. خروج.")
        return

    # پاسخ API صفحه‌بندی‌شده است: {"meta": {...}, "items": [...]}
    positions = response.get("items", []) if isinstance(response, dict) else response

    open_positions = [p for p in positions if p.get("status") == "OPENED" and p.get("isActive")]
    print(f"تعداد پوزیشن‌های باز: {len(open_positions)}")

    # --- قانون ۳: فقط یک پوزیشن باز ---
    if ONLY_ONE_TRADE and len(open_positions) > 1:
        # قدیمی‌ترین (یا اولین در لیست) رو نگه می‌داریم، بقیه رو می‌بندیم
        keep_id = open_positions[0]["id"]
        for p in open_positions[1:]:
            pid = p["id"]
            print(f"بستن پوزیشن اضافه {pid} طبق قانون «فقط یک معامله باز»")
            request("POST", f"{FUTURES_PREFIX}/positions/{pid}/close", {"orderType": "MARKET"})
        # بعد از بستن، دوباره لیست رو به‌روز می‌کنیم
        open_positions = [p for p in open_positions if p["id"] == keep_id]

    for p in open_positions:
        pid = str(p["id"])
        symbol = p["symbol"]
        side = p["side"]  # "LONG" or "SHORT"
        entry_price = float(p["entryPrice"])
        size = float(p["size"])
        current_sl = p.get("stopLoss")

        key = pid

        if key not in state:
            # پوزیشن تازه دیده شده: اگه حد ضرر نداره (یا صفره)، اجباری بذار
            if current_sl is None or current_sl == "" or float(current_sl or 0) == 0:
                new_sl = calc_stop_loss(entry_price, side, size, account_balance, RISK_PERCENT)
                if new_sl is None:
                    print(f"نتونستم حد ضرر {symbol} (id={pid}) رو محاسبه کنم (size نامعتبر).")
                    continue
                print(f"تنظیم حد ضرر اجباری {RISK_PERCENT}% برای {symbol} (id={pid}) روی {new_sl}")
                result = request(
                    "PATCH",
                    f"{FUTURES_PREFIX}/positions/{pid}/tpsl",
                    {"stopLoss": str(new_sl), "stopLossOrderType": "STOP_MARKET"},
                )
                if result is not None:
                    state[key] = {"symbol": symbol, "side": side, "sl": new_sl}
            else:
                # حد ضرر از قبل تنظیم شده (مثلا دستی)؛ به‌عنوان مرجع ذخیره کن
                state[key] = {"symbol": symbol, "side": side, "sl": float(current_sl)}
                print(f"پوزیشن {symbol} (id={pid}) از قبل حد ضرر {current_sl} داشت؛ ذخیره شد.")
        else:
            # --- قانون ۲: قفل جابه‌جایی حد ضرر ---
            if LOCK_STOP_LOSS and current_sl:
                original_sl = state[key]["sl"]
                current_sl_f = float(current_sl)
                risk_increased = False

                if side == "LONG":
                    if current_sl_f < original_sl - 1e-8:
                        risk_increased = True
                else:
                    if current_sl_f > original_sl + 1e-8:
                        risk_increased = True

                if risk_increased:
                    print(f"افزایش ریسک شناسایی شد در {symbol} (id={pid}). برگردوندن حد ضرر به {original_sl}")
                    request(
                        "PATCH",
                        f"{FUTURES_PREFIX}/positions/{pid}/tpsl",
                        {"stopLoss": str(original_sl), "stopLossOrderType": "STOP_MARKET"},
                    )
                elif current_sl_f != original_sl:
                    # جابه‌جایی به نفع معامله (تریلینگ) مجاز است
                    print(f"حد ضرر {symbol} به نفع معامله جابه‌جا شد: {original_sl} -> {current_sl_f}")
                    state[key]["sl"] = current_sl_f

    # پاک‌سازی state از پوزیشن‌های بسته‌شده
    open_ids = {str(p["id"]) for p in open_positions}
    for k in list(state.keys()):
        if k not in open_ids:
            print(f"پوزیشن {k} دیگر باز نیست؛ از state حذف شد.")
            del state[k]

    save_state(state)
    print("اجرا کامل شد.")


if __name__ == "__main__":
    main()
