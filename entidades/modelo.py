"""
Modelo de datos para entidades CONFIGURABLES (las que arma el usuario en la UI).
El Banco no usa esto: usa codigo (entidades/banco.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Condicion:
    """Condición de aplicación de una regla: 'aplica si [campo] [operador] [valor]'.

    Operadores: '=', '!=', 'contiene', 'no_contiene', 'vacio', 'no_vacio',
    'en_lista', 'no_en_lista' (valor = lista separada por comas). `campo` es
    el nombre lógico de OTRO campo de la misma entidad (resuelto vía
    Contexto.get en entidades/reglas.py).
    """
    campo: str
    operador: str
    valor: str = ""

    def to_dict(self) -> dict:
        return {"campo": self.campo, "operador": self.operador, "valor": self.valor}

    @classmethod
    def from_dict(cls, d: dict) -> "Condicion":
        return cls(campo=d["campo"], operador=d["operador"], valor=d.get("valor", ""))


@dataclass
class ReglaConfig:
    id: str
    parametros: dict[str, Any] = field(default_factory=dict)
    # Condiciones (AND) que gatean si la regla se evalúa en cada fila.
    # `condiciones_negar=True` niega el AND completo (De Morgan: permite
    # expresar "aplica salvo que se cumplan TODAS", p. ej. "opcional solo si
    # es persona moral Y extranjera").
    condiciones: list[Condicion] = field(default_factory=list)
    condiciones_negar: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "parametros": self.parametros,
                "condiciones": [c.to_dict() for c in self.condiciones],
                "condiciones_negar": self.condiciones_negar}

    @classmethod
    def from_dict(cls, d: dict) -> "ReglaConfig":
        return cls(id=d["id"], parametros=d.get("parametros", {}) or {},
                   condiciones=[Condicion.from_dict(c) for c in d.get("condiciones", [])],
                   condiciones_negar=bool(d.get("condiciones_negar", False)))


@dataclass
class CampoConfig:
    logico: str
    etiqueta: str = ""
    reglas: list[ReglaConfig] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"logico": self.logico, "etiqueta": self.etiqueta,
                "reglas": [r.to_dict() for r in self.reglas]}

    @classmethod
    def from_dict(cls, d: dict) -> "CampoConfig":
        return cls(logico=d["logico"], etiqueta=d.get("etiqueta", ""),
                   reglas=[ReglaConfig.from_dict(r) for r in d.get("reglas", [])])


@dataclass
class RequisitoNivel:
    """Campos obligatorios (no vacíos) para una combinación nivel/tipo/modalidad.

    - nivel: "1".."4"
    - tipo_persona: "fisica" | "moral" | "ambos"
    - modalidad: "presencial" | "remota" | "ambas"
    - campos: nombres lógicos de los campos que deben venir llenos.
    """
    nivel: str
    tipo_persona: str = "ambos"
    modalidad: str = "ambas"
    campos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"nivel": str(self.nivel), "tipo_persona": self.tipo_persona,
                "modalidad": self.modalidad, "campos": list(self.campos)}

    @classmethod
    def from_dict(cls, d: dict) -> "RequisitoNivel":
        return cls(nivel=str(d["nivel"]),
                   tipo_persona=d.get("tipo_persona", "ambos"),
                   modalidad=d.get("modalidad", "ambas"),
                   campos=list(d.get("campos", [])))


@dataclass
class LimiteOperacion:
    """Límite de monto mensual para operaciones, por nivel y tipo de persona.

    - concepto: "abono_mensual" (suma de abonos en UDIS) | "efectivo_usd"
      (suma de efectivo convertido a USD).
    - nivel: "1".."4" | "todos".
    - tipo_persona: "fisica" | "moral" | "ambos".
    - limite: tope permitido (en UDIS o USD según el concepto). None = sin límite
      (no se valida). 0 = prohibido (cualquier monto > 0 genera hallazgo).
    """
    concepto: str
    nivel: str = "todos"
    tipo_persona: str = "ambos"
    limite: float | None = None

    def to_dict(self) -> dict:
        return {"concepto": self.concepto, "nivel": str(self.nivel),
                "tipo_persona": self.tipo_persona, "limite": self.limite}

    @classmethod
    def from_dict(cls, d: dict) -> "LimiteOperacion":
        return cls(concepto=d["concepto"], nivel=str(d.get("nivel", "todos")),
                   tipo_persona=d.get("tipo_persona", "ambos"),
                   limite=d.get("limite"))


@dataclass
class EntidadConfig:
    nombre: str
    descripcion: str = ""
    campos_cliente: list[CampoConfig] = field(default_factory=list)
    campos_operacion: list[CampoConfig] = field(default_factory=list)
    # Requisitos por nivel de cuenta (clientes) y campos que los determinan.
    requisitos_cliente: list[RequisitoNivel] = field(default_factory=list)
    campo_nivel: str = ""            # campo lógico que contiene el nivel (1-4)
    campo_tipo_persona: str = ""     # campo lógico física/moral (opcional)
    campo_modalidad: str = ""        # campo lógico presencial/remota (opcional)
    # Sinónimos de nivel: {valor en los datos -> nivel canónico}, p. ej.
    # {"Tradicional": "4", "Básica": "2"}. Se suman a los reconocidos por defecto.
    aliases_nivel: dict[str, str] = field(default_factory=dict)
    # Límites de operación por nivel (montos). Requiere designar los campos de
    # operación (roles: fecha, monto, cuenta, cliente, nivel, tipo_persona,
    # tipo_operacion, instrumento -> nombre lógico) y qué valores cuentan como
    # abono / efectivo.
    limites_operacion: list[LimiteOperacion] = field(default_factory=list)
    op_campos: dict[str, str] = field(default_factory=dict)
    op_valores_abono: list[str] = field(default_factory=list)
    op_valores_efectivo: list[str] = field(default_factory=list)
    # Instrumento 'cheque de caja' (separado de efectivo) y valores de la
    # columna 'moneda' (rol "moneda" en op_campos) que indican dólares.
    op_valores_cheque_caja: list[str] = field(default_factory=list)
    op_valores_moneda_usd: list[str] = field(default_factory=list)
    # Activa el diálogo de configuración de operaciones estilo Banco (moneda/
    # agrupación/filtros de monto con operador libre), aun si la entidad no
    # define límites de operación por nivel.
    op_filtros_habilitado: bool = False

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "campos_cliente": [c.to_dict() for c in self.campos_cliente],
            "campos_operacion": [c.to_dict() for c in self.campos_operacion],
            "requisitos_cliente": [r.to_dict() for r in self.requisitos_cliente],
            "campo_nivel": self.campo_nivel,
            "campo_tipo_persona": self.campo_tipo_persona,
            "campo_modalidad": self.campo_modalidad,
            "aliases_nivel": dict(self.aliases_nivel),
            "limites_operacion": [l.to_dict() for l in self.limites_operacion],
            "op_campos": dict(self.op_campos),
            "op_valores_abono": list(self.op_valores_abono),
            "op_valores_efectivo": list(self.op_valores_efectivo),
            "op_valores_cheque_caja": list(self.op_valores_cheque_caja),
            "op_valores_moneda_usd": list(self.op_valores_moneda_usd),
            "op_filtros_habilitado": self.op_filtros_habilitado,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EntidadConfig":
        return cls(
            nombre=d["nombre"],
            descripcion=d.get("descripcion", ""),
            campos_cliente=[CampoConfig.from_dict(c) for c in d.get("campos_cliente", [])],
            campos_operacion=[CampoConfig.from_dict(c) for c in d.get("campos_operacion", [])],
            requisitos_cliente=[RequisitoNivel.from_dict(r) for r in d.get("requisitos_cliente", [])],
            campo_nivel=d.get("campo_nivel", ""),
            campo_tipo_persona=d.get("campo_tipo_persona", ""),
            campo_modalidad=d.get("campo_modalidad", ""),
            aliases_nivel=dict(d.get("aliases_nivel", {})),
            limites_operacion=[LimiteOperacion.from_dict(l) for l in d.get("limites_operacion", [])],
            op_campos=dict(d.get("op_campos", {})),
            op_valores_abono=list(d.get("op_valores_abono", [])),
            op_valores_efectivo=list(d.get("op_valores_efectivo", [])),
            op_valores_cheque_caja=list(d.get("op_valores_cheque_caja", [])),
            op_valores_moneda_usd=list(d.get("op_valores_moneda_usd", [])),
            op_filtros_habilitado=bool(d.get("op_filtros_habilitado", False)),
        )
