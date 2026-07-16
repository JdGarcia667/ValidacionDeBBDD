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

from core.validator_operaciones import ValidatorOperaciones
from core.sqlite_validator_operaciones import SQLiteValidatorOperaciones
from .base import ValidadorEntidad
from .modelo import EntidadConfig, CampoConfig
from .reglas import CATALOGO, Contexto, construir

COLS = ["fila", "id", "campo", "columna", "valor", "Tipo_Error"]

# Roles de campo de operación (fecha/monto/cuenta/...) -> nombre lógico FIJO,
# en el mismo espacio de claves que esperan ValidatorOperaciones/
# LimitesOperaciones (idéntico al CAMPOS_LIMITES de Banco). El mapeo real
# (lógico arbitrario -> columna) se traduce a este espacio antes de invocar
# esos motores, para poder reutilizarlos tal cual sin reimplementarlos.
_ROLES_A_CLAVE = {
    "fecha": "fecha_operacion", "monto": "monto", "cuenta": "id_cuenta",
    "cliente": "id_cliente", "nivel": "nivel_cuenta", "tipo_persona": "tipo de persona",
    "tipo_operacion": "tipo_operacion", "instrumento": "instrumento_monetario",
    "saldo": "saldo", "moneda": "moneda_operacion",
}


def _q(nombre: str) -> str:
    """Cita un identificador SQL (columnas con espacios/acentos)."""
    return '"' + str(nombre).replace('"', '""') + '"'


def _regla_de_ambito(campo: CampoConfig, ambito: str) -> "ReglaConfig | None":
    return next((r for r in campo.reglas if CATALOGO[r.id].ambito == ambito), None)


def _tiene_unico(campo: CampoConfig) -> bool:
    return _regla_de_ambito(campo, "columna") is not None


def _regla_relacion(campo: CampoConfig):
    """Regla de ambito 'relacion' del campo (p. ej. 'mismo_valor_en'), o None."""
    return _regla_de_ambito(campo, "relacion")


class EntidadConfigurable(ValidadorEntidad):
    requiere_tipo_persona = False

    def __init__(self, config: EntidadConfig):
        self.config = config
        self.nombre = config.nombre
        self.descripcion = config.descripcion
        self.es_builtin = False

    @property
    def requiere_config_operaciones(self) -> bool:
        # Se necesita el diálogo de configuración (moneda/agrupación/filtros y,
        # si aplica, archivos de tasas UDIS/tipo de cambio) tanto si la entidad
        # define límites de operación por nivel como si se activaron los
        # filtros de monto con operador libre (estilo Banco).
        return bool(self.tiene_limites_operacion() or self.config.op_filtros_habilitado)

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
        config = config or {}
        res = self._validar(df, mapeo, self.config.campos_operacion, "id_operacion")
        mapeo_generico = self._mapeo_operaciones_generico(mapeo)
        if self.config.op_filtros_habilitado:
            errores_vo, _ = ValidatorOperaciones(df, mapeo_generico, config).validar_todo()
            res.update(errores_vo)
        lim = self._limites_validador(df, mapeo_generico, config)
        if lim is not None:
            res.update(lim.validar())
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
        config = config or {}
        res = self._validar_sqlite(db_path, mapeo, self.config.campos_operacion,
                                   "id_operacion", progreso)
        mapeo_generico = self._mapeo_operaciones_generico(mapeo)
        if self.config.op_filtros_habilitado:
            # Motor combinado (filtros de monto + límites, si los hay): mismo
            # camino genérico que usa Banco, sin reimplementar la re-agregación
            # por lotes.
            limites_kwargs = self._limites_kwargs(config) if self.tiene_limites_operacion() else None
            errores, _ = SQLiteValidatorOperaciones(
                db_path, mapeo_generico, config, progreso=progreso,
                limites_kwargs=limites_kwargs).validar_todo()
            res.update(errores)
        else:
            res.update(self._limites_sqlite(db_path, mapeo, config, progreso))
        return res

    # ------------------------------------------------------------------ #
    # Traducción de roles de campo de operación al espacio de claves fijas
    # ------------------------------------------------------------------ #
    def _mapeo_operaciones_generico(self, mapeo: dict) -> dict:
        """Combina self.config.op_campos (rol -> lógico) con mapeo (lógico ->
        columna real) para producir el mapeo en el espacio de claves fijas
        (_ROLES_A_CLAVE) que esperan ValidatorOperaciones/LimitesOperaciones."""
        out = {}
        for rol, clave in _ROLES_A_CLAVE.items():
            logico = self.config.op_campos.get(rol)
            col = mapeo.get(logico) if logico else None
            if col:
                out[clave] = col
        return out

    # ------------------------------------------------------------------ #
    # Límites de operación por nivel (montos)
    # ------------------------------------------------------------------ #
    def _limites_kwargs(self, config) -> dict:
        from core.niveles import construir_aliases_nivel
        return dict(
            limites=self.config.limites_operacion, campos=_ROLES_A_CLAVE,
            valores_abono=self.config.op_valores_abono,
            valores_efectivo=self.config.op_valores_efectivo,
            valores_cheque_caja=self.config.op_valores_cheque_caja,
            valores_moneda_usd=self.config.op_valores_moneda_usd,
            archivo_udis=config.get("archivo_udis"), mapeo_udis=config.get("mapeo_udis"),
            archivo_tc=config.get("archivo_tc"), mapeo_tc=config.get("mapeo_tc"),
            aliases_nivel=construir_aliases_nivel(self.config.aliases_nivel))

    def _limites_validador(self, df, mapeo_generico, config):
        """Construye el validador de límites si la entidad los define; si no, None."""
        if not self.config.limites_operacion or not self.config.op_campos:
            return None
        from core.limites_operaciones import LimitesOperaciones
        return LimitesOperaciones(df, mapeo_generico, **self._limites_kwargs(config))

    def _limites_sqlite(self, db_path, mapeo, config, progreso) -> dict:
        lim = self._limites_validador(None, self._mapeo_operaciones_generico(mapeo), config)
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
        hallazgos += self._hallazgos_relacion_memoria(df, mapeo, campos, id_col)
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
        # Consistencia ('mismo_valor_en'): global, vía SQL.
        if any(_regla_relacion(c) is not None for c in campos):
            if progreso:
                progreso("Buscando inconsistencias en todo el conjunto...")
            hallazgos += self._relacion_sqlite(db_path, mapeo, campos, id_col)
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

    def _hallazgos_relacion_memoria(self, df, mapeo, campos, id_col) -> list[dict]:
        out = []
        for campo in campos:
            regla = _regla_relacion(campo)
            if regla is None:
                continue
            col = mapeo.get(campo.logico)
            campo_ref = regla.parametros.get("campo_referencia")
            col_ref = mapeo.get(campo_ref) if campo_ref else None
            if not col or col not in df.columns or not col_ref or col_ref not in df.columns:
                continue
            out.extend(_inconsistencias(df, col, col_ref, campo.logico, campo_ref, id_col))
        return out

    def _relacion_sqlite(self, db_path, mapeo, campos, id_col) -> list[dict]:
        from core.multi_loader import TABLA
        out = []
        conn = sqlite3.connect(db_path)
        try:
            for campo in campos:
                regla = _regla_relacion(campo)
                if regla is None:
                    continue
                col = mapeo.get(campo.logico)
                campo_ref = regla.parametros.get("campo_referencia")
                col_ref = mapeo.get(campo_ref) if campo_ref else None
                if not col or not col_ref:
                    continue
                qcol, qref = _q(col), _q(col_ref)
                valido = (f"TRIM({qcol}) <> '' AND "
                          f"LOWER(TRIM({qcol})) NOT IN ('nan','none','null')")
                sel_id = f", {_q(id_col)}" if id_col else ""
                q = (f"SELECT rowid, {qcol}{sel_id} FROM {TABLA} "
                     f"WHERE {valido} AND UPPER(TRIM({qcol})) IN "
                     f"(SELECT UPPER(TRIM({qcol})) FROM {TABLA} WHERE {valido} "
                     f" GROUP BY UPPER(TRIM({qcol})) "
                     f" HAVING COUNT(DISTINCT UPPER(TRIM({qref}))) > 1)")
                for r in conn.execute(q).fetchall():
                    rowid, valor = r[0], r[1]
                    idv = r[2] if id_col else (rowid - 1)
                    out.append(_h(rowid + 1, idv, campo.logico, col, valor,
                                  f"{campo.logico} repetido con distinto valor en {campo_ref}"))
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


def _inconsistencias(df, col, col_ref, campo_logico, campo_ref_logico, id_col) -> list[dict]:
    """Filas cuyo valor en `col` se repite pero con distinto valor en `col_ref`
    (p. ej. mismo CURP con nombre diferente). Comparación case-insensitive."""
    if col is None or col not in df.columns or col_ref is None or col_ref not in df.columns:
        return []
    clave = df[col].astype(str).str.strip().str.upper()
    valido = ~clave.str.lower().isin(["", "nan", "none", "null"])
    ref = df[col_ref].astype(str).str.strip().str.upper()
    sub = pd.DataFrame({"_clave": clave, "_ref": ref}, index=df.index)[valido]
    grupos = sub.groupby("_clave")["_ref"].nunique()
    claves_malas = set(grupos[grupos > 1].index)
    idx = sub.index[sub["_clave"].isin(claves_malas)]
    out = []
    for i in idx:
        idv = df.loc[i, id_col] if id_col and id_col in df.columns else i
        out.append(_h(_fila(i), idv, campo_logico, col, df.loc[i, col],
                      f"{campo_logico} repetido con distinto valor en {campo_ref_logico}"))
    return out
