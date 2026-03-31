from fuzzywuzzy import fuzz
import re

class Mapper:
    """
    Intenta mapear automáticamente las columnas del archivo con los campos requeridos.
    Utiliza similitud de cadenas y palabras clave.
    """
    
    CAMPOS_REQUERIDOS = [
        "id_cliente", "nombre", "fecha_nacimiento", "genero", "tipo de persona",
        "estatus_cliente", "fecha_inicio_relacion", "fecha_termino_relacion",
        "grado_riesgo", "fecha_riesgo", "PEP", "Nacionalidad", "Pais_nacimiento",
        "entidad_federativa", "Actividad_generica", "Actividad_especifica",
        "Teléfono", "Correo electronico", "CURP", "RFC", "Dirección", "Nivel_cuenta"
    ]
    
    @classmethod
    def map_columns(cls, columnas_archivo):
        """
        columnas_archivo: lista de nombres de columnas del archivo original.
        Retorna un dict {campo_requerido: columna_archivo_o_None}
        """
        mapeo = {}
        columnas_norm = [cls._normalizar(col) for col in columnas_archivo]
        
        for req in cls.CAMPOS_REQUERIDOS:
            req_norm = cls._normalizar(req)
            mejor_match = None
            mejor_score = 0
            for idx, col_norm in enumerate(columnas_norm):
                score = fuzz.ratio(req_norm, col_norm)
                # También considerar si la columna contiene palabras clave del requerido
                palabras_req = set(req_norm.split())
                palabras_col = set(col_norm.split())
                if palabras_req & palabras_col:
                    score += 20  # bonus si comparten palabras
                if score > mejor_score and score > 60:  # umbral mínimo
                    mejor_score = score
                    mejor_match = columnas_archivo[idx]
            mapeo[req] = mejor_match
        return mapeo
    
    @staticmethod
    def _normalizar(texto):
        """Elimina acentos, espacios extras y pasa a minúsculas."""
        texto = texto.lower().strip()
        texto = re.sub(r'[áàäâ]', 'a', texto)
        texto = re.sub(r'[éèëê]', 'e', texto)
        texto = re.sub(r'[íìïî]', 'i', texto)
        texto = re.sub(r'[óòöô]', 'o', texto)
        texto = re.sub(r'[úùüû]', 'u', texto)
        texto = re.sub(r'[^a-z0-9\s]', '', texto)  # eliminar caracteres especiales
        texto = re.sub(r'\s+', ' ', texto)        # espacios múltiples a uno
        return texto