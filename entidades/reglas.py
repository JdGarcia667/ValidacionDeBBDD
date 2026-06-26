"""
Catalogo de reglas para entidades configurables (las que crea el usuario).
Cada regla es fn(valor, ctx) -> str | None. El CATALOGO es la fuente de verdad para
el motor y para la UI (que ofrece las reglas al armar una entidad).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import pandas as pd

from core.utils import normalizar_texto, ESTADOS_MEXICANOS_NORM
from core.paises import es_pais_valido


@dataclass
class Contexto:
    fila: Any
    row: "pd.Series"
    mapeo: dict
    df: "pd.DataFrame"

    def get(self, campo_logico: str):
        col = self.mapeo.get(campo_logico)
        if col is not None and col in self.row.index:
            return self.row[col]
        return None


Regla = Callable[[Any, Contexto], "str | None"]


def es_vacio(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in ("", "nan", "none", "null")


def parse_fecha(valor):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(valor, errors="coerce", dayfirst=True)


def _norm(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


# ---------------------- reglas genericas ---------------------- #
def r_no_vacio() -> Regla:
    def f(valor, ctx):
        return "Campo vacio" if es_vacio(valor) else None
    return f


def r_longitud_exacta(longitud: int) -> Regla:
    longitud = int(longitud)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        n = len(str(valor).strip())
        return f"Longitud {n}, se esperaban {longitud}" if n != longitud else None
    return f


def r_longitud_min(minimo: int) -> Regla:
    minimo = int(minimo)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        n = len(str(valor).strip())
        return f"Longitud {n}, minimo {minimo}" if n < minimo else None
    return f


def r_longitud_max(maximo: int) -> Regla:
    maximo = int(maximo)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        n = len(str(valor).strip())
        return f"Longitud {n}, maximo {maximo}" if n > maximo else None
    return f


def r_regex(patron: str, mensaje: str = "Formato invalido") -> Regla:
    compilado = re.compile(patron)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        return None if compilado.fullmatch(str(valor).strip()) else mensaje
    return f


def r_solo_numeros() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        return None if str(valor).strip().isdigit() else "Debe contener solo digitos"
    return f


def r_min_digitos(minimo: int) -> Regla:
    minimo = int(minimo)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        digitos = re.sub(r"\D", "", str(valor))
        return f"{len(digitos)} digitos, minimo {minimo}" if len(digitos) < minimo else None
    return f


def r_sin_repetidos_consecutivos(cantidad: int = 5) -> Regla:
    cantidad = int(cantidad)
    patron = re.compile(r"(\d)\1{" + str(cantidad - 1) + r"}")
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        if patron.search(re.sub(r"\D", "", str(valor))):
            return f"{cantidad} digitos consecutivos repetidos"
        return None
    return f


def r_rango_numerico(minimo: float = None, maximo: float = None) -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        try:
            n = float(str(valor).replace(",", "").strip())
        except ValueError:
            return "No es un numero valido"
        if minimo is not None and n < float(minimo):
            return f"Valor {n} menor al minimo {minimo}"
        if maximo is not None and n > float(maximo):
            return f"Valor {n} mayor al maximo {maximo}"
        return None
    return f


def r_min_separadores(minimo: int = 5, separadores: str = " ,") -> Regla:
    minimo = int(minimo)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        s = str(valor)
        if sum(s.count(c) for c in separadores) < minimo:
            return f"Pocos separadores, minimo {minimo}"
        return None
    return f


def r_contiene(subcadena: str = "@") -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        return None if subcadena in str(valor) else f"No contiene '{subcadena}'"
    return f


def r_al_menos_un_espacio() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        return None if str(valor).strip().count(" ") >= 1 else "Debe tener al menos un espacio"
    return f


def r_edad_entre(min_anios: int = 18, max_anios: int = 120) -> Regla:
    min_anios, max_anios = int(min_anios), int(max_anios)
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        fecha = parse_fecha(valor)
        if pd.isna(fecha):
            return "Fecha invalida"
        hoy = date.today()
        edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
        if edad < min_anios:
            return f"Edad {edad} menor a {min_anios}"
        if edad > max_anios:
            return f"Edad {edad} mayor a {max_anios}"
        return None
    return f


def r_fecha_valida() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        return "Fecha invalida" if pd.isna(parse_fecha(valor)) else None
    return f


def r_valor_en(opciones: list = None, normalizar: bool = True) -> Regla:
    opciones = opciones or []
    permitidos = {_norm(o) if normalizar else str(o) for o in opciones}
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        v = _norm(valor) if normalizar else str(valor)
        return f"Valor '{valor}' no permitido" if v not in permitidos else None
    return f


# ---------------------- reglas compuestas (Mexico) ---------------------- #
def r_curp() -> Regla:
    def f(valor, ctx):
        curp = str(valor).strip().upper()
        if curp in ("NAN", "", "NONE", "NULL"):
            return "CURP faltante"
        errores = []
        if len(curp) != 18:
            errores.append(f"Longitud incorrecta: {len(curp)} caracteres")
        if not re.fullmatch(r"[A-Z0-9]+", curp):
            errores.append("Caracteres no permitidos")
        if errores:
            return "; ".join(errores)
        genero = ctx.get("genero")
        if not es_vacio(genero):
            g = _norm(genero)
            esperado = "H" if g in ("MALE", "M", "HOMBRE", "H") else (
                "M" if g in ("FEMALE", "F", "MUJER") else "")
            if esperado and len(curp) >= 11 and curp[10] != esperado:
                return f"Genero CURP: esperado '{esperado}', obtenido '{curp[10]}'"
        return None
    return f


def r_rfc() -> Regla:
    def f(valor, ctx):
        rfc = str(valor).strip().upper()
        if rfc in ("NAN", "", "NONE", "NULL"):
            return "RFC faltante"
        errores = []
        if len(rfc) != 13:
            errores.append(f"Longitud incorrecta: {len(rfc)} caracteres")
        if len(rfc) >= 4 and not re.match(r"^[A-Z]{4}", rfc):
            errores.append("Primeros 4 caracteres no son letras")
        if len(rfc) >= 10 and not re.match(r"^[0-9]{6}", rfc[4:10]):
            errores.append("Caracteres 5 al 10 no son numeros")
        if len(rfc) == 13 and not re.match(r"^[A-Z0-9]{3}$", rfc[10:]):
            errores.append("Ultimos 3 caracteres no son alfanumericos")
        return "; ".join(errores) if errores else None
    return f


# Variantes de país que se consideran México (normalizadas).
_VARIANTES_MX = {normalizar_texto(v).upper() for v in ("Mexico", "Mexicana", "Mex", "MX")}


def r_entidad_federativa_mx() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return "Entidad federativa vacia"
        pais = ctx.get("pais_nacimiento") or ctx.get("Pais_nacimiento")
        # No aplica a extranjeros: solo se valida el estado si el país es México.
        if not es_vacio(pais) and normalizar_texto(str(pais)).upper() in _VARIANTES_MX:
            if normalizar_texto(str(valor)).upper() not in ESTADOS_MEXICANOS_NORM:
                return f"Entidad '{valor}' no valida para Mexico"
        return None
    return f


def r_pais_valido() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        if not es_pais_valido(valor):
            return f"Pais '{valor}' no reconocido"
        return None
    return f


# ---------------------- catalogo ---------------------- #
@dataclass
class Parametro:
    nombre: str
    tipo: str
    etiqueta: str
    default: Any = None


@dataclass
class ReglaCatalogo:
    id: str
    etiqueta: str
    descripcion: str
    constructor: Callable[..., Regla]
    ambito: str = "valor"
    parametros: list = field(default_factory=list)


CATALOGO: dict[str, ReglaCatalogo] = {
    "no_vacio": ReglaCatalogo("no_vacio", "No vacio", "No puede estar vacio.", r_no_vacio),
    "unico": ReglaCatalogo("unico", "Valor unico", "Sin duplicados en la columna.",
                           lambda: None, ambito="columna"),
    "longitud_exacta": ReglaCatalogo("longitud_exacta", "Longitud exacta", "N caracteres exactos.",
        r_longitud_exacta, parametros=[Parametro("longitud", "int", "Longitud", 18)]),
    "longitud_min": ReglaCatalogo("longitud_min", "Longitud minima", "Minimo de caracteres.",
        r_longitud_min, parametros=[Parametro("minimo", "int", "Minimo", 1)]),
    "longitud_max": ReglaCatalogo("longitud_max", "Longitud maxima", "Maximo de caracteres.",
        r_longitud_max, parametros=[Parametro("maximo", "int", "Maximo", 100)]),
    "regex": ReglaCatalogo("regex", "Expresion regular", "Coincidir con un patron.",
        r_regex, parametros=[Parametro("patron", "str", "Patron", r"[A-Z0-9]+"),
                             Parametro("mensaje", "str", "Mensaje", "Formato invalido")]),
    "solo_numeros": ReglaCatalogo("solo_numeros", "Solo digitos", "Solo numeros.", r_solo_numeros),
    "min_digitos": ReglaCatalogo("min_digitos", "Minimo de digitos", "Minimo de digitos.",
        r_min_digitos, parametros=[Parametro("minimo", "int", "Minimo", 10)]),
    "sin_repetidos_consecutivos": ReglaCatalogo("sin_repetidos_consecutivos",
        "Sin digitos repetidos", "Rechaza N digitos repetidos seguidos.",
        r_sin_repetidos_consecutivos, parametros=[Parametro("cantidad", "int", "Cantidad", 5)]),
    "rango_numerico": ReglaCatalogo("rango_numerico", "Rango numerico", "Dentro de un rango.",
        r_rango_numerico, parametros=[Parametro("minimo", "float", "Minimo", 0),
                                      Parametro("maximo", "float", "Maximo", None)]),
    "min_separadores": ReglaCatalogo("min_separadores", "Minimo de separadores",
        "Cuenta espacios/comas (direcciones).",
        r_min_separadores, parametros=[Parametro("minimo", "int", "Minimo", 5),
                                       Parametro("separadores", "str", "Separadores", " ,")]),
    "contiene": ReglaCatalogo("contiene", "Contiene texto", "Debe contener una subcadena.",
        r_contiene, parametros=[Parametro("subcadena", "str", "Subcadena", "@")]),
    "al_menos_un_espacio": ReglaCatalogo("al_menos_un_espacio", "Al menos un espacio",
        "Util para nombre y apellido.", r_al_menos_un_espacio),
    "edad_entre": ReglaCatalogo("edad_entre", "Edad entre", "Calcula edad y la valida.",
        r_edad_entre, parametros=[Parametro("min_anios", "int", "Edad minima", 18),
                                  Parametro("max_anios", "int", "Edad maxima", 120)]),
    "fecha_valida": ReglaCatalogo("fecha_valida", "Fecha valida", "Fecha parseable.", r_fecha_valida),
    "valor_en": ReglaCatalogo("valor_en", "Valor en lista", "Pertenece a un conjunto.",
        r_valor_en, parametros=[Parametro("opciones", "lista", "Opciones (coma)", []),
                                Parametro("normalizar", "str", "Normalizar (si/no)", "si")]),
    "curp": ReglaCatalogo("curp", "CURP (Mexico)",
        "18 alfanumericos; valida genero vs campo 'genero'.", r_curp),
    "rfc": ReglaCatalogo("rfc", "RFC fisica (Mexico)", "13: 4 letras, 6 digitos, 3 alfanum.", r_rfc),
    "entidad_federativa_mx": ReglaCatalogo("entidad_federativa_mx", "Entidad federativa (Mexico)",
        "Estado valido si pais es Mexico.", r_entidad_federativa_mx),
    "pais_valido": ReglaCatalogo("pais_valido", "Pais valido (ISO)",
        "Pais reconocido por nombre, ISO alfa-2/3 o clave numerica.", r_pais_valido),
}


def construir(regla_cfg) -> Regla:
    meta = CATALOGO[regla_cfg.id]
    params = dict(regla_cfg.parametros)
    if regla_cfg.id == "valor_en" and isinstance(params.get("normalizar"), str):
        params["normalizar"] = params["normalizar"].strip().lower() in ("si", "true", "1")
    return meta.constructor(**params)
