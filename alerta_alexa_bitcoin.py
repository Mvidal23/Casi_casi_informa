
import requests

def enviar_alerta_alexa():
    url = "https://webhooks.voicemonkey.io/catch/630edd338ab6c57b331be08bea65720c/6d84874157"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print("✅ Mensaje enviado a Alexa correctamente.")
        else:
            print(f"⚠️ Error al enviar mensaje. Código: {response.status_code}")
    except Exception as e:
        print(f"❌ Excepción: {e}")

# Ejecutar alerta
enviar_alerta_alexa()
