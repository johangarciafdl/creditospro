"""Las herramientas de seguridad corren con las pruebas, no cuando uno se acuerda.

Un analisis que hay que lanzar a mano se lanza el dia que se instala y nunca
mas. Atadas a pytest, un fallo nuevo aparece en el mismo sitio donde ya se
mira todos los dias.

Reparto:

- **Bandit** revisa el codigo Python en busca de patrones peligrosos. Es
  local y rapido, asi que corre siempre.
- **pip-audit** contrasta las dependencias contra la base de vulnerabilidades
  publicada, y para eso necesita internet. Va marcada `red` y queda fuera de
  la suite normal: `pytest` tiene que seguir funcionando sin conexion y sin
  tardar minutos. Se lanza con `pytest -m red`, y conviene hacerlo antes de
  cada despliegue.

Si una herramienta no esta instalada la prueba se salta con un aviso, en vez
de fallar: no tiene sentido romper la suite de alguien que solo clono el
repositorio.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
# Lo que se analiza: el codigo de la aplicacion y los scripts de mantenimiento.
# Las pruebas no, porque usan contrasenas de mentira a proposito.
CARPETAS = ["app", "scripts"]


def _disponible(modulo: str) -> bool:
    return subprocess.run([sys.executable, "-c", f"import {modulo}"],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _disponible("bandit"),
                    reason="bandit no instalado: pip install 'bandit[toml]'")
def test_bandit_no_encuentra_nada_serio():
    """Falla ante un hallazgo de gravedad media o alta con confianza alta.

    Se exige confianza alta a proposito. Bandit marca como sospechosa
    cualquier consulta construida con cadenas, aunque no haya entrada de
    usuario cerca: con confianza baja incluida, la prueba fallaria por un
    script de respaldo que recorre una lista fija de tablas, y una prueba
    que grita sin motivo se acaba desactivando.
    """
    salida = Path(tempfile.gettempdir()) / "creditospro_bandit.json"
    subprocess.run(
        [sys.executable, "-m", "bandit", "-r", *CARPETAS,
         "-f", "json", "-o", str(salida), "-q"],
        cwd=RAIZ, capture_output=True, timeout=300,
    )
    assert salida.exists(), "bandit no llego a escribir su informe"
    informe = json.loads(salida.read_text(encoding="utf-8"))

    serios = [
        r for r in informe["results"]
        if r["issue_severity"] in ("MEDIUM", "HIGH") and r["issue_confidence"] == "HIGH"
    ]
    detalle = "\n  ".join(
        f"[{r['issue_severity']}] {r['test_id']} {r['filename']}:{r['line_number']}"
        f" — {r['issue_text'][:90]}"
        for r in serios
    )
    assert not serios, f"Bandit encontro {len(serios)} hallazgo(s):\n  {detalle}"


@pytest.mark.red
@pytest.mark.skipif(not _disponible("pip_audit"),
                    reason="pip-audit no instalado: pip install pip-audit")
def test_las_dependencias_no_tienen_vulnerabilidades_conocidas():
    """Contrasta requirements.txt contra la base de vulnerabilidades.

    Es la clase de fallo que no depende de como este escrito el codigo: una
    biblioteca que ayer era correcta hoy tiene un aviso publicado, y solo se
    entera quien pregunta.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pip_audit", "-r", "requirements.txt",
         "--progress-spinner", "off", "--format", "json"],
        cwd=RAIZ, capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0 and not r.stdout.strip():
        pytest.skip(f"pip-audit no pudo consultar la base: {r.stderr[-200:]}")

    datos = json.loads(r.stdout)
    afectadas = [
        f"{d['name']} {d['version']}: "
        + ", ".join(v.get("id", "?") for v in d.get("vulns", []))
        for d in datos.get("dependencies", [])
        if d.get("vulns")
    ]
    assert not afectadas, (
        "Dependencias con vulnerabilidades conocidas:\n  " + "\n  ".join(afectadas)
    )


# .env.example y la documentacion traen ejemplos con el hueco a la vista.
# Se reconocen por la palabra que ocupa el hueco, no por el fichero: dejar
# un fichero entero sin revisar es como acaba subiendose una clave de verdad.
_PALABRAS_DE_RELLENO = (
    "usuario", "contrase", "password", "passwd", "clave", "host", "user",
    "pass", "xxx", "changeme", "tu-", "tu_", "your", "example", "ejemplo",
    "<", ">", "...", "aqui", "here", "placeholder", "basedatos",
)


def _es_marcador(texto: str) -> bool:
    minus = texto.lower()
    return any(p in minus for p in _PALABRAS_DE_RELLENO)


@pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")
def test_ningun_secreto_versionado():
    """Las claves no pueden acabar en el repositorio.

    Lo mas facil de hacer mal y lo mas caro de deshacer: una clave subida a
    git sigue en el historial aunque se borre del fichero, asi que hay que
    detectarla antes del commit, no despues.
    """
    patrones = [
        ("clave secreta de Supabase", r"sb_secret_[A-Za-z0-9_\-]{10,}"),
        ("clave service_role heredada", r"eyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}\."),
        ("contrasena en una URL de base de datos", r"postgres(ql)?://[^:\s]+:[^@\s]{8,}@"),
        ("clave privada", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ]
    import re
    seguidos = subprocess.run(["git", "ls-files"], cwd=RAIZ,
                              capture_output=True, text=True).stdout.split()
    hallazgos = []
    for relativo in seguidos:
        ruta = RAIZ / relativo
        if not ruta.is_file() or ruta.suffix in {".png", ".jpg", ".ico", ".webp", ".pyc"}:
            continue
        try:
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for nombre, patron in patrones:
            for m in re.finditer(patron, texto):
                if _es_marcador(m.group(0)):
                    continue
                linea = texto[:m.start()].count("\n") + 1
                hallazgos.append(f"{relativo}:{linea}: {nombre}")
    assert not hallazgos, (
        "Hay secretos en ficheros versionados:\n  " + "\n  ".join(hallazgos)
    )
