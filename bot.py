import json
import logging
import time
import requests
import finpy_tse as tse
from apscheduler.schedulers.background import BackgroundScheduler

# اطلاعات اختصاصی بله
BALE_TOKEN = "1477750405:r61oAMkuW_ClP0qkEn5GBPbx9GsoILbhGr8"
ADMIN_CHAT_ID = 926478427
BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

logging.basicConfig(level=logging.INFO)
ALERTS_FILE = "alerts.json"

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

def send_message(text):
    """ارسال پیام به حساب شما در بله"""
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def check_market():
    """رصد لحظه‌ای قیمت‌ها و صف‌ها در بازار بورس"""
    if not alerts:
        return

    for symbol, conf in list(alerts.items()):
        try:
            df = tse.Get_Intraday_Data(symbol)
            if df.empty:
                continue

            last_price = float(df['close'].iloc[-1])
            high_price = float(df['high'].iloc[-1])

            # بررسی تارگت
            if "target" in conf and last_price >= conf["target"]:
                send_message(f"🎯 تارگت نماد {symbol} تاچ شد!\nقیمت: {last_price:,.0f} ریال")
                del conf["target"]

            # بررسی حد ضرر
            if "stop" in conf and last_price <= conf["stop"]:
                send_message(f"🚨 حد ضرر نماد {symbol} فعال شد!\nقیمت: {last_price:,.0f} ریال")
                del conf["stop"]

            # بررسی عرضه صف خرید
            if conf.get("watch_queue_buy") and last_price < high_price:
                send_message(f"⚠️ صف خرید نماد {symbol} عرضه شد / ریخت!")
                conf["watch_queue_buy"] = False

            save_alerts(alerts)
        except Exception as e:
            logging.error(f"Error checking {symbol}: {e}")

def handle_command(text):
    """پردازش دستورات دریافتی از چت بله"""
    parts = text.strip().split()
    cmd = parts[0]

    if cmd == "/start":
        return (
            "📊 بازوی دیده‌بان بورس بله فعال شد.\n\n"
            "دستورات:\n"
            "🔹 ثبت تارگت: /target فولاد 5500\n"
            "🔹 ثبت حد ضرر: /stop فولاد 4800\n"
            "🔹 هشدار ریزش صف خرید: /queue_buy فولاد\n"
            "🔹 لیست هشدارها: /list\n"
            "🔹 حذف هشدار: /remove فولاد"
        )
    elif cmd == "/target" and len(parts) >= 3:
        symbol, price = parts[1], float(parts[2])
        alerts.setdefault(symbol, {})["target"] = price
        save_alerts(alerts)
        return f"✅ تارگت {symbol} روی {price:,.0f} ریال تنظیم شد."
    elif cmd == "/stop" and len(parts) >= 3:
        symbol, price = parts[1], float(parts[2])
        alerts.setdefault(symbol, {})["stop"] = price
        save_alerts(alerts)
        return f"🛑 حد ضرر {symbol} روی {price:,.0f} ریال تنظیم شد."
    elif cmd == "/queue_buy" and len(parts) >= 2:
        symbol = parts[1]
        alerts.setdefault(symbol, {})["watch_queue_buy"] = True
        save_alerts(alerts)
        return f"🟢 رصد ریزش صف خرید {symbol} فعال شد."
    elif cmd == "/list":
        if not alerts:
            return "هیچ هشداری ثبت نشده است."
        res = "📋 هشدارهای شما:\n"
        for s, d in alerts.items():
            res += f"\n📌 {s}: " + ", ".join(f"{k}: {v}" for k, v in d.items())
        return res
    elif cmd == "/remove" and len(parts) >= 2:
        symbol = parts[1]
        if symbol in alerts:
            del alerts[symbol]
            save_alerts(alerts)
            return f"🗑 هشدار نماد {symbol} حذف شد."
        return "نماد یافت نشد."
    return "دستور نامعتبر است."

def run_bot():
    scheduler = BackgroundScheduler()
    # رصد بازار هر ۹۰ ثانیه
    scheduler.add_job(check_market, 'interval', seconds=90)
    scheduler.start()

    offset = 0
    send_message("🚀 ربات بورس در بله با موفقیت روشن و آنلاین شد.")

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
                        reply = handle_command(text)
                        send_message(reply)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    run_bot()
