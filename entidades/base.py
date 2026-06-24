"""
Interfaz comun de una entidad financiera.

Dos implementaciones:
  - BancoValidador: envuelve tu codigo real (core.validator / core.validator_operaciones).
  - EntidadConfigurable: motor de reglas para entidades que crea el usuario desde la UI.

Ambas devuelven el mismo formato que ya usa tu pipeline:
    dict {categoria: DataFrame}  (igual que Validator.validar_todo)
para que core.report_generator.ReportGenerator funcione sin cambios.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class ValidadorEntidad(ABC):
    nombre: str = ""
    descripcion: str = ""
    es_builtin: bool = False
    # banca: pregunta tipo de persona si no esta mapeado
    requiere_tipo_persona: bool = False
    # banca: necesita config de operaciones (moneda, filtros, tasas)
    requiere_config_operaciones: bool = False

    @abstractmethod
    def campos_cliente(self) -> list[str]:
        ...

    @abstractmethod
    def campos_operacion(self) -> list[str]:
        ...

    @abstractmethod
    def validar_clientes(self, df: pd.DataFrame, mapeo: dict,
                         tipo_persona_default: str | None = None) -> dict:
        ...

    @abstractmethod
    def validar_operaciones(self, df: pd.DataFrame, mapeo: dict,
                            config: dict | None = None) -> dict:
        ...

    def tiene_limites_operacion(self) -> bool:
        """True si la entidad valida límites de monto por nivel (requiere cargar
        los archivos de tasas UDIS y tipo de cambio)."""
        return False

    # ------------------------------------------------------------------ #
    # Validación desde SQLite (grandes volúmenes divididos en varios archivos).
    # Implementación por defecto: lee toda la tabla y delega en el método normal.
    # Las entidades que sí saben procesar por lotes (Banco) lo sobreescriben.
    # ------------------------------------------------------------------ #
    def validar_clientes_sqlite(self, db_path: str, mapeo: dict,
                                tipo_persona_default: str | None = None,
                                progreso=None) -> dict:
        from core.multi_loader import leer_todo
        if progreso:
            progreso("Leyendo datos de clientes...")
        return self.validar_clientes(leer_todo(db_path), mapeo, tipo_persona_default)

    def validar_operaciones_sqlite(self, db_path: str, mapeo: dict,
                                   config: dict | None = None, progreso=None) -> dict:
        from core.multi_loader import leer_todo
        if progreso:
            progreso("Leyendo datos de operaciones...")
        return self.validar_operaciones(leer_todo(db_path), mapeo, config)
