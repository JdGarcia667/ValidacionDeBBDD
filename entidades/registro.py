"""
Registro de entidades: Banco (codigo) + entidades del usuario (JSON en entidades/usuario/).
Todas se entregan como instancias de ValidadorEntidad.
"""
from __future__ import annotations

import json
import os
import re
import sys

from .base import ValidadorEntidad
from .banco import BancoValidador
from .configurable import EntidadConfigurable
from .modelo import EntidadConfig


def _dir_usuario() -> str:
    """Carpeta donde se guardan las entidades del usuario (JSON) y el override
    de Banco. En desarrollo, junto al código (entidades/usuario/), igual que
    siempre. Empaquetada con PyInstaller (`flet pack`), `__file__` apunta a una
    carpeta temporal que se recrea/descarta en cada arranque — ahí se perdería
    todo lo guardado. En ese caso se usa una carpeta persistente del usuario
    (%APPDATA% en Windows, ~/.validaciondebbdd en otros sistemas)."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ValidacionDeBBDD", "usuario")
    return os.path.join(os.path.dirname(__file__), "usuario")


DIR_USUARIO = _dir_usuario()
# Archivo especial de overrides de Banco (no es una entidad seleccionable: no
# lleva clave "nombre" y su archivo empieza con "_", excluido explícitamente
# en listar_entidades()).
ARCHIVO_CONFIG_BANCO = os.path.join(DIR_USUARIO, "_banco_config.json")

_BUILTINS: dict[str, type] = {"Banco": BancoValidador}


def _slug(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")


def _asegurar_dir():
    os.makedirs(DIR_USUARIO, exist_ok=True)


def listar_entidades() -> list[str]:
    nombres = list(_BUILTINS.keys())
    _asegurar_dir()
    for f in sorted(os.listdir(DIR_USUARIO)):
        if f.startswith("_"):
            continue
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


# --------------------------------------------------------------------------- #
# Overrides de Banco: requisitos por nivel, límites de operación y parámetros
# de Validator, editables desde la UI sin tocar entidades/banco.py.
# --------------------------------------------------------------------------- #
def cargar_config_banco() -> dict | None:
    """None si no hay overrides guardados (se usa el comportamiento de fábrica)."""
    if not os.path.exists(ARCHIVO_CONFIG_BANCO):
        return None
    try:
        with open(ARCHIVO_CONFIG_BANCO, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def guardar_config_banco(data: dict) -> None:
    _asegurar_dir()
    with open(ARCHIVO_CONFIG_BANCO, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def restaurar_config_banco() -> None:
    """Borra los overrides: Banco vuelve a su comportamiento de fábrica."""
    if os.path.exists(ARCHIVO_CONFIG_BANCO):
        os.remove(ARCHIVO_CONFIG_BANCO)
