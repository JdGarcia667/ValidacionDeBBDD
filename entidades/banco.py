"""
Entidad BANCO: envuelve tu codigo real, sin reimplementarlo.

Los campos logicos son exactamente los que esperan tus clases (Mapper.CAMPOS_REQUERIDOS
y MapperOperaciones.CAMPOS_REQUERIDOS), para que el mapeo {campo: columna_real}
llegue tal cual a Validator / ValidatorOperaciones.
"""
from __future__ import annotations

import pandas as pd

import pandas as pd

from core.validator import Validator, DEFAULT_CONFIG as _VALIDATOR_DEFAULT_CONFIG
from core.validator_operaciones import ValidatorOperaciones
from core.niveles import validar_requisitos
from core.limites_operaciones import LimitesOperaciones
from .base import ValidadorEntidad
from .modelo import RequisitoNivel, LimiteOperacion
# OJO: NO importar entidades.registro a nivel de módulo — registro.py importa
# BancoValidador de este mismo archivo (import circular). Se importa dentro de
# config_efectiva() en su lugar (lazy import), donde ya no hay ciclo porque
# para entonces ambos módulos ya terminaron de cargar.


# Campos requeridos para clientes (identicos a core/mapper.py: Mapper.CAMPOS_REQUERIDOS)
CAMPOS_CLIENTE = [
    "id_cliente", "nombre", "apellido_paterno", "apellido_materno",
    "fecha_nacimiento", "genero", "tipo de persona",
    "estatus_cliente", "fecha_inicio_relacion", "fecha_termino_relacion",
    "grado_riesgo", "fecha_riesgo", "PEP", "Nacionalidad", "Pais_nacimiento",
    "entidad_federativa", "Actividad_generica", "Actividad_especifica",
    "Teléfono", "Correo electronico", "CURP", "RFC", "Dirección",
    # Identificación oficial (requerida en nivel 3 Limitada).
    "numero_identificacion", "tipo_identificacion",
    "firma electronica avanzada",
    # Persona moral: representante legal (todas) e identificación fiscal
    # extranjera (cuando la moral es extranjera; en ese caso no aplica RFC).
    "representante_legal", "numero_identificacion_fiscal",
    "pais_asignacion_rfc", "numero_serie_firma",
    # Domicilio dividido en columnas (opcional; alternativa a 'Dirección').
    "calle_avenida_via", "numero_exterior", "numero_interior",
    "colonia_urbanizacion", "alcaldia_municipio", "ciudad_poblacion",
    "entidad_federativa_estado", "codigo_postal", "pais",
    "Nivel_cuenta", "modalidad de apertura",
    # Respuesta de la consulta a RENAPO (N1 y N3 remota) y geolocalización
    # de la apertura de cuenta (N4 Limitada).
    "Respuesta RENAPO", "Geolocalización",
]

# Requisitos por nivel de cuenta (clientes). Mapeo del marco regulatorio a las
# columnas DISPONIBLES en la base; los requisitos documentales (FIEL, copias de
# identificación, comprobante de domicilio, propietario real, geolocalización...)
# no son columnas y por tanto no se validan aquí.
_N = RequisitoNivel
_DEMOGRAFICOS_FISICA = [
    "nombre", "genero", "fecha_nacimiento", "entidad_federativa", "Pais_nacimiento",
    "Nacionalidad", "Actividad_generica", "Dirección", "Teléfono",
    "Correo electronico", "CURP", "RFC",
]
_CORPORATIVO_MORAL_BASE = [
    "nombre", "Actividad_generica", "Nacionalidad", "RFC", "Dirección",
    "Teléfono", "fecha_nacimiento", "firma electronica avanzada" # fecha = constitución
]
# En modalidad remota, persona moral exige adicionalmente correo electrónico.
_CORPORATIVO_MORAL_REMOTA = _CORPORATIVO_MORAL_BASE + ["Correo electronico"]
# Identificación oficial: número + tipo (INE, pasaporte, etc.).
_IDENTIFICACION = ["numero_identificacion", "tipo_identificacion"]
# Nivel 3 Limitada: requisito ÚNICO para ambos tipos de persona y ambas
# modalidades. Campos comunes a física y moral (sin los exclusivos de física
# como CURP/género, que igual se validan aparte) + identificación oficial.
_N3_LIMITADA = [
    "nombre", "fecha_nacimiento", "Nacionalidad", "Actividad_generica",
    "Dirección", "Teléfono", "Correo electronico", "RFC",
] + _IDENTIFICACION

REQUISITOS_BANCO = [
    # Nivel 1 y 2: exclusivos de persona física.
    _N("1", "fisica", "presencial", ["nombre", "fecha_nacimiento"]),
    # N1 remota exige adicionalmente respuesta de RENAPO.
    _N("1", "fisica", "remota",
       ["nombre", "genero", "entidad_federativa", "fecha_nacimiento", "Respuesta RENAPO"]),
    _N("2", "fisica", "presencial", ["nombre", "fecha_nacimiento", "Dirección"]),
    _N("2", "fisica", "remota",
       ["nombre", "genero", "entidad_federativa", "fecha_nacimiento", "Dirección"]),
    # Nivel 3: física y moral, diferenciados por modalidad. Remota exige
    # además respuesta de RENAPO (ambos tipos) y correo (persona moral).
    _N("3", "fisica", "presencial", _DEMOGRAFICOS_FISICA),
    _N("3", "fisica", "remota", _DEMOGRAFICOS_FISICA + ["Respuesta RENAPO"]),
    _N("3", "moral", "presencial", _CORPORATIVO_MORAL_BASE),
    _N("3", "moral", "remota", _CORPORATIVO_MORAL_REMOTA + ["Respuesta RENAPO"]),
    # Nivel 3 Limitada ("3L"): mismo requisito para ambos tipos de persona y
    # ambas modalidades de apertura.
    _N("3L", "ambos", "ambas", _N3_LIMITADA),
    # Nivel 4: física sin cambios por modalidad; moral exige correo solo en
    # remota (en presencial es opcional).
    _N("4", "fisica", "ambas", _DEMOGRAFICOS_FISICA),
    _N("4", "moral", "presencial", _CORPORATIVO_MORAL_BASE),
    _N("4", "moral", "remota", _CORPORATIVO_MORAL_REMOTA),
    # Nivel 4 Limitada ("4L"): mismos requisitos que N4 presencial (correo
    # opcional para persona moral) más geolocalización obligatoria.
    _N("4L", "fisica", "ambas", _DEMOGRAFICOS_FISICA + ["Geolocalización"]),
    _N("4L", "moral", "ambas", _CORPORATIVO_MORAL_BASE + ["Geolocalización"]),
]

# Campos requeridos para operaciones (identicos a core/mapper_operaciones.py)
CAMPOS_OPERACION = [
    "id_operacion", "id_cuenta", "id_cliente", "monto", "tipo_operacion",
    "instrumento_monetario", "fecha_operacion", "nivel_cuenta", "tipo de persona",
    # Saldo de la cuenta (para el tope de saldo en N1, en UDIS).
    "saldo",
]

# --- Límites de operación por nivel (montos) --- #
# Roles de campo de operación -> nombre lógico (para el motor de límites).
CAMPOS_LIMITES = {
    "fecha": "fecha_operacion", "monto": "monto", "cuenta": "id_cuenta",
    "cliente": "id_cliente", "nivel": "nivel_cuenta", "tipo_persona": "tipo de persona",
    "tipo_operacion": "tipo_operacion", "instrumento": "instrumento_monetario",
    "saldo": "saldo",
}
# Qué valores de tipo_operacion son ABONO y de instrumento son EFECTIVO.
VALORES_ABONO = ["IN", "ABONO", "DEPOSITO", "DEP", "ENTRADA", "CREDITO", "PAGO"]
VALORES_EFECTIVO = ["EFECTIVO", "CASH"]

_L = LimiteOperacion
LIMITES_BANCO = [
    # Abonos mensuales en UDIS. Nivel 1-2 solo física; 3 ambos; 4 sin límite.
    _L("abono_mensual", "1", "fisica", 750),
    _L("abono_mensual", "2", "fisica", 3000),
    _L("abono_mensual", "3", "ambos", 10000),
    _L("abono_mensual", "3L", "ambos", 10000),
    _L("abono_mensual", "4", "ambos", None),
    _L("abono_mensual", "4L", "ambos", 30000),
    # Efectivo en USD por tipo de persona (mensual por cliente).
    _L("efectivo_usd", "todos", "fisica", 4000),
    _L("efectivo_usd", "todos", "moral", 0),
    # Movimientos individuales en efectivo (abono/depósito/pago), en MXN.
    # Física "simple": 300,000; física con actividad empresarial, moral y
    # fideicomiso: 500,000.
    _L("efectivo_individual_mxn", "todos", "fisica", 300000),
    _L("efectivo_individual_mxn", "todos", "fisica_ae", 500000),
    _L("efectivo_individual_mxn", "todos", "moral", 500000),
    _L("efectivo_individual_mxn", "todos", "fideicomiso", 500000),
    # Efectivo mensual en MXN (todos los movimientos en efectivo, cualquier
    # sentido), tope único para todos los tipos de persona.
    _L("efectivo_mensual_mxn", "todos", "ambos", 1000000),
    # Operaciones relevantes: cargo o abono individual en efectivo cuyo
    # equivalente en USD sea >= al umbral, para cualquier tipo de persona.
    _L("operacion_relevante_usd", "todos", "ambos", 7500),
    # Saldo de cuenta en UDIS: solo Nivel 1.
    _L("saldo_udis", "1", "ambos", 1000),
]


def config_efectiva() -> dict:
    """Config de Banco vigente: overrides guardados por la UI si existen, si no
    las constantes de fábrica de este archivo. Reemplazo TOTAL por clave de
    nivel superior (no merge por entrada) — la usan tanto BancoValidador (para
    validar) como la UI (para precargar el editor)."""
    from . import registro
    overrides = registro.cargar_config_banco() or {}
    return {
        "requisitos_cliente": (
            [RequisitoNivel.from_dict(d) for d in overrides["requisitos_cliente"]]
            if "requisitos_cliente" in overrides else list(REQUISITOS_BANCO)),
        "limites_operacion": (
            [LimiteOperacion.from_dict(d) for d in overrides["limites_operacion"]]
            if "limites_operacion" in overrides else list(LIMITES_BANCO)),
        "valores_abono": overrides.get("valores_abono", list(VALORES_ABONO)),
        "valores_efectivo": overrides.get("valores_efectivo", list(VALORES_EFECTIVO)),
        "validator_config": {**_VALIDATOR_DEFAULT_CONFIG,
                            **overrides.get("validator_config", {})},
    }


class BancoValidador(ValidadorEntidad):
    nombre = "Banco"
    descripcion = ("Validaciones base para instituciones bancarias. "
                   "Usa la logica real de core/validator.py y core/validator_operaciones.py.")
    es_builtin = True
    requiere_tipo_persona = True
    requiere_config_operaciones = True

    def campos_cliente(self) -> list[str]:
        return list(CAMPOS_CLIENTE)

    def campos_operacion(self) -> list[str]:
        return list(CAMPOS_OPERACION)

    def tiene_limites_operacion(self) -> bool:
        return bool(LIMITES_BANCO)

    def validar_clientes(self, df: pd.DataFrame, mapeo: dict,
                         tipo_persona_default: str | None = None) -> dict:
        cfg = config_efectiva()
        errores, _ = Validator(df, mapeo, tipo_persona_default,
                               config=cfg["validator_config"]).validar_todo()
        hallazgos = validar_requisitos(df, mapeo, cfg["requisitos_cliente"],
                                       campo_nivel="Nivel_cuenta",
                                       campo_tipo_persona="tipo de persona",
                                       campo_modalidad="modalidad de apertura",
                                       default_tipo=_default_tipo(tipo_persona_default))
        if hallazgos:
            errores["Requisitos por Nivel"] = pd.DataFrame(hallazgos)
        return errores

    def validar_operaciones(self, df: pd.DataFrame, mapeo: dict,
                            config: dict | None = None) -> dict:
        config = config or {}
        errores, _ = ValidatorOperaciones(df, mapeo, config).validar_todo()
        errores.update(self._limites(df, mapeo, config).validar())
        return errores

    def _limites(self, df, mapeo, config) -> LimitesOperaciones:
        """Construye el validador de límites con los archivos de tasas del config."""
        cfg = config_efectiva()
        return LimitesOperaciones(
            df, mapeo, cfg["limites_operacion"], campos=CAMPOS_LIMITES,
            valores_abono=cfg["valores_abono"], valores_efectivo=cfg["valores_efectivo"],
            archivo_udis=config.get("archivo_udis"), mapeo_udis=config.get("mapeo_udis"),
            archivo_tc=config.get("archivo_tc"), mapeo_tc=config.get("mapeo_tc"))

    # --- Validación por lotes desde SQLite (grandes volúmenes) --- #
    def validar_clientes_sqlite(self, db_path: str, mapeo: dict,
                                tipo_persona_default: str | None = None,
                                progreso=None) -> dict:
        from core.sqlite_validator import SQLiteValidator
        cfg = config_efectiva()
        errores, _ = SQLiteValidator(
            db_path, mapeo, tipo_persona_default, progreso=progreso,
            requisitos=cfg["requisitos_cliente"], campo_nivel="Nivel_cuenta",
            campo_tipo_persona="tipo de persona", campo_modalidad="modalidad de apertura",
            default_tipo=_default_tipo(tipo_persona_default),
            validator_config=cfg["validator_config"]).validar_todo()
        return errores

    def validar_operaciones_sqlite(self, db_path: str, mapeo: dict,
                                   config: dict | None = None, progreso=None) -> dict:
        from core.sqlite_validator_operaciones import SQLiteValidatorOperaciones
        config = config or {}
        cfg = config_efectiva()
        limites_kwargs = dict(
            limites=cfg["limites_operacion"], campos=CAMPOS_LIMITES,
            valores_abono=cfg["valores_abono"], valores_efectivo=cfg["valores_efectivo"],
            archivo_udis=config.get("archivo_udis"), mapeo_udis=config.get("mapeo_udis"),
            archivo_tc=config.get("archivo_tc"), mapeo_tc=config.get("mapeo_tc"))
        errores, _ = SQLiteValidatorOperaciones(
            db_path, mapeo, config, progreso=progreso,
            limites_kwargs=limites_kwargs).validar_todo()
        return errores


def _default_tipo(tipo_persona_default: str | None) -> str:
    """Tipo por defecto para los niveles cuando 'tipo de persona' no está mapeado."""
    if tipo_persona_default and "moral" in tipo_persona_default.lower():
        return "moral"
    return "fisica"
