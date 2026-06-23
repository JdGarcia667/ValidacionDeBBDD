import re

# Constantes de validación
TELEFONO_MIN_DIGITOS = 10
DIRECCION_MIN_SEPARADORES = 5
# Años de dos dígitos <= este valor se interpretan como 2000+, el resto como 1900+
YEAR_CORTE_SIGLO = 50

ESTADOS_MEXICANOS = [
    'Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche', 'Coahuila',
    'Colima', 'Chiapas', 'Chihuahua', 'Ciudad de México', 'Durango', 'Guanajuato',
    'Guerrero', 'Hidalgo', 'Jalisco', 'México', 'Michoacán', 'Morelos', 'Nayarit',
    'Nuevo León', 'Oaxaca', 'Puebla', 'Querétaro', 'Quintana Roo', 'San Luis Potosí',
    'Sinaloa', 'Sonora', 'Tabasco', 'Tamaulipas', 'Tlaxcala', 'Veracruz', 'Yucatán',
    'Zacatecas', 'CDMX',
]


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


# Set normalizado listo para comparación — se construye una vez al importar el módulo
ESTADOS_MEXICANOS_NORM: set[str] = {normalizar_texto(e).upper() for e in ESTADOS_MEXICANOS}
