"""Auto-mapeo (sin dependencias externas) campo logico -> columna real."""
from __future__ import annotations

import re
import unicodedata


def normaliza(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    return re.sub(r"[\s_]+", "", t)


SINONIMOS = {
    "telefono": ["tel", "celular", "movil", "phone"],
    "correoelectronico": ["correo", "email", "mail"],
    "fechanacimiento": ["fechanac", "nacimiento", "fdn", "birthdate"],
    "entidadfederativa": ["estado", "entidad"],
    "paisnacimiento": ["pais", "paisorigen"],
    "nombre": ["nombrecompleto", "razonsocial", "nombrerazonsocial"],
    "tipodepersona": ["tipopersona", "personalidad"],
    "estatuscliente": ["estatus", "status"],
    "fechainiciorelacion": ["fechainicio", "inicio", "alta"],
    "fechaterminorelacion": ["fechatermino", "termino", "baja"],
    "gradoriesgo": ["riesgo", "nivelriesgo"],
    "fechariesgo": ["fecharisk"],
    "nacionalidad": ["nacion"],
    "actividadgenerica": ["actividadgen", "giro"],
    "actividadespecifica": ["actividadesp"],
    "nivelcuenta": ["nivel"],
    "idcliente": ["clienteid", "idcli"],
    "idoperacion": ["operacionid", "idop"],
    "idcuenta": ["cuentaid", "cuenta"],
    "tipooperacion": ["tipo", "tipoop"],
    "instrumentomonetario": ["instrumento", "moneda"],
    "fechaoperacion": ["fechaop", "fecha"],
    "monto": ["importe", "cantidad", "valor"],
}


def auto_mapear(columnas: list[str], campos_logicos: list[str]) -> dict[str, str | None]:
    norm_cols = {normaliza(c): c for c in columnas}
    mapeo: dict[str, str | None] = {}
    for logico in campos_logicos:
        nl = normaliza(logico)
        if nl in norm_cols:
            mapeo[logico] = norm_cols[nl]
            continue
        candidato = None
        for syn in SINONIMOS.get(nl, []):
            if normaliza(syn) in norm_cols:
                candidato = norm_cols[normaliza(syn)]
                break
        if candidato:
            mapeo[logico] = candidato
            continue
        for ncol, real in norm_cols.items():
            if nl and (nl in ncol or ncol in nl):
                candidato = real
                break
        mapeo[logico] = candidato
    return mapeo
