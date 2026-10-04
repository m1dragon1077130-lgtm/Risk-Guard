"""
RiskGuard — ربات مدیریت ریسک، حد ضرر (۰.۵$) و حد سود (۲.۵$) حساب TrueTrade
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
MAX_LOSS_USD = 0.50    # حداکثر حد ضرر: ۵۰ سنت
MAX_PROFIT_USD = 2.50  # حداکثر حد سود: ۲ دلار و ۵۰ سنت

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

    # ۱. قانون تک معامله
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

    # ۲. تنظیم حد ضرر (۰.۵۰$) و حد سود (۲.۵۰$)
    for p in open_positions:
        pid = str(p["id"])
        symbol = p["symbol"]
        side = str(p["side"]).upper()
        entry_price = float(p["entryPrice"])
        size = float(p.get("size", 0))
        current_sl = p.get("stopLoss")
        current_tp = p.get("takeProfit")

        if size <= 0:
            continue

        sl_distance = MAX_LOSS_USD / size
        tp_distance = MAX_PROFIT_USD / size

        if side == "LONG":
            target_sl = round(entry_price - sl_distance, 4)
            target_tp = round(entry_price + tp_distance, 4)
        else:
            target_sl = round(entry_price + sl_distance, 4)
            target_tp = round(entry_price - tp_distance, 4)

        key = pid

        if key not in state:
            payload = {"stopLossOrderType": "STOP_MARKET", "takeProfitOrderType": "TAKE_PROFIT_MARKET"}
            
            if current_sl is None or str(current_sl).strip() == "" or float(current_sl or 0) == 0:
                payload["stopLoss"] = str(target_sl)
                print(f"ثبت حد ضرر ۵۰ سنتی برای {symbol} روی قیمت: {target_sl}")

            if current_tp is None or str(current_tp).strip() == "" or float(current_tp or 0) == 0:
                payload["takeProfit"] = str(target_tp)
                print(f"ثبت حد سود ۲.۵ دلاری برای {symbol} روی قیمت: {target_tp}")

            if "stopLoss" in payload or "takeProfit" in payload:
                if "stopLoss" not in payload and current_sl:
                    payload["stopLoss"] = str(current_sl)
                if "takeProfit" not in payload and current_tp:
                    payload["takeProfit"] = str(current_tp)

                result = request("PATCH", f"{FUTURES_PREFIX}/positions/{pid}/tpsl", payload)
                if result is not None:
                    print(f"✅ TP/SL برای {symbol} با موفقیت ثبت شد.")
                    state[key] = {
                        "symbol": symbol,
                        "side": side,
                        "sl": float(payload.get("stopLoss", current_sl or target_sl)),
                        "tp": float(payload.get("takeProfit", current_tp or target_tp))
                    }
                else:
                    print(f"❌ خطا در ثبت TP/SL.")
            else:
                state[key] = {
                    "symbol": symbol,
                    "side": side,
                    "sl": float(current_sl),
                    "tp": float(current_tp)
                }
        else:
            # قفل کردن حد ضرر جهت جلوگیری از افزایش ریسک
            if LOCK_STOP_LOSS and current_sl:
                original_sl = float(state[key]["sl"])
                current_sl_f = float(current_sl)
                risk_increased = False

                if side == "LONG":
                    if current_sl_f < original_sl - 1e-6:
                        risk_increased = True
                else:
                    if current_sl_f > original_sl + 1e-6:
                        risk_increased = True

                if risk_increased:
                    print(f"⚠️ افزایش ریسک در {symbol}! بازگرداندن حد ضرر به {original_sl}")
                    request(
                        "PATCH",
                        f"{FUTURES_PREFIX}/positions/{pid}/tpsl",
                        {"stopLoss": str(original_sl), "stopLossOrderType": "STOP_MARKET"},
                    )
                elif abs(current_sl_f - original_sl) > 1e-6:
                    print(f"حد ضرر {symbol} به نفع معامله جابه‌جا شد: {original_sl} -> {current_sl_f}")
                    state[key]["sl"] = current_sl_f

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
