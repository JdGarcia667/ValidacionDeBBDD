"""Validación de LÍMITES DE OPERACIÓN por nivel de cuenta (montos).

Dos familias de validación, ambas configurables por (concepto, nivel, tipo de
persona) vía `LimiteOperacion` (ver `entidades/modelo.py`), para que se puedan
personalizar igual en el Banco y en entidades configurables por el usuario:

- AGREGADAS (mensuales, por cuenta/cliente y mes calendario):
  - "abono_mensual": suma de abonos (tipo_operacion configurable) en UDIS.
  - "efectivo_usd": suma de ABONOS en efectivo, en USD (>=). Antes sumaba
    cualquier movimiento en efectivo (abono o cargo); se corrigió a solo
    abonos, según el criterio real de la validación.
  - "efectivo_mensual_mxn": suma de efectivo en MXN (sin conversión), en
    cualquier sentido (abono o cargo).
- INDIVIDUALES (por operación, sin agregar):
  - "efectivo_individual_mxn": monto en MXN de un abono/depósito/pago en
    efectivo (sin conversión).
  - "operacion_relevante_usd": cargo o abono en efectivo cuyo equivalente en
    USD alcanza el umbral (>=), sin importar el sentido del movimiento.
  - "efectivo_abono_usd_individual": abono en efectivo cuya MONEDA declarada
    ya es dólares (no un equivalente convertido), monto individual (>=).
  - "cheque_caja_usd": cargo o abono con instrumento 'cheque de caja', monto
    (convertido a USD si hace falta) que alcanza el umbral (>=).
  - "saldo_udis": saldo de cuenta (columna aparte de 'monto') en UDIS.

Los montos en MXN se convierten con los archivos de tasas que ya carga el
diálogo de operaciones (UDIS y tipo de cambio); las validaciones en MXN puro
no requieren ningún archivo de tasas.

Moneda de la operación (campo opcional 'moneda'): algunas operaciones ya
declaran su monto en dólares (no en pesos por convertir). Cuando la columna de
moneda está mapeada y el valor de la fila calza con `valores_moneda_usd`, el
monto se usa TAL CUAL como equivalente en USD (sin dividir por el tipo de
cambio); el resto de las filas se sigue convirtiendo con el archivo de tipo de
cambio, igual que antes. Si no se mapea la columna de moneda, el
comportamiento es idéntico al de siempre (todo se convierte).

La fase de agrupación está separada de la de límites para poder re-agregar los
grupos entre lotes (SQLite) y obtener totales correctos. Las validaciones
INDIVIDUALES no necesitan re-agregación: cada hallazgo es autocontenido, así
que en modo por lotes basta con concatenar los hallazgos de cada lote.
"""
from __future__ import annotations

import pandas as pd

from core.niveles import normalizar_nivel, tipo_de, categoria_persona
from core.utils import parsear_fecha

ABONO_UDIS = "abono_mensual"
EFECTIVO_USD = "efectivo_usd"
EFECTIVO_MENSUAL_MXN = "efectivo_mensual_mxn"
EFECTIVO_INDIVIDUAL_MXN = "efectivo_individual_mxn"
OPERACION_RELEVANTE_USD = "operacion_relevante_usd"
EFECTIVO_ABONO_USD_INDIVIDUAL = "efectivo_abono_usd_individual"
CHEQUE_CAJA_USD = "cheque_caja_usd"
SALDO_UDIS = "saldo_udis"

# Conceptos cuyo hallazgo se dispara con "igual o mayor" (>=) al límite; el
# resto (abono_mensual, efectivo_mensual_mxn, efectivo_individual_mxn,
# saldo_udis) usa "mayor estricto" (>), como siempre.
_CONCEPTOS_IGUAL_O_MAYOR = {
    EFECTIVO_USD, OPERACION_RELEVANTE_USD, EFECTIVO_ABONO_USD_INDIVIDUAL, CHEQUE_CAJA_USD,
}


def _excede(valor, limite, concepto) -> bool:
    return valor >= limite if concepto in _CONCEPTOS_IGUAL_O_MAYOR else valor > limite


def _limpiar_num(serie):
    return pd.to_numeric(serie.astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                         errors="coerce")


def _cargar_tasas(archivo, mapeo):
    """Lee un archivo de tasas (UDIS o tipo de cambio) -> df[fecha, tasa] o None."""
    if not archivo or not mapeo:
        return None
    try:
        t = pd.read_excel(archivo)
    except Exception:                                 # noqa: BLE001
        return None
    f, v = mapeo.get("fecha"), mapeo.get("valor")
    if f not in t.columns or v not in t.columns:
        return None
    t = t[[f, v]].copy()
    t[f] = parsear_fecha(t[f])
    t[v] = _limpiar_num(t[v])
    t = t.dropna().sort_values(f).rename(columns={f: "fecha", v: "tasa"})
    return t if not t.empty else None


def _convertir(fnorm, montos, tasas):
    """Convierte montos MXN dividiendo por la tasa de la fecha más cercana (<=).

    Tanto UDIS como USD se obtienen dividiendo: UDIS = MXN / valor_UDI (pesos por
    UDI); USD = MXN / tipo_de_cambio (pesos por dólar). Es la convención estándar
    y consistente con la conversión a UDIS del resto del sistema.
    """
    base = pd.DataFrame({"_f": fnorm, "_m": montos}).sort_values("_f")
    merged = pd.merge_asof(base, tasas, left_on="_f", right_on="fecha", direction="backward")
    merged.index = base.index
    return merged["_m"] / merged["tasa"]


def _upper(valores):
    return {str(v).strip().upper() for v in (valores or [])}


def _fila(idx):
    try:
        return int(idx) + 2
    except (TypeError, ValueError):
        return idx


class LimitesOperaciones:
    def __init__(self, df, mapeo, limites, *, campos, valores_abono, valores_efectivo,
                 valores_cheque_caja=None, valores_moneda_usd=None,
                 archivo_udis=None, mapeo_udis=None, archivo_tc=None, mapeo_tc=None,
                 default_tipo="fisica", aliases_nivel=None):
        self.df = df
        self.mapeo = mapeo
        self.limites = limites or []
        self.campos = campos                  # roles -> nombre lógico
        self.valores_abono = valores_abono
        self.valores_efectivo = valores_efectivo
        # Instrumento 'cheque de caja' (separado de efectivo) y valores de la
        # columna 'moneda' que indican que el monto YA viene en dólares.
        self.valores_cheque_caja = valores_cheque_caja or []
        self.valores_moneda_usd = valores_moneda_usd or []
        self.default_tipo = default_tipo
        self.aliases_nivel = aliases_nivel
        self.tasas_udis = _cargar_tasas(archivo_udis, mapeo_udis)
        self.tasas_tc = _cargar_tasas(archivo_tc, mapeo_tc)

    def _col(self, rol):
        logico = self.campos.get(rol)
        return self.mapeo.get(logico) if logico else None

    # ------------------------------------------------------------------ #
    def _construir_base(self):
        """Arma el frame de trabajo por fila: fecha, monto, categorías y
        conversiones (UDIS/USD). Devuelve None si faltan fecha/monto."""
        df = self.df
        col_fecha, col_monto = self._col("fecha"), self._col("monto")
        if not col_fecha or not col_monto or col_fecha not in df.columns or col_monto not in df.columns:
            return None
        col_cuenta, col_cliente = self._col("cuenta"), self._col("cliente")
        col_nivel, col_tipo = self._col("nivel"), self._col("tipo_persona")
        col_top, col_inst = self._col("tipo_operacion"), self._col("instrumento")
        col_saldo = self._col("saldo")
        col_moneda = self._col("moneda")

        fecha = parsear_fecha(df[col_fecha])
        monto = _limpiar_num(df[col_monto])
        mask = fecha.notna() & monto.notna()
        if not mask.any():
            return None

        w = pd.DataFrame(index=df.index[mask])
        w["mes"] = fecha[mask].dt.to_period("M").astype(str)
        w["fnorm"] = fecha[mask].dt.normalize()
        w["monto"] = monto[mask]
        w["cuenta"] = df.loc[mask, col_cuenta].astype(str) if col_cuenta else ""
        w["cliente"] = df.loc[mask, col_cliente].astype(str) if col_cliente else ""
        w["nivel"] = (df.loc[mask, col_nivel].map(lambda v: normalizar_nivel(v, self.aliases_nivel))
                      if col_nivel and col_nivel in df.columns else None)
        w["tipo"] = (df.loc[mask, col_tipo].map(lambda v: tipo_de(v, self.default_tipo))
                     if col_tipo and col_tipo in df.columns else self.default_tipo)
        w["categoria"] = (df.loc[mask, col_tipo].map(lambda v: categoria_persona(v, self.default_tipo))
                          if col_tipo and col_tipo in df.columns
                          else categoria_persona(None, self.default_tipo))
        w["top"] = (df.loc[mask, col_top].astype(str).str.strip().str.upper()
                    if col_top and col_top in df.columns else "")
        w["inst"] = (df.loc[mask, col_inst].astype(str).str.strip().str.upper()
                     if col_inst and col_inst in df.columns else "")
        if col_saldo and col_saldo in df.columns:
            w["saldo"] = _limpiar_num(df.loc[mask, col_saldo])

        if col_moneda and col_moneda in df.columns:
            moneda_norm = df.loc[mask, col_moneda].astype(str).str.strip().str.upper()
            w["es_usd"] = moneda_norm.isin(_upper(self.valores_moneda_usd))
        else:
            w["es_usd"] = False

        if self.tasas_udis is not None:
            w["udis"] = _convertir(w["fnorm"], w["monto"], self.tasas_udis)
            if "saldo" in w:
                w["saldo_udis"] = _convertir(w["fnorm"], w["saldo"], self.tasas_udis)
        # "usd": monto tal cual si la fila ya declara moneda USD; si no, se
        # convierte con el tipo de cambio (si hay archivo cargado). Se crea la
        # columna si hay alguna manera de obtener un valor (archivo de tasas o
        # filas ya en USD); si no, se omite igual que antes.
        if self.tasas_tc is not None or bool(w["es_usd"].any()):
            usd_convertido = (_convertir(w["fnorm"], w["monto"], self.tasas_tc)
                              if self.tasas_tc is not None
                              else pd.Series(float("nan"), index=w.index))
            w["usd"] = w["monto"].where(w["es_usd"], usd_convertido)
        return w

    def agrupar(self):
        """Devuelve (g_abonos, g_efectivo_usd, g_efectivo_mxn): sumas
        mensuales por grupo (pre-límite)."""
        w = self._construir_base()
        if w is None:
            return None, None, None

        g_abonos = None
        if "udis" in w and self.valores_abono:
            ab = w[w["top"].isin(_upper(self.valores_abono)) & w["udis"].notna()]
            if not ab.empty:
                g_abonos = (ab.groupby(["cuenta", "mes", "nivel", "tipo"], dropna=False)["udis"]
                            .agg(total="sum", n="count").reset_index())

        ef_cash = w[w["inst"].isin(_upper(self.valores_efectivo))] if self.valores_efectivo else w.iloc[0:0]

        g_efectivo_usd = None
        if "usd" in w and self.valores_efectivo and self.valores_abono:
            # Solo ABONOS en efectivo (no cargos/retiros).
            ef_abono = ef_cash[ef_cash["top"].isin(_upper(self.valores_abono))]
            ef = ef_abono[ef_abono["usd"].notna()]
            if not ef.empty:
                g_efectivo_usd = (ef.groupby(["cliente", "mes", "tipo"], dropna=False)["usd"]
                                  .agg(total="sum", n="count").reset_index())

        g_efectivo_mxn = None
        if self.valores_efectivo and not ef_cash.empty:
            g_efectivo_mxn = (ef_cash.groupby(["cliente", "mes", "categoria"], dropna=False)["monto"]
                              .agg(total="sum", n="count").reset_index())
        return g_abonos, g_efectivo_usd, g_efectivo_mxn

    def individuales(self) -> dict:
        """Hallazgos por operación individual (sin agregar): topes de efectivo
        en MXN por transacción, operaciones relevantes (USD) y saldo (UDIS)."""
        w = self._construir_base()
        if w is None:
            return {}
        sheets = {}

        if self.valores_efectivo and self.valores_abono:
            ab_cash = w[w["inst"].isin(_upper(self.valores_efectivo)) &
                       w["top"].isin(_upper(self.valores_abono))]
            filas = []
            for idx, r in ab_cash.iterrows():
                lim = self._limite(EFECTIVO_INDIVIDUAL_MXN, "todos", r["categoria"])
                if lim is not None and r["monto"] > lim:
                    filas.append({
                        "fila": _fila(idx), "id_cliente": r["cliente"], "id_cuenta": r["cuenta"],
                        "fecha": r["fnorm"].date().isoformat(), "categoria": r["categoria"],
                        "monto_MXN": round(float(r["monto"]), 2), "limite_MXN": lim,
                        "Tipo_Error": (f"Movimiento individual en efectivo {r['monto']:.2f} MXN "
                                       f"excede el límite {lim} MXN ({r['categoria']})")})
            if filas:
                sheets["Efectivo Individual sobre Limite (MXN)"] = pd.DataFrame(filas)

        if "usd" in w and self.valores_efectivo:
            cash = w[w["inst"].isin(_upper(self.valores_efectivo)) & w["usd"].notna()]
            filas = []
            for idx, r in cash.iterrows():
                lim = self._limite(OPERACION_RELEVANTE_USD, "todos", r["categoria"])
                if lim is not None and _excede(r["usd"], lim, OPERACION_RELEVANTE_USD):
                    filas.append({
                        "fila": _fila(idx), "id_cliente": r["cliente"], "id_cuenta": r["cuenta"],
                        "fecha": r["fnorm"].date().isoformat(), "categoria": r["categoria"],
                        "monto_USD": round(float(r["usd"]), 2), "umbral_USD": lim,
                        "Tipo_Error": (f"Operación relevante: {r['usd']:.2f} USD "
                                       f"(>= {lim} USD) en efectivo")})
            if filas:
                sheets["Operaciones Relevantes"] = pd.DataFrame(filas)

        if "usd" in w and self.valores_efectivo and self.valores_abono:
            # Abonos en efectivo cuya MONEDA declarada ya es dólares (no un
            # equivalente convertido de pesos): monto individual >= umbral.
            ab_usd = w[w["inst"].isin(_upper(self.valores_efectivo))
                      & w["top"].isin(_upper(self.valores_abono)) & w["es_usd"]]
            filas = []
            for idx, r in ab_usd.iterrows():
                lim = self._limite(EFECTIVO_ABONO_USD_INDIVIDUAL, "todos", r["categoria"])
                if lim is not None and _excede(r["monto"], lim, EFECTIVO_ABONO_USD_INDIVIDUAL):
                    filas.append({
                        "fila": _fila(idx), "id_cliente": r["cliente"], "id_cuenta": r["cuenta"],
                        "fecha": r["fnorm"].date().isoformat(), "categoria": r["categoria"],
                        "monto_USD": round(float(r["monto"]), 2), "limite_USD": lim,
                        "Tipo_Error": (f"Abono en efectivo en dólares {r['monto']:.2f} USD "
                                       f">= {lim} USD ({r['categoria']})")})
            if filas:
                sheets["Efectivo en Dolares sobre Limite"] = pd.DataFrame(filas)

        if "usd" in w and self.valores_cheque_caja:
            # Cargos o abonos con instrumento 'cheque de caja' (cualquier
            # sentido), convertido a USD si hace falta.
            cheques = w[w["inst"].isin(_upper(self.valores_cheque_caja)) & w["usd"].notna()]
            filas = []
            for idx, r in cheques.iterrows():
                lim = self._limite(CHEQUE_CAJA_USD, "todos", r["categoria"])
                if lim is not None and _excede(r["usd"], lim, CHEQUE_CAJA_USD):
                    filas.append({
                        "fila": _fila(idx), "id_cliente": r["cliente"], "id_cuenta": r["cuenta"],
                        "fecha": r["fnorm"].date().isoformat(), "categoria": r["categoria"],
                        "monto_USD": round(float(r["usd"]), 2), "limite_USD": lim,
                        "Tipo_Error": (f"Cheque de caja {r['usd']:.2f} USD >= {lim} USD "
                                       f"({r['categoria']})")})
            if filas:
                sheets["Cheque de Caja sobre Limite (USD)"] = pd.DataFrame(filas)

        if "saldo_udis" in w:
            sal = w[w["saldo_udis"].notna()]
            filas = []
            for idx, r in sal.iterrows():
                lim = self._limite(SALDO_UDIS, r["nivel"], r["categoria"])
                if lim is not None and r["saldo_udis"] > lim:
                    filas.append({
                        "fila": _fila(idx), "id_cliente": r["cliente"], "id_cuenta": r["cuenta"],
                        "fecha": r["fnorm"].date().isoformat(), "nivel": r["nivel"],
                        "saldo_UDIS": round(float(r["saldo_udis"]), 2), "limite_UDIS": lim,
                        "Tipo_Error": (f"Saldo {r['saldo_udis']:.2f} UDIS excede el límite "
                                       f"{lim} UDIS (nivel {r['nivel']})")})
            if filas:
                sheets["Saldo sobre Limite (UDIS)"] = pd.DataFrame(filas)

        return sheets

    # ------------------------------------------------------------------ #
    def _limite(self, concepto, nivel, tipo):
        for l in self.limites:
            if l.concepto != concepto:
                continue
            if str(l.nivel) not in (str(nivel), "todos"):
                continue
            if l.tipo_persona not in (tipo, "ambos"):
                continue
            return l.limite          # puede ser 0 (prohibido) o None (sin límite)
        return None

    def aplicar_limites(self, g_abonos, g_efectivo_usd, g_efectivo_mxn) -> dict:
        sheets = {}
        if g_abonos is not None and not g_abonos.empty:
            filas = []
            for _, r in g_abonos.iterrows():
                lim = self._limite(ABONO_UDIS, r["nivel"], r["tipo"])
                if lim is not None and r["total"] > lim:
                    filas.append({
                        "id_cuenta": r["cuenta"], "mes": r["mes"], "nivel": r["nivel"],
                        "tipo": r["tipo"], "operaciones": int(r["n"]),
                        "abonos_UDIS": round(float(r["total"]), 2), "limite_UDIS": lim,
                        "Tipo_Error": (f"Abonos {r['total']:.2f} UDIS exceden el límite "
                                       f"{lim} (nivel {r['nivel']}, {r['tipo']})")})
            if filas:
                sheets["Abonos sobre Limite (UDIS)"] = pd.DataFrame(filas)

        if g_efectivo_usd is not None and not g_efectivo_usd.empty:
            filas = []
            for _, r in g_efectivo_usd.iterrows():
                lim = self._limite(EFECTIVO_USD, "todos", r["tipo"])
                if lim is not None and _excede(r["total"], lim, EFECTIVO_USD):
                    filas.append({
                        "id_cliente": r["cliente"], "mes": r["mes"], "tipo": r["tipo"],
                        "operaciones": int(r["n"]),
                        "abonos_USD": round(float(r["total"]), 2), "limite_USD": lim,
                        "Tipo_Error": (f"Abonos en efectivo {r['total']:.2f} USD >= al límite "
                                       f"{lim} ({r['tipo']})")})
            if filas:
                sheets["Efectivo USD sobre Limite"] = pd.DataFrame(filas)

        if g_efectivo_mxn is not None and not g_efectivo_mxn.empty:
            filas = []
            for _, r in g_efectivo_mxn.iterrows():
                lim = self._limite(EFECTIVO_MENSUAL_MXN, "todos", r["categoria"])
                if lim is not None and r["total"] > lim:
                    filas.append({
                        "id_cliente": r["cliente"], "mes": r["mes"], "categoria": r["categoria"],
                        "operaciones": int(r["n"]),
                        "efectivo_MXN": round(float(r["total"]), 2), "limite_MXN": lim,
                        "Tipo_Error": (f"Efectivo {r['total']:.2f} MXN excede el límite mensual "
                                       f"{lim} MXN ({r['categoria']})")})
            if filas:
                sheets["Efectivo MXN mensual sobre Limite"] = pd.DataFrame(filas)
        return sheets

    def validar(self) -> dict:
        ga, ge_usd, ge_mxn = self.agrupar()
        sheets = self.aplicar_limites(ga, ge_usd, ge_mxn)
        sheets.update(self.individuales())
        return sheets


def reagregar(parciales_abonos, parciales_efectivo_usd, parciales_efectivo_mxn):
    """Re-agrega los grupos parciales de varios lotes (SQLite) -> (g_abonos,
    g_efectivo_usd, g_efectivo_mxn)."""
    g_ab = None
    if parciales_abonos:
        t = pd.concat(parciales_abonos, ignore_index=True)
        g_ab = (t.groupby(["cuenta", "mes", "nivel", "tipo"], dropna=False)
                .agg(total=("total", "sum"), n=("n", "sum")).reset_index())
    g_ef_usd = None
    if parciales_efectivo_usd:
        t = pd.concat(parciales_efectivo_usd, ignore_index=True)
        g_ef_usd = (t.groupby(["cliente", "mes", "tipo"], dropna=False)
                    .agg(total=("total", "sum"), n=("n", "sum")).reset_index())
    g_ef_mxn = None
    if parciales_efectivo_mxn:
        t = pd.concat(parciales_efectivo_mxn, ignore_index=True)
        g_ef_mxn = (t.groupby(["cliente", "mes", "categoria"], dropna=False)
                    .agg(total=("total", "sum"), n=("n", "sum")).reset_index())
    return g_ab, g_ef_usd, g_ef_mxn
