"""Construccion de los estaticos servidos al navegador.

Cada archivo de `static/css` y `static/js` se minifica y se copia a
`static/dist/` con el hash de su contenido en el nombre
(`app.3f9c1a2b.css`). Eso permite servirlos con `Cache-Control: immutable`
y un año de vida: el navegador no vuelve a pedirlos nunca mientras no
cambien, y cuando cambian el nombre cambia con ellos, asi que no hace falta
purgar nada ni esperar a que expire una cache vieja.

No se generan source maps a proposito: expondrian el codigo original en
produccion y solo sirven para depurar, que aqui se hace sobre las fuentes.

Si la minificacion de un archivo falla, se copia el original en lugar de
tumbar el arranque: es preferible servir el archivo sin minificar a dejar
la aplicacion sin ese recurso.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

from app.utils.minificar import minificar_css, minificar_js

logger = logging.getLogger(__name__)

# Se construyen todos los .js/.css de estas carpetas.
CARPETAS = ("css", "js")

# Estos NO pasan por el pipeline: su URL es parte del contrato con el
# navegador y no puede llevar hash.
#   sw.js         -> el alcance del service worker depende de su ruta
#   manifest.json -> lo referencia <link rel="manifest"> con ruta fija
EXCLUIDOS = {"sw.js"}

_manifiesto: dict[str, str] = {}


def _hash_corto(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()[:8]


def construir(base_dir: Path) -> dict[str, str]:
    """Minifica y versiona los estaticos. Devuelve el manifiesto."""
    global _manifiesto
    origen = base_dir / "static"
    destino = origen / "dist"

    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)

    manifiesto: dict[str, str] = {}
    total_antes = total_despues = 0

    for carpeta in CARPETAS:
        raiz = origen / carpeta
        if not raiz.is_dir():
            continue
        for archivo in sorted(raiz.glob("*")):
            if not archivo.is_file() or archivo.name in EXCLUIDOS:
                continue
            if archivo.suffix not in (".js", ".css"):
                continue

            texto = archivo.read_text(encoding="utf-8")
            try:
                minificado = (
                    minificar_css(texto) if archivo.suffix == ".css" else minificar_js(texto)
                )
            except Exception:
                logger.exception("No se pudo minificar %s; se sirve sin minificar", archivo.name)
                minificado = texto

            datos = minificado.encode("utf-8")
            nombre = f"{archivo.stem}.{_hash_corto(datos)}{archivo.suffix}"
            (destino / carpeta).mkdir(parents=True, exist_ok=True)
            (destino / carpeta / nombre).write_bytes(datos)

            manifiesto[f"{carpeta}/{archivo.name}"] = f"{carpeta}/{nombre}"
            total_antes += len(texto.encode("utf-8"))
            total_despues += len(datos)

    (destino / "manifiesto.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _manifiesto = manifiesto

    if total_antes:
        ahorro = 100 - round(100 * total_despues / total_antes)
        logger.info(
            "Estaticos construidos: %d archivos, %d -> %d bytes (%d%% menos)",
            len(manifiesto), total_antes, total_despues, ahorro,
        )
    return manifiesto


def estatico(ruta: str) -> str:
    """URL publica de un estatico. Usar en las plantillas: {{ estatico('js/app.js') }}.

    Si el archivo no esta construido (por ejemplo en un test que no arranca
    el ciclo de vida de la app) se devuelve la ruta sin versionar, que sigue
    funcionando: solo se pierde la cache larga.
    """
    versionado = _manifiesto.get(ruta)
    return f"/static/dist/{versionado}" if versionado else f"/static/{ruta}"
