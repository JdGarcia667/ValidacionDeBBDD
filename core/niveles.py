"""Validación de requisitos por NIVEL DE CUENTA (clientes).

Cada entidad define, por nivel (1-4), qué campos deben venir llenos, pudiendo
diferenciar por tipo de persona (física/moral) y por modalidad de apertura
(presencial/remota). Esta lógica es por fila, así que sirve igual para la
validación en memoria y por lotes (SQLite).
"""
from __future__ import annotations

import re

import pandas as pd

from core.utils import normalizar_texto

NIVELES = ["1", "2", "3", "3L", "4", "4L"]


def construir_aliases_nivel(pares) -> dict:
    """Normaliza un mapa {alias: nivel} para búsqueda robusta (sin acentos, mayúsculas)."""
    out = {}
    for alias, nivel in (pares or {}).items():
        clave = normalizar_texto(str(alias)).upper()
        if clave:
            out[clave] = str(nivel)
    return out


# Sinónimos de nivel reconocidos por defecto cuando la columna no dice "1/2/3/4".
_ALIASES_NIVEL_DEFAULT = construir_aliases_nivel({
    "Tradicional": "4", "Tradicionales": "4", "Cuenta Tradicional": "4",
    "Cuentas Tradicionales": "4", "Sin limite": "4", "Ilimitada": "4",
    "Limitada": "3L", "Cuenta Limitada": "3L", "Nivel 3 Limitada": "3L",
    "4 Limitada": "4L", "Nivel 4 Limitada": "4L",
})


def _vacio(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in ("", "nan", "none", "null")


def _fila(idx):
    try:
        return int(idx) + 2
    except (TypeError, ValueError):
        return idx


def normalizar_nivel(valor, aliases=None) -> str | None:
    """Mapea el valor de la columna de nivel a '1'..'4', '3L' o '4L'.

    Reconoce: dígito explícito ('Nivel 2', '2', 2.0...), las variantes
    Limitada ('N3 Limitada', '3 Limitada', '3L', 'N3L' -> '3L'; análogo para
    '4L') y sinónimos por nombre (p. ej. 'Tradicional' -> '4', 'Limitada' ->
    '3L'). `aliases` agrega o sobreescribe sinónimos propios de la entidad
    (ya normalizados)."""
    if _vacio(valor):
        return None
    mapa = _ALIASES_NIVEL_DEFAULT if not aliases else {**_ALIASES_NIVEL_DEFAULT, **aliases}
    clave = normalizar_texto(str(valor)).upper()
    if clave in mapa:
        return mapa[clave]
    t = str(valor).strip().lower()
    m = re.search(r"[1-4]", t)
    if not m:
        return None
    nivel = m.group(0)
    if nivel in ("3", "4") and re.search(rf"limitad|{nivel}\s*l\b", t):
        return nivel + "L"
    return nivel


def normalizar_modalidad(valor, default: str = "presencial") -> str:
    if _vacio(valor):
        return default
    t = str(valor).strip().lower()
    if "remot" in t or t in ("r", "online", "digital", "no presencial"):
        return "remota"
    if "presen" in t or t in ("p", "fisica", "sucursal"):
        return "presencial"
    return default


def tipo_de(valor, default: str = "fisica") -> str:
    if _vacio(valor):
        return default
    return "moral" if "moral" in str(valor).strip().lower() else "fisica"


def categoria_persona(valor, default: str = "fisica") -> str:
    """Subtipo de persona para límites de operación (montos): 'fisica',
    'fisica_ae' (física con actividad empresarial), 'moral' o 'fideicomiso'.

    Se detecta por texto sobre la misma columna 'tipo de persona' (igual que
    `tipo_de`, pero con más granularidad). `default` es el valor devuelto
    cuando la celda viene vacía."""
    if _vacio(valor):
        return default
    t = str(valor).strip().lower()
    if "fideicomiso" in t:
        return "fideicomiso"
    if "moral" in t:
        return "moral"
    if "empresarial" in t:
        return "fisica_ae"
    return "fisica"


def campos_requeridos(requisitos, nivel: str, tipo: str, modalidad: str) -> list[str]:
    """Unión de campos requeridos por las reglas que aplican a la combinación."""
    out: list[str] = []
    for r in requisitos:
        if str(r.nivel) != nivel:
            continue
        if r.tipo_persona not in (tipo, "ambos"):
            continue
        if r.modalidad not in (modalidad, "ambas"):
            continue
        for c in r.campos:
            if c not in out:
                out.append(c)
    return out


def _tipos_por_nivel(requisitos) -> dict[str, set]:
    """Para cada nivel definido, qué tipos de persona admite."""
    res: dict[str, set] = {}
    for r in requisitos:
        s = res.setdefault(str(r.nivel), set())
        if r.tipo_persona == "ambos":
            s.update(("fisica", "moral"))
        else:
            s.add(r.tipo_persona)
    return res


def validar_requisitos(df, mapeo, requisitos, *, campo_nivel, campo_tipo_persona="",
                       campo_modalidad="", default_modalidad="presencial",
                       default_tipo="fisica", id_logico="id_cliente",
                       aliases_nivel=None) -> list[dict]:
    """Devuelve una lista de hallazgos (dicts) por campos faltantes según el nivel.

    Cada hallazgo: {fila, id_cliente, nivel, tipo, modalidad, campo, columna, Tipo_Error}.
    """
    if not requisitos or not campo_nivel:
        return []
    col_nivel = mapeo.get(campo_nivel)
    if not col_nivel or col_nivel not in df.columns:
        return []  # sin columna de nivel no se puede aplicar
    col_tipo = mapeo.get(campo_tipo_persona) if campo_tipo_persona else None
    col_mod = mapeo.get(campo_modalidad) if campo_modalidad else None
    col_id = mapeo.get(id_logico)

    niveles_def = {str(r.nivel) for r in requisitos}
    tipos_por_nivel = _tipos_por_nivel(requisitos)

    out: list[dict] = []
    for idx, row in df.iterrows():
        nivel = normalizar_nivel(row[col_nivel], aliases_nivel)
        if nivel is None or nivel not in niveles_def:
            continue  # nivel vacío o no configurado: lo cubre otra validación
        tipo = tipo_de(row[col_tipo], default_tipo) if (col_tipo and col_tipo in df.columns) else default_tipo
        modalidad = (normalizar_modalidad(row[col_mod], default_modalidad)
                     if (col_mod and col_mod in df.columns) else default_modalidad)
        idv = row[col_id] if (col_id and col_id in df.columns) else idx
        fila = _fila(idx)

        if tipo not in tipos_por_nivel.get(nivel, set()):
            out.append(_h(fila, idv, nivel, tipo, modalidad, "Nivel_cuenta", col_nivel,
                          f"Nivel {nivel} no aplica a persona {tipo}"))
            continue

        for campo in campos_requeridos(requisitos, nivel, tipo, modalidad):
            col = mapeo.get(campo)
            valor = row[col] if (col and col in df.columns) else None
            if _vacio(valor):
                out.append(_h(fila, idv, nivel, tipo, modalidad, campo, col or "(sin mapear)",
                              f"Falta '{campo}' (requerido en nivel {nivel}, "
                              f"{tipo}, {modalidad})"))
    return out


def _h(fila, idv, nivel, tipo, modalidad, campo, columna, tipo_error) -> dict:
    return {"fila": fila, "id_cliente": idv, "nivel": nivel, "tipo": tipo,
            "modalidad": modalidad, "campo": campo, "columna": columna,
            "Tipo_Error": tipo_error}
