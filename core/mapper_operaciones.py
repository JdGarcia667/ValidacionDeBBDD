from fuzzywuzzy import fuzz
import re

class MapperOperaciones:
    CAMPOS_REQUERIDOS = [
        'id_operacion', 'id_cuenta', 'id_cliente', 'monto', 'tipo_operacion',
        'instrumento_monetario', 'fecha_operacion', 'nivel_cuenta'
    ]
    
    @classmethod
    def map_columns(cls, columnas_archivo):
        mapeo = {}
        columnas_norm = [cls._normalizar(col) for col in columnas_archivo]
        for req in cls.CAMPOS_REQUERIDOS:
            req_norm = cls._normalizar(req)
            mejor_match = None
            mejor_score = 0
            for idx, col_norm in enumerate(columnas_norm):
                score = fuzz.ratio(req_norm, col_norm)
                palabras_req = set(req_norm.split())
                palabras_col = set(col_norm.split())
                if palabras_req & palabras_col:
                    score += 20
                if score > mejor_score and score > 60:
                    mejor_score = score
                    mejor_match = columnas_archivo[idx]
            mapeo[req] = mejor_match
        return mapeo

    @staticmethod
    def _normalizar(texto):
        texto = texto.lower().strip()
        texto = re.sub(r'[áàäâ]', 'a', texto)
        texto = re.sub(r'[éèëê]', 'e', texto)
        texto = re.sub(r'[íìïî]', 'i', texto)
        texto = re.sub(r'[óòöô]', 'o', texto)
        texto = re.sub(r'[úùüû]', 'u', texto)
        texto = re.sub(r'[^a-z0-9\s]', '', texto)
        texto = re.sub(r'\s+', ' ', texto)
        return texto