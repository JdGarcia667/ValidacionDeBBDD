"""Validación de operaciones por lotes desde SQLite (grandes volúmenes).

La agrupación de operaciones es GLOBAL (por cuenta/mes/instrumento), así que no
basta con validar cada lote por separado: se agrupa cada lote y luego se vuelven
a sumar los grupos sobre todo el conjunto antes de aplicar los filtros. Así los
totales coinciden con los de la validación en memoria aunque un mismo grupo
quede partido entre varios lotes.
"""
from __future__ import annotations

import pandas as pd

from core.multi_loader import iter_chunks, CHUNK_SIZE
from core.limites_operaciones import LimitesOperaciones, reagregar
from core.validator_operaciones import ValidatorOperaciones


class SQLiteValidatorOperaciones:
    def __init__(self, db_path, mapeo, config, chunksize=CHUNK_SIZE, progreso=None,
                 limites_kwargs=None):
        self.db_path = db_path
        self.mapeo = mapeo
        self.config = config
        self.chunksize = chunksize
        self.progreso = progreso
        # Configuración opcional de límites de operación (montos por nivel).
        self.limites_kwargs = limites_kwargs

    def validar_todo(self):
        parciales: list[pd.DataFrame] = []
        group_cols: list | None = None
        # Límites de operación: se agrupan por lote y se re-agregan al final.
        lim = (LimitesOperaciones(pd.DataFrame(), self.mapeo, **self.limites_kwargs)
               if self.limites_kwargs else None)
        parc_abonos: list[pd.DataFrame] = []
        parc_efectivo_usd: list[pd.DataFrame] = []
        parc_efectivo_mxn: list[pd.DataFrame] = []
        # Hallazgos individuales (no se agregan): se concatenan lote a lote.
        parc_individuales: dict[str, list[pd.DataFrame]] = {}

        for offset, chunk in iter_chunks(self.db_path, self.chunksize):
            if self.progreso:
                self.progreso(f"Agrupando operaciones (desde fila {offset:,})...")
            grouped, gc = ValidatorOperaciones(chunk, self.mapeo, self.config).agrupar()
            if grouped is not None and not grouped.empty:
                parciales.append(grouped)
                group_cols = gc
            if lim is not None:
                lim.df = chunk
                ga, ge_usd, ge_mxn = lim.agrupar()
                if ga is not None and not ga.empty:
                    parc_abonos.append(ga)
                if ge_usd is not None and not ge_usd.empty:
                    parc_efectivo_usd.append(ge_usd)
                if ge_mxn is not None and not ge_mxn.empty:
                    parc_efectivo_mxn.append(ge_mxn)
                for nombre, df_hallazgos in lim.individuales().items():
                    parc_individuales.setdefault(nombre, []).append(df_hallazgos)

        # Límites (abonos UDIS / efectivo USD y MXN) re-agregados sobre todos los lotes.
        resultado_limites = {}
        if lim is not None:
            g_ab, g_ef_usd, g_ef_mxn = reagregar(parc_abonos, parc_efectivo_usd, parc_efectivo_mxn)
            resultado_limites = lim.aplicar_limites(g_ab, g_ef_usd, g_ef_mxn)
            for nombre, partes in parc_individuales.items():
                resultado_limites[nombre] = pd.concat(partes, ignore_index=True)

        if not parciales or not group_cols:
            if resultado_limites:
                return resultado_limites, sum(len(v) for v in resultado_limites.values())
            return {}, 0

        # Re-agregación global: sumar los grupos parciales de cada lote.
        total = pd.concat(parciales, ignore_index=True)
        if self.progreso:
            self.progreso("Consolidando grupos de todos los lotes...")

        global_grouped = total.groupby(group_cols, dropna=False).agg(
            total_monto=('total_monto', 'sum'),
            cantidad_operaciones=('cantidad_operaciones', 'sum'),
            monto_pesos=('monto_pesos', 'sum'),
        ).reset_index()

        # id_cliente es informativo: tomar el primero por grupo si está presente.
        if 'id_cliente' in total.columns:
            id_cli = (total.groupby(group_cols, dropna=False)['id_cliente']
                      .first().reset_index())
            global_grouped = global_grouped.merge(id_cli, on=group_cols, how='left')

        # Reutiliza la misma lógica de filtros que la validación en memoria.
        errores, total_err = ValidatorOperaciones(
            pd.DataFrame(), self.mapeo, self.config, self.progreso).aplicar_filtros(global_grouped)
        errores.update(resultado_limites)
        return errores, total_err + sum(len(v) for v in resultado_limites.values())
