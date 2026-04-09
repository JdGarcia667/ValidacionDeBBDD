import pandas as pd
import sqlite3
from core.validator import Validator

class SQLiteValidator:
    def __init__(self, db_path, table_name, mapeo, tipo_persona_default=None, chunksize=50000):
        self.db_path = db_path
        self.table_name = table_name
        self.mapeo = mapeo
        self.tipo_persona_default = tipo_persona_default
        self.chunksize = chunksize

    def validar_todo(self, update_callback=None):
        conn = sqlite3.connect(self.db_path)
        # Obtener total de filas para el progreso
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total_rows = cursor.fetchone()[0]
        conn.close()

        errores_dataframes = {}
        offset = 0
        all_errors = []
        processed = 0

        while True:
            if update_callback:
                update_callback(f"Procesando lote {processed // self.chunksize + 1}...")
            # Leer un lote
            query = f"SELECT * FROM {self.table_name} LIMIT {self.chunksize} OFFSET {offset}"
            chunk = pd.read_sql_query(query, sqlite3.connect(self.db_path))
            if chunk.empty:
                break
            # Ajustar índices de fila
            chunk.index = range(offset, offset + len(chunk))
            # Validar el lote con el validador normal
            validator = Validator(chunk, self.mapeo, self.tipo_persona_default)
            errores_dfs, _ = validator.validar_todo()
            # Recolectar errores con la fila original
            for key, df_err in errores_dfs.items():
                if not df_err.empty:
                    # Ajustar la columna 'fila' si existe
                    if 'fila' in df_err.columns:
                        # La fila ya está en términos del chunk? El validador usa índice +2, pero ya está bien porque el índice es el offset
                        pass
                    all_errors.append(df_err)
            processed += len(chunk)
            offset += self.chunksize

        if all_errors:
            errores_dataframes['Hallazgos'] = pd.concat(all_errors, ignore_index=True)
        return errores_dataframes, len(all_errors)