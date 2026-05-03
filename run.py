"""
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
        port=PORT,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    main()
