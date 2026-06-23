"""
Registro de entidades: Banco (codigo) + entidades del usuario (JSON en entidades/usuario/).
Todas se entregan como instancias de ValidadorEntidad.
"""
from __future__ import annotations

import json
import os
import re

from .base import ValidadorEntidad
from .banco import BancoValidador
from .configurable import EntidadConfigurable
from .modelo import EntidadConfig

DIR_USUARIO = os.path.join(os.path.dirname(__file__), "usuario")

_BUILTINS: dict[str, type] = {"Banco": BancoValidador}


def _slug(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")


def _asegurar_dir():
    os.makedirs(DIR_USUARIO, exist_ok=True)


def listar_entidades() -> list[str]:
    nombres = list(_BUILTINS.keys())
    _asegurar_dir()
    for f in sorted(os.listdir(DIR_USUARIO)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(DIR_USUARIO, f), encoding="utf-8") as fh:
                    nombre = json.load(fh).get("nombre")
                if nombre and nombre not in nombres:
                    nombres.append(nombre)
            except (json.JSONDecodeError, OSError):
                continue
    return nombres


def cargar_entidad(nombre: str) -> ValidadorEntidad:
    if nombre in _BUILTINS:
        return _BUILTINS[nombre]()
    _asegurar_dir()
    ruta = os.path.join(DIR_USUARIO, f"{_slug(nombre)}.json")
    if not os.path.exists(ruta):
        for f in os.listdir(DIR_USUARIO):
            if f.endswith(".json"):
                with open(os.path.join(DIR_USUARIO, f), encoding="utf-8") as fh:
                    d = json.load(fh)
                if d.get("nombre") == nombre:
                    return EntidadConfigurable(EntidadConfig.from_dict(d))
        raise KeyError(f"Entidad no encontrada: {nombre}")
    with open(ruta, encoding="utf-8") as fh:
        return EntidadConfigurable(EntidadConfig.from_dict(json.load(fh)))


def guardar_entidad(config: EntidadConfig) -> str:
    if config.nombre in _BUILTINS:
        raise ValueError(f"'{config.nombre}' es una entidad predefinida.")
    _asegurar_dir()
    ruta = os.path.join(DIR_USUARIO, f"{_slug(config.nombre)}.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(config.to_dict(), fh, ensure_ascii=False, indent=2)
    return ruta


def eliminar_entidad(nombre: str) -> bool:
    if nombre in _BUILTINS:
        return False
    ruta = os.path.join(DIR_USUARIO, f"{_slug(nombre)}.json")
    if os.path.exists(ruta):
        os.remove(ruta)
        return True
    return False
