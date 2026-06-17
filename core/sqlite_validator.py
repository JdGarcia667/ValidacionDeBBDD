import logging
import sqlite3

import pandas as pd

from core.utils import validar_nombre_tabla
from core.validator import Validator

logger = logging.getLogger(__name__)


class SQLiteValidator:
    def __init__(self, db_path: str, table_name: str, mapeo: dict,
                 tipo_persona_default: str | None = None, chunksize: int = 50000):
        self.db_path = db_path
        # validar_nombre_tabla lanza ValueError si el nombre tiene caracteres inseguros
        self.table_name = validar_nombre_tabla(table_name)
        self.mapeo = mapeo
        self.tipo_persona_default = tipo_persona_default
        self.chunksize = chunksize

    def validar_todo(self, update_callback=None) -> tuple[dict, int]:
        with sqlite3.connect(self.db_path) as conn:
            total_rows = conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

        logger.info("Iniciando validación SQLite: %d filas en tabla '%s'", total_rows, self.table_name)

        all_errors = []
        offset = 0
        processed = 0
        lote_num = 0

        while True:
            lote_num = processed // self.chunksize + 1
            if update_callback:
                update_callback(f"Procesando lote {lote_num}...")
            logger.debug("Lote %d — offset %d", lote_num, offset)

            with sqlite3.connect(self.db_path) as conn:
                chunk = pd.read_sql_query(
                    f"SELECT * FROM {self.table_name} LIMIT {self.chunksize} OFFSET {offset}",
                    conn,
                )
            if chunk.empty:
                break

            chunk.index = range(offset, offset + len(chunk))
            validator = Validator(chunk, self.mapeo, self.tipo_persona_default)
            errores_dfs, _ = validator.validar_todo()
            for df_err in errores_dfs.values():
                if not df_err.empty:
                    all_errors.append(df_err)

            processed += len(chunk)
            offset += self.chunksize

        errores_dataframes = {}
        if all_errors:
            errores_dataframes['Hallazgos'] = pd.concat(all_errors, ignore_index=True)

        logger.info("Validación SQLite completada: %d lotes procesados", lote_num)
        return errores_dataframes, len(all_errors)
