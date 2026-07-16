"""Plantilla de entidad configurable equivalente a Banco.

Traduce las validaciones "de fábrica" de Banco (core/validator.py +
entidades/banco.py: CHECKS_CAMPO/CHECKS_GENERALES, REQUISITOS_BANCO,
LIMITES_BANCO) al catálogo de reglas genérico (entidades/reglas.py), usando
condiciones donde Banco distingue por tipo de persona o por "extranjero".

Sirve para dos cosas (una sola fuente de verdad para ambas):
  - "Empezar desde plantilla de Banco" en el constructor de entidades: precarga
    campos/reglas listos para renombrar/editar en vez de armar todo desde cero.
  - El diálogo "Ver catálogo de validaciones" usa esta misma función para
    mostrar, campo por campo, qué reglas equivalen a las de Banco.

No es una réplica exacta 1:1 (algunas condiciones de Banco, como "extranjero",
se aproximan combinando 'tipo de persona' y 'Pais_nacimiento' — ver
[[project-paridad-banco-configurables]] en la memoria del proyecto para el
detalle de las limitaciones conocidas).
"""
from __future__ import annotations

from .banco import (
    CAMPOS_CLIENTE, CAMPOS_OPERACION, REQUISITOS_BANCO, LIMITES_BANCO,
    CAMPOS_LIMITES, VALORES_ABONO, VALORES_EFECTIVO, VALORES_CHEQUE_CAJA,
    VALORES_MONEDA_USD,
)
from .modelo import EntidadConfig, CampoConfig, ReglaConfig, Condicion

TIPO_PERSONA = "tipo de persona"
_MX = "Mexico,Mexicana,Mex,MX"

COND_FISICA = [Condicion(TIPO_PERSONA, "no_contiene", "moral")]
COND_MORAL = [Condicion(TIPO_PERSONA, "contiene", "moral")]
COND_MORAL_EXTRANJERA = [Condicion(TIPO_PERSONA, "contiene", "moral"),
                         Condicion("Pais_nacimiento", "no_en_lista", _MX)]
COND_MORAL_NACIONAL = [Condicion(TIPO_PERSONA, "contiene", "moral"),
                       Condicion("Pais_nacimiento", "en_lista", _MX)]


def _r(rid, parametros=None, condiciones=None, negar=False) -> ReglaConfig:
    return ReglaConfig(id=rid, parametros=parametros or {},
                       condiciones=condiciones or [], condiciones_negar=negar)


def _campo(logico: str, *reglas: ReglaConfig) -> CampoConfig:
    return CampoConfig(logico=logico, reglas=list(reglas))


def plantilla_banco() -> EntidadConfig:
    """EntidadConfig equivalente a Banco, construida con el catálogo genérico.

    `nombre` queda vacío a propósito: al guardar, la UI exige ponerle nombre
    (así nunca se confunde con la entidad Banco de verdad ni se sobrescribe)."""
    campos_cliente = [
        _campo("id_cliente", _r("no_vacio"), _r("unico")),
        _campo("nombre", _r("no_vacio"), _r("al_menos_un_espacio", condiciones=COND_FISICA)),
        _campo("apellido_paterno",
               _r("al_menos_uno_de", {"campos": ["apellido_materno"]}, COND_FISICA)),
        _campo("apellido_materno"),
        _campo("fecha_nacimiento",
               _r("no_vacio"), _r("fecha_valida"), _r("fecha_no_futura"),
               _r("edad_entre", {"min_anios": 18, "max_anios": 110}, COND_FISICA)),
        _campo("genero", _r("no_vacio", condiciones=COND_FISICA)),
        _campo(TIPO_PERSONA, _r("no_vacio")),
        _campo("estatus_cliente", _r("no_vacio")),
        _campo("fecha_inicio_relacion", _r("no_vacio"), _r("fecha_valida"), _r("fecha_no_futura")),
        _campo("fecha_termino_relacion",
               _r("fecha_no_anterior_a", {"campo_referencia": "fecha_inicio_relacion"}),
               _r("debe_estar_vacio",
                  condiciones=[Condicion("estatus_cliente", "contiene", "activo")])),
        _campo("grado_riesgo", _r("no_vacio")),
        _campo("fecha_riesgo", _r("no_vacio"), _r("fecha_valida")),
        _campo("PEP", _r("no_vacio")),
        _campo("Nacionalidad", _r("no_vacio")),
        _campo("Pais_nacimiento", _r("no_vacio"), _r("pais_valido")),
        _campo("entidad_federativa",
               _r("entidad_federativa_mx"),
               _r("consistencia_nacimiento",
                  {"campo_pais": "Pais_nacimiento", "campo_nacionalidad": "Nacionalidad"})),
        _campo("Actividad_generica",
               _r("al_menos_uno_de", {"campos": ["Actividad_especifica"]})),
        _campo("Actividad_especifica"),
        _campo("Teléfono", _r("min_digitos", {"minimo": 10}),
               _r("sin_repetidos_consecutivos", {"cantidad": 5})),
        _campo("Correo electronico",
               _r("no_vacio", condiciones=COND_MORAL_EXTRANJERA, negar=True),
               _r("contiene", {"subcadena": "@"})),
        _campo("CURP",
               _r("curp", condiciones=COND_FISICA),
               _r("unico"),
               _r("mismo_valor_en", {"campo_referencia": "nombre"})),
        _campo("RFC",
               _r("rfc", {"tipo_persona": "fisica"}, COND_FISICA),
               _r("rfc", {"tipo_persona": "moral"}, COND_MORAL_NACIONAL),
               _r("unico")),
        # "Dirección" (columna única): de esta depende REQUISITOS_BANCO (niveles
        # de cuenta). Las columnas divididas de abajo son una validación APARTE
        # y más detallada, igual que en Banco (ambas pueden mapearse a la vez).
        _campo("Dirección", _r("min_separadores", {"minimo": 5})),
        _campo("calle_avenida_via",
               _r("direccion_completa", {
                   "campos_obligatorios": ["numero_exterior", "entidad_federativa_estado",
                                           "codigo_postal", "pais"],
                   "campos_ciudad_alcaldia": ["ciudad_poblacion", "alcaldia_municipio"],
               })),
        _campo("numero_exterior"), _campo("numero_interior"),
        _campo("colonia_urbanizacion"), _campo("alcaldia_municipio"),
        _campo("ciudad_poblacion"), _campo("entidad_federativa_estado"),
        _campo("codigo_postal"), _campo("pais"),
        _campo("numero_identificacion"), _campo("tipo_identificacion"),
        _campo("firma electronica avanzada",
               _r("solo_numeros"), _r("longitud_exacta", {"longitud": 20}), _r("unico")),
        _campo("representante_legal",
               _r("no_vacio", condiciones=COND_MORAL),
               _r("al_menos_un_espacio", condiciones=COND_MORAL)),
        _campo("numero_identificacion_fiscal",
               _r("no_vacio", condiciones=COND_MORAL_EXTRANJERA)),
        _campo("pais_asignacion_rfc",
               _r("no_vacio", condiciones=COND_MORAL_EXTRANJERA),
               _r("pais_valido", condiciones=COND_MORAL_EXTRANJERA)),
        _campo("numero_serie_firma"),
        _campo("Nivel_cuenta", _r("no_vacio")),
        _campo("modalidad de apertura"),
        _campo("Respuesta RENAPO"), _campo("Geolocalización"),
    ]
    # Todo campo listado en CAMPOS_CLIENTE que no se referenció arriba, para
    # que quede disponible en el mapeo aunque no tenga reglas propias.
    ya = {c.logico for c in campos_cliente}
    campos_cliente += [_campo(c) for c in CAMPOS_CLIENTE if c not in ya]

    campos_operacion = [_campo("id_operacion", _r("no_vacio"), _r("unico"))]
    ya_op = {c.logico for c in campos_operacion}
    campos_operacion += [_campo(c) for c in CAMPOS_OPERACION if c not in ya_op]

    return EntidadConfig(
        nombre="", descripcion="Plantilla equivalente a Banco (renombrar antes de guardar).",
        campos_cliente=campos_cliente, campos_operacion=campos_operacion,
        requisitos_cliente=list(REQUISITOS_BANCO),
        campo_nivel="Nivel_cuenta", campo_tipo_persona=TIPO_PERSONA,
        campo_modalidad="modalidad de apertura",
        limites_operacion=list(LIMITES_BANCO), op_campos=dict(CAMPOS_LIMITES),
        op_valores_abono=list(VALORES_ABONO), op_valores_efectivo=list(VALORES_EFECTIVO),
        op_valores_cheque_caja=list(VALORES_CHEQUE_CAJA),
        op_valores_moneda_usd=list(VALORES_MONEDA_USD),
        op_filtros_habilitado=True,
    )
