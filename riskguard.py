# ---------------- استخراج موجودی کل اکانت ----------------
def get_total_equity() -> float:
    # ۱. ابتدا بررسی موجودی از /accounting/assets
    res = request("GET", "/accounting/assets")
    max_bal = 0.0
    if res and isinstance(res, list):
        for item in res:
            for key in ["balance", "availableBalance", "equity"]:
                if key in item and item[key] is not None:
                    try:
                        val = float(item[key])
                        # نادیده گرفتن مقادیر علمی بسیار کوچک نزدیک به صفر
                        if val > max_bal and val > 0.01:
                            max_bal = val
                    except (ValueError, TypeError):
                        pass
    
    if max_bal > 0:
        print(f"موجودی کل حساب شناسایی شد: ${max_bal}")
        return max_bal

    # ۲. اگر در assets موجودی مستقیم پیدا نشد، محاسبه از طریق پوزیشن‌ها
    pos_res = request("GET", f"{FUTURES_PREFIX}/positions")
    if pos_res:
        items = pos_res.get("items", []) if isinstance(pos_res, dict) else pos_res
        total_margin = 0.0
        total_pnl = 0.0
        for p in items:
            if p.get("status") == "OPENED" 
