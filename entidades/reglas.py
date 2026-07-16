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

from core.utils import normalizar_texto, ESTADOS_MEXICANOS_NORM, parsear_fecha
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


# ---------------------- condiciones de aplicacion ---------------------- #
# 'aplica si [campo] [operador] [valor]'. `campo` es el nombre logico de OTRO
# campo de la misma entidad (se resuelve con Contexto.get). Combinables (AND)
# vía ReglaConfig.condiciones; ReglaConfig.condiciones_negar niega el AND
# completo (De Morgan), para expresar "aplica salvo que se cumplan TODAS".
OPERADORES_CONDICION = [
    "=", "!=", "contiene", "no_contiene", "vacio", "no_vacio", "en_lista", "no_en_lista",
]


def _evaluar_condicion(valor, operador: str, referencia: str) -> bool:
    if operador == "vacio":
        return es_vacio(valor)
    if operador == "no_vacio":
        return not es_vacio(valor)
    v = "" if es_vacio(valor) else _norm(valor)
    if operador == "=":
        return v == _norm(referencia)
    if operador == "!=":
        return v != _norm(referencia)
    if operador == "contiene":
        return _norm(referencia) in v
    if operador == "no_contiene":
        return _norm(referencia) not in v
    if operador in ("en_lista", "no_en_lista"):
        opciones = {_norm(o) for o in str(referencia or "").split(",") if o.strip()}
        pertenece = v in opciones
        return pertenece if operador == "en_lista" else not pertenece
    return True


def _condiciones_cumplen(condiciones, ctx: "Contexto") -> bool:
    return all(_evaluar_condicion(ctx.get(c.campo), c.operador, c.valor) for c in condiciones)


def parse_fecha(valor):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return parsear_fecha(valor)


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


def r_fecha_no_futura() -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        fecha = parse_fecha(valor)
        if pd.isna(fecha):
            return None  # cubierto por fecha_valida
        if fecha.date() > date.today():
            return "Fecha futura"
        return None
    return f


def r_fecha_no_anterior_a(campo_referencia: str) -> Regla:
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        fecha = parse_fecha(valor)
        if pd.isna(fecha):
            return None  # cubierto por fecha_valida
        ref = ctx.get(campo_referencia)
        if es_vacio(ref):
            return None
        fecha_ref = parse_fecha(ref)
        if pd.isna(fecha_ref):
            return None
        if fecha < fecha_ref:
            return f"Anterior a '{campo_referencia}'"
        return None
    return f


def r_debe_estar_vacio() -> Regla:
    """Opuesto de 'no_vacio'. Util combinada con una condicion, p. ej. 'fecha de
    termino debe estar vacia si el estatus contiene activo'."""
    def f(valor, ctx):
        return None if es_vacio(valor) else "Debe estar vacio"
    return f


def r_al_menos_uno_de(campos: list = None) -> Regla:
    """Error si el valor propio Y todos los campos listados (otros campos
    logicos, via ctx) estan vacios. Util para pares tipo 'actividad generica /
    actividad especifica' donde basta con que uno de los dos venga lleno."""
    campos = campos or []
    def f(valor, ctx):
        if not es_vacio(valor):
            return None
        if all(es_vacio(ctx.get(c)) for c in campos):
            return "Vacio: se requiere al menos uno de (" + ", ".join(campos) + ")"
        return None
    return f


def r_direccion_completa(campos_obligatorios: list = None,
                          campos_ciudad_alcaldia: list = None) -> Regla:
    """Domicilio dividido en varias columnas: exige que el campo propio y cada
    uno de `campos_obligatorios` (otros campos logicos, via ctx) esten llenos;
    si se listan `campos_ciudad_alcaldia`, exige que al menos uno de ellos
    tambien lo este (p. ej. ciudad O alcaldia/municipio)."""
    campos_obligatorios = campos_obligatorios or []
    campos_ciudad_alcaldia = campos_ciudad_alcaldia or []
    def f(valor, ctx):
        problemas = []
        if es_vacio(valor):
            problemas.append("este campo")
        for c in campos_obligatorios:
            if es_vacio(ctx.get(c)):
                problemas.append(c)
        if campos_ciudad_alcaldia and all(es_vacio(ctx.get(c)) for c in campos_ciudad_alcaldia):
            problemas.append("uno de (" + ", ".join(campos_ciudad_alcaldia) + ")")
        if problemas:
            return "Domicilio incompleto, falta: " + ", ".join(problemas)
        return None
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


def r_rfc(tipo_persona: str = "fisica") -> Regla:
    """RFC fisica (13: 4 letras) o moral (12: 3 letras). Sin parametro se
    comporta igual que antes (fisica), retrocompatible con configs guardadas."""
    moral = str(tipo_persona).strip().lower() == "moral"
    longitud = 12 if moral else 13
    n_letras = 3 if moral else 4
    fin_fecha = n_letras + 6
    def f(valor, ctx):
        rfc = str(valor).strip().upper()
        if rfc in ("NAN", "", "NONE", "NULL"):
            return "RFC faltante"
        errores = []
        if len(rfc) != longitud:
            errores.append(f"Longitud incorrecta: {len(rfc)} caracteres (esperado {longitud})")
        if len(rfc) >= n_letras and not re.match(r"^[A-Z]{%d}" % n_letras, rfc):
            errores.append(f"Primeros {n_letras} caracteres no son letras")
        if len(rfc) >= fin_fecha and not re.match(r"^[0-9]{6}$", rfc[n_letras:fin_fecha]):
            errores.append("Los 6 caracteres de la fecha no son numeros")
        if len(rfc) == longitud and not re.match(r"^[A-Z0-9]{3}$", rfc[fin_fecha:]):
            errores.append("Ultimos 3 caracteres (homoclave) no son alfanumericos")
        return "; ".join(errores) if errores else None
    return f


# Variantes de país que se consideran México (normalizadas).
_VARIANTES_MX = {normalizar_texto(v).upper() for v in ("Mexico", "Mexicana", "Mex", "MX")}


def r_entidad_federativa_mx() -> Regla:
    def f(valor, ctx):
        pais = ctx.get("pais_nacimiento") or ctx.get("Pais_nacimiento")
        extranjero = not es_vacio(pais) and normalizar_texto(str(pais)).upper() not in _VARIANTES_MX
        # No aplica a extranjeros: ni se exige llena ni se valida el estado.
        if extranjero:
            return None
        if es_vacio(valor):
            return "Entidad federativa vacia"
        if normalizar_texto(str(valor)).upper() not in ESTADOS_MEXICANOS_NORM:
            return f"Entidad '{valor}' no valida para Mexico"
        return None
    return f


def r_consistencia_nacimiento(campo_pais: str = "", campo_nacionalidad: str = "") -> Regla:
    """Si el valor propio es un estado mexicano valido pero el pais y/o la
    nacionalidad (otros campos logicos, via ctx) indican que NO es Mexico,
    marca una inconsistencia. Deja `campo_pais`/`campo_nacionalidad` vacios
    para omitir esa comparacion."""
    def f(valor, ctx):
        if es_vacio(valor):
            return None
        if normalizar_texto(str(valor)).upper() not in ESTADOS_MEXICANOS_NORM:
            return None
        problemas = []
        if campo_pais:
            pais = ctx.get(campo_pais)
            if not es_vacio(pais) and normalizar_texto(str(pais)).upper() not in _VARIANTES_MX:
                problemas.append(f"pais '{pais}' no es Mexico")
        if campo_nacionalidad:
            nac = ctx.get(campo_nacionalidad)
            if not es_vacio(nac) and normalizar_texto(str(nac)).upper() not in _VARIANTES_MX:
                problemas.append(f"nacionalidad '{nac}' no es Mexico")
        if problemas:
            return "Inconsistencia con entidad federativa mexicana: " + "; ".join(problemas)
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
    "fecha_no_futura": ReglaCatalogo("fecha_no_futura", "Fecha no futura",
        "Rechaza fechas posteriores a hoy.", r_fecha_no_futura),
    "fecha_no_anterior_a": ReglaCatalogo("fecha_no_anterior_a", "Fecha no anterior a otro campo",
        "Compara contra otra fecha de la misma fila (p. ej. termino >= inicio).",
        r_fecha_no_anterior_a,
        parametros=[Parametro("campo_referencia", "str", "Campo logico de referencia", "")]),
    "debe_estar_vacio": ReglaCatalogo("debe_estar_vacio", "Debe estar vacio",
        "Opuesto de 'No vacio'; util junto con una condicion.", r_debe_estar_vacio),
    "al_menos_uno_de": ReglaCatalogo("al_menos_uno_de", "Al menos uno de (varios campos)",
        "Error solo si este campo Y todos los listados estan vacios.",
        r_al_menos_uno_de, parametros=[Parametro("campos", "lista", "Otros campos logicos (coma)", [])]),
    "direccion_completa": ReglaCatalogo("direccion_completa", "Direccion dividida en columnas",
        "Exige campos obligatorios y, opcional, 'al menos uno de' (ciudad o alcaldia).",
        r_direccion_completa,
        parametros=[Parametro("campos_obligatorios", "lista", "Campos obligatorios (coma)", []),
                    Parametro("campos_ciudad_alcaldia", "lista",
                              "Ciudad/alcaldia: al menos uno (coma, opcional)", [])]),
    "valor_en": ReglaCatalogo("valor_en", "Valor en lista", "Pertenece a un conjunto.",
        r_valor_en, parametros=[Parametro("opciones", "lista", "Opciones (coma)", []),
                                Parametro("normalizar", "str", "Normalizar (si/no)", "si")]),
    "curp": ReglaCatalogo("curp", "CURP (Mexico)",
        "18 alfanumericos; valida genero vs campo 'genero'.", r_curp),
    "rfc": ReglaCatalogo("rfc", "RFC (Mexico)",
        "13 (fisica, 4 letras) o 12 (moral, 3 letras); 6 digitos, homoclave.",
        r_rfc, parametros=[Parametro("tipo_persona", "str", "Tipo (fisica/moral)", "fisica")]),
    "entidad_federativa_mx": ReglaCatalogo("entidad_federativa_mx", "Entidad federativa (Mexico)",
        "Estado valido si pais es Mexico.", r_entidad_federativa_mx),
    "consistencia_nacimiento": ReglaCatalogo("consistencia_nacimiento",
        "Consistencia entidad/pais/nacionalidad",
        "Si el campo es un estado mexicano valido, exige que pais y/o "
        "nacionalidad (otros campos) tambien indiquen Mexico.",
        r_consistencia_nacimiento,
        parametros=[Parametro("campo_pais", "str", "Campo logico de pais (opcional)", ""),
                    Parametro("campo_nacionalidad", "str",
                              "Campo logico de nacionalidad (opcional)", "")]),
    "pais_valido": ReglaCatalogo("pais_valido", "Pais valido (ISO)",
        "Pais reconocido por nombre, ISO alfa-2/3 o clave numerica.", r_pais_valido),
    "mismo_valor_en": ReglaCatalogo("mismo_valor_en", "Mismo valor en (consistencia)",
        "Filas que comparten valor en este campo deben compartir el mismo "
        "valor en el campo de referencia (p. ej. mismo CURP -> mismo nombre).",
        lambda: None, ambito="relacion",
        parametros=[Parametro("campo_referencia", "str", "Campo logico de referencia", "")]),
}


def construir(regla_cfg) -> Regla:
    meta = CATALOGO[regla_cfg.id]
    params = dict(regla_cfg.parametros)
    if regla_cfg.id == "valor_en" and isinstance(params.get("normalizar"), str):
        params["normalizar"] = params["normalizar"].strip().lower() in ("si", "true", "1")
    fn = meta.constructor(**params)
    condiciones = getattr(regla_cfg, "condiciones", None)
    if not condiciones:
        return fn
    negar = getattr(regla_cfg, "condiciones_negar", False)

    def f(valor, ctx, _fn=fn, _cond=condiciones, _neg=negar):
        cumple = _condiciones_cumplen(_cond, ctx)
        if _neg:
            cumple = not cumple
        if not cumple:
            return None
        return _fn(valor, ctx)
    return f
