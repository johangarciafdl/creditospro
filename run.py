"""
CreditosPro v3.0 - Entry point con verificacion de licencia
"""
import sys, os, time, threading, webbrowser, socket
from pathlib import Path

# Cargar .env temprano
from dotenv import load_dotenv
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"[CreditosPro] Variables cargadas desde: {env_file}")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
PORT = int(os.getenv("PORT", "8000"))

# Validar variables criticas (no usar fallbacks debiles)
_missing = [name for name, val in (("DATABASE_URL", DATABASE_URL), ("SECRET_KEY", SECRET_KEY)) if not val]
if _missing:
    print(f"[CreditosPro] ERROR: faltan variables de entorno: {', '.join(_missing)}")
    print("[CreditosPro] Crea un archivo .env a partir de .env.example")
    sys.exit(1)


def check_license_on_start() -> bool:
    """Retorna True si puede continuar, False si debe ir a activacion"""
    try:
        import license_manager
        result = license_manager.check_license()
        if result.get("valid"):
            empresa = result.get("empresa_nombre", "")
            days_left = result.get("days_left", 0)
            print(f"[CreditosPro] Licencia valida - {empresa} - {days_left} dias restantes")
            return True
        print(f"[CreditosPro] LICENCIA: {result.get('error')}")
        print(f"[CreditosPro] Machine ID: {result.get('machine_id', '?')}")
        return False
    except ImportError:
        env = os.getenv("ENVIRONMENT", "production").strip().lower()
        if env == "development":
            print("[CreditosPro] Modo desarrollo (sin verificacion de licencia)")
            return True
        print("[CreditosPro] ERROR: license_manager no disponible en produccion.")
        return False
    except Exception as e:
        print(f"[CreditosPro] Error verificando licencia: {e}")
        return False


LICENSE_VALID = check_license_on_start()


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
        url = f"http://127.0.0.1:{PORT}"
        if not LICENSE_VALID:
            url += "/license/activar"
        webbrowser.open(url)
        return

    if os.getenv("CREDITOSPRO_NO_BROWSER", "0") != "1":
        threading.Thread(target=abrir_navegador, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=PORT,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    main()
