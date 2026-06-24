"""Validación de LÍMITES DE OPERACIÓN por nivel de cuenta (montos).

Dos validaciones, ambas mensuales (mes calendario), con los montos en MXN
convertidos con los archivos de tasas que ya carga el diálogo de operaciones:

- Abonos por nivel: suma de abonos (tipo_operacion configurable) convertida a
  UDIS, por cuenta y mes, comparada contra el tope del nivel/tipo de persona.
- Efectivo en USD: suma de operaciones en efectivo convertida a USD, por cliente
  y mes, comparada contra el tope por tipo de persona (física/moral).

La fase de agrupación está separada de la de límites para poder re-agregar los
grupos entre lotes (SQLite) y obtener totales correctos.
"""
from __future__ import annotations

import pandas as pd

from core.niveles import normalizar_nivel, tipo_de

ABONO_UDIS = "abono_mensual"
EFECTIVO_USD = "efectivo_usd"


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
    t[f] = pd.to_datetime(t[f], errors="coerce", dayfirst=True)
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


class LimitesOperaciones:
    def __init__(self, df, mapeo, limites, *, campos, valores_abono, valores_efectivo,
                 archivo_udis=None, mapeo_udis=None, archivo_tc=None, mapeo_tc=None,
                 default_tipo="fisica"):
        self.df = df
        self.mapeo = mapeo
        self.limites = limites or []
        self.campos = campos                  # roles -> nombre lógico
        self.valores_abono = valores_abono
        self.valores_efectivo = valores_efectivo
        self.default_tipo = default_tipo
        self.tasas_udis = _cargar_tasas(archivo_udis, mapeo_udis)
        self.tasas_tc = _cargar_tasas(archivo_tc, mapeo_tc)

    def _col(self, rol):
        logico = self.campos.get(rol)
        return self.mapeo.get(logico) if logico else None

    # ------------------------------------------------------------------ #
    def agrupar(self):
        """Devuelve (g_abonos, g_efectivo): sumas mensuales por grupo (pre-límite)."""
        df = self.df
        col_fecha, col_monto = self._col("fecha"), self._col("monto")
        if not col_fecha or not col_monto or col_fecha not in df.columns or col_monto not in df.columns:
            return None, None
        col_cuenta, col_cliente = self._col("cuenta"), self._col("cliente")
        col_nivel, col_tipo = self._col("nivel"), self._col("tipo_persona")
        col_top, col_inst = self._col("tipo_operacion"), self._col("instrumento")

        fecha = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
        monto = _limpiar_num(df[col_monto])
        mask = fecha.notna() & monto.notna()
        if not mask.any():
            return None, None

        w = pd.DataFrame(index=df.index[mask])
        w["mes"] = fecha[mask].dt.to_period("M").astype(str)
        w["fnorm"] = fecha[mask].dt.normalize()
        w["monto"] = monto[mask]
        w["cuenta"] = df.loc[mask, col_cuenta].astype(str) if col_cuenta else ""
        w["cliente"] = df.loc[mask, col_cliente].astype(str) if col_cliente else ""
        w["nivel"] = (df.loc[mask, col_nivel].map(normalizar_nivel)
                      if col_nivel and col_nivel in df.columns else None)
        w["tipo"] = (df.loc[mask, col_tipo].map(lambda v: tipo_de(v, self.default_tipo))
                     if col_tipo and col_tipo in df.columns else self.default_tipo)
        w["top"] = (df.loc[mask, col_top].astype(str).str.strip().str.upper()
                    if col_top and col_top in df.columns else "")
        w["inst"] = (df.loc[mask, col_inst].astype(str).str.strip().str.upper()
                     if col_inst and col_inst in df.columns else "")

        if self.tasas_udis is not None:
            w["udis"] = _convertir(w["fnorm"], w["monto"], self.tasas_udis)
        if self.tasas_tc is not None:
            w["usd"] = _convertir(w["fnorm"], w["monto"], self.tasas_tc)

        g_abonos = None
        if "udis" in w and self.valores_abono:
            ab = w[w["top"].isin(_upper(self.valores_abono)) & w["udis"].notna()]
            if not ab.empty:
                g_abonos = (ab.groupby(["cuenta", "mes", "nivel", "tipo"], dropna=False)["udis"]
                            .agg(total="sum", n="count").reset_index())

        g_efectivo = None
        if "usd" in w and self.valores_efectivo:
            ef = w[w["inst"].isin(_upper(self.valores_efectivo)) & w["usd"].notna()]
            if not ef.empty:
                g_efectivo = (ef.groupby(["cliente", "mes", "tipo"], dropna=False)["usd"]
                              .agg(total="sum", n="count").reset_index())
        return g_abonos, g_efectivo

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

    def aplicar_limites(self, g_abonos, g_efectivo) -> dict:
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

        if g_efectivo is not None and not g_efectivo.empty:
            filas = []
            for _, r in g_efectivo.iterrows():
                lim = self._limite(EFECTIVO_USD, "todos", r["tipo"])
                if lim is not None and r["total"] > lim:
                    filas.append({
                        "id_cliente": r["cliente"], "mes": r["mes"], "tipo": r["tipo"],
                        "operaciones": int(r["n"]),
                        "efectivo_USD": round(float(r["total"]), 2), "limite_USD": lim,
                        "Tipo_Error": (f"Efectivo {r['total']:.2f} USD excede el límite "
                                       f"{lim} ({r['tipo']})")})
            if filas:
                sheets["Efectivo USD sobre Limite"] = pd.DataFrame(filas)
        return sheets

    def validar(self) -> dict:
        ga, ge = self.agrupar()
        return self.aplicar_limites(ga, ge)


def reagregar(parciales_abonos, parciales_efectivo):
    """Re-agrega los grupos parciales de varios lotes (SQLite) -> (g_abonos, g_efectivo)."""
    g_ab = None
    if parciales_abonos:
        t = pd.concat(parciales_abonos, ignore_index=True)
        g_ab = (t.groupby(["cuenta", "mes", "nivel", "tipo"], dropna=False)
                .agg(total=("total", "sum"), n=("n", "sum")).reset_index())
    g_ef = None
    if parciales_efectivo:
        t = pd.concat(parciales_efectivo, ignore_index=True)
        g_ef = (t.groupby(["cliente", "mes", "tipo"], dropna=False)
                .agg(total=("total", "sum"), n=("n", "sum")).reset_index())
    return g_ab, g_ef
