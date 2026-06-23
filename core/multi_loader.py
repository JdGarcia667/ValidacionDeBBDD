"""Carga de múltiples archivos: en memoria (concatenado) o en SQLite por lotes.

Permite validar bases que vienen divididas en varios archivos y, para grandes
volúmenes, almacenarlas en una base SQLite temporal procesada por lotes, sin
mantener todo el conjunto en memoria a la vez.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pandas as pd

from core.io_utils import leer_tabla

TABLA = "datos"
# A partir de este total de filas conviene usar SQLite por lotes.
UMBRAL_FILAS_SQLITE = 500_000
CHUNK_SIZE = 50_000


def _alinear(df: pd.DataFrame, columnas: list[str] | None) -> tuple[pd.DataFrame, list[str]]:
    """Asegura que todos los archivos compartan el mismo orden de columnas."""
    if columnas is None:
        return df, list(df.columns)
    if list(df.columns) != columnas:
        df = df.reindex(columns=columnas, fill_value="")
    return df, columnas


# --------------------------------------------------------------------------- #
# Carga en memoria
# --------------------------------------------------------------------------- #
def leer_varios(paths: list[str]) -> pd.DataFrame:
    """Lee y concatena varios archivos (CSV/Excel) en un único DataFrame."""
    if not paths:
        raise ValueError("No se proporcionaron archivos.")
    dfs: list[pd.DataFrame] = []
    columnas: list[str] | None = None
    for p in paths:
        df, columnas = _alinear(leer_tabla(p), columnas)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


# --------------------------------------------------------------------------- #
# Carga en SQLite (por lotes, un archivo a la vez)
# --------------------------------------------------------------------------- #
def construir_db(paths: list[str], db_path: str | None = None,
                 chunksize: int = CHUNK_SIZE, progreso=None) -> tuple[str, int]:
    """Carga varios archivos en una tabla SQLite temporal (uno a la vez).

    Devuelve (db_path, total_filas). El pico de memoria es el de un solo archivo,
    no el de todos concatenados.
    """
    if not paths:
        raise ValueError("No se proporcionaron archivos.")
    if not db_path:
        fd, db_path = tempfile.mkstemp(suffix=".db", prefix="validacion_")
        os.close(fd)
    conn = sqlite3.connect(db_path)
    try:
        total = 0
        columnas: list[str] | None = None
        for i, p in enumerate(paths):
            if progreso:
                progreso(f"Cargando {os.path.basename(p)} en SQLite...")
            df, columnas = _alinear(leer_tabla(p), columnas)
            total += len(df)
            df.to_sql(TABLA, conn, if_exists="replace" if i == 0 else "append",
                      index=False, chunksize=chunksize)
    finally:
        conn.close()
    return db_path, total


def contar_filas(db_path: str, tabla: str = TABLA) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    finally:
        conn.close()


def leer_muestra(db_path: str, n: int = 100, tabla: str = TABLA) -> pd.DataFrame:
    """Lee las primeras n filas (para la hoja de muestra del reporte)."""
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(f"SELECT * FROM {tabla} LIMIT {int(n)}", conn)
    finally:
        conn.close()


def leer_todo(db_path: str, tabla: str = TABLA) -> pd.DataFrame:
    """Lee la tabla completa (fallback para entidades que no validan por lotes)."""
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(f"SELECT * FROM {tabla}", conn)
    finally:
        conn.close()


def iter_chunks(db_path: str, chunksize: int = CHUNK_SIZE, tabla: str = TABLA):
    """Itera (offset, chunk_df) por lotes, asignando un índice de fila global.

    El índice global permite que los reportes de error apunten a la fila real
    dentro del conjunto completo (no solo dentro del lote).
    """
    conn = sqlite3.connect(db_path)
    try:
        offset = 0
        while True:
            chunk = pd.read_sql_query(
                f"SELECT * FROM {tabla} LIMIT {chunksize} OFFSET {offset}", conn)
            if chunk.empty:
                break
            chunk.index = range(offset, offset + len(chunk))
            yield offset, chunk
            offset += len(chunk)
    finally:
        conn.close()


def eliminar_db(db_path: str | None) -> None:
    """Borra la base SQLite temporal (silencioso si no existe)."""
    try:
        if db_path and os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass
