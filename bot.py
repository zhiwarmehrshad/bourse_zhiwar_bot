import json
import logging
import time
import requests
import finpy_tse as tse
from apscheduler.schedulers.background import BackgroundScheduler

BALE_TOKEN = "1477750405:r61oAMkuW_ClP0qkEn5GBPbx9GsoILbhGr8"
ADMIN_CHAT_ID = 926478427
BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

logging.basicConfig(level=logging.INFO)
ALERTS_FILE = "alerts.json"

# وضعیت گام‌به‌گام کاربر (State Machine)
user_states = {}

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
    """ارسال پیام به پیوی کاربر در بله"""
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def get_main_keyboard():
    """کیبورد منوی اصلی بله"""
    return {
        "keyboard": [
            [{"text": "🎯 ردیاب (تارگت و حد ضرر)"}, {"text": "📡 رادار (صف‌های خرید و فروش)"}],
            [{"text": "📋 لیست هشدارهای فعال"}, {"text": "✏️ ویرایش یا حذف سهم"}]
        ],
        "resize_keyboard": True
    }

def get_cancel_keyboard():
    """کیبورد انصراف"""
    return {
        "keyboard": [
            [{"text": "❌ انصراف و بازگشت به منوی اصلی"}]
        ],
        "resize_keyboard": True
    }

def check_market():
    """رصد دوره‌ای بازار بورس"""
    if not alerts:
        return

    for symbol, conf in list(alerts.items()):
        try:
            df = tse.Get_Intraday_Data(symbol)
            if df.empty:
                continue

            last_price = float(df['close'].iloc[-1])
            high_price = float(df['high'].iloc[-1])
            low_price = float(df['low'].iloc[-1])

            # بررسی تارگت اول
            if "target1" in conf and last_price >= conf["target1"]:
                send_message(f"🎯 *تارگت اول نماد {symbol} تاچ شد!*\nقیمت معامله: {last_price:,.0f} ریال\nتارگت: {conf['target1']:,.0f} ریال")
                del conf["target1"]

            # بررسی تارگت دوم
            if "target2" in conf and last_price >= conf["target2"]:
                send_message(f"🚀 *تارگت دوم نماد {symbol} تاچ شد!*\nقیمت معامله: {last_price:,.0f} ریال\nتارگت: {conf['target2']:,.0f} ریال")
                del conf["target2"]

            # بررسی استاپ لاس (حد ضرر)
            if "stop" in conf and last_price <= conf["stop"]:
                send_message(f"🚨 *حد ضرر نماد {symbol} لمس شد!*\nقیمت معامله: {last_price:,.0f} ریال\nحد ضرر: {conf['stop']:,.0f} ریال")
                del conf["stop"]

            # بررسی ریزش صف خرید
            if conf.get("watch_queue_buy") and last_price < high_price:
                send_message(f"⚠️ *صف خرید نماد {symbol} ریخت / عرضه شد!*\nقیمت جاری: {last_price:,.0f}")
                conf["watch_queue_buy"] = False

            # بررسی جمع شدن صف فروش
            if conf.get("watch_queue_sell") and last_price > low_price:
                send_message(f"🟢 *صف فروش نماد {symbol} جمع شد!*\nقیمت جاری: {last_price:,.0f}")
                conf["watch_queue_sell"] = False

            save_alerts(alerts)
        except Exception as e:
            logging.error(f"Error checking {symbol}: {e}")

def handle_message(text):
    """مدیریت گفتگو و هدایت گام‌به‌گام کاربر"""
    text = text.strip()
    state = user_states.get("step")

    # کلید انصراف عمومی
    if text == "❌ انصراف و بازگشت به منوی اصلی":
        user_states.clear()
        send_message("عملیات لغو شد. به منوی اصلی بازگشتید.", get_main_keyboard())
        return

    # دستور استارت یا بازگشت به منو
    if text in ["/start", "منو"]:
        user_states.clear()
        send_message("سلام! به سامانه دیده‌بان هوشمند بورس خوش آمدید.\nلطفاً یک بخش را انتخاب کنید:", get_main_keyboard())
        return

    # 1. ورود به بخش ردیاب
    if text == "🎯 ردیاب (تارگت و حد ضرر)":
        user_states["step"] = "R_WAIT_SYMBOL"
        send_message("لطفاً نام نماد مورد نظر را به فارسی بنویسید (مثلاً: فولاد):", get_cancel_keyboard())
        return

    # دریافت نام نماد در ردیاب
    if state == "R_WAIT_SYMBOL":
        symbol = text
        send_message(f"در حال استعلام قیمت نماد {symbol} از سامانه بورس...")
        try:
            df = tse.Get_Intraday_Data(symbol)
            if df.empty:
                send_message("⚠️ اطلاعاتی برای این نماد یافت نشد. لطفاً نام نماد را با املای دقیق بنویسید:")
                return
            current_price = float(df['close'].iloc[-1])
            user_states["symbol"] = symbol
            user_states["step"] = "R_WAIT_T1"
            send_message(
                f"✅ نماد: {symbol}\n💵 آخرین قیمت تابلو: {current_price:,.0f} ریال\n\nحالا قیمت **تارگت اول (حد سود)** را به ریال وارد کنید:",
                get_cancel_keyboard()
            )
        except Exception:
            send_message("⚠️ خطا در اتصال به TSETMC. لطفاً مجدداً نام نماد را بنویسید:")
        return

    # دریافت تارگت اول
    if state == "R_WAIT_T1":
        try:
            t1 = float(text.replace(",", ""))
            user_states["t1"] = t1
            user_states["step"] = "R_WAIT_T2"
            send_message("✅ تارگت اول ثبت شد.\n\nحالا **تارگت دوم** را بنویسید (اگر تارگت دوم ندارید، عدد 0 را بفرستید):")
        except ValueError:
            send_message("لطفاً قیمت را فقط به صورت عدد وارد کنید:")
        return

    # دریافت تارگت دوم
    if state == "R_WAIT_T2":
        try:
            t2 = float(text.replace(",", ""))
            user_states["t2"] = t2 if t2 > 0 else None
            user_states["step"] = "R_WAIT_STOP"
            send_message("حالا قیمت **حد ضرر (Stop Loss)** را به ریال بنویسید:")
        except ValueError:
            send_message("لطفاً قیمت را به صورت عدد وارد کنید (یا 0 بنویسید):")
        return

    # دریافت استاپ لاس و ذخیره نهایی
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
                f"🎉 پرونده ردیابی نماد *{symbol}* با موفقیت ذخیره شد:\n"
                f"🔹 تارگت ۱: {user_states['t1']:,.0f} ریال\n"
            )
            if user_states.get("t2"):
                res_text += f"🔹 تارگت ۲: {user_states['t2']:,.0f} ریال\n"
            res_text += f"🛑 حد ضرر: {stop_price:,.0f} ریال\n\nبه محض تاچ شدن هر سطح، به شما پیام می‌دهم."

            user_states.clear()
            send_message(res_text, get_main_keyboard())
        except ValueError:
            send_message("لطفاً حد ضرر را فقط به صورت عدد بنویسید:")
        return

    # 2. ورود به بخش رادار (صف خرید و فروش)
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

    # 3. مشاهده لیست هشدارهای فعال
    if text == "📋 لیست هشدارهای فعال":
        if not alerts:
            send_message("شما در حال حاضر هیچ نمادی در ردیاب یا رادار ثبت نکرده‌اید.", get_main_keyboard())
            return
        
        report = "📋 *لیست دیده‌بان‌های فعال شما:*\n\n"
        for s, d in alerts.items():
            report += f"📌 *نماد {s}:*\n"
            if "target1" in d:
                report += f"  - تارگت اول: {d['target1']:,.0f} ریال\n"
            if "target2" in d:
                report += f"  - تارگت دوم: {d['target2']:,.0f} ریال\n"
            if "stop" in d:
                report += f"  - حد ضرر: {d['stop']:,.0f} ریال\n"
            if d.get("watch_queue_buy"):
                report += "  - رادار: گوش‌به‌زنگ ریختن صف خرید\n"
            if d.get("watch_queue_sell"):
                report += "  - رادار: گوش‌به‌زنگ جمع شدن صف فروش\n"
            report += "──────────\n"
        send_message(report, get_main_keyboard())
        return

    # 4. ویرایش یا حذف سهم
    if text == "✏️ ویرایش یا حذف سهم":
        if not alerts:
            send_message("هیچ نمادی برای حذف یا ویرایش وجود ندارد.", get_main_keyboard())
            return
        # ساخت کیبورد با دکمه‌های نمادهای موجود
        symbol_buttons = [[{"text": f"حذف {s}"}] for s in alerts.keys()]
        symbol_buttons.append([{"text": "❌ انصراف و بازگشت به منوی اصلی"}])
        user_states["step"] = "WAIT_REMOVE"
        send_message("سهمی که می‌خواهید حذف شود را انتخاب کنید (یا نامش را بنویسید):", {"keyboard": symbol_buttons, "resize_keyboard": True})
        return

    if state == "WAIT_REMOVE":
        target_symbol = text.replace("حذف ", "").strip()
        if target_symbol in alerts:
            del alerts[target_symbol]
            save_alerts(alerts)
            user_states.clear()
            send_message(f"🗑 تمامی هشدارهای مربوط به نماد {target_symbol} با موفقیت پاک شد.", get_main_keyboard())
        else:
            send_message("این نماد یافت نشد. لطفاً نام نماد را مجدداً ارسال کنید:")
        return

    # پیام پیش‌فرض برای متون ناشناخته
    send_message("لطفاً از دکمه‌های زیر استفاده کنید:", get_main_keyboard())

def run_bot():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_market, 'interval', seconds=90)
    scheduler.start()

    offset = 0
    send_message("🚀 ربات دیده‌بان بورس با منوی تعاملی جدید روشن و آماده است!", get_main_keyboard())

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
