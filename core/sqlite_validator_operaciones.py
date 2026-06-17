import logging
import sqlite3

import pandas as pd

from core.utils import validar_nombre_tabla
from core.validator_operaciones import ValidatorOperaciones

logger = logging.getLogger(__name__)


class SQLiteValidatorOperaciones:
    def __init__(self, db_path: str, table_name: str, mapeo: dict, config: dict, chunksize: int = 50000):
        self.db_path = db_path
        # validar_nombre_tabla lanza ValueError si el nombre tiene caracteres inseguros
        self.table_name = validar_nombre_tabla(table_name)
        self.mapeo = mapeo
        self.config = config
        self.chunksize = chunksize

    def validar_todo(self, update_callback=None) -> tuple[dict, int]:
        with sqlite3.connect(self.db_path) as conn:
            total_rows = conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]

        logger.info("Iniciando validación operaciones SQLite: %d filas en tabla '%s'", total_rows, self.table_name)

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
            validator = ValidatorOperaciones(chunk, self.mapeo, self.config, update_callback)
            errores_dfs, _ = validator.validar_todo()
            for df_err in errores_dfs.values():
                if not df_err.empty:
                    all_errors.append(df_err)

            processed += len(chunk)
            offset += self.chunksize

        if all_errors:
            logger.info("Validación operaciones completada: %d lotes, %d hallazgos", lote_num, len(all_errors))
            return {'Operaciones con excesos': pd.concat(all_errors, ignore_index=True)}, len(all_errors)

        logger.info("Validación operaciones completada: sin hallazgos")
        return {}, 0
