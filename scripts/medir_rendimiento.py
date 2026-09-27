"""Mide cuanto tarda cada pantalla en responder, contra el servidor que sea.

    python scripts/medir_rendimiento.py                 # produccion
    python scripts/medir_rendimiento.py --base http://127.0.0.1:8000

Para que los numeros signifiquen algo hace falta separar dos cosas que se
suelen confundir:

- **La red**: el viaje de ida y vuelta desde donde se mide hasta el servidor.
  Desde Colombia a un servidor en Virginia son ~200 ms que no dependen del
  codigo. El script los estima con /health, que no toca la base de datos, y
  los descuenta.
- **El servidor**: lo que de verdad cuesta construir la respuesta. Es lo
  unico sobre lo que se puede trabajar desde aqui.

Sin esa resta, cualquier medida hecha desde una casa con mala conexion
parece un problema de la aplicacion, y cualquiera hecha al lado del servidor
parece que todo va perfecto.

Se piden varias veces y se queda con la MEDIANA: una peticion suelta puede
caer en un arranque en frio o en un pico de la red y no dice nada.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

PRODUCCION = "https://creditospro-production.up.railway.app"

# Lo que de verdad abre la gente. Las que necesitan sesion se marcan.
PANTALLAS = [
    ("/health", "salud (sin base de datos)", False),
    ("/", "portada", False),
    ("/auth/login", "pantalla de entrada", False),
    ("/ruta", "ruta del cobrador", True),
    ("/caja", "caja", True),
    ("/dashboard", "panel", True),
    ("/clientes", "clientes", True),
]

REPETICIONES = 5


def _pedir(url: str, galletas: str = "") -> tuple[int, float, int]:
    # Solo http(s). urlopen tambien abre file:// y esquemas raros, asi que un
    # --base mal puesto (o copiado de otro sitio) podria hacer que esto leyera
    # archivos del disco en vez de medir un servidor.
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Solo se puede medir http o https, no: {url[:40]}")
    pet = urllib.request.Request(url, headers={
        "User-Agent": "medir-rendimiento/1.0",
        **({"Cookie": galletas} if galletas else {}),
    })
    inicio = time.perf_counter()
    try:
        # nosec B310: el esquema se comprueba arriba (solo http/https);
        # bandit lo marca porque no puede seguir esa comprobacion.
        with urllib.request.urlopen(pet, timeout=60) as r:  # nosec B310
            cuerpo = r.read()
            return r.status, (time.perf_counter() - inicio) * 1000, len(cuerpo)
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - inicio) * 1000, 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=os.getenv("BASE_MEDICION", PRODUCCION))
    ap.add_argument("--galletas", default=os.getenv("COOKIE_MEDICION", ""),
                    help="Cookie de una sesion abierta, para las pantallas "
                         "que la necesitan (cp_session=...)")
    ap.add_argument("--repeticiones", type=int, default=REPETICIONES)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"Midiendo {base}  ({args.repeticiones} intentos por pantalla)\n")

    # El suelo de la red: /health no consulta nada pesado, asi que lo que
    # tarda es basicamente el viaje.
    suelos = [_pedir(f"{base}/health")[1] for _ in range(args.repeticiones)]
    suelo = statistics.median(suelos)
    print(f"Viaje de ida y vuelta (estimado con /health): {suelo:6.0f} ms")
    print("Todo lo de abajo ya lleva ese viaje descontado.\n")

    print(f"{'pantalla':34} {'servidor':>10} {'total':>9} {'tamano':>9}  estado")
    print("-" * 78)
    problemas = []
    for ruta, nombre, necesita_sesion in PANTALLAS:
        if necesita_sesion and not args.galletas:
            print(f"{nombre:34} {'-':>10} {'-':>9} {'-':>9}  (necesita sesion)")
            continue
        medidas, estado, tam = [], 0, 0
        for _ in range(args.repeticiones):
            estado, ms, tam = _pedir(f"{base}{ruta}", args.galletas)
            medidas.append(ms)
        total = statistics.median(medidas)
        servidor = max(0.0, total - suelo)
        aviso = ""
        if servidor > 500:
            aviso = "  <-- LENTA"
            problemas.append((nombre, servidor))
        print(f"{nombre:34} {servidor:8.0f} ms {total:7.0f} ms "
              f"{tam/1024:7.1f} KB  {estado}{aviso}")

    print()
    if problemas:
        print("Pantallas que tardan mas de medio segundo en construirse:")
        for nombre, ms in problemas:
            print(f"  - {nombre}: {ms:.0f} ms")
        return 1
    print("Ninguna pantalla pasa de medio segundo de trabajo en el servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
