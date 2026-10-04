"""
RiskGuard — ربات مدیریت ریسک و حد ضرر حساب TrueTrade
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
RISK_PERCENT = float(os.environ.get("RISK_PERCENT", "3.0"))  # ۳٪ ریسک از کل موجودی
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


def fetch_dynamic_account_equity() -> float:
    print("\n--- در حال استخراج پویای موجودی کل حساب از API ---")
    
    pos_res = request("GET", f"{FUTURES_PREFIX}/positions")
    total_futures_equity = 0.0

    if pos_res:
        items = pos_res.get("items", []) if isinstance(pos_res, dict) else pos_res
        active_positions = [p for p in items if isinstance(p, dict) and p.get("status") == "OPENED" and p.get("isActive")]
        
        for p in active_positions:
            margin = float(p.get("initialMargin", 0))
            if margin == 0:
                notional = float(p.get("notionalSize", 0))
                leverage = float(p.get("leverage", 1))
                if leverage > 0:
                    margin = notional / leverage

            pnl = float(p.get("unrealizedPnL", 0))
            total_futures_equity += (margin + pnl)

        if total_futures_equity > 0:
            print(f"موجودی پویا از بخش فیوچرز محاسبه شد: ${round(total_futures_equity, 4)}")

    assets_res = request("GET", "/accounting/assets")
    max_asset_val = 0.0

    if assets_res and isinstance(assets_res, list):
        for item in assets_res:
            if isinstance(item, dict):
                for key in ["equity", "balance", "walletBalance", "marginBalance", "availableBalance"]:
                    if key in item and item[key] is not None:
                        try:
                            val = float(item[key])
                            if val > max_asset_val and val > 0.01:
                                max_asset_val = val
                        except (ValueError, TypeError):
                            pass

    if max_asset_val > 0:
        print(f"موجودی پویا از /accounting/assets دریافت شد: ${round(max_asset_val, 4)}")

    final_equity = max(total_futures_equity, max_asset_val)

    if final_equity > 0:
        print(f"✅ موجودی کل نهایی حساب (Dynamic Equity): ${round(final_equity, 4)}\n")
        return final_equity

    print("❌ خطا: امکان دریافت پویا موجودی حساب وجود ندارد.")
    return 0.0


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


def main():
    state = load_state()

    total_equity = fetch_dynamic_account_equity()

    if total_equity <= 0:
        print("به دلیل عدم موفقیت در دریافت موجودی از API، اجرای کد متوقف شد.")
        return

    target_loss_usd = total_equity * (RISK_PERCENT / 100.0)
    print(f"میزان زیان مجاز ({RISK_PERCENT}٪ از ${round(total_equity, 4)}): ${round(target_loss_usd, 4)}")

    response = request("GET", f"{FUTURES_PREFIX}/positions")
    if response is None:
        print("عدم دریافت اطلاعات پوزیشن‌ها. خروج.")
        return

    positions = response.get("items", []) if isinstance(response, dict) else response
    open_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "OPENED" and p.get("isActive")]
    print(f"تعداد پوزیشن‌های باز: {len(open_positions)}")

    if not open_positions:
        print("هیچ پوزیشن بازی یافت نشد.")
        return

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

    for p in open_positions:
        pid = str(p["id"])
        symbol = p["symbol"]
        side = str(p["side"]).upper()
        entry_price = float(p["entryPrice"])
        size = float(p.get("size", 0))
        current_sl = p.get("stopLoss")

        if size <= 0:
            print(f"حجم پوزیشن صفر یا نامعتبر است ({symbol}).")
            continue

        key = pid

        if key not in state:
            if current_sl is None or str(current_sl).strip() == "" or float(current_sl or 0) == 0:
                price_distance = target_loss_usd / size
                
                if side == "LONG":
                    new_sl = round(entry_price - price_distance, 4)
                else:
                    new_sl = round(entry_price + price_distance, 4)

                print(f"ثبت حد ضرر ۳٪ برای {symbol} روی قیمت: {new_sl} (مبلغ ریسک: ${round(target_loss_usd, 4)})")

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
                print(f"پوزیشن {symbol} از قبل حد ضرر {current_sl} داشت.")
        else:
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
    print("اجرا کامل شد.")


if __name__ == "__main__":
    main()
