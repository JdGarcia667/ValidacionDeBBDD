import pandas as pd
import sqlite3
from core.validator_operaciones import ValidatorOperaciones

class SQLiteValidatorOperaciones:
    def __init__(self, db_path, table_name, mapeo, config, chunksize=50000):
        self.db_path = db_path
        self.table_name = table_name
        self.mapeo = mapeo
        self.config = config
        self.chunksize = chunksize

    def validar_todo(self, update_callback=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total_rows = cursor.fetchone()[0]
        conn.close()

        all_errors = []
        offset = 0
        processed = 0

        while True:
            if update_callback:
                update_callback(f"Procesando lote {processed // self.chunksize + 1}...")
            query = f"SELECT * FROM {self.table_name} LIMIT {self.chunksize} OFFSET {offset}"
            chunk = pd.read_sql_query(query, sqlite3.connect(self.db_path))
            if chunk.empty:
                break
            # Ajustar índices
            chunk.index = range(offset, offset + len(chunk))
            # Usar el validador normal de operaciones (funciona por lotes)
            validator = ValidatorOperaciones(chunk, self.mapeo, self.config, update_callback)
            errores_dfs, _ = validator.validar_todo()
            for key, df_err in errores_dfs.items():
                if not df_err.empty:
                    all_errors.append(df_err)
            processed += len(chunk)
            offset += self.chunksize

        if all_errors:
            return {'Operaciones con excesos': pd.concat(all_errors, ignore_index=True)}, len(all_errors)
        return {}, 0