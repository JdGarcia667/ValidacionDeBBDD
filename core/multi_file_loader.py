import os
import pandas as pd
from core.file_reader import FileReader

class MultiFileLoader:
    @staticmethod
    def load_files(file_paths, use_sqlite=False, sqlite_path=None, chunk_size=50000):
        """
        Carga múltiples archivos y los concatena.
        Si use_sqlite=True, guarda en SQLite y retorna (ruta_db, nombre_tabla, total_filas).
        Si no, retorna (DataFrame, None, total_filas).
        """
        if not file_paths:
            raise ValueError("No se proporcionaron archivos")
        
        total_rows = 0
        
        if use_sqlite:
            import sqlite3
            if not sqlite_path:
                sqlite_path = "temp_validation.db"
            conn = sqlite3.connect(sqlite_path)
            table_name = "datos"
            first = True
            for path in file_paths:
                df = FileReader.read(path)
                total_rows += len(df)
                if first:
                    df.to_sql(table_name, conn, if_exists='replace', index=False, chunksize=chunk_size)
                    first = False
                else:
                    df.to_sql(table_name, conn, if_exists='append', index=False, chunksize=chunk_size)
            conn.close()
            return sqlite_path, table_name, total_rows
        else:
            dfs = []
            for path in file_paths:
                df = FileReader.read(path)
                dfs.append(df)
                total_rows += len(df)
            # Si es demasiado grande, lanzar advertencia (umbral 500k)
            if total_rows > 500000:
                raise MemoryWarning(f"Demasiados registros ({total_rows}). Considere usar SQLite.")
            return pd.concat(dfs, ignore_index=True), None, total_rows