"""Minificacion conservadora de JS y CSS, sin source maps.

Por que no se usa jsmin: colapsa el contenido de los template literals
(`hola ${x} y` queda `hola ${x}y`), y este proyecto los usa para construir
casi todo el HTML dinamico -- minificar con el cambiaria textos que ve el
cliente. Aqui se hace lo unico que es seguro sin un parser completo de
ECMAScript: quitar comentarios y la sangria, respetando literales.

Las lineas NO se juntan entre si: sin un analisis de ASI, unir lineas puede
cambiar el significado del programa. La ganancia real de juntarlas es
minima porque el servidor ya sirve todo con gzip, que comprime muy bien la
sangria repetida; lo que si ahorra es no mandar comentarios ni espacios.
"""
from __future__ import annotations

import re

import rcssmin


def _es_inicio_de_regex(anterior: str) -> bool:
    """Decide si una '/' abre un literal de expresion regular o es division.

    Se mira el ultimo caracter significativo: tras un valor (identificador,
    numero, ')', ']') una '/' divide; en cualquier otra posicion abre regex.
    """
    if not anterior:
        return True
    if anterior.isalnum() or anterior in "_$":
        # Puede ser `return /re/` o `a / b`; las palabras clave se resuelven aparte.
        return False
    return anterior not in ")]}"


_PALABRAS_ANTES_DE_REGEX = (
    "return", "typeof", "instanceof", "in", "of", "new", "delete",
    "void", "throw", "case", "do", "else", "yield", "await",
)


def minificar_js(codigo: str) -> str:
    """Quita comentarios y sangria de JavaScript sin tocar los literales."""
    salida: list[str] = []
    i = 0
    n = len(codigo)
    # Ultimo caracter significativo emitido, para distinguir regex de division.
    ultimo = ""
    # Pila de template literals: cada `${` anidado vuelve a modo codigo.
    plantillas: list[int] = []

    while i < n:
        c = codigo[i]
        dos = codigo[i:i + 2]

        # --- comentarios ---
        if dos == "//" and not plantillas:
            fin = codigo.find("\n", i)
            i = n if fin == -1 else fin
            continue
        if dos == "/*" and not plantillas:
            fin = codigo.find("*/", i + 2)
            if fin == -1:
                break
            # Un comentario de bloque que abarcaba varias lineas deja un salto,
            # para no pegar dos sentencias que estaban en lineas distintas.
            if "\n" in codigo[i:fin]:
                salida.append("\n")
            i = fin + 2
            continue

        # --- cadenas normales ---
        if c in "\"'":
            j = i + 1
            while j < n:
                if codigo[j] == "\\":
                    j += 2
                    continue
                if codigo[j] == c:
                    break
                j += 1
            salida.append(codigo[i:j + 1])
            ultimo = c
            i = j + 1
            continue

        # --- template literals (se copian tal cual, incluidos sus saltos) ---
        if c == "`":
            salida.append(c)
            plantillas.append(1)
            i += 1
            while i < n and plantillas:
                ch = codigo[i]
                if ch == "\\":
                    salida.append(codigo[i:i + 2])
                    i += 2
                    continue
                if ch == "`":
                    plantillas.pop()
                    salida.append(ch)
                    i += 1
                    continue
                if codigo[i:i + 2] == "${":
                    # Dentro de ${...} vuelve a ser codigo: se delega al bucle
                    # principal buscando la llave de cierre equilibrada.
                    prof = 1
                    j = i + 2
                    while j < n and prof:
                        if codigo[j] == "{":
                            prof += 1
                        elif codigo[j] == "}":
                            prof -= 1
                        elif codigo[j] in "\"'`":
                            cierre = codigo[j]
                            j += 1
                            while j < n and codigo[j] != cierre:
                                j += 2 if codigo[j] == "\\" else 1
                        j += 1
                    salida.append("${" + minificar_js(codigo[i + 2:j - 1]) + "}")
                    i = j
                    continue
                salida.append(ch)
                i += 1
            ultimo = "`"
            continue

        # --- literales de expresion regular ---
        if c == "/":
            palabra = re.search(r"([A-Za-z_$][\w$]*)$", "".join(salida))
            abre = _es_inicio_de_regex(ultimo) or (
                palabra is not None and palabra.group(1) in _PALABRAS_ANTES_DE_REGEX
            )
            if abre:
                j = i + 1
                clase = False
                while j < n:
                    ch = codigo[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        clase = True
                    elif ch == "]":
                        clase = False
                    elif ch == "/" and not clase:
                        break
                    elif ch == "\n":
                        j = -1
                        break
                    j += 1
                if j > 0:
                    j += 1
                    while j < n and codigo[j].isalpha():
                        j += 1
                    salida.append(codigo[i:j])
                    ultimo = "/"
                    i = j
                    continue
            salida.append(c)
            ultimo = c
            i += 1
            continue

        salida.append(c)
        if not c.isspace():
            ultimo = c
        i += 1

    # Ya sin comentarios ni literales partidos: se quita la sangria y las
    # lineas vacias. El contenido de los template literals ya esta copiado
    # tal cual, asi que esta limpieza no puede alcanzarlo.
    texto = "".join(salida)
    partes = texto.split("`")
    for k in range(0, len(partes), 2):  # solo los tramos fuera de plantillas
        lineas = (ln.strip() for ln in partes[k].split("\n"))
        partes[k] = "\n".join(ln for ln in lineas if ln)
    return "`".join(partes).strip()


def minificar_css(codigo: str) -> str:
    """Minifica CSS con rcssmin, que si es seguro para este lenguaje."""
    return rcssmin.cssmin(codigo, keep_bang_comments=False)
