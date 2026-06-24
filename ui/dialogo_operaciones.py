"""
Dialogo de configuracion de operaciones (para entidades que lo requieren, como el Banco).
Construye el dict 'config' que espera core.validator_operaciones.ValidatorOperaciones:
    {moneda, agrupacion, filtros, archivo_udis, archivo_tc, mapeo_udis, mapeo_tc}
"""
from __future__ import annotations

import flet as ft
import pandas as pd


class ConfigOperacionesDialog:
    def __init__(self, page: ft.Page, al_confirmar, requiere_tasas: bool = False):
        self.page = page
        self.al_confirmar = al_confirmar
        # Si la entidad valida límites por nivel, se necesitan SIEMPRE ambos
        # archivos de tasas (UDIS y tipo de cambio), independientemente de la
        # moneda de análisis elegida.
        self.requiere_tasas = requiere_tasas
        self.filtros: list[tuple[str, float]] = []
        self.archivo_udis = None
        self.archivo_tc = None
        self.mapeo_udis = None
        self.mapeo_tc = None

        # FilePicker (Flet 0.85: servicios async; pick_files devuelve el resultado).
        self.fp_udis = ft.FilePicker()
        self.fp_tc = ft.FilePicker()
        page.services.extend([self.fp_udis, self.fp_tc])

    # ------------------------------------------------------------------ #
    def abrir(self):
        # RadioGroup sin on_change en constructor (mejor prevenir)
        self.moneda = ft.RadioGroup(
            value="MONEDA NACIONAL",
            content=ft.Column([ft.Radio(value=v, label=v)
                               for v in ["MONEDA NACIONAL", "UDIS", "DOLARES"]]),
        )
        self.moneda.on_change = lambda e: self._toggle_tasas()

        self.agrupacion = ft.RadioGroup(
            value="por_instrumento",
            content=ft.Column([
                ft.Radio(value="por_instrumento", label="Agrupar por instrumento"),
                ft.Radio(value="todas", label="Agrupar todas las operaciones"),
            ]),
        )

        self.op_filtro = ft.Dropdown(width=80, value=">",
                                     options=[ft.dropdown.Option(o) for o in [">", "<", ">=", "<="]])
        self.val_filtro = ft.TextField(label="Monto", width=140)
        self.lista_filtros = ft.Column(spacing=2)

        self.udis_status = ft.Text("", size=11, color=ft.Colors.GREY_700)
        self.tc_status = ft.Text("", size=11, color=ft.Colors.GREY_700)
        self.fila_udis = ft.Row([
            ft.ElevatedButton("Archivo UDIS", icon=ft.Icons.UPLOAD_FILE,
                              on_click=lambda e: self.page.run_task(self._cargar_tasa, "udis")),
            self.udis_status], visible=False)
        self.fila_tc = ft.Row([
            ft.ElevatedButton("Archivo tipo de cambio", icon=ft.Icons.UPLOAD_FILE,
                              on_click=lambda e: self.page.run_task(self._cargar_tasa, "tc")),
            self.tc_status], visible=False)
        if self.requiere_tasas:                      # límites por nivel: ambos siempre
            self.fila_udis.visible = True
            self.fila_tc.visible = True

        nota_tasas = ft.Text(
            "Esta entidad valida límites por nivel: carga el archivo de UDIS (para "
            "abonos) y el de tipo de cambio (para efectivo en USD).",
            size=11, italic=True, color=ft.Colors.BLUE_700,
            visible=self.requiere_tasas)

        contenido = ft.Container(width=560, content=ft.Column([
            ft.Text("Moneda de analisis", weight=ft.FontWeight.BOLD),
            self.moneda,
            nota_tasas, self.fila_udis, self.fila_tc,
            ft.Divider(),
            ft.Text("Agrupacion", weight=ft.FontWeight.BOLD),
            self.agrupacion,
            ft.Divider(),
            ft.Text("Filtros de monto (sobre el total agrupado)", weight=ft.FontWeight.BOLD),
            ft.Text("Sin filtros no se generan hallazgos de operaciones.",
                    size=11, italic=True, color=ft.Colors.GREY_700),
            ft.Row([self.op_filtro, self.val_filtro,
                    ft.IconButton(ft.Icons.ADD_CIRCLE, on_click=lambda e: self._agregar_filtro())]),
            self.lista_filtros,
        ], scroll=ft.ScrollMode.AUTO, height=460))

        self.dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Configuracion de operaciones"),
            content=contenido,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(cancelado=True)),
                ft.FilledButton("Confirmar", on_click=lambda e: self._confirmar()),
            ],
        )
        self._abrir(self.dlg)

    # ------------------------------------------------------------------ #
    def _toggle_tasas(self):
        m = self.moneda.value
        # Con límites por nivel ambos archivos quedan visibles siempre.
        self.fila_udis.visible = self.requiere_tasas or m == "UDIS"
        self.fila_tc.visible = self.requiere_tasas or m == "DOLARES"
        self.page.update()

    def _agregar_filtro(self):
        try:
            val = float((self.val_filtro.value or "").replace(",", "").strip())
        except ValueError:
            self._toast("El monto del filtro debe ser numerico.")
            return
        op = self.op_filtro.value
        self.filtros.append((op, val))
        self.lista_filtros.controls.append(ft.Text(f"total_monto {op} {val}"))
        self.val_filtro.value = ""
        self.page.update()

    async def _cargar_tasa(self, cual: str):
        fp = self.fp_udis if cual == "udis" else self.fp_tc
        files = await fp.pick_files(allow_multiple=False,
                                    allowed_extensions=["xlsx", "xls"])
        if not files:
            return
        ruta = files[0].path
        try:
            cols = list(pd.read_excel(ruta, nrows=5).columns)
        except Exception as ex:                       # noqa: BLE001
            self._toast(f"No se pudo leer el archivo: {ex}")
            return
        self._mapear_tasa(cual, ruta, cols)

    def _mapear_tasa(self, cual: str, ruta: str, cols: list):
        dd_fecha = ft.Dropdown(label="Columna FECHA", width=240,
                               options=[ft.dropdown.Option(c) for c in cols])
        dd_valor = ft.Dropdown(label="Columna VALOR", width=240,
                               options=[ft.dropdown.Option(c) for c in cols])

        def aceptar(e):
            if not dd_fecha.value or not dd_valor.value:
                self._toast("Selecciona ambas columnas.")
                return
            mapeo = {"fecha": dd_fecha.value, "valor": dd_valor.value}
            if cual == "udis":
                self.archivo_udis, self.mapeo_udis = ruta, mapeo
                self.udis_status.value = "Cargado ✓"
            else:
                self.archivo_tc, self.mapeo_tc = ruta, mapeo
                self.tc_status.value = "Cargado ✓"
            self._cerrar_secundario()
            self.page.update()

        self.dlg2 = ft.AlertDialog(
            modal=True, title=ft.Text(f"Mapear columnas — {cual.upper()}"),
            content=ft.Column([dd_fecha, dd_valor], tight=True),
            actions=[ft.FilledButton("Aceptar", on_click=aceptar),
                     ft.TextButton("Cancelar", on_click=lambda e: self._cerrar_secundario())],
        )
        self._abrir(self.dlg2)

    def _confirmar(self):
        m = self.moneda.value
        if m == "UDIS" and not self.archivo_udis:
            self._toast("Para UDIS carga el archivo de valores UDIS.")
            return
        if m == "DOLARES" and not self.archivo_tc:
            self._toast("Para DOLARES carga el archivo de tipo de cambio.")
            return
        if self.requiere_tasas and not (self.archivo_udis and self.archivo_tc):
            self._toast("Esta entidad valida límites por nivel: carga ambos archivos "
                        "(UDIS y tipo de cambio).")
            return
        config = {
            "moneda": m,
            "agrupacion": self.agrupacion.value,
            "filtros": self.filtros,
            "archivo_udis": self.archivo_udis,
            "archivo_tc": self.archivo_tc,
            "mapeo_udis": self.mapeo_udis,
            "mapeo_tc": self.mapeo_tc,
        }
        self._cerrar()
        self.al_confirmar(config)

    # ------------------------------------------------------------------ #
    def _abrir(self, dlg):
        self.page.show_dialog(dlg)

    def _cerrar(self, cancelado=False):
        self.page.pop_dialog()
        if cancelado:
            self.al_confirmar(None)

    def _cerrar_secundario(self):
        self.page.pop_dialog()

    def _toast(self, msg):
        self.page.show_dialog(ft.SnackBar(ft.Text(msg)))