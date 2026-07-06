"""
Entidad CONFIGURABLE: motor de reglas para las entidades que crea el usuario.
Implementa la misma interfaz que el Banco y devuelve {categoria: DataFrame} para que
el reporte funcione igual.

Soporta validación por lotes desde SQLite (grandes volúmenes): las reglas de
VALOR son por fila (se aplican lote por lote) y la regla de columna 'unico'
(duplicados) es global, así que se calcula con SQL sobre toda la tabla.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from .base import ValidadorEntidad
from .modelo import EntidadConfig, CampoConfig
from .reglas import CATALOGO, Contexto, construir

COLS = ["fila", "id", "campo", "columna", "valor", "Tipo_Error"]


def _q(nombre: str) -> str:
    """Cita un identificador SQL (columnas con espacios/acentos)."""
    return '"' + str(nombre).replace('"', '""') + '"'


def _tiene_unico(campo: CampoConfig) -> bool:
    return any(CATALOGO[r.id].ambito == "columna" and r.id == "unico"
               for r in campo.reglas)


class EntidadConfigurable(ValidadorEntidad):
    requiere_tipo_persona = False
    requiere_config_operaciones = False

    def __init__(self, config: EntidadConfig):
        self.config = config
        self.nombre = config.nombre
        self.descripcion = config.descripcion
        self.es_builtin = False

    def campos_cliente(self) -> list[str]:
        return [c.logico for c in self.config.campos_cliente]

    def campos_operacion(self) -> list[str]:
        return [c.logico for c in self.config.campos_operacion]

    def tiene_limites_operacion(self) -> bool:
        return bool(self.config.limites_operacion)

    # ------------------------------------------------------------------ #
    # Validación en memoria
    # ------------------------------------------------------------------ #
    def validar_clientes(self, df, mapeo, tipo_persona_default=None) -> dict:
        return self._validar(df, mapeo, self.config.campos_cliente, "id_cliente")

    def validar_operaciones(self, df, mapeo, config=None) -> dict:
        res = self._validar(df, mapeo, self.config.campos_operacion, "id_operacion")
        res.update(self._limites_memoria(df, mapeo, config or {}))
        return res

    # ------------------------------------------------------------------ #
    # Validación por lotes desde SQLite (mismo resultado, sin cargar todo)
    # ------------------------------------------------------------------ #
    def validar_clientes_sqlite(self, db_path, mapeo, tipo_persona_default=None,
                                progreso=None) -> dict:
        return self._validar_sqlite(db_path, mapeo, self.config.campos_cliente,
                                    "id_cliente", progreso)

    def validar_operaciones_sqlite(self, db_path, mapeo, config=None,
                                   progreso=None) -> dict:
        res = self._validar_sqlite(db_path, mapeo, self.config.campos_operacion,
                                   "id_operacion", progreso)
        res.update(self._limites_sqlite(db_path, mapeo, config or {}, progreso))
        return res

    # ------------------------------------------------------------------ #
    # Límites de operación por nivel (montos)
    # ------------------------------------------------------------------ #
    def _limites_validador(self, df, mapeo, config):
        """Construye el validador de límites si la entidad los define; si no, None."""
        if not self.config.limites_operacion or not self.config.op_campos:
            return None
        from core.limites_operaciones import LimitesOperaciones
        from core.niveles import construir_aliases_nivel
        return LimitesOperaciones(
            df, mapeo, self.config.limites_operacion, campos=self.config.op_campos,
            valores_abono=self.config.op_valores_abono,
            valores_efectivo=self.config.op_valores_efectivo,
            archivo_udis=config.get("archivo_udis"), mapeo_udis=config.get("mapeo_udis"),
            archivo_tc=config.get("archivo_tc"), mapeo_tc=config.get("mapeo_tc"),
            aliases_nivel=construir_aliases_nivel(self.config.aliases_nivel))

    def _limites_memoria(self, df, mapeo, config) -> dict:
        lim = self._limites_validador(df, mapeo, config)
        return lim.validar() if lim is not None else {}

    def _limites_sqlite(self, db_path, mapeo, config, progreso) -> dict:
        lim = self._limites_validador(None, mapeo, config)
        if lim is None:
            return {}
        from core.multi_loader import iter_chunks
        from core.limites_operaciones import reagregar
        parc_ab, parc_ef_usd, parc_ef_mxn = [], [], []
        parc_individuales: dict[str, list[pd.DataFrame]] = {}
        for offset, chunk in iter_chunks(db_path):
            if progreso:
                progreso(f"Límites de operación (desde fila {offset:,})...")
            lim.df = chunk
            ga, ge_usd, ge_mxn = lim.agrupar()
            if ga is not None and not ga.empty:
                parc_ab.append(ga)
            if ge_usd is not None and not ge_usd.empty:
                parc_ef_usd.append(ge_usd)
            if ge_mxn is not None and not ge_mxn.empty:
                parc_ef_mxn.append(ge_mxn)
            for nombre, df_hallazgos in lim.individuales().items():
                parc_individuales.setdefault(nombre, []).append(df_hallazgos)
        g_ab, g_ef_usd, g_ef_mxn = reagregar(parc_ab, parc_ef_usd, parc_ef_mxn)
        resultado = lim.aplicar_limites(g_ab, g_ef_usd, g_ef_mxn)
        for nombre, partes in parc_individuales.items():
            resultado[nombre] = pd.concat(partes, ignore_index=True)
        return resultado

    # ------------------------------------------------------------------ #
    def _validar(self, df, mapeo, campos: list[CampoConfig], id_logico) -> dict:
        if df is None or df.empty or not campos:
            return {}
        id_col = mapeo.get(id_logico)
        hallazgos: list[dict] = []
        hallazgos += self._faltantes(df, mapeo, campos)
        hallazgos += self._hallazgos_valor(df, mapeo, campos, id_col)
        hallazgos += self._hallazgos_unico_memoria(df, mapeo, campos, id_col)
        if id_logico == "id_cliente":
            hallazgos += self._hallazgos_niveles(df, mapeo)
        if not hallazgos:
            return {}
        return {"Hallazgos": pd.DataFrame(hallazgos, columns=COLS)}

    def _validar_sqlite(self, db_path, mapeo, campos: list[CampoConfig],
                        id_logico, progreso=None) -> dict:
        from core.multi_loader import iter_chunks, leer_muestra
        if not campos:
            return {}
        id_col = mapeo.get(id_logico)
        hallazgos: list[dict] = []
        # Columnas no encontradas: basta comprobarlo una vez (sobre una muestra).
        hallazgos += self._faltantes(leer_muestra(db_path, n=1), mapeo, campos)
        # Reglas de valor (y requisitos por nivel): por lotes.
        for offset, chunk in iter_chunks(db_path):
            if progreso:
                progreso(f"Validando '{self.nombre}' (desde fila {offset:,})...")
            hallazgos += self._hallazgos_valor(chunk, mapeo, campos, id_col)
            if id_logico == "id_cliente":
                hallazgos += self._hallazgos_niveles(chunk, mapeo)
        # Duplicados ('unico'): global, vía SQL.
        if any(_tiene_unico(c) for c in campos):
            if progreso:
                progreso("Buscando duplicados en todo el conjunto...")
            hallazgos += self._duplicados_sqlite(db_path, mapeo, campos, id_col)
        if not hallazgos:
            return {}
        return {"Hallazgos": pd.DataFrame(hallazgos, columns=COLS)}

    # --- piezas reutilizables --- #
    def _faltantes(self, df, mapeo, campos) -> list[dict]:
        out = []
        for campo in campos:
            col = mapeo.get(campo.logico)
            if campo.reglas and (col is None or col not in df.columns):
                out.append(_h("-", "-", campo.logico, col or "(sin mapear)",
                              "", "Columna no encontrada"))
        return out

    def _hallazgos_valor(self, df, mapeo, campos, id_col) -> list[dict]:
        out = []
        for campo in campos:
            col = mapeo.get(campo.logico)
            if col is None or col not in df.columns:
                continue
            reglas_valor = [r for r in campo.reglas if CATALOGO[r.id].ambito == "valor"]
            if not reglas_valor:
                continue
            funcs = [construir(r) for r in reglas_valor]
            for idx, row in df.iterrows():
                valor = row[col]
                ctx = Contexto(idx, row, mapeo, df)
                errs = [m for fn in funcs if (m := fn(valor, ctx))]
                if errs:
                    idv = row[id_col] if id_col and id_col in df.columns else idx
                    out.append(_h(_fila(idx), idv, campo.logico, col, valor, "; ".join(errs)))
        return out

    def _hallazgos_niveles(self, df, mapeo) -> list[dict]:
        """Requisitos por nivel de cuenta (solo clientes), si la entidad los define."""
        if not self.config.requisitos_cliente or not self.config.campo_nivel:
            return []
        from core.niveles import validar_requisitos, construir_aliases_nivel
        out = []
        for h in validar_requisitos(
                df, mapeo, self.config.requisitos_cliente,
                campo_nivel=self.config.campo_nivel,
                campo_tipo_persona=self.config.campo_tipo_persona,
                campo_modalidad=self.config.campo_modalidad,
                aliases_nivel=construir_aliases_nivel(self.config.aliases_nivel)):
            ctx = f"{h['nivel']}/{h['tipo']}/{h['modalidad']}"
            out.append(_h(h["fila"], h["id_cliente"], h["campo"], h["columna"],
                          ctx, h["Tipo_Error"]))
        return out

    def _hallazgos_unico_memoria(self, df, mapeo, campos, id_col) -> list[dict]:
        out = []
        for campo in campos:
            if not _tiene_unico(campo):
                continue
            col = mapeo.get(campo.logico)
            out.extend(_duplicados(df, col, campo.logico, id_col))
        return out

    def _duplicados_sqlite(self, db_path, mapeo, campos, id_col) -> list[dict]:
        from core.multi_loader import TABLA
        out = []
        conn = sqlite3.connect(db_path)
        try:
            for campo in campos:
                if not _tiene_unico(campo):
                    continue
                col = mapeo.get(campo.logico)
                if not col:
                    continue
                qcol = _q(col)
                valido = (f"TRIM({qcol}) <> '' AND "
                          f"LOWER(TRIM({qcol})) NOT IN ('nan','none','null')")
                sel_id = f", {_q(id_col)}" if id_col else ""
                q = (f"SELECT rowid, {qcol}{sel_id} FROM {TABLA} "
                     f"WHERE {valido} AND {qcol} IN "
                     f"(SELECT {qcol} FROM {TABLA} WHERE {valido} "
                     f" GROUP BY {qcol} HAVING COUNT(*) > 1)")
                for r in conn.execute(q).fetchall():
                    rowid, valor = r[0], r[1]
                    # rowid (1..N) = índice global + 1; _fila usa índice + 2.
                    idv = r[2] if id_col else (rowid - 1)
                    out.append(_h(rowid + 1, idv, campo.logico, col, valor,
                                  f"{campo.logico} duplicado"))
        finally:
            conn.close()
        return out


def _fila(idx):
    try:
        return int(idx) + 2
    except (TypeError, ValueError):
        return idx


def _h(fila, idv, campo, columna, valor, tipo) -> dict:
    return {"fila": fila, "id": idv, "campo": campo, "columna": columna,
            "valor": valor, "Tipo_Error": tipo}


def _duplicados(df, col, campo_logico, id_col) -> list[dict]:
    if col is None or col not in df.columns:
        return []
    serie = df[col].astype(str).str.strip()
    dup = serie[serie.duplicated(keep=False) & ~serie.str.lower().isin(["", "nan", "none", "null"])]
    out = []
    for idx in dup.index:
        idv = df.loc[idx, id_col] if id_col and id_col in df.columns else idx
        out.append(_h(_fila(idx), idv, campo_logico, col, df.loc[idx, col],
                      f"{campo_logico} duplicado"))
    return out
