"""
CreditosPro v2.1 — Módulo Administrador (.exe)
===============================================
Wrapper PyWebView que abre el panel de admin en una ventana nativa de Windows.

Modo de uso:
  - LOCAL:  python administrador.py
            Levanta el servidor FastAPI localmente y abre la ventana.
  - REMOTO: python administrador.py --url https://mi-servidor.railway.app
            Solo abre la ventana apuntando al servidor en la nube
            (cobradores y admin comparten la misma DB).

Empaquetado a .exe:
  pip install pyinstaller pywebview
  pyinstaller --noconsole --onefile --name="CreditosPro Admin" administrador.py

Arquitectura:
  ┌─────────────────────────────────────────────────────┐
  │  .exe  (Administrador)                              │
  │  ┌──────────────────────┐   HTTP/JSON   ┌────────┐  │
  │  │  PyWebView (ventana) │◄────────────►│FastAPI │  │
  │  └──────────────────────┘              │ Server │  │
  └─────────────────────────────────────────┤        ├──┘
                                             │ SQLite │
  Cobradores (celular/navegador) ──────────►│  DB    │
                                             └────────┘
"""
import sys
import os
import time
import threading
import argparse
import subprocess
import signal
from pathlib import Path

# ─── Cargar variables de entorno desde .env si existe ────────────────────────
_base = Path(__file__).parent
_dotenv = _base / ".env"
if _dotenv.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv)
        print(f"[CreditosPro] Variables cargadas desde {_dotenv}")
    except ImportError:
        pass

# ─── Validar variables requeridas ────────────────────────────────────────────
if not os.getenv("DATABASE_URL"):
    print("ERROR: La variable DATABASE_URL no está configurada en .env")
    print("Ejemplo Supabase: postgresql://postgres.[REF]:[PASS]@aws-1-us-east-1.pooler.supabase.com:6543/postgres")
    print("Ejemplo local:   sqlite:///./creditospro.db")
    sys.exit(1)

if not os.getenv("SECRET_KEY"):
    print("ERROR: La variable SECRET_KEY no está configurada en .env")
    sys.exit(1)

# ─── Argumento: URL del servidor remoto (opcional) ───────────────────────────
parser = argparse.ArgumentParser(description="CreditosPro Admin")
parser.add_argument("--url", default="", help="URL del servidor remoto (ej: https://mi-servidor.railway.app)")
parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Puerto local (default 8000)")
parser.add_argument("--debug", action="store_true", help="Modo debug")
args, _ = parser.parse_known_args()

SERVER_URL = args.url.rstrip("/") if args.url else f"http://127.0.0.1:{args.port}"
USE_REMOTE = bool(args.url)
PORT = args.port

# Verificar si estamos usando PostgreSQL o SQLite
DB_URL = os.getenv("DATABASE_URL", "")
USING_POSTGRES = DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://")
if USING_POSTGRES:
    print("[CreditosPro] Base de datos: PostgreSQL (Remoto)")
else:
    print("[CreditosPro] Base de datos: SQLite (Local)")


# ─── Ventana principal ────────────────────────────────────────────────────────
class AdminApp:
    def __init__(self):
        self.server_process = None
        self.window = None
        self.server_ready = False

    def _iniciar_servidor_local(self):
        """Levanta FastAPI en un proceso separado (solo si no hay servidor remoto)"""
        if USE_REMOTE:
            print(f"[CreditosPro] Conectando a servidor remoto: {SERVER_URL}")
            self.server_ready = True
            return

        print(f"[CreditosPro] Iniciando servidor local en puerto {PORT}...")
        # Encuentra el directorio del script/exe
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        run_py = base / "run.py"

        if not run_py.exists():
            # Modo desarrollo: usar uvicorn directamente
            cmd = [sys.executable, "-m", "uvicorn",
                   "app.main:app", "--host", "127.0.0.1",
                   "--port", str(PORT), "--log-level", "warning"]
        else:
            cmd = [sys.executable, str(run_py), "--no-browser"]

        env = os.environ.copy()
        env["CREDITOSPRO_NO_BROWSER"] = "1"

        self.server_process = subprocess.Popen(
            cmd,
            cwd=str(base),
            env=env,
            stdout=subprocess.DEVNULL if not args.debug else None,
            stderr=subprocess.DEVNULL if not args.debug else None,
        )

        # Esperar hasta que el servidor responda
        import urllib.request
        for _ in range(30):  # max 15 segundos
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/auth/login", timeout=1)
                self.server_ready = True
                print("[CreditosPro] ✅ Servidor listo")
                return
            except Exception:
                time.sleep(0.5)

        print("[CreditosPro] ⚠ El servidor tardó más de lo esperado")
        self.server_ready = True

    def _hilo_servidor(self):
        self._iniciar_servidor_local()

    def run(self):
        try:
            import webview
        except ImportError:
            print("ERROR: pywebview no está instalado.")
            print("Instala con: pip install pywebview")
            # Fallback: abrir en el navegador del sistema
            import webbrowser
            self._iniciar_servidor_local()
            time.sleep(2)
            webbrowser.open(SERVER_URL)
            input("Presiona Enter para cerrar...")
            return

        # Iniciar servidor en hilo paralelo
        t = threading.Thread(target=self._hilo_servidor, daemon=True)
        t.start()

        # Esperar a que el servidor esté listo (máx 12 segundos)
        for _ in range(24):
            if self.server_ready:
                break
            time.sleep(0.5)

        # Crear ventana nativa
        self.window = webview.create_window(
            title="CreditosPro — Panel Administrativo",
            url=SERVER_URL,
            width=1280,
            height=800,
            min_size=(1024, 680),
            background_color="#0f3d28",
            # Exponer API JS para comunicación nativa
            js_api=NativeAPI(self),
        )

        # Configurar al cerrar
        def on_closing():
            self._limpiar()
            return True

        self.window.events.closing += on_closing

        # Iniciar webview (bloquea hasta que se cierra)
        webview.start(debug=args.debug)

    def _limpiar(self):
        """Cierra el servidor al cerrar la ventana"""
        if self.server_process:
            print("[CreditosPro] Cerrando servidor local...")
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=3)
            except Exception:
                self.server_process.kill()


class NativeAPI:
    """
    API JavaScript nativa expuesta a la ventana WebView.
    Permite funciones especiales que solo tiene el .exe del admin.
    Uso desde JS: window.pywebview.api.imprimir_reporte(url)
    """
    def __init__(self, app: AdminApp):
        self.app = app

    def imprimir_reporte(self, url: str):
        """Abre el diálogo de impresión del SO"""
        try:
            if self.app.window:
                self.app.window.evaluate_js("window.print()")
        except Exception as e:
            print(f"Error impresión: {e}")

    def abrir_archivo(self, ruta: str):
        """Abre un archivo Excel/PDF con la aplicación predeterminada.

        Restringe el acceso a rutas dentro del proyecto (uploads/, backups/, reportes/)
        para evitar que codigo malicioso en la pagina abra archivos del sistema.
        """
        import subprocess
        from pathlib import Path as _Path

        try:
            if not ruta or not isinstance(ruta, str):
                return {"ok": False, "error": "Ruta invalida"}

            base = _Path(__file__).resolve().parent
            allowed_roots = [
                (base / sub).resolve() for sub in ("uploads", "backups", "reportes", "static")
            ]
            try:
                target = (base / ruta).resolve() if not _Path(ruta).is_absolute() else _Path(ruta).resolve()
            except (OSError, ValueError):
                return {"ok": False, "error": "Ruta invalida"}

            inside_allowed = any(
                str(target).startswith(str(root) + os.sep) or target == root
                for root in allowed_roots
            )
            if not inside_allowed or not target.is_file():
                print(f"[CreditosPro] Bloqueado abrir_archivo fuera de carpetas permitidas: {ruta}")
                return {"ok": False, "error": "Archivo no permitido"}

            if sys.platform == "win32":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target)], check=False)
            else:
                subprocess.run(["xdg-open", str(target)], check=False)
            return {"ok": True}
        except Exception as e:
            print(f"Error abriendo archivo: {e}")
            return {"ok": False, "error": "Error abriendo archivo"}

    def get_info_sistema(self):
        """Retorna info del sistema para el panel admin"""
        return {
            "version": "2.0.0",
            "modo": "remoto" if USE_REMOTE else "local",
            "servidor": SERVER_URL,
            "platform": sys.platform,
        }

    def minimizar(self):
        if self.app.window:
            self.app.window.minimize()

    def maximizar(self):
        if self.app.window:
            self.app.window.toggle_fullscreen()


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print(" CreditosPro v2.0 — Panel Administrador")
    print("=" * 50)
    if USE_REMOTE:
        print(f" Modo: REMOTO → {SERVER_URL}")
    else:
        print(f" Modo: LOCAL  → http://127.0.0.1:{PORT}")
    print()

    app = AdminApp()
    app.run()
