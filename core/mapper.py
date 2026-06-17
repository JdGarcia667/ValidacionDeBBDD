from fuzzywuzzy import fuzz
from core.utils import normalizar_texto


class Mapper:
    """Mapea automáticamente columnas del archivo con los campos requeridos usando similitud de cadenas."""

    CAMPOS_REQUERIDOS = [
        "id_cliente", "nombre", "fecha_nacimiento", "genero", "tipo de persona",
        "estatus_cliente", "fecha_inicio_relacion", "fecha_termino_relacion",
        "grado_riesgo", "fecha_riesgo", "PEP", "Nacionalidad", "Pais_nacimiento",
        "entidad_federativa", "Actividad_generica", "Actividad_especifica",
        "Teléfono", "Correo electronico", "CURP", "RFC", "Dirección", "Nivel_cuenta"
    ]

    @classmethod
    def map_columns(cls, columnas_archivo: list[str]) -> dict[str, str | None]:
        """Retorna un dict {campo_requerido: columna_archivo_o_None}."""
        mapeo = {}
        columnas_norm = [normalizar_texto(col) for col in columnas_archivo]

        for req in cls.CAMPOS_REQUERIDOS:
            req_norm = normalizar_texto(req)
            mejor_match = None
            mejor_score = 0
            palabras_req = set(req_norm.split())
            for idx, col_norm in enumerate(columnas_norm):
                score = fuzz.ratio(req_norm, col_norm)
                if palabras_req & set(col_norm.split()):
                    score += 20
                if score > mejor_score and score > 60:
                    mejor_score = score
                    mejor_match = columnas_archivo[idx]
            mapeo[req] = mejor_match
        return mapeo
