import os
import time
import requests
import random
import csv
from datetime import datetime
import pytz

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ========== CONFIGURACIÓN vía entorno ==========
VM_TOKEN = os.getenv('VM_TOKEN', '630edd338ab6c57b331be08bea65720c')
VM_DEVICE_NORMAL = os.getenv('VM_DEVICE_NORMAL', 'casi-casi')
VM_DEVICE_URGENT = os.getenv('VM_DEVICE_URGENT', 'casi-casi-urgent')
VOICE_NORMAL = os.getenv('VOICE_NORMAL', 'Mia')
VOICE_URGENT = os.getenv('VOICE_URGENT', 'Lupe')
LANGUAGE = os.getenv('LANGUAGE', 'es-MX')
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')

BREAKOUT_CHANGE = float(os.getenv('BREAKOUT_CHANGE', '300'))
CONSOLIDATION_WINDOW = int(os.getenv('CONSOLIDATION_WINDOW', '12'))
CONSOLIDATION_THRESHOLD = float(os.getenv('CONSOLIDATION_THRESHOLD', '0.5'))
RSI_PERIOD = int(os.getenv('RSI_PERIOD', '14'))
RSI_OVERBOUGHT = float(os.getenv('RSI_OVERBOUGHT', '70'))
RSI_OVERSOLD = float(os.getenv('RSI_OVERSOLD', '30'))

TIMEZONE = os.getenv('TIMEZONE', 'America/Santiago')
ACTIVE_HOUR_START = int(os.getenv('ACTIVE_HOUR_START', '7'))
ACTIVE_HOUR_END = int(os.getenv('ACTIVE_HOUR_END', '23'))
SUMMARY_HOUR = int(os.getenv('SUMMARY_HOUR', '7'))

PRICE_FILE = os.getenv('PRICE_FILE', 'precio_prev.txt')
LOG_FILE = os.getenv('LOG_FILE', 'alertas_casi_casi.log')
LAST_SUMMARY_FILE = os.getenv('LAST_SUMMARY_FILE', 'last_summary.txt')
HEALTH_CSV = os.getenv('HEALTH_CSV', 'health_metrics.csv')
GOOGLE_CREDENTIALS_FILE = os.getenv(
    'GOOGLE_CREDENTIALS_FILE',
     'client_secret.json')
GOOGLE_TOKEN_FILE = os.getenv('GOOGLE_TOKEN_FILE', 'token_calendar.json')
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

INACTIVITY_TIMEOUT = int(os.getenv('INACTIVITY_TIMEOUT', '300'))
last_activity = time.time()
last_health_hour = None

# ========== FRASES CÓMICAS ==========
PHRASES = {
    'consolidation': [
        "Casi casi se empalaga el BTC en {price}$",
        "Goldo goldo, lateralito en {price}$"
    ],
    'breakout': [
        "¡Alerta Casi casi! BTC rompe y llega a {price}$",
        "Goldo goldo, ¡ruptura! BTC en {price}$"
    ],
    'max': [
        "¡Épico Goldo! BTC cambió {change}$ y está en {price}$",
        "Casi casi infarto: BTC {change}$ hasta {price}$"
    ],
    'rsi_overbought': [
        "Goldo, RSI está alto ({rsi}), ojo con sobrecompra"
    ],
    'rsi_oversold': [
        "Goldo, RSI bajito ({rsi}), quizás tierra fértil"
    ],
    'summary': [
        "Buenos días Goldo goldo, arranca la jornada con BTC en {price}$ y {status}"
    ],
    'error': [
        "¡Goldo! Error en {stage}, reintentando..."
    ],
    'health': [
        "Casi casi sigue vivo, son las {hour:02d}:{minute:02d}"
    ]
}

# ========== UTILIDADES ==========


def read_file(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return f.read().strip()
    return None


def write_file(path, content):
    with open(path, 'w') as f:
        f.write(str(content))


def log(msg, alert_type='INFO'):
    timestamp = datetime.now().isoformat()
    with open(LOG_FILE, 'a') as f:
        f.write(f"{timestamp} [{alert_type}] {msg}\n")


def random_phrase(alert_type, **kwargs):
    return random.choice(PHRASES.get(alert_type, ['{price}'])).format(**kwargs)


def retry(func, stage, retries=3, delay=5, **kwargs):
    for attempt in range(retries):
        try:
            return func(**kwargs)
        except Exception as e:
            phr = random_phrase('error', stage=stage)
            send_voice(phr, urgent=True)
            log(f"Error en {stage}: {e}", 'ERROR')
            time.sleep(delay)
    return None

# ========== FUNCIONES BINANCE ==========


def get_current_price(sym=SYMBOL):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
    return float(requests.get(url, timeout=5).json()['price'])


def get_historical_prices(
    sym=SYMBOL,
    interval='5m',
    limit=CONSOLIDATION_WINDOW +
     RSI_PERIOD):
    url = "https://api.binance.com/api/v3/klines"
    params = {'symbol': sym, 'interval': interval, 'limit': limit}
    data = requests.get(url, params=params, timeout=5).json()
    return [float(c[4]) for c in data]


def calculate_rsi(prices, period=RSI_PERIOD):
    if len(prices) < period + 1:
        return None
    gains = [max(prices[i + 1] - prices[i], 0) for i in range(period)]
    losses = [max(prices[i] - prices[i + 1], 0) for i in range(period)]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period or 1e-6
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def is_consolidating(prices):
    high, low = max(prices), min(prices)
    return ((high - low) / low) * 100 < CONSOLIDATION_THRESHOLD


def is_breakout(current, prices):
    return current > max(prices) or current < min(prices)


def in_active_hours():
    tz = pytz.timezone(TIMEZONE)
    return ACTIVE_HOUR_START <= datetime.now(tz).hour < ACTIVE_HOUR_END

# ========== GOOGLE CALENDAR ==========


def autenticar_google():
    creds = None
    if os.path.exists(GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            GOOGLE_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GOOGLE_TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds


def obtener_eventos_hoy(service):
    tz = pytz.timezone(TIMEZONE)
    start = datetime.now(tz).replace(
    hour=0, minute=0, second=0).isoformat() + 'Z'
    end = datetime.now(tz).replace(
    hour=23, minute=59, second=59).isoformat() + 'Z'
    ev = service.events().list(calendarId='primary', timeMin=start, timeMax=end,
                                singleEvents=True, orderBy='startTime').execute()
    return ev.get('items', [])


def formatear_eventos(eventos):
    if not eventos:
        return 'No tienes reuniones hoy.'
    txt = f"Hoy tienes {
    len(eventos)} reunión{
        'es' if len(eventos) > 1 else ''}. "
    for e in eventos:
        s = e['start'].get('dateTime', e['start'].get('date'))
        h = s[11:16]
        sumr = e.get('summary', 'sin nombre')
        txt += f"A las {h}, {sumr}. "
    return txt

# ========== SENSOR PLACEHOLDER ==========


def check_presence():
    return True


def update_activity():
    global last_activity
    if check_presence():
        last_activity = time.time()


def is_inactive():
    return (time.time() - last_activity) > INACTIVITY_TIMEOUT

# ========== VOICE MONKEY ==========


def send_voice(msg, urgent=False):
    device = VM_DEVICE_URGENT if urgent else VM_DEVICE_NORMAL
    voice = VOICE_URGENT if urgent else VOICE_NORMAL
    params = {
    'token': VM_TOKEN,
    'device': device,
    'voice': voice,
    'text': msg,
     'lang': LANGUAGE}
    try:
         requests.get(
    'https://api-v2.voicemonkey.io/trigger',
    params=params,
     timeout=5)
        log(msg, 'URGENT' if urgent else 'VOICE')
    except Exception as e:
        log(f"Fallo al enviar voz: {e}", 'ERROR')

# ========== RESUMEN DIARIO ==========
def send_daily_summary():
    current = retry(get_current_price, 'precio')
    prices = retry(get_historical_prices, 'histórico')
    status = 'en consolidación' if is_consolidating(prices) else 'en rango normal'
    try:
        creds = autenticar_google()
        service = build('calendar', 'v3', credentials=creds)
        evs = obtener_eventos_hoy(service)
        cal = formatear_eventos(evs)
    except Exception:
        cal = 'No se pudo acceder al calendario.'
    phrase = random_phrase('summary', price=round(current), status=status)
    resumen = f"{phrase}. {cal}"
    send_voice(resumen)
    log('Resumen diario enviado', 'SUMMARY')


def should_send_summary():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    last = read_file(LAST_SUMMARY_FILE)
    if now.hour == SUMMARY_HOUR and last != now.date().isoformat():
        write_file(LAST_SUMMARY_FILE, now.date().isoformat())
        return True
    return False

# ========== MÉTRICAS DE SALUD ==========
def record_health():
    global last_health_hour
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    if now.hour != last_health_hour:
        last_health_hour = now.hour
        if not os.path.exists(HEALTH_CSV):
            with open(HEALTH_CSV, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'status'])
        with open(HEALTH_CSV, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([now.isoformat(), 'OK'])
        phrase = random_phrase('health', hour=now.hour, minute=now.minute)
        send_voice(phrase)

# ========== LÓGICA PRINCIPAL ==========
def main():
    prev_price = None
    last = read_file(PRICE_FILE)
    try:
        prev_price = float(last) if last else None
    except:
        prev_price = None

    while True:
        update_activity()
        record_health()

        if should_send_summary() and in_active_hours():
            send_daily_summary()

        if is_inactive():
            print('[Modo Zen] Sin notificaciones (inactivo)')
        else:
            current = retry(get_current_price, 'precio')
            prices = retry(get_historical_prices, 'histórico')
            if not current or not prices:
                time.sleep(60)
                continue

            msg, urgent = None, False

            # RSI
            rsi = calculate_rsi(prices)
            if rsi is not None and rsi >= RSI_OVERBOUGHT:
                msg = random_phrase('rsi_overbought', rsi=round(rsi))
            elif rsi is not None and rsi <= RSI_OVERSOLD:
                msg = random_phrase('rsi_oversold', rsi=round(rsi))
            # Consolidación
            elif is_consolidating(prices):
                msg = random_phrase('consolidation', price=round(current))
            # Ruptura
            elif is_breakout(current, prices):
                msg = random_phrase('breakout', price=round(current))

            # Alerta máxima
            if prev_price is not None:
                change = round(abs(current - prev_price))
                if change >= BREAKOUT_CHANGE and is_breakout(current, prices):
                    msg = random_phrase('max', change=change, price=round(current))
                    urgent = True

            if msg and in_active_hours():
                send_voice(msg, urgent)
                log(msg, 'ALERT')
                prev_price = current
                write_file(PRICE_FILE, current)

        time.sleep(60)

if __name__ == '__main__':
    main()
