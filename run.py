"""
<<<<<<< HEAD
CreditosPro v3.0 — Entry point con verificacion de licencia
"""
import sys, os, time, threading, webbrowser, socket
from pathlib import Path

# ── Config desde .env ─────────────────────────────────────────────────────────
from dotenv import load_dotenv
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"[CreditosPro] Variables cargadas desde: {env_file}")

DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY   = os.getenv("SECRET_KEY", "creditospro-dev-2024")
PORT         = int(os.getenv("PORT", "8000"))

os.environ["DATABASE_URL"] = DATABASE_URL
os.environ["SECRET_KEY"]   = SECRET_KEY

# ── Verificar licencia ────────────────────────────────────────────────────────
def check_license_on_start() -> bool:
    """Retorna True si puede continuar, False si debe ir a activacion"""
    try:
        import license_manager
        result = license_manager.check_license()
        if result["valid"]:
            empresa = result.get("empresa_nombre", "")
            days_left = result.get("days_left", 0)
            print(f"[CreditosPro] Licencia valida — {empresa} — {days_left} dias restantes")
            return True
        else:
            print(f"[CreditosPro] LICENCIA: {result.get('error')}")
            print(f"[CreditosPro] Machine ID: {result.get('machine_id','?')}")
            return False
    except ImportError:
        # Sin license_manager.py → modo desarrollo
        print("[CreditosPro] Modo desarrollo (sin verificacion de licencia)")
        return True
    except Exception as e:
        print(f"[CreditosPro] Error verificando licencia: {e}")
        return False  # Seguro: si hay error, bloquear

LICENSE_VALID = check_license_on_start()

# ── Servidor ──────────────────────────────────────────────────────────────────
def puerto_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

def abrir_navegador():
    time.sleep(1.5)
    url = f"http://127.0.0.1:{PORT}"
    if not LICENSE_VALID:
        url += "/license/activar"
    webbrowser.open(url)

def main():
    if not puerto_libre(PORT):
        # Ya hay una instancia corriendo
        url = f"http://127.0.0.1:{PORT}"
        if not LICENSE_VALID:
            url += "/license/activar"
        webbrowser.open(url)
        return

    threading.Thread(target=abrir_navegador, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
=======
CreditosPro v2.0 — run.py
Entry point compatible con ejecución directa y desde administrador.py
"""
import sys
import os
import uvicorn
import threading
import webbrowser
import time

NO_BROWSER = "--no-browser" in sys.argv or os.getenv("CREDITOSPRO_NO_BROWSER") == "1"
PORT = int(os.getenv("CREDITOSPRO_PORT", "8000"))

# Asegurar que el directorio del script esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def abrir_navegador():
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    if not NO_BROWSER:
        t = threading.Thread(target=abrir_navegador, daemon=True)
        t.start()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
        port=PORT,
        log_level="warning",
        reload=False,
    )

<<<<<<< HEAD
=======

>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
if __name__ == "__main__":
    main()
