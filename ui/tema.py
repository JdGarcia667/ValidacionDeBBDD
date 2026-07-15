"""Paleta de marca de la app (logo en assets/logo.png: fondo negro, ámbar y gris)."""
from __future__ import annotations

import flet as ft

AMBAR = "#EFAF1E"
GRIS = "#636567"
NEGRO = "#000000"
# Tintes derivados para texto/bordes legibles sobre fondo oscuro (el ámbar y el
# gris de marca, tal cual, no siempre dan suficiente contraste para texto chico).
TEXTO_MUTED = "#A8ABAE"   # gris de marca aclarado, para texto secundario
BORDE = "#3A3B3D"         # gris de marca oscurecido, para bordes sutiles


def aplicar_tema(page: ft.Page) -> None:
    """Tema oscuro con los colores de la empresa (fondo negro, acentos ámbar/gris)."""
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = NEGRO
    tema = ft.Theme(
        color_scheme_seed=AMBAR,
        color_scheme=ft.ColorScheme(
            primary=AMBAR, on_primary=NEGRO,
            secondary=GRIS, on_secondary="#FFFFFF",
            surface=NEGRO, on_surface="#FFFFFF",
        ),
        scaffold_bgcolor=NEGRO,
    )
    page.theme = tema
    page.dark_theme = tema
    page.window.bgcolor = NEGRO
    # page.window.icon requiere específicamente un .ico (ver flet.controls.core
    # .window.Window.icon: "The file should have the `.ico` extension.
    # Limitation: Has effect on Windows only."). Un .png ahí se ignora en
    # silencio: por eso no se veía en la ventana ni en la barra de tareas.
    page.window.icon = "logo.ico"
