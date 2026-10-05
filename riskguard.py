"""
RiskGuard — ربات مدیریت ریسک، حد ضرر (۰.۵$)، حد سود (۵ برابر ریسک) و قفل سود روی R:R=1
اجرای پیوسته و مداوم روی GitHub Actions
"""

import os
import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error

# ---------------- تنظیمات ثابت ریسک و سود ----------------
MAX_LOSS_USD = 0.50         # حداکثر حد ضرر: ۵۰ سنت ($۰.۵۰)
REWARD_RATIO = 5.0          # حد سود: ۵ برابر حد ضرر ($۲.۵۰)
TRIGGER_RATIO = 2.0         # آستانه جابه‌جایی SL: ۲ برابر حد ضرر ($۱.۰۰ سود شناور)
LOCK_PROFIT_RATIO = 1.0     # قفل سود: انتقال SL به ۱ برابر حد ضرر ($۰.۵۰ سود)

# زمان‌بندی اجرای پیوسته روی گیتهاب اکشنز
MAX_RUN_TIME_SECONDS = 5 * 3600 + 50 * 60  # ۵ ساعت و ۵۰ دقیقه
CHECK_INTERVAL_SECONDS = 20                 # بررسی پوزیشن‌ها هر ۲۰ ثانیه

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
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        print(f"خطای HTTP {e.code} در {method} {uri}: {err_body}")
        return None
    except Exception as e:
        print(f"خطا در {method} {uri}: {e}")
        return None


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


def run_riskguard_cycle(state):
    response = request("GET", f"{FUTURES_PREFIX}/positions")
    if response is None:
        print("عدم دریافت اطلاعات پوزیشن‌ها.")
        return

    positions = response.get("items", []) if isinstance(response, dict) else response
    open_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "OPENED" and p.get("isActive")]

    if not open_positions:
        return

    # ۱. قانون تک معامله (نگه‌داشتن قدیمی‌ترین پوزیشن و بستن مابقی)
    if ONLY_ONE_TRADE and len(open_positions) > 1:
        open_positions.sort(key=lambda p: (p.get("createdAt", ""), p.get("id")))

        oldest_position = open_positions[0]
        oldest_id = oldest_position["id"]
        print(f"قدیمی‌ترین پوزیشن نگه داشته شد: ID {oldest_id} ({oldest_position.get('symbol')})")

        for p in open_positions[1:]:
            pid = p["id"]
            print(f"بستن پوزیشن جدیدتر {pid} ({p.get('symbol')}) طبق قانون تک معامله")
            request("POST", f"{FUTURES_PREFIX}/positions/{pid}/close", {"orderType": "MARKET"})

        open_positions = [oldest_position]

    # ۲. بررسی و مدیریت ریسک، حد ضرر، حد سود و قفل سود
    for p in open_positions:
        pid = str(p["id"])
        symbol = p["symbol"]
        side = str(p["side"]).upper()
        entry_price = float(p["entryPrice"])
        size = float(p.get("size", 0))
        current_sl = p.get("stopLoss")
        current_tp = p.get("takeProfit")
        unrealized_pnl = float(p.get("unrealizedPnl", 0) or p.get("pnl", 0) or 0)

        if size <= 0:
            continue

        # محاسبه فاصله‌های قیمتی
        sl_distance = MAX_LOSS_USD / size                          # فاصله ۰.۵۰$ (ریسک)
        tp_distance = (MAX_LOSS_USD * REWARD_RATIO) / size         # فاصله ۲.۵۰$ (۵ برابر ریسک)
        lock_profit_distance = (MAX_LOSS_USD * LOCK_PROFIT_RATIO) / size  # فاصله ۰.۵۰$ سود (۱ برابر ریسک)

        if side == "LONG":
            target_sl = round(entry_price - sl_distance, 4)
            target_tp = round(entry_price + tp_distance, 4)
            profit_sl_price = round(entry_price + lock_profit_distance, 4)  # قیمت حد ضرر در سود R:R=1
        else:
            target_sl = round(entry_price + sl_distance, 4)
            target_tp = round(entry_price - tp_distance, 4)
            profit_sl_price = round(entry_price - lock_profit_distance, 4)  # قیمت حد ضرر در سود R:R=1

        key = pid
        needs_update = False
        payload = {"stopLossOrderType": "STOP_MARKET", "takeProfitOrderType": "TAKE_PROFIT_MARKET"}

        # ذخیره وضعیت اولیه پوزیشن
        if key not in state:
            state[key] = {
                "symbol": symbol,
                "side": side,
                "entry": entry_price,
                "initial_sl": target_sl,
                "initial_tp": target_tp,
                "sl": target_sl,
                "tp": target_tp,
                "is_profit_locked": False
            }

        # ۳. بررسی شرط قفل سود (اگر سود شناور به ۲ برابر حد ضرر اولیه / ۱.۰۰$ رسید)
        trigger_threshold = MAX_LOSS_USD * TRIGGER_RATIO  # معادل ۱.۰۰ دلار سود
        if unrealized_pnl >= trigger_threshold and not state[key].get("is_profit_locked", False):
            print(f"🎯 سود {symbol} به بیش از {trigger_threshold}$ رسید ({unrealized_pnl:.2f}$). انتقال حد ضرر به R:R=1 (قیمت: {profit_sl_price} / سود قفل‌شده: +0.50$).")
            state[key]["sl"] = profit_sl_price
            state[key]["is_profit_locked"] = True
            payload["stopLoss"] = str(profit_sl_price)
            needs_update = True

        # ۴. کنترل و تثبیت حد ضرر (در صورت پاک شدن یا افزایش ریسک)
        if not needs_update:
            if current_sl is None or str(current_sl).strip() == "" or float(current_sl or 0) == 0:
                print(f"⚠️ حد ضرر {symbol} حذف شده بود! تنظیم مجدد روی {state[key]['sl']}")
                payload["stopLoss"] = str(state[key]["sl"])
                needs_update = True
            elif LOCK_STOP_LOSS:
                current_sl_f = float(current_sl)
                saved_sl_f = float(state[key]["sl"])

                risk_increased = False
                if side == "LONG" and current_sl_f < saved_sl_f - 1e-6:
                    risk_increased = True
                elif side == "SHORT" and current_sl_f > saved_sl_f + 1e-6:
                    risk_increased = True

                if risk_increased:
                    print(f"⚠️ افزایش ریسک در {symbol}! بازگرداندن حد ضرر از {current_sl_f} به {saved_sl_f}")
                    payload["stopLoss"] = str(saved_sl_f)
                    needs_update = True
                elif abs(current_sl_f - saved_sl_f) > 1e-6:
                    print(f"حد ضرر {symbol} به نفع معامله جابه‌جا شد: {saved_sl_f} -> {current_sl_f}")
                    state[key]["sl"] = current_sl_f

        # ۵. کنترل حد سود: اگر حذف شده بود، یا از هدف ۵ برابر ریسک «دورتر» شده بود، برگردان.
        #    اگر کمتر از هدف (نزدیک‌تر به ورودی) شده باشد، دست نمی‌زنیم.
        target_tp_f = float(state[key]["tp"])
        if current_tp is None or str(current_tp).strip() == "" or float(current_tp or 0) == 0:
            print(f"⚠️ حد سود {symbol} حذف شده بود! تنظیم مجدد روی ۵ برابر ریسک ({target_tp_f})")
            payload["takeProfit"] = str(target_tp_f)
            needs_update = True
        else:
            current_tp_f = float(current_tp)
            too_far = (current_tp_f > target_tp_f + 1e-6) if side == "LONG" else (current_tp_f < target_tp_f - 1e-6)
            if too_far:
                print(f"⚠️ حد سود {symbol} از هدف ۵ برابر ریسک دورتر شده بود ({current_tp_f}). بازگرداندن به {target_tp_f}")
                payload["takeProfit"] = str(target_tp_f)
                needs_update = True

        # اعمال تغییرات روی صرافی
        if needs_update:
            if "stopLoss" not in payload:
                payload["stopLoss"] = str(current_sl) if current_sl else str(state[key]["sl"])
            if "takeProfit" not in payload:
                payload["takeProfit"] = str(current_tp) if current_tp else str(state[key]["tp"])

            result = request("PATCH", f"{FUTURES_PREFIX}/positions/{pid}/tpsl", payload)
            if result is not None:
                print(f"✅ اصلاح/تنظیم TP/SL برای {symbol} با موفقیت انجام شد.")
            else:
                print(f"❌ خطا در اصلاح TP/SL برای {symbol}.")

    # پاکسازی پوزیشن‌های بسته شده از حافظه
    open_ids = {str(p["id"]) for p in open_positions}
    for k in list(state.keys()):
        if k not in open_ids:
            del state[k]

    save_state(state)


def main():
    start_time = time.time()
    print("🚀 چرخه ۵ ساعت و ۵۰ دقیقه‌ای RiskGuard شروع شد...")

    while True:
        elapsed = time.time() - start_time
        if elapsed >= MAX_RUN_TIME_SECONDS:
            print("⏱ زمان این چرخه به پایان رسید. تحویل به اجرای بعدی...")
            break

        try:
            state = load_state()
            run_riskguard_cycle(state)
        except Exception as e:
            print(f"خطا در اجرای چرخه: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
