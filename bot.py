import json
import logging
import time
import requests
from apscheduler.schedulers.background import BackgroundScheduler

BALE_TOKEN = "1477750405:r61oAMkuW_ClP0qkEn5GBPbx9GsoILbhGr8"
ADMIN_CHAT_ID = 926478427
BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

logging.basicConfig(level=logging.INFO)
ALERTS_FILE = "alerts.json"

user_states = {}

# هدر استاندارد برای جلوگیری از بلاک شدن توسط سرور بورس
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://www.tsetmc.com/"
}

def load_alerts():
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_alerts(data):
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

alerts = load_alerts()

def send_message(text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🎯 ردیاب (تارگت و حد ضرر)"}, {"text": "📡 رادار (صف‌های خرید و فروش)"}],
            [{"text": "📋 لیست هشدارهای فعال"}, {"text": "✏️ ویرایش یا حذف سهم"}]
        ],
        "resize_keyboard": True
    }

def get_cancel_keyboard():
    return {
        "keyboard": [
            [{"text": "❌ انصراف و بازگشت به منوی اصلی"}]
        ],
        "resize_keyboard": True
    }

def normalize_text(text):
    """یکسان‌سازی حروف فارسی و عربی (ی و ک)"""
    return text.replace("ي", "ی").replace("ك", "ک").strip()

def get_symbol_data(symbol_name):
    """دریافت قیمت و وضعیت تابلو با وب‌سرویس مستقیم TSETMC"""
    norm_symbol = normalize_text(symbol_name)
    try:
        # ۱. جستجوی شناسه سهم
        search_url = f"http://old.tsetmc.com/tsevservice/data/search.aspx?svalue={norm_symbol}"
        res = requests.get(search_url, headers=HEADERS, timeout=10)
        lines = res.text.strip().split(";")
        
        target_inscode = None
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 2:
                name_in_tse = normalize_text(parts[0])
                if norm_symbol == name_in_tse or norm_symbol in name_in_tse:
                    target_inscode = parts[1]
                    break
        
        if not target_inscode and len(lines) > 0 and len(lines[0].split(",")) >= 2:
            target_inscode = lines[0].split(",")[1]

        if not target_inscode:
            return None

        # ۲. دریافت دیتای تابلوی سهم
        inst_url = f"http://old.tsetmc.com/tsevservice/data/InstData.aspx?i={target_inscode}"
        inst_res = requests.get(inst_url, headers=HEADERS, timeout=10)
        data_parts = inst_res.text.strip().split(";")

        if len(data_parts) < 1:
            return None

        # استخراج قیمت‌ها از ساختار استاندارد تابلو
        info = data_parts[0].split(",")
        last_price = float(info[2])       # آخرین معامله
        close_price = float(info[3])      # قیمت پایانی
        high_price = float(info[6])       # سقف مجاز روز
        low_price = float(info[7])        # کف مجاز روز

        return {
            "last": last_price,
            "close": close_price,
            "high": high_price,
            "low": low_price,
            "inscode": target_inscode
        }
    except Exception as e:
        logging.error(f"Error fetching TSE data for {symbol_name}: {e}")
        return None

def check_market():
    """رصد دوره‌ای بازار بورس"""
    if not alerts:
        return

    for symbol, conf in list(alerts.items()):
        data = get_symbol_data(symbol)
        if not data:
            continue

        last_price = data["last"]
        high_price = data["high"]
        low_price = data["low"]

        # بررسی تارگت اول
        if "target1" in conf and last_price >= conf["target1"]:
            send_message(f"🎯 *تارگت اول نماد {symbol} تاچ شد!*\nقیمت معامله: {last_price:,.0f} ریال\nتارگت: {conf['target1']:,.0f} ریال")
            del conf["target1"]

        # بررسی تارگت دوم
        if "target2" in conf and last_price >= conf["target2"]:
            send_message(f"🚀 *تارگت دوم نماد {symbol} تاچ شد!*\nقیمت معامله: {last_price:,.0f} ریال\nتارگت: {conf['target2']:,.0f} ریال")
            del conf["target2"]

        # بررسی استاپ لاس
        if "stop" in conf and last_price <= conf["stop"]:
            send_message(f"🚨 *حد ضرر نماد {symbol} لمس شد!*\nقیمت معامله: {last_price:,.0f} ریال\nحد ضرر: {conf['stop']:,.0f} ریال")
            del conf["stop"]

        # بررسی عرضه صف خرید
        if conf.get("watch_queue_buy") and last_price < high_price:
            send_message(f"⚠️ *صف خرید نماد {symbol} ریخت / عرضه شد!*\nقیمت جاری: {last_price:,.0f}")
            conf["watch_queue_buy"] = False

        # بررسی جمع شدن صف فروش
        if conf.get("watch_queue_sell") and last_price > low_price:
            send_message(f"🟢 *صف فروش نماد {symbol} جمع شد!*\nقیمت جاری: {last_price:,.0f}")
            conf["watch_queue_sell"] = False

        save_alerts(alerts)

def handle_message(text):
    text = text.strip()
    state = user_states.get("step")

    if text == "❌ انصراف و بازگشت به منوی اصلی":
        user_states.clear()
        send_message("عملیات لغو شد. به منوی اصلی بازگشتید.", get_main_keyboard())
        return

    if text in ["/start", "منو"]:
        user_states.clear()
        send_message("سلام! به سامانه دیده‌بان هوشمند بورس خوش آمدید.\nلطفاً یک بخش را انتخاب کنید:", get_main_keyboard())
        return

    if text == "🎯 ردیاب (تارگت و حد ضرر)":
        user_states["step"] = "R_WAIT_SYMBOL"
        send_message("لطفاً نام نماد مورد نظر را به فارسی بنویسید (مثلاً: فولاد):", get_cancel_keyboard())
        return

    if state == "R_WAIT_SYMBOL":
        symbol = text
        send_message(f"در حال استعلام قیمت نماد {symbol} از سامانه بورس...")
        data = get_symbol_data(symbol)
        if not data:
            send_message("⚠️ اطلاعاتی برای این نماد یافت نشد یا بورس در دسترس نیست. لطفاً مجدداً نام نماد را بررسی کرده و بنویسید:")
            return
        
        current_price = data["last"]
        user_states["symbol"] = symbol
        user_states["step"] = "R_WAIT_T1"
        send_message(
            f"✅ نماد: {symbol}\n💵 آخرین قیمت معامله: {current_price:,.0f} ریال\n\nحالا قیمت **تارگت اول (حد سود)** را به ریال وارد کنید:",
            get_cancel_keyboard()
        )
        return

    if state == "R_WAIT_T1":
        try:
            t1 = float(text.replace(",", ""))
            user_states["t1"] = t1
            user_states["step"] = "R_WAIT_T2"
            send_message("✅ تارگت اول ثبت شد.\n\nحالا **تارگت دوم** را بنویسید (اگر ندارید عدد 0 را بفرستید):")
        except ValueError:
            send_message("لطفاً قیمت را فقط به صورت عدد وارد کنید:")
        return

    if state == "R_WAIT_T2":
        try:
            t2 = float(text.replace(",", ""))
            user_states["t2"] = t2 if t2 > 0 else None
            user_states["step"] = "R_WAIT_STOP"
            send_message("حالا قیمت **حد ضرر (Stop Loss)** را به ریال بنویسید:")
        except ValueError:
            send_message("لطفاً قیمت را به صورت عدد وارد کنید (یا 0 بنویسید):")
        return

    if state == "R_WAIT_STOP":
        try:
            stop_price = float(text.replace(",", ""))
            symbol = user_states["symbol"]
            
            alerts.setdefault(symbol, {})
            alerts[symbol]["target1"] = user_states["t1"]
            if user_states.get("t2"):
                alerts[symbol]["target2"] = user_states["t2"]
            alerts[symbol]["stop"] = stop_price
            save_alerts(alerts)

            res_text = (
                f"🎉 پرونده ردیابی نماد *{symbol}* ثبت شد:\n"
                f"🔹 تارگت ۱: {user_states['t1']:,.0f} ریال\n"
            )
            if user_states.get("t2"):
                res_text += f"🔹 تارگت ۲: {user_states['t2']:,.0f} ریال\n"
            res_text += f"🛑 حد ضرر: {stop_price:,.0f} ریال"

            user_states.clear()
            send_message(res_text, get_main_keyboard())
        except ValueError:
            send_message("لطفاً حد ضرر را فقط به صورت عدد بنویسید:")
        return

    if text == "📡 رادار (صف‌های خرید و فروش)":
        user_states["step"] = "RADAR_WAIT_SYMBOL"
        send_message("لطفاً نام نماد را جهت رصد صف بنویسید (مثلاً: خودرو):", get_cancel_keyboard())
        return

    if state == "RADAR_WAIT_SYMBOL":
        user_states["symbol"] = text
        user_states["step"] = "RADAR_CHOOSE_TYPE"
        markup = {
            "keyboard": [
                [{"text": "🟢 رصد ریزش صف خرید"}, {"text": "🔴 رصد جمع شدن صف فروش"}],
                [{"text": "❌ انصراف و بازگشت به منوی اصلی"}]
            ],
            "resize_keyboard": True
        }
        send_message(f"نماد {text} دریافت شد. چه نوع رصدی فعال شود؟", markup)
        return

    if state == "RADAR_CHOOSE_TYPE":
        symbol = user_states["symbol"]
        if text == "🟢 رصد ریزش صف خرید":
            alerts.setdefault(symbol, {})["watch_queue_buy"] = True
            save_alerts(alerts)
            user_states.clear()
            send_message(f"✅ رادار فعال شد: به محض عرضه یا ریختن صف خرید {symbol} به شما هشدار داده می‌شود.", get_main_keyboard())
        elif text == "🔴 رصد جمع شدن صف فروش":
            alerts.setdefault(symbol, {})["watch_queue_sell"] = True
            save_alerts(alerts)
            user_states.clear()
            send_message(f"✅ رادار فعال شد: به محض جمع شدن صف فروش {symbol} به شما اطلاع خواهم داد.", get_main_keyboard())
        return

    if text == "📋 لیست هشدارهای فعال":
        if not alerts:
            send_message("شما در حال حاضر هیچ نمادی ثبت نکرده‌اید.", get_main_keyboard())
            return
        
        report = "📋 *لیست دیده‌بان‌های فعال:*\n\n"
        for s, d in alerts.items():
            report += f"📌 *نماد {s}:*\n"
            if "target1" in d:
                report += f"  - تارگت اول: {d['target1']:,.0f} ریال\n"
            if "target2" in d:
                report += f"  - تارگت دوم: {d['target2']:,.0f} ریال\n"
            if "stop" in d:
                report += f"  - حد ضرر: {d['stop']:,.0f} ریال\n"
            if d.get("watch_queue_buy"):
                report += "  - رادار: ریختن صف خرید\n"
            if d.get("watch_queue_sell"):
                report += "  - رادار: جمع شدن صف فروش\n"
            report += "──────────\n"
        send_message(report, get_main_keyboard())
        return

    if text == "✏️ ویرایش یا حذف سهم":
        if not alerts:
            send_message("هیچ نمادی برای حذف یا ویرایش وجود ندارد.", get_main_keyboard())
            return
        symbol_buttons = [[{"text": f"حذف {s}"}] for s in alerts.keys()]
        symbol_buttons.append([{"text": "❌ انصراف و بازگشت به منوی اصلی"}])
        user_states["step"] = "WAIT_REMOVE"
        send_message("سهمی که می‌خواهید حذف شود را انتخاب کنید:", {"keyboard": symbol_buttons, "resize_keyboard": True})
        return

    if state == "WAIT_REMOVE":
        target_symbol = text.replace("حذف ", "").strip()
        if target_symbol in alerts:
            del alerts[target_symbol]
            save_alerts(alerts)
            user_states.clear()
            send_message(f"🗑 تمامی هشدارهای مربوط به نماد {target_symbol} حذف شد.", get_main_keyboard())
        else:
            send_message("این نماد یافت نشد. لطفاً نام نماد را مجدداً ارسال کنید:")
        return

    send_message("لطفاً از دکمه‌های زیر استفاده کنید:", get_main_keyboard())

def run_bot():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_market, 'interval', seconds=90)
    scheduler.start()

    offset = 0
    send_message("🚀 ربات دیده‌بان بورس با متد اتصال مستقیم آماده شد!", get_main_keyboard())

    while True:
        try:
            url = f"{BASE_URL}/getUpdates?offset={offset}&timeout=20"
            res = requests.get(url, timeout=25).json()
            if res.get("ok") and "result" in res:
                for item in res["result"]:
                    offset = item["update_id"] + 1
                    msg = item.get("message", {})
                    if str(msg.get("chat", {}).get("id")) == str(ADMIN_CHAT_ID):
                        text = msg.get("text", "")
                        handle_message(text)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    run_bot()
