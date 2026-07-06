import re

import pandas as pd

# Constantes de validación
TELEFONO_MIN_DIGITOS = 10
DIRECCION_MIN_SEPARADORES = 6
# Años de dos dígitos <= este valor se interpretan como 2000+, el resto como 1900+
YEAR_CORTE_SIGLO = 50

# Texto en formato ISO ('YYYY-MM-DD', con o sin hora) no es ambiguo: siempre es
# año-mes-día. dateutil/pandas con dayfirst=True puede, sin embargo, intercambiar
# mes y día incluso en fechas ISO cuando ambos valores son <=12 (p. ej.
# '2026-01-10' -> 10 de octubre en vez de 10 de enero). `parsear_fecha` evita
# ese intercambio detectando el formato ISO y parseándolo sin dayfirst.
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}([ t]|$)", re.IGNORECASE)


def parsear_fecha(valor, dayfirst: bool = True):
    """Convierte a fecha(s) sin la ambigüedad de 'dayfirst' en texto ISO.

    Acepta tanto un valor escalar (celda) como una Series/columna completa.
    Texto ISO ('YYYY-MM-DD...') se interpreta siempre año-mes-día; el resto de
    los formatos de texto (p. ej. 'DD/MM/YYYY') respeta `dayfirst` igual que
    antes. Valores que no son texto (Timestamp, datetime, NaN, ya parseados
    por pandas al leer Excel) se pasan directo a `pd.to_datetime`, donde
    `dayfirst` no aplica."""
    if isinstance(valor, pd.Series):
        if pd.api.types.is_datetime64_any_dtype(valor):
            return pd.to_datetime(valor, errors="coerce")
        texto = valor.astype(str).str.strip()
        iso = texto.str.match(_FECHA_ISO_RE)
        # format="mixed": sin esto, pandas infiere UN solo formato para toda la
        # columna a partir del primer valor y vuelve NaT cualquier fila que no
        # calce con ese formato (columnas con fechas en más de un formato
        # quedarían casi vacías). Con "mixed" cada valor se parsea por separado.
        sin_ambiguedad = pd.to_datetime(texto, errors="coerce", dayfirst=False, format="mixed")
        con_dayfirst = pd.to_datetime(texto, errors="coerce", dayfirst=dayfirst, format="mixed")
        return sin_ambiguedad.where(iso, con_dayfirst)
    if isinstance(valor, str):
        texto = valor.strip()
        if _FECHA_ISO_RE.match(texto):
            return pd.to_datetime(texto, errors="coerce", dayfirst=False)
        return pd.to_datetime(texto, errors="coerce", dayfirst=dayfirst)
    return pd.to_datetime(valor, errors="coerce")

def normalizar_texto(texto: str) -> str:
    """Elimina acentos, caracteres especiales y espacios extras; pasa a minúsculas."""
    if not isinstance(texto, str):
        return ""
    texto = texto.lower().strip()
    texto = re.sub(r'[áàäâ]', 'a', texto)
    texto = re.sub(r'[éèëê]', 'e', texto)
    texto = re.sub(r'[íìïî]', 'i', texto)
    texto = re.sub(r'[óòöô]', 'o', texto)
    texto = re.sub(r'[úùüû]', 'u', texto)
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto


def validar_nombre_tabla(nombre: str) -> str:
    """Valida que el nombre de tabla SQLite solo contenga caracteres seguros y lo retorna.

    Previene inyección SQL cuando el nombre se interpola en queries.
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', nombre):
        raise ValueError(f"Nombre de tabla inválido: '{nombre}'")
    return nombre


# --------------------------------------------------------------------------- #
# Catálogo de entidades federativas de México.
# Cada entrada: (nombre oficial, ISO 3166-2 sin 'MX-', clave CNBV, alias extra).
# Del catálogo se deriva el conjunto normalizado que acepta, para una misma
# entidad: nombre oficial, ISO (con y sin 'MX-'), clave CNBV (con y sin cero
# inicial) y variantes comunes.
# --------------------------------------------------------------------------- #
_ESTADOS_MX = [
    ("Aguascalientes", "AGU", "01", []),
    ("Baja California", "BCN", "02", ["BC"]),
    ("Baja California Sur", "BCS", "03", []),
    ("Campeche", "CAM", "04", []),
    ("Coahuila de Zaragoza", "COA", "05", ["Coahuila"]),
    ("Colima", "COL", "06", []),
    ("Chiapas", "CHP", "07", []),
    ("Chihuahua", "CHH", "08", []),
    ("Ciudad de México", "CMX", "09", ["CDMX", "Distrito Federal", "DF"]),
    ("Durango", "DUR", "10", []),
    ("Guanajuato", "GUA", "11", []),
    ("Guerrero", "GRO", "12", []),
    ("Hidalgo", "HID", "13", []),
    ("Jalisco", "JAL", "14", []),
    ("Estado de México", "MEX", "15", ["México", "Edo de México", "Edo. México"]),
    ("Michoacán de Ocampo", "MIC", "16", ["Michoacán"]),
    ("Morelos", "MOR", "17", []),
    ("Nayarit", "NAY", "18", []),
    ("Nuevo León", "NLE", "19", []),
    ("Oaxaca", "OAX", "20", []),
    ("Puebla", "PUE", "21", []),
    ("Querétaro", "QUE", "22", []),
    ("Quintana Roo", "ROO", "23", []),
    ("San Luis Potosí", "SLP", "24", []),
    ("Sinaloa", "SIN", "25", []),
    ("Sonora", "SON", "26", []),
    ("Tabasco", "TAB", "27", []),
    ("Tamaulipas", "TAM", "28", []),
    ("Tlaxcala", "TLA", "29", []),
    ("Veracruz de Ignacio de la Llave", "VER", "30", ["Veracruz"]),
    ("Yucatán", "YUC", "31", []),
    ("Zacatecas", "ZAC", "32", []),
]


def _aliases_estado(nombre, iso3, cnbv, extra):
    alias = [nombre, iso3, f"MX-{iso3}", cnbv, *extra]
    if cnbv.startswith("0"):            # admite la clave CNBV sin cero inicial
        alias.append(cnbv.lstrip("0"))
    return alias


# Nombres oficiales (compatibilidad) y conjunto normalizado de todas las variantes.
ESTADOS_MEXICANOS = [nombre for nombre, *_ in _ESTADOS_MX]
ESTADOS_MEXICANOS_NORM: set[str] = set()
_ESTADO_CANONICO: dict[str, str] = {}   # variante normalizada -> nombre oficial
for _nombre, _iso, _cnbv, _extra in _ESTADOS_MX:
    for _a in _aliases_estado(_nombre, _iso, _cnbv, _extra):
        _n = normalizar_texto(_a).upper()
        if _n:
            ESTADOS_MEXICANOS_NORM.add(_n)
            _ESTADO_CANONICO.setdefault(_n, _nombre)


def canonizar_estado(valor) -> str | None:
    """Devuelve el nombre oficial del estado a partir de cualquier variante
    (nombre, ISO con/sin 'MX-', clave CNBV, alias), o None si no se reconoce."""
    return _ESTADO_CANONICO.get(normalizar_texto(str(valor)).upper())
