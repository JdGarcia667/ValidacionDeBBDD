from fuzzywuzzy import fuzz
from core.utils import normalizar_texto


class MapperOperaciones:
    """Mapea automáticamente columnas de operaciones con los campos requeridos."""

    CAMPOS_REQUERIDOS = [
        'id_operacion', 'id_cuenta', 'id_cliente', 'monto', 'tipo_operacion',
        'instrumento_monetario', 'fecha_operacion', 'nivel_cuenta'
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
