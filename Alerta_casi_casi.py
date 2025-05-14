import os
import time
import requests
from datetime import datetime

TOKEN = "630edd338ab6c57b331be08bea65720c_1ae988467b35049c96db6c480b2eac42"
DEVICE = "casi-casi"
VOZ = "Mia"
LENGUAJE = "es-MX"
UMBRAL_ALERTA = 300
ARCHIVO_PRECIO = "precio_prev.txt"

def obtener_precio_btc():
    try:
        data = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT").json()
        return float(data["price"])
    except:
        return None

def enviar_alerta(precio):
    texto = f"Goldo goldo, el precio de Bitcoin es {round(precio):,} dólares"
    url = (
        "https://api-v2.voicemonkey.io/announcement?"
        f"token={TOKEN}&device={DEVICE}&text={requests.utils.quote(texto)}"
        f"&voice={VOZ}&language={LENGUAJE}"
    )
    requests.get(url)

def leer_ultimo_precio():
    try:
        with open(ARCHIVO_PRECIO, "r") as f:
            return float(f.read())
    except:
        return None

def guardar_precio(precio):
    with open(ARCHIVO_PRECIO, "w") as f:
        f.write(str(precio))

# 🔁 Monitoreo constante con horario
while True:
    hora_actual = datetime.now().hour

    if 7 <= hora_actual < 24:
        precio_actual = obtener_precio_btc()
        precio_anterior = leer_ultimo_precio()

        if precio_actual:
            diferencia = abs(precio_actual - precio_anterior) if precio_anterior else UMBRAL_ALERTA + 1
            if diferencia >= UMBRAL_ALERTA:
                enviar_alerta(precio_actual)
                guardar_precio(precio_actual)
    else:
        print("😴 Horario de descanso... la Casi casi no molesta.")

    time.sleep(60)
