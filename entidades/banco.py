"""
Entidad BANCO: envuelve tu codigo real, sin reimplementarlo.

Los campos logicos son exactamente los que esperan tus clases (Mapper.CAMPOS_REQUERIDOS
y MapperOperaciones.CAMPOS_REQUERIDOS), para que el mapeo {campo: columna_real}
llegue tal cual a Validator / ValidatorOperaciones.
"""
from __future__ import annotations

import pandas as pd

import pandas as pd

from core.validator import Validator
from core.validator_operaciones import ValidatorOperaciones
from core.niveles import validar_requisitos
from core.limites_operaciones import LimitesOperaciones
from .base import ValidadorEntidad
from .modelo import RequisitoNivel, LimiteOperacion


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
    # Domicilio dividido en columnas (opcional; alternativa a 'Dirección').
    "calle_avenida_via", "numero_exterior", "numero_interior",
    "colonia_urbanizacion", "alcaldia_municipio", "ciudad_poblacion",
    "entidad_federativa_estado", "codigo_postal", "pais",
    "Nivel_cuenta", "modalidad de apertura",
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
_CORPORATIVO_MORAL = [
    "nombre", "Actividad_generica", "Nacionalidad", "RFC", "Dirección",
    "Teléfono", "Correo electronico", "fecha_nacimiento",  # fecha = constitución
]
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
    _N("1", "fisica", "remota", ["nombre", "genero", "entidad_federativa", "fecha_nacimiento"]),
    _N("2", "fisica", "presencial", ["nombre", "fecha_nacimiento", "Dirección"]),
    _N("2", "fisica", "remota",
       ["nombre", "genero", "entidad_federativa", "fecha_nacimiento", "Dirección"]),
    # Nivel 3 y 4: física y moral. En columnas de BBDD ambos niveles coinciden
    # (sus diferencias en el marco son documentales, no de datos).
    _N("3", "fisica", "ambas", _DEMOGRAFICOS_FISICA),
    _N("3", "moral", "ambas", _CORPORATIVO_MORAL),
    # Nivel 3 Limitada ("3L"): mismo requisito para ambos tipos de persona y
    # ambas modalidades de apertura.
    _N("3L", "ambos", "ambas", _N3_LIMITADA),
    _N("4", "fisica", "ambas", _DEMOGRAFICOS_FISICA),
    _N("4", "moral", "ambas", _CORPORATIVO_MORAL),
]

# Campos requeridos para operaciones (identicos a core/mapper_operaciones.py)
CAMPOS_OPERACION = [
    "id_operacion", "id_cuenta", "id_cliente", "monto", "tipo_operacion",
    "instrumento_monetario", "fecha_operacion", "nivel_cuenta", "tipo de persona",
]

# --- Límites de operación por nivel (montos) --- #
# Roles de campo de operación -> nombre lógico (para el motor de límites).
CAMPOS_LIMITES = {
    "fecha": "fecha_operacion", "monto": "monto", "cuenta": "id_cuenta",
    "cliente": "id_cliente", "nivel": "nivel_cuenta", "tipo_persona": "tipo de persona",
    "tipo_operacion": "tipo_operacion", "instrumento": "instrumento_monetario",
}
# Qué valores de tipo_operacion son ABONO y de instrumento son EFECTIVO.
VALORES_ABONO = ["IN", "ABONO", "DEPOSITO", "DEP", "ENTRADA", "CREDITO"]
VALORES_EFECTIVO = ["EFECTIVO", "CASH"]

_L = LimiteOperacion
LIMITES_BANCO = [
    # Abonos mensuales en UDIS. Nivel 1-2 solo física; 3 ambos; 4 sin límite.
    _L("abono_mensual", "1", "fisica", 750),
    _L("abono_mensual", "2", "fisica", 3000),
    _L("abono_mensual", "3", "ambos", 10000),
    _L("abono_mensual", "4", "ambos", None),
    # Efectivo en USD por tipo de persona (mensual por cliente).
    _L("efectivo_usd", "todos", "fisica", 4000),
    _L("efectivo_usd", "todos", "moral", 0),
]


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
        errores, _ = Validator(df, mapeo, tipo_persona_default).validar_todo()
        hallazgos = validar_requisitos(df, mapeo, REQUISITOS_BANCO,
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
        return LimitesOperaciones(
            df, mapeo, LIMITES_BANCO, campos=CAMPOS_LIMITES,
            valores_abono=VALORES_ABONO, valores_efectivo=VALORES_EFECTIVO,
            archivo_udis=config.get("archivo_udis"), mapeo_udis=config.get("mapeo_udis"),
            archivo_tc=config.get("archivo_tc"), mapeo_tc=config.get("mapeo_tc"))

    # --- Validación por lotes desde SQLite (grandes volúmenes) --- #
    def validar_clientes_sqlite(self, db_path: str, mapeo: dict,
                                tipo_persona_default: str | None = None,
                                progreso=None) -> dict:
        from core.sqlite_validator import SQLiteValidator
        errores, _ = SQLiteValidator(
            db_path, mapeo, tipo_persona_default, progreso=progreso,
            requisitos=REQUISITOS_BANCO, campo_nivel="Nivel_cuenta",
            campo_tipo_persona="tipo de persona", campo_modalidad="modalidad de apertura",
            default_tipo=_default_tipo(tipo_persona_default)).validar_todo()
        return errores

    def validar_operaciones_sqlite(self, db_path: str, mapeo: dict,
                                   config: dict | None = None, progreso=None) -> dict:
        from core.sqlite_validator_operaciones import SQLiteValidatorOperaciones
        config = config or {}
        limites_kwargs = dict(
            limites=LIMITES_BANCO, campos=CAMPOS_LIMITES,
            valores_abono=VALORES_ABONO, valores_efectivo=VALORES_EFECTIVO,
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
