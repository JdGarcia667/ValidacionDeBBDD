"""Validación de clientes por lotes desde SQLite (grandes volúmenes).

Cada lote se valida con el Validator normal SIN su detección de duplicados
(que es global). Los duplicados —IDs repetidos y mismo CURP con distinto
nombre— se calculan sobre todo el conjunto con consultas SQL, de forma que el
resultado coincide con la validación en memoria aunque los registros estén
repartidos en varios lotes.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from core.multi_loader import iter_chunks, leer_muestra, CHUNK_SIZE, TABLA
from core.niveles import validar_requisitos
from core.validator import Validator


def _q(nombre: str) -> str:
    """Cita un identificador SQL (columnas con espacios/acentos)."""
    return '"' + str(nombre).replace('"', '""') + '"'


class SQLiteValidator:
    def __init__(self, db_path, mapeo, tipo_persona_default=None,
                 chunksize=CHUNK_SIZE, progreso=None,
                 requisitos=None, campo_nivel="", campo_tipo_persona="",
                 campo_modalidad="", default_tipo="fisica", validator_config=None):
        self.db_path = db_path
        self.mapeo = mapeo
        self.tipo_persona_default = tipo_persona_default
        self.chunksize = chunksize
        self.progreso = progreso
        # Requisitos por nivel (opcional): se validan por lote (lógica por fila).
        self.requisitos = requisitos
        self.campo_nivel = campo_nivel
        self.campo_tipo_persona = campo_tipo_persona
        self.campo_modalidad = campo_modalidad
        self.default_tipo = default_tipo
        # Parámetros/toggles de Validator (ver core/validator.py DEFAULT_CONFIG).
        self.validator_config = validator_config or {}
        self.checks_deshabilitados = set(self.validator_config.get("checks_deshabilitados") or [])

    # ------------------------------------------------------------------ #
    def validar_todo(self):
        acum: dict[str, list[pd.DataFrame]] = {}
        niveles: list[dict] = []

        # 1) Validaciones por fila / por lote (sin duplicados globales)
        for offset, chunk in iter_chunks(self.db_path, self.chunksize):
            if self.progreso:
                self.progreso(f"Validando clientes (desde fila {offset:,})...")
            errores, _ = Validator(chunk, self.mapeo, self.tipo_persona_default,
                                   config=self.validator_config).validar_todo(
                                       incluir_duplicados=False)
            for cat, df in errores.items():
                if df is not None and not df.empty:
                    acum.setdefault(cat, []).append(df)
            # Requisitos por nivel (lógica por fila -> por lote)
            if self.requisitos and self.campo_nivel:
                niveles += validar_requisitos(
                    chunk, self.mapeo, self.requisitos, campo_nivel=self.campo_nivel,
                    campo_tipo_persona=self.campo_tipo_persona,
                    campo_modalidad=self.campo_modalidad, default_tipo=self.default_tipo)

        resultado = {cat: pd.concat(dfs, ignore_index=True)
                     for cat, dfs in acum.items()}
        if niveles:
            resultado["Requisitos por Nivel"] = pd.DataFrame(niveles)

        # 2) Duplicados globales vía SQL
        if self.progreso:
            self.progreso("Buscando duplicados en todo el conjunto...")
        for cat, df in self._duplicados_globales().items():
            if df is not None and not df.empty:
                resultado[cat] = df

        total = sum(len(df) for df in resultado.values())
        return resultado, total

    # ------------------------------------------------------------------ #
    def _columnas_reales(self):
        """Resuelve los nombres reales de columnas (logico -> columna del archivo)
        reutilizando la normalización del Validator sobre una muestra."""
        muestra = leer_muestra(self.db_path, n=1)
        v = Validator(muestra, self.mapeo, self.tipo_persona_default)
        return v.col_mapping, v._obtener_columnas_base()

    def _duplicados_globales(self) -> dict:
        col_map, base = self._columnas_reales()
        col_id = col_map.get('id_cliente')
        col_nombre = col_map.get('nombre')
        col_curp = col_map.get('CURP')
        col_firma = col_map.get('firma electronica avanzada')
        base_cols = list(dict.fromkeys(base.values()))  # sin repetidos, ordenado

        salida = {}
        deshabilitados = self.checks_deshabilitados
        conn = sqlite3.connect(self.db_path)
        try:
            # IDs duplicados
            if col_id and "ids_duplicados" not in deshabilitados:
                cols = ", ".join(_q(c) for c in base_cols) or _q(col_id)
                q = (f"SELECT {cols} FROM {TABLA} WHERE {_q(col_id)} IN "
                     f"(SELECT {_q(col_id)} FROM {TABLA} "
                     f" GROUP BY {_q(col_id)} HAVING COUNT(*) > 1)")
                df = pd.read_sql_query(q, conn)
                if not df.empty:
                    df['Tipo_Error'] = 'ID duplicado'
                    salida['IDs Duplicados'] = df

            # Mismo CURP con nombre diferente
            if col_nombre and col_curp and "nombres_duplicados_curp" not in deshabilitados:
                cols = ", ".join(_q(c) for c in dict.fromkeys(base_cols + [col_nombre, col_curp]))
                sub = (f"SELECT UPPER(TRIM({_q(col_curp)})) AS k FROM {TABLA} "
                       f"WHERE TRIM({_q(col_curp)}) <> '' "
                       f"  AND LOWER(TRIM({_q(col_curp)})) NOT IN ('nan','none','null') "
                       f"GROUP BY UPPER(TRIM({_q(col_curp)})) "
                       f"HAVING COUNT(DISTINCT LOWER(TRIM({_q(col_nombre)}))) > 1")
                q = (f"SELECT {cols} FROM {TABLA} "
                     f"WHERE UPPER(TRIM({_q(col_curp)})) IN ({sub})")
                df = pd.read_sql_query(q, conn)
                if not df.empty:
                    df['Tipo_Error'] = 'Mismo CURP con nombre diferente'
                    salida['Nombres Duplicados (CURP)'] = df

            # Firma electrónica avanzada duplicada (única por cliente)
            if col_firma and "firmas_duplicadas" not in deshabilitados:
                df = self._duplicados_col_sql(conn, base_cols, col_firma, col_id=col_id)
                if not df.empty:
                    df['Tipo_Error'] = 'Firma electrónica avanzada duplicada'
                    salida['Firmas Duplicadas'] = df

            # CURP asignado a más de un cliente (único)
            if col_curp and "curp_duplicado" not in deshabilitados:
                df = self._duplicados_col_sql(conn, base_cols, col_curp, col_id=col_id, upper=True)
                if not df.empty:
                    df['Tipo_Error'] = 'CURP asignado a más de un cliente'
                    salida['CURPs Duplicados'] = df

            # RFC asignado a más de un cliente (único)
            col_rfc = col_map.get('RFC')
            if col_rfc and "rfc_duplicado" not in deshabilitados:
                df = self._duplicados_col_sql(conn, base_cols, col_rfc, col_id=col_id, upper=True)
                if not df.empty:
                    df['Tipo_Error'] = 'RFC asignado a más de un cliente'
                    salida['RFCs Duplicados'] = df
        finally:
            conn.close()
        return salida

    @staticmethod
    def _duplicados_col_sql(conn, base_cols, col, col_id=None, upper=False):
        """Filas cuyo valor en `col` está en más de un cliente (ignorando vacíos).
        La unicidad es por id_cliente distinto (si se conoce); si no, por fila.
        Si upper, compara sin distinguir mayúsculas."""
        expr = f"UPPER(TRIM({_q(col)}))" if upper else f"TRIM({_q(col)})"
        cols = ", ".join(_q(c) for c in dict.fromkeys(base_cols + [col]))
        valido = (f"TRIM({_q(col)}) <> '' AND "
                  f"LOWER(TRIM({_q(col)})) NOT IN ('nan','none','null')")
        having = (f"COUNT(DISTINCT TRIM({_q(col_id)})) > 1" if col_id else "COUNT(*) > 1")
        q = (f"SELECT {cols} FROM {TABLA} WHERE {valido} AND {expr} IN "
             f"(SELECT {expr} FROM {TABLA} WHERE {valido} "
             f" GROUP BY {expr} HAVING {having})")
        return pd.read_sql_query(q, conn)
