"""Punto de entrada de la aplicacion (Flet)."""
import flet as ft

from ui.app import main

if __name__ == "__main__":
    # Flet >=0.80 usa ft.run; versiones previas, ft.app
    try:
        ft.run(main)
    except AttributeError:
        ft.app(target=main)
