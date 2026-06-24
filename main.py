"""Punto de entrada de la aplicacion (Flet)."""
import os
import sys

# Asegura que la carpeta del proyecto esté en sys.path para que 'core',
# 'entidades' y 'ui' se importen sin importar desde dónde se lance la app
# (terminal, IDE, doble clic o 'flet run').
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flet as ft

from ui.app import main

if __name__ == "__main__":
    # Flet >=0.80 usa ft.run; versiones previas, ft.app
    try:
        ft.run(main)
    except AttributeError:
        ft.app(target=main)
