"""Lectura de tablas (CSV/Excel) preservando el formato dd/mm/yyyy de fechas."""
from __future__ import annotations

import pandas as pd


def leer_tabla(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%d/%m/%Y")
        return df.astype(object).where(df.notna(), "")
    return pd.read_csv(path, dtype=str, keep_default_na=False)
