"""
CreditosPro v3.0 - Entry point
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


def puerto_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def abrir_navegador():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    if not puerto_libre(PORT):
        webbrowser.open(f"http://127.0.0.1:{PORT}")
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
