"""
UI principal (Flet) de Validacion de BBDD.

Flujo:
  1) Eliges entidad (Banco u otra creada por ti).
  2) Cargas clientes y/o operaciones (CSV/Excel).
  3) Revisas/ajustas el mapeo (campo lógico -> columna real), auto-sugerido.
  4) Validar:
       - clientes: si la entidad lo requiere y no mapeaste 'tipo de persona', se pregunta.
       - operaciones: si la entidad lo requiere, se abre la config (moneda/filtros/tasas).
  5) Ves los hallazgos por hoja y exportas el Excel (core.report_generator).

Tambien puedes crear entidades nuevas con su propio catalogo de reglas.
"""
from __future__ import annotations

import asyncio
import os
import traceback

import flet as ft
import pandas as pd

from entidades.registro import (
    listar_entidades, cargar_entidad, guardar_entidad, eliminar_entidad,
)
from entidades.mapeo import auto_mapear
from entidades.modelo import (
    EntidadConfig, CampoConfig, ReglaConfig, RequisitoNivel, LimiteOperacion, Condicion,
)
from entidades.reglas import CATALOGO, OPERADORES_CONDICION
from entidades.plantillas import plantilla_banco
from core.report_generator import ReportGenerator
from core import multi_loader as ml
from ui.dialogo_operaciones import ConfigOperacionesDialog
from ui.tema import AMBAR, TEXTO_MUTED, BORDE, aplicar_tema

NO_MAPEAR = "(no mapear)"

UNIDAD_LIMITE = {
    "abono_mensual": "UDIS", "efectivo_usd": "USD", "efectivo_mensual_mxn": "MXN",
    "efectivo_individual_mxn": "MXN", "operacion_relevante_usd": "USD",
    "efectivo_abono_usd_individual": "USD", "cheque_caja_usd": "USD",
    "saldo_udis": "UDIS",
}


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        page.title = "Validacion de BBDD"
        aplicar_tema(page)
        # Un poco más de espacio arriba: la etiqueta flotante del Dropdown
        # "Entidad financiera" del header queda casi pegada al borde superior
        # y se recorta contra la barra de título con solo el padding parejo.
        page.padding = ft.Padding(18, 28, 18, 18)

        self.entidad = None
        # df_cli/df_ops: DataFrame completo (memoria) o muestra (modo SQLite) o None.
        self.df_cli = None
        self.df_ops = None
        # db_cli/db_ops: ruta a la base SQLite temporal cuando se usa ese modo.
        self.db_cli = None
        self.db_ops = None
        self.total_cli = 0
        self.total_ops = 0
        self._progreso_msg = ""
        self.map_cli_dd: dict[str, ft.Dropdown] = {}
        self.map_ops_dd: dict[str, ft.Dropdown] = {}
        self.hallazgos: dict[str, pd.DataFrame] = {}
        # Nombre original de la entidad configurable que se está editando (None
        # si el constructor está creando una nueva). Permite borrar el JSON
        # viejo si se guarda con un nombre distinto (renombrar).
        self._editando_nombre_original: str | None = None

        # File pickers (Flet 0.85: son servicios y pick_files/save_file son
        # corutinas que devuelven el resultado; no hay on_result).
        self.fp_cli = ft.FilePicker()
        self.fp_ops = ft.FilePicker()
        self.fp_export = ft.FilePicker()
        page.services.extend([self.fp_cli, self.fp_ops, self.fp_export])

        # Limpia las bases SQLite temporales al cerrar la aplicación.
        page.on_close = lambda e: self._limpiar_temporales()

        self._construir()

    def _limpiar_temporales(self):
        ml.eliminar_db(self.db_cli)
        ml.eliminar_db(self.db_ops)

    # ================================================================== #
    # Construccion de la pantalla
    # ================================================================== #
    def _construir(self):
        # Dropdown sin on_change en constructor
        self.dd_entidad = ft.Dropdown(label="Entidad financiera", width=260)
        self.dd_entidad.on_select = lambda e: self._seleccionar_entidad(e.control.value)

        self.btn_eliminar = ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar entidad",
                                          on_click=lambda e: self._eliminar_entidad(), visible=False)
        self.btn_editar = ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Editar entidad",
                                        on_click=lambda e: self._editar_entidad_actual(),
                                        visible=False)

        # Inicializar paneles de mapeo ANTES de refrescar entidades.
        # scroll=AUTO: muestra barra deslizadora cuando hay mas campos de los
        # que caben en la altura fija del contenedor (ver col_cli/col_ops).
        self.panel_map_cli = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
        self.panel_map_ops = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)

        self._refrescar_entidades()

        header = ft.Row([
            ft.Text("Validacion de BBDD", size=22, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            self.dd_entidad,
            self.btn_editar,
            self.btn_eliminar,
            ft.FilledButton("Nueva entidad", icon=ft.Icons.ADD,
                            on_click=lambda e: self._abrir_constructor()),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.txt_cli = ft.Text("Sin archivo", size=12, color=TEXTO_MUTED)
        self.txt_ops = ft.Text("Sin archivo", size=12, color=TEXTO_MUTED)

        # Bordes con ft.Border.all (B mayúscula)
        col_cli = ft.Container(expand=1, padding=12,
                                border=ft.Border.all(1, BORDE),
                                border_radius=8, content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.PEOPLE_OUTLINE), ft.Text("Clientes", weight=ft.FontWeight.BOLD)]),
                ft.Row([ft.ElevatedButton("Cargar clientes", icon=ft.Icons.UPLOAD_FILE,
                        on_click=lambda e: self.page.run_task(self._cargar, "cli")),
                        self.txt_cli]),
                ft.Divider(), ft.Text("Mapeo de columnas", size=12, weight=ft.FontWeight.BOLD),
                ft.Container(self.panel_map_cli, height=260, padding=4),
            ]))
        col_ops = ft.Container(expand=1, padding=12,
                                border=ft.Border.all(1, BORDE),
                                border_radius=8, content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.SWAP_HORIZ), ft.Text("Operaciones", weight=ft.FontWeight.BOLD)]),
                ft.Row([ft.ElevatedButton("Cargar operaciones", icon=ft.Icons.UPLOAD_FILE,
                        on_click=lambda e: self.page.run_task(self._cargar, "ops")),
                        self.txt_ops]),
                ft.Divider(), ft.Text("Mapeo de columnas", size=12, weight=ft.FontWeight.BOLD),
                ft.Container(self.panel_map_ops, height=260, padding=4),
            ]))

        # Puedes seleccionar varios archivos por base. Para volúmenes muy grandes,
        # marca SQLite: carga y valida por lotes sin saturar la memoria.
        self.chk_sqlite = ft.Checkbox(
            label="Usar SQLite (grandes volúmenes)", value=False,
            tooltip="Procesa los archivos por lotes en una base temporal. "
                    "Recomendado para más de ~500k filas.")

        acciones = ft.Row([
            ft.FilledButton("Validar", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self._validar()),
            ft.OutlinedButton("Exportar Excel", icon=ft.Icons.DOWNLOAD,
                              on_click=lambda e: self._exportar()),
            ft.Container(expand=True),
            self.chk_sqlite,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # Progreso en vivo (carga/validación en segundo plano).
        self.txt_progreso = ft.Text("", size=12, visible=False, color=AMBAR)
        self.prog_bar = ft.ProgressBar(visible=False)
        progreso = ft.Column([self.txt_progreso, self.prog_bar], spacing=4)

        self.resumen = ft.Row(wrap=True, spacing=6)

        # Dropdown de hoja sin on_change en constructor
        self.dd_hoja = ft.Dropdown(label="Hoja", width=320, visible=False)
        self.dd_hoja.on_select = lambda e: self._render_hoja(e.control.value)

        # Column con scroll vertical (barra siempre visible) que llena la
        # altura fija del contenedor de resultados.
        self.tabla = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True)
        resultados = ft.Container(padding=12,
                                  border=ft.Border.all(1, BORDE),
                                  border_radius=8, content=ft.Column([
                ft.Text("Resultados", weight=ft.FontWeight.BOLD),
                self.resumen, self.dd_hoja,
                ft.Container(self.tabla, height=320),
            ]))

        self.page.add(ft.Column([
            header, ft.Divider(),
            ft.Row([col_cli, col_ops], vertical_alignment=ft.CrossAxisAlignment.START),
            acciones, progreso, resultados,
        ], spacing=12, scroll=ft.ScrollMode.AUTO))

    # ================================================================== #
    # Entidades
    # ================================================================== #
    def _refrescar_entidades(self):
        self.dd_entidad.options = [ft.dropdown.Option(n) for n in listar_entidades()]
        if not self.dd_entidad.value and self.dd_entidad.options:
            self.dd_entidad.value = self.dd_entidad.options[0].key
            self._seleccionar_entidad(self.dd_entidad.value)

    def _seleccionar_entidad(self, nombre: str):
        if not nombre:
            return
        self.entidad = cargar_entidad(nombre)
        self.btn_eliminar.visible = not getattr(self.entidad, "es_builtin", False)
        self.btn_editar.visible = True
        self._rehacer_mapeo("cli")
        self._rehacer_mapeo("ops")
        self.page.update()

    def _editar_entidad_actual(self):
        if not self.entidad:
            return
        if getattr(self.entidad, "es_builtin", False):
            self._abrir_editor_banco()
        else:
            self._abrir_constructor(existing=self.entidad.config)

    def _eliminar_entidad(self):
        nombre = self.dd_entidad.value
        if not nombre:
            return

        def confirmar(e):
            self._cerrar(dlg)
            if eliminar_entidad(nombre):
                self.dd_entidad.value = None
                self._refrescar_entidades()
                self._toast(f"Entidad '{nombre}' eliminada.")
            else:
                self._toast("No se pudo eliminar (las entidades predefinidas no se borran).")
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Eliminar entidad"),
            content=ft.Text(f"¿Eliminar la entidad '{nombre}'?\n"
                            "Esta acción no se puede deshacer."),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(dlg)),
                     ft.FilledButton("Eliminar", on_click=confirmar)])
        self._abrir(dlg)

    # ================================================================== #
    # Archivos y mapeo
    # ================================================================== #
    async def _cargar(self, cual: str):
        fp = self.fp_cli if cual == "cli" else self.fp_ops
        files = await fp.pick_files(allow_multiple=True,
                                    allowed_extensions=["csv", "xlsx", "xls"])
        if not files:
            return
        paths = [f.path for f in files]
        # La carga (concatenado o construcción de SQLite) corre en segundo plano
        # para no congelar la ventana con archivos grandes.
        self._progreso_msg = "Cargando archivos..."
        self._mostrar_progreso(True)
        loop = asyncio.get_running_loop()
        ticker = loop.create_task(self._tick_progreso())
        try:
            ok, aviso = await loop.run_in_executor(None, self._trabajo_carga, cual, paths)
        finally:
            ticker.cancel()
            self._mostrar_progreso(False)
        if not ok:
            self._toast(aviso)
            return
        if aviso:
            self._toast(aviso)
        self._rehacer_mapeo(cual)
        self.page.update()

    def _trabajo_carga(self, cual: str, paths: list[str]) -> tuple[bool, str]:
        """Corre en el executor; devuelve (ok, aviso_para_toast)."""
        nombre = (os.path.basename(paths[0]) if len(paths) == 1
                  else f"{len(paths)} archivos")
        self._limpiar_db(cual)                      # descarta una DB temporal previa
        try:
            if self.chk_sqlite.value:
                self._cargar_sqlite(cual, paths, nombre)
                return True, ""
            try:
                self._set_progreso("Leyendo archivos en memoria...")
                df = ml.leer_varios(paths)
            except MemoryError:
                self._set_progreso("Datos muy grandes; cambiando a SQLite...")
                self._cargar_sqlite(cual, paths, nombre)
                return True, "Datos muy grandes: se usó SQLite por lotes."
            self._set_memoria(cual, df, nombre)
            if len(df) > ml.UMBRAL_FILAS_SQLITE:
                return True, (f"{len(df):,} filas. Para volúmenes así conviene "
                              "marcar 'Usar SQLite'.")
            return True, ""
        except Exception as ex:                       # noqa: BLE001
            return False, f"No se pudo leer el archivo: {ex}"

    def _set_memoria(self, cual: str, df: pd.DataFrame, nombre: str):
        if cual == "cli":
            self.df_cli, self.db_cli, self.total_cli = df, None, len(df)
        else:
            self.df_ops, self.db_ops, self.total_ops = df, None, len(df)
        self._set_label(cual, f"{nombre} — {len(df):,} filas")

    def _cargar_sqlite(self, cual: str, paths: list[str], nombre: str):
        db_path, total = ml.construir_db(paths, progreso=self._set_progreso)
        muestra = ml.leer_muestra(db_path, n=100)   # solo para mapeo/muestra
        if cual == "cli":
            self.df_cli, self.db_cli, self.total_cli = muestra, db_path, total
        else:
            self.df_ops, self.db_ops, self.total_ops = muestra, db_path, total
        self._set_label(cual, f"{nombre} — {total:,} filas (SQLite)")

    def _set_label(self, cual: str, texto: str):
        (self.txt_cli if cual == "cli" else self.txt_ops).value = texto

    def _limpiar_db(self, cual: str):
        db_path = self.db_cli if cual == "cli" else self.db_ops
        if db_path:
            ml.eliminar_db(db_path)
        if cual == "cli":
            self.db_cli = None
        else:
            self.db_ops = None

    def _rehacer_mapeo(self, cual: str):
        panel = self.panel_map_cli if cual == "cli" else self.panel_map_ops
        destino = self.map_cli_dd if cual == "cli" else self.map_ops_dd
        df = self.df_cli if cual == "cli" else self.df_ops
        panel.controls.clear()
        destino.clear()
        if self.entidad is None:
            return
        campos = self.entidad.campos_cliente() if cual == "cli" else self.entidad.campos_operacion()
        if not campos:
            panel.controls.append(ft.Text("Esta entidad no valida este tipo.", italic=True,
                                          size=12, color=TEXTO_MUTED))
            return
        columnas = list(df.columns) if df is not None else []
        sugerido = auto_mapear(columnas, campos) if columnas else {c: None for c in campos}
        opciones = [ft.dropdown.Option(NO_MAPEAR)] + [ft.dropdown.Option(c) for c in columnas]
        for campo in campos:
            dd = ft.Dropdown(label=campo, width=300, dense=True, options=opciones,
                             value=sugerido.get(campo) or NO_MAPEAR)
            destino[campo] = dd
            panel.controls.append(dd)

    def _leer_mapeo(self, cual: str) -> dict:
        destino = self.map_cli_dd if cual == "cli" else self.map_ops_dd
        return {campo: (dd.value if dd.value and dd.value != NO_MAPEAR else None)
                for campo, dd in destino.items()}

    # ================================================================== #
    # Flujo de validacion
    # ================================================================== #
    def _tiene_cli(self) -> bool:
        return self.df_cli is not None

    def _tiene_ops(self) -> bool:
        return self.df_ops is not None

    def _validar(self):
        if self.entidad is None:
            self._toast("Selecciona una entidad.")
            return
        if not self._tiene_cli() and not self._tiene_ops():
            self._toast("Carga al menos un archivo (clientes u operaciones).")
            return
        # 1) Recolectar entradas (mapeos) y, si hace falta, abrir diálogos.
        self._map_cli = self._leer_mapeo("cli") if self._tiene_cli() else {}
        self._map_ops = self._leer_mapeo("ops") if self._tiene_ops() else {}
        self._tp_default = None
        self._cfg_ops = None
        self._cancelado_ops = False
        if (self._tiene_cli() and self.entidad.requiere_tipo_persona
                and not self._map_cli.get("tipo de persona")):
            self._preguntar_tipo_persona(self._tras_tipo_persona)
        else:
            self._tras_tipo_persona(None)

    def _tras_tipo_persona(self, default):
        self._tp_default = default
        if self._tiene_ops() and self.entidad.requiere_config_operaciones:
            ConfigOperacionesDialog(
                self.page, self._tras_config,
                requiere_tasas=self.entidad.tiene_limites_operacion()).abrir()
        else:
            self._tras_config(None)

    def _tras_config(self, config):
        # Si las operaciones requerían config y se canceló, se omiten.
        self._cancelado_ops = (config is None and self._tiene_ops()
                               and self.entidad.requiere_config_operaciones)
        self._cfg_ops = config
        # 2) Ejecutar la validación pesada en segundo plano (no congela la UI).
        self.page.run_task(self._ejecutar_validacion)

    # ------------------------------------------------------------------ #
    # Ejecución en segundo plano con progreso en vivo
    # ------------------------------------------------------------------ #
    async def _ejecutar_validacion(self):
        self._progreso_msg = "Preparando validación..."
        self._errores_ui = []
        self._mostrar_progreso(True)
        loop = asyncio.get_running_loop()
        ticker = loop.create_task(self._tick_progreso())
        try:
            acum = await loop.run_in_executor(None, self._trabajo_validacion)
        finally:
            ticker.cancel()
            self._mostrar_progreso(False)
        for msg in self._errores_ui:
            self._toast(msg)
        self.hallazgos = acum
        self._mostrar_resultados()

    def _trabajo_validacion(self) -> dict:
        """Corre en un hilo del executor; no toca controles de la UI."""
        acum: dict = {}
        if self._tiene_cli():
            try:
                if self.db_cli:
                    err = self.entidad.validar_clientes_sqlite(
                        self.db_cli, self._map_cli, self._tp_default,
                        progreso=self._set_progreso)
                else:
                    self._set_progreso("Validando clientes...")
                    err = self.entidad.validar_clientes(
                        self.df_cli, self._map_cli, self._tp_default)
                acum.update(err)
            except Exception as ex:                   # noqa: BLE001
                self._errores_ui.append(f"Error validando clientes: {ex}")
                traceback.print_exc()
        if self._tiene_ops() and not self._cancelado_ops:
            try:
                if self.db_ops:
                    err = self.entidad.validar_operaciones_sqlite(
                        self.db_ops, self._map_ops, self._cfg_ops,
                        progreso=self._set_progreso)
                else:
                    self._set_progreso("Validando operaciones...")
                    err = self.entidad.validar_operaciones(
                        self.df_ops, self._map_ops, self._cfg_ops)
                acum.update(err)
            except Exception as ex:                   # noqa: BLE001
                self._errores_ui.append(f"Error validando operaciones: {ex}")
                traceback.print_exc()
        return acum

    async def _tick_progreso(self):
        """Refresca el texto de progreso en la UI cada 0.25 s mientras corre."""
        try:
            while True:
                self.txt_progreso.value = self._progreso_msg
                self.page.update()
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            pass

    def _set_progreso(self, msg: str):
        # Llamado desde el hilo de trabajo: solo guarda el mensaje (el ticker lo pinta).
        self._progreso_msg = msg

    def _mostrar_progreso(self, mostrar: bool):
        self.prog_bar.visible = mostrar
        self.txt_progreso.visible = mostrar
        if mostrar:
            self.txt_progreso.value = self._progreso_msg
        self.page.update()

    def _preguntar_tipo_persona(self, cont):
        def responder(default):
            self._cerrar(dlg)
            cont(default)
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Tipo de persona"),
            content=ft.Text("No mapeaste 'tipo de persona'. Trataremos todos los registros como un solo tipo.\n"
                            "Son todas personas FISICAS?"),
            actions=[
                ft.TextButton("Si (Fisicas)", on_click=lambda e: responder("Física")),
                ft.TextButton("No (Morales)", on_click=lambda e: responder("Moral")),
            ],
        )
        self._abrir(dlg)

    # ================================================================== #
    # Resultados
    # ================================================================== #
    def _mostrar_resultados(self):
        self.resumen.controls.clear()
        self.tabla.controls.clear()
        if not self.hallazgos:
            self.resumen.controls.append(
                ft.Container(ft.Text("Sin hallazgos ✓", color=ft.Colors.GREEN_300),
                             bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREEN),
                             padding=8, border_radius=6))
            self.dd_hoja.visible = False
            self.page.update()
            return
        total = sum(len(v) for v in self.hallazgos.values())
        self.resumen.controls.append(
            ft.Container(ft.Text(f"{total} hallazgos", weight=ft.FontWeight.BOLD,
                                 color=ft.Colors.RED_300),
                         bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.RED),
                         padding=8, border_radius=6))
        for nombre, df in self.hallazgos.items():
            self.resumen.controls.append(
                ft.Container(ft.Text(f"{nombre}: {len(df)}", size=12, color="#FFFFFF"),
                             bgcolor=ft.Colors.with_opacity(0.12, AMBAR),
                             padding=8, border_radius=6))
        self.dd_hoja.options = [ft.dropdown.Option(n) for n in self.hallazgos]
        self.dd_hoja.value = next(iter(self.hallazgos))
        self.dd_hoja.visible = True
        self._render_hoja(self.dd_hoja.value)
        self.page.update()

    def _render_hoja(self, nombre: str):
        self.tabla.controls.clear()
        df = self.hallazgos.get(nombre)
        if df is None or df.empty:
            self.page.update()
            return
        df = df.head(80)
        cols = [ft.DataColumn(ft.Text(str(c))) for c in df.columns]
        filas = [ft.DataRow(cells=[ft.DataCell(ft.Text("" if pd.isna(v) else str(v)))
                                   for v in row]) for row in df.itertuples(index=False)]
        # Row con scroll horizontal (para tablas anchas con muchas columnas)
        # anidada en self.tabla (scroll vertical) -> desplazamiento en 2D.
        self.tabla.controls.append(
            ft.Row([ft.DataTable(columns=cols, rows=filas, column_spacing=18)],
                   scroll=ft.ScrollMode.ALWAYS, vertical_alignment=ft.CrossAxisAlignment.START))
        self.page.update()

    # ================================================================== #
    # Export
    # ================================================================== #
    def _exportar(self):
        if not self.hallazgos:
            self._toast("Primero valida (no hay resultados para exportar).")
            return
        self.page.run_task(self._exportar_async)

    async def _exportar_async(self):
        ruta = await self.fp_export.save_file(file_name="reporte_validacion.xlsx",
                                              allowed_extensions=["xlsx"])
        if not ruta:
            return
        if not ruta.lower().endswith(".xlsx"):
            ruta += ".xlsx"
        self._guardar_en(ruta)

    def _guardar_en(self, ruta: str):
        df_orig = self.df_cli if self.df_cli is not None else self.df_ops
        mapeo = {**(self._leer_mapeo("cli") if self.df_cli is not None else {}),
                 **(self._leer_mapeo("ops") if self.df_ops is not None else {})}
        try:
            ReportGenerator.generar_reporte(self.hallazgos, df_orig, mapeo, ruta, [])
            self._toast(f"Reporte guardado: {ruta}")
        except Exception as ex:                       # noqa: BLE001
            self._toast(f"Error al exportar: {ex}")
            traceback.print_exc()

    # ================================================================== #
    # Constructor de entidades nuevas
    # ================================================================== #
    def _abrir_constructor(self, existing: EntidadConfig | None = None):
        self.nuevo_nombre = ft.TextField(label="Nombre de la entidad", width=320,
                                         value=existing.nombre if existing else "")
        self.nuevo_desc = ft.TextField(label="Descripcion", width=320,
                                       value=existing.descripcion if existing else "")
        self.campos_cli: list[CampoConfig] = list(existing.campos_cliente) if existing else []
        self.campos_ops: list[CampoConfig] = list(existing.campos_operacion) if existing else []
        self.requisitos_cli: list[RequisitoNivel] = (
            list(existing.requisitos_cliente) if existing else [])
        self.limites_op: list[LimiteOperacion] = (
            list(existing.limites_operacion) if existing else [])
        self.lista_cli = ft.Column(spacing=2,
            controls=[ft.Text(f"• {c.logico} ({len(c.reglas)} reglas)") for c in self.campos_cli])
        self.lista_ops = ft.Column(spacing=2,
            controls=[ft.Text(f"• {c.logico} ({len(c.reglas)} reglas)") for c in self.campos_ops])
        self.lista_niveles = ft.Column(spacing=2, controls=[
            ft.Text(f"• Nivel {r.nivel} / {r.tipo_persona} / {r.modalidad}: "
                    f"{', '.join(r.campos)}", size=12) for r in self.requisitos_cli])
        self.lista_limites = ft.Column(spacing=2, controls=[
            ft.Text(f"• {l.concepto} / nivel {l.nivel} / {l.tipo_persona}: "
                    f"{'sin límite' if l.limite is None else f'{l.limite:g} ' + UNIDAD_LIMITE.get(l.concepto, '')}".strip(),
                    size=12) for l in self.limites_op])

        # Designación de qué campo lógico (de clientes) lleva el nivel/tipo/modalidad.
        self.dd_campo_nivel = ft.Dropdown(label="Campo de NIVEL (1-4)", width=200, dense=True)
        self.dd_campo_tipo = ft.Dropdown(label="Campo TIPO persona (opc.)", width=200, dense=True)
        self.dd_campo_modalidad = ft.Dropdown(label="Campo MODALIDAD (opc.)", width=200, dense=True)
        self._refrescar_opciones_nivel()
        if existing:
            self.dd_campo_nivel.value = existing.campo_nivel or NO_MAPEAR
            self.dd_campo_tipo.value = existing.campo_tipo_persona or NO_MAPEAR
            self.dd_campo_modalidad.value = existing.campo_modalidad or NO_MAPEAR

        # Designación de campos de OPERACIÓN para límites de monto.
        self.op_roles = [("fecha", "Fecha"), ("monto", "Monto"), ("cuenta", "Cuenta"),
                         ("cliente", "Cliente"), ("nivel", "Nivel"),
                         ("tipo_persona", "Tipo persona"), ("tipo_operacion", "Tipo operación"),
                         ("instrumento", "Instrumento"), ("saldo", "Saldo"),
                         ("moneda", "Moneda")]
        self.op_dd = {rol: ft.Dropdown(label=etq, width=150, dense=True)
                      for rol, etq in self.op_roles}
        self.tf_abono = ft.TextField(label="Valores de ABONO (coma)", width=300, dense=True,
                                     value=(", ".join(existing.op_valores_abono) if existing
                                            else "IN, ABONO, DEPOSITO"))
        self.tf_efectivo = ft.TextField(label="Valores de EFECTIVO (coma)", width=300, dense=True,
                                        value=(", ".join(existing.op_valores_efectivo) if existing
                                               else "EFECTIVO"))
        self.tf_cheque_caja = ft.TextField(
            label="Valores de CHEQUE DE CAJA (coma)", width=300, dense=True,
            value=(", ".join(existing.op_valores_cheque_caja) if existing
                   else "CHEQUE DE CAJA"))
        self.tf_moneda_usd = ft.TextField(
            label="Valores de moneda = DOLARES (coma)", width=300, dense=True,
            value=(", ".join(existing.op_valores_moneda_usd) if existing else "USD"))
        # Sinónimos de nivel: para mapear valores que no dicen "1/2/3/4".
        self.tf_aliases_nivel = ft.TextField(
            label="Sinónimos de nivel (alias=nivel, coma)", width=420, dense=True,
            hint_text="Ej: Tradicional=4, Básica=2, Limitada=3L, Limitada 4=4L",
            value=(", ".join(f"{a}={n}" for a, n in existing.aliases_nivel.items())
                   if existing else ""))
        self._refrescar_opciones_op()
        if existing:
            for rol, dd in self.op_dd.items():
                dd.value = existing.op_campos.get(rol) or NO_MAPEAR

        self.chk_filtros_op = ft.Checkbox(
            label="Habilitar filtros de monto en operaciones (como Banco)",
            value=(existing.op_filtros_habilitado if existing else False))

        self._editando_nombre_original = existing.nombre if existing else None

        acciones_ayuda = [ft.TextButton("Ver catálogo de validaciones", icon=ft.Icons.MENU_BOOK,
                                        on_click=lambda e: self._ver_catalogo_validaciones())]
        if existing is None:
            acciones_ayuda.append(ft.TextButton(
                "Empezar desde plantilla de Banco", icon=ft.Icons.CONTENT_COPY,
                on_click=lambda e: self._cargar_plantilla_banco()))

        cuerpo = ft.Container(width=640, content=ft.Column([
            self.nuevo_nombre, self.nuevo_desc,
            ft.Row(acciones_ayuda, wrap=True),
            ft.Divider(),
            ft.Text("Campos de CLIENTES", weight=ft.FontWeight.BOLD),
            self.lista_cli,
            ft.TextButton("Agregar campo de cliente", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_campo("cli")),
            ft.Divider(),
            ft.Text("Campos de OPERACIONES", weight=ft.FontWeight.BOLD),
            self.lista_ops,
            ft.TextButton("Agregar campo de operacion", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_campo("ops")),
            ft.Divider(),
            ft.Text("Requisitos por NIVEL DE CUENTA (clientes)", weight=ft.FontWeight.BOLD),
            ft.Text("Indica qué campos llevan el nivel/tipo/modalidad y agrega, por nivel, "
                    "los campos que deben venir llenos.", size=11, color=TEXTO_MUTED),
            ft.Row([self.dd_campo_nivel, self.dd_campo_tipo, self.dd_campo_modalidad], wrap=True),
            ft.Text("Si la columna de nivel no dice '1/2/3/4', mapea sus valores "
                    "(Tradicional→4, Limitada→3L y Limitada 4→4L ya se reconocen):",
                    size=11, color=TEXTO_MUTED),
            self.tf_aliases_nivel,
            self.lista_niveles,
            ft.TextButton("Agregar requisito de nivel", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_requisito_nivel()),
            ft.Divider(),
            ft.Text("Límites de OPERACIÓN por nivel (montos)", weight=ft.FontWeight.BOLD),
            ft.Text("Designa los campos de operación y los valores de abono/efectivo/"
                    "cheque de caja/moneda; luego agrega los topes por nivel. Abonos se "
                    "evalúan en UDIS, efectivo en USD y en MXN, saldo en UDIS (requiere "
                    "cargar ambos archivos de tasas al validar). El campo 'Moneda' es "
                    "opcional: si una fila ya declara moneda de dólares, su monto se usa "
                    "tal cual (sin convertir). 'Tipo persona' admite también 'fisica_ae' "
                    "(física con actividad empresarial) y 'fideicomiso'.",
                    size=11, color=TEXTO_MUTED),
            ft.Row(list(self.op_dd.values()), wrap=True),
            ft.Row([self.tf_abono, self.tf_efectivo, self.tf_cheque_caja, self.tf_moneda_usd],
                  wrap=True),
            self.lista_limites,
            ft.TextButton("Agregar límite de operación", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_limite_op()),
            ft.Divider(),
            self.chk_filtros_op,
            ft.Text("Al validar, se pedirá moneda de análisis, agrupación y filtros de "
                    "monto con operador libre (>, <, >=, <=) sobre el total agrupado, "
                    "igual que en Banco. Se activa automáticamente si defines límites "
                    "de operación (para pedir los archivos de tasas).",
                    size=11, color=TEXTO_MUTED),
        ], scroll=ft.ScrollMode.AUTO, height=460))

        self.dlg_constructor = ft.AlertDialog(
            modal=True, title=ft.Text("Editar entidad" if existing else "Nueva entidad"),
            content=cuerpo,
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(self.dlg_constructor)),
                     ft.FilledButton("Guardar", on_click=lambda e: self._guardar_entidad())])
        self._abrir(self.dlg_constructor)

    def _cargar_plantilla_banco(self):
        """Precarga el constructor con una entidad equivalente a Banco (campos,
        reglas, requisitos por nivel y límites), lista para renombrar/editar en
        vez de armar todo desde cero."""
        self._cerrar(self.dlg_constructor)
        self._abrir_constructor(existing=plantilla_banco())
        self._editando_nombre_original = None  # es una entidad nueva, no una edición
        self._toast("Plantilla de Banco cargada: ponle un nombre y ajusta lo que necesites.")

    def _texto_regla(self, regla: ReglaConfig) -> str:
        meta = CATALOGO[regla.id]
        partes = [meta.etiqueta]
        if regla.parametros:
            params_txt = ", ".join(f"{k}={v}" for k, v in regla.parametros.items() if v not in (None, "", []))
            if params_txt:
                partes[0] += f" ({params_txt})"
        if regla.condiciones:
            cond_txt = " y ".join(f"{c.campo} {c.operador} '{c.valor}'" for c in regla.condiciones)
            prefijo = "salvo que" if regla.condiciones_negar else "solo si"
            partes.append(f"[{prefijo} {cond_txt}]")
        return " ".join(partes)

    def _ver_catalogo_validaciones(self):
        """Referencia: todas las reglas disponibles + cómo las usa Banco en cada
        campo (misma función `plantilla_banco()` que arma la plantilla, para que
        nunca quede desincronizada de lo que realmente se puede reutilizar)."""
        secciones = [ft.Text("Reglas disponibles para cualquier entidad", weight=ft.FontWeight.BOLD)]
        for rid, meta in CATALOGO.items():
            extra = f" · ámbito: {meta.ambito}" if meta.ambito != "valor" else ""
            params = (", ".join(p.nombre for p in meta.parametros)) if meta.parametros else ""
            linea = f"• {meta.etiqueta} ({rid}){extra}"
            if params:
                linea += f" — parámetros: {params}"
            secciones.append(ft.Text(linea, size=12))
            secciones.append(ft.Text(f"   {meta.descripcion}", size=11, color=TEXTO_MUTED))

        secciones.append(ft.Divider())
        secciones.append(ft.Text(
            "Cómo las combina Banco, campo por campo (referencia — usa "
            "'Empezar desde plantilla de Banco' para precargar esto tal cual)",
            weight=ft.FontWeight.BOLD))
        banco = plantilla_banco()
        for etiqueta, campos in (("CLIENTES", banco.campos_cliente), ("OPERACIONES", banco.campos_operacion)):
            secciones.append(ft.Text(etiqueta, weight=ft.FontWeight.BOLD, size=12))
            for c in campos:
                if not c.reglas:
                    continue
                reglas_txt = "; ".join(self._texto_regla(r) for r in c.reglas)
                secciones.append(ft.Text(f"• {c.logico}: {reglas_txt}", size=12))
        secciones.append(ft.Text(
            f"Requisitos por nivel de cuenta: {len(banco.requisitos_cliente)} reglas definidas "
            f"(campo de nivel: '{banco.campo_nivel}', tipo persona: '{banco.campo_tipo_persona}', "
            f"modalidad: '{banco.campo_modalidad}').", size=12))
        secciones.append(ft.Text(
            f"Límites de operación por nivel (montos): {len(banco.limites_operacion)} definidos "
            f"(abonos en UDIS, efectivo en USD/MXN, cheque de caja, saldo...).", size=12))

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Catálogo de validaciones"),
            content=ft.Container(width=680, content=ft.Column(
                secciones, scroll=ft.ScrollMode.AUTO, height=480, spacing=2)),
            actions=[ft.TextButton("Cerrar", on_click=lambda e: self._cerrar(dlg))])
        self._abrir(dlg)

    def _editar_campo(self, cual: str):
        logico = ft.TextField(label="Campo logico (ej. CURP, monto)", width=320)
        checks = {}
        params_fields = {}
        # rid -> {"lista": [(tf_campo, dd_op, tf_valor), ...], "negar": ft.Checkbox}
        cond_state: dict[str, dict] = {}
        controles = []
        for rid, meta in CATALOGO.items():
            chk = ft.Checkbox(label=f"{meta.etiqueta}", value=False)
            checks[rid] = chk
            fila = [chk]
            for p in meta.parametros:
                tf = ft.TextField(label=p.etiqueta, width=120, dense=True,
                                  value="" if p.default is None else str(p.default))
                params_fields[(rid, p.nombre)] = (tf, p)
                fila.append(tf)

            cond_filas = ft.Column(spacing=2)
            cond_negar = ft.Checkbox(label="Negar (aplica cuando NO se cumplen)", value=False)
            cond_lista: list[tuple] = []
            cond_state[rid] = {"lista": cond_lista, "negar": cond_negar}

            def _agregar_condicion(e, _filas=cond_filas, _lista=cond_lista):
                tf_campo = ft.TextField(label="Campo logico", width=140, dense=True)
                dd_op = ft.Dropdown(label="Operador", width=140, dense=True, value="=",
                                    options=[ft.dropdown.Option(o) for o in OPERADORES_CONDICION])
                tf_valor = ft.TextField(label="Valor", width=140, dense=True)
                _lista.append((tf_campo, dd_op, tf_valor))
                _filas.controls.append(ft.Row([tf_campo, dd_op, tf_valor], wrap=True))
                self.page.update()

            bloque = ft.Column([
                ft.Row(fila, wrap=True),
                ft.Row([ft.TextButton("+ Condición 'aplica si...'", on_click=_agregar_condicion),
                       cond_negar]),
                cond_filas,
            ], spacing=0)
            controles.append(bloque)

        def aceptar(e):
            if not logico.value:
                self._toast("Escribe el nombre del campo logico.")
                return
            reglas = []
            for rid, chk in checks.items():
                if not chk.value:
                    continue
                params = {}
                for p in CATALOGO[rid].parametros:
                    tf, meta_p = params_fields[(rid, p.nombre)]
                    params[p.nombre] = self._convertir(tf.value, meta_p)
                condiciones = [
                    Condicion(campo=tf_campo.value.strip(), operador=dd_op.value,
                             valor=(tf_valor.value or "").strip())
                    for tf_campo, dd_op, tf_valor in cond_state[rid]["lista"]
                    if tf_campo.value and dd_op.value
                ]
                reglas.append(ReglaConfig(id=rid, parametros=params, condiciones=condiciones,
                                          condiciones_negar=cond_state[rid]["negar"].value))
            campo = CampoConfig(logico=logico.value.strip(), reglas=reglas)
            destino = self.campos_cli if cual == "cli" else self.campos_ops
            lista = self.lista_cli if cual == "cli" else self.lista_ops
            destino.append(campo)
            lista.controls.append(ft.Text(f"• {campo.logico} ({len(reglas)} reglas)"))
            if cual == "cli":
                self._refrescar_opciones_nivel()   # nuevos campos disponibles para niveles
            else:
                self._refrescar_opciones_op()      # nuevos campos de operación
            self._cerrar(dlg)
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f"Campo de {'cliente' if cual == 'cli' else 'operacion'}"),
            content=ft.Container(width=620, content=ft.Column(
                [logico, ft.Text("Reglas (cada una puede llevar condiciones 'aplica si...', "
                                 "referenciando OTROS campos logicos de esta entidad):",
                                 weight=ft.FontWeight.BOLD, size=12)] + controles,
                scroll=ft.ScrollMode.AUTO, height=440)),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(dlg)),
                     ft.FilledButton("Agregar", on_click=aceptar)])
        self._abrir(dlg)

    def _refrescar_opciones_nivel(self):
        """Actualiza las opciones de los 3 dropdowns con los campos de cliente actuales."""
        nombres = [c.logico for c in self.campos_cli]
        opciones = [ft.dropdown.Option(NO_MAPEAR)] + [ft.dropdown.Option(n) for n in nombres]
        for dd in (self.dd_campo_nivel, self.dd_campo_tipo, self.dd_campo_modalidad):
            dd.options = list(opciones)
            if dd.value not in ([NO_MAPEAR] + nombres):
                dd.value = NO_MAPEAR

    def _editar_requisito_nivel(self):
        if not self.campos_cli:
            self._toast("Primero agrega campos de cliente.")
            return
        dd_nivel = ft.Dropdown(label="Nivel", width=110, value="1",
                               options=[ft.dropdown.Option(n) for n in ["1", "2", "3", "3L", "4", "4L"]])
        dd_tipo = ft.Dropdown(label="Tipo persona", width=160, value="ambos",
                              options=[ft.dropdown.Option(t) for t in ["ambos", "fisica", "moral"]])
        dd_mod = ft.Dropdown(label="Modalidad", width=170, value="ambas",
                             options=[ft.dropdown.Option(m) for m in ["ambas", "presencial", "remota"]])
        checks = {c.logico: ft.Checkbox(label=c.logico, value=False) for c in self.campos_cli}

        def aceptar(e):
            campos = [k for k, chk in checks.items() if chk.value]
            if not campos:
                self._toast("Selecciona al menos un campo obligatorio.")
                return
            req = RequisitoNivel(nivel=dd_nivel.value, tipo_persona=dd_tipo.value,
                                 modalidad=dd_mod.value, campos=campos)
            self.requisitos_cli.append(req)
            self.lista_niveles.controls.append(
                ft.Text(f"• Nivel {req.nivel} / {req.tipo_persona} / {req.modalidad}: "
                        f"{', '.join(campos)}", size=12))
            self._cerrar(dlg)
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Requisito de nivel"),
            content=ft.Container(width=560, content=ft.Column(
                [ft.Row([dd_nivel, dd_tipo, dd_mod], wrap=True),
                 ft.Text("Campos obligatorios para esta combinación:",
                         weight=ft.FontWeight.BOLD)] + list(checks.values()),
                scroll=ft.ScrollMode.AUTO, height=380)),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(dlg)),
                     ft.FilledButton("Agregar", on_click=aceptar)])
        self._abrir(dlg)

    def _refrescar_opciones_op(self):
        """Actualiza las opciones de los dropdowns de campos de operación."""
        nombres = [c.logico for c in self.campos_ops]
        opciones = [ft.dropdown.Option(NO_MAPEAR)] + [ft.dropdown.Option(n) for n in nombres]
        for dd in self.op_dd.values():
            dd.options = list(opciones)
            if dd.value not in ([NO_MAPEAR] + nombres):
                dd.value = NO_MAPEAR

    def _editar_limite_op(self):
        dd_concepto = ft.Dropdown(label="Concepto", width=220, value="abono_mensual",
                                  options=[ft.dropdown.Option(c) for c in [
                                      "abono_mensual", "efectivo_usd", "efectivo_mensual_mxn",
                                      "efectivo_individual_mxn", "operacion_relevante_usd",
                                      "efectivo_abono_usd_individual", "cheque_caja_usd",
                                      "saldo_udis"]])
        dd_nivel = ft.Dropdown(label="Nivel", width=120, value="todos",
                               options=[ft.dropdown.Option(n) for n in
                                        ["todos", "1", "2", "3", "3L", "4", "4L"]])
        dd_tipo = ft.Dropdown(label="Tipo persona", width=170, value="ambos",
                              options=[ft.dropdown.Option(t) for t in
                                       ["ambos", "fisica", "fisica_ae", "moral", "fideicomiso"]])
        tf_limite = ft.TextField(label="Límite (vacío = sin límite)", width=200)

        def aceptar(e):
            txt = (tf_limite.value or "").strip().replace(",", "")
            limite = None
            if txt != "":
                try:
                    limite = float(txt)
                except ValueError:
                    self._toast("El límite debe ser numérico (o vacío para 'sin límite').")
                    return
            lim = LimiteOperacion(concepto=dd_concepto.value, nivel=dd_nivel.value,
                                  tipo_persona=dd_tipo.value, limite=limite)
            self.limites_op.append(lim)
            unidad = UNIDAD_LIMITE.get(lim.concepto, "")
            txt_lim = "sin límite" if limite is None else f"{limite:g} {unidad}".strip()
            self.lista_limites.controls.append(
                ft.Text(f"• {lim.concepto} / nivel {lim.nivel} / {lim.tipo_persona}: {txt_lim}",
                        size=12))
            self._cerrar(dlg)
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Límite de operación"),
            content=ft.Container(width=520, content=ft.Column(
                [ft.Row([dd_concepto, dd_nivel, dd_tipo], wrap=True), tf_limite,
                 ft.Text("abono_mensual: tope de abonos del mes en UDIS.\n"
                         "efectivo_usd: tope de ABONOS en efectivo del mes en USD (>= al "
                         "valor indicado; 0 = prohibido).\n"
                         "efectivo_mensual_mxn: tope de efectivo del mes en MXN (sin conversión).\n"
                         "efectivo_individual_mxn: tope por movimiento de abono/depósito en "
                         "efectivo, en MXN (sin conversión).\n"
                         "operacion_relevante_usd: marca cargos o abonos en efectivo cuyo "
                         "equivalente en USD sea >= al valor indicado.\n"
                         "efectivo_abono_usd_individual: abono en efectivo cuya moneda ya es "
                         "dólares (sin conversión), monto individual >= al valor indicado.\n"
                         "cheque_caja_usd: cargo o abono con instrumento 'cheque de caja' "
                         "(convertido a USD si hace falta) >= al valor indicado.\n"
                         "saldo_udis: tope de saldo de cuenta en UDIS.",
                         size=11, color=TEXTO_MUTED)], tight=True)),
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(dlg)),
                     ft.FilledButton("Agregar", on_click=aceptar)])
        self._abrir(dlg)

    def _convertir(self, valor, p):
        valor = (valor or "").strip()
        if p.tipo == "int":
            try:
                return int(valor)
            except ValueError:
                return p.default
        if p.tipo == "float":
            if valor == "":
                return None
            try:
                return float(valor)
            except ValueError:
                return p.default
        if p.tipo == "lista":
            return [x.strip() for x in valor.split(",") if x.strip()]
        return valor

    def _guardar_entidad(self):
        nombre = (self.nuevo_nombre.value or "").strip()
        if not nombre:
            self._toast("La entidad necesita un nombre.")
            return
        if not self.campos_cli and not self.campos_ops:
            self._toast("Agrega al menos un campo.")
            return

        def _designado(dd):
            return dd.value if dd.value and dd.value != NO_MAPEAR else ""
        campo_nivel = _designado(self.dd_campo_nivel)
        if self.requisitos_cli and not campo_nivel:
            self._toast("Definiste requisitos por nivel: indica el campo de NIVEL.")
            return

        op_campos = {rol: _designado(dd) for rol, dd in self.op_dd.items() if _designado(dd)}
        if self.limites_op and not (op_campos.get("fecha") and op_campos.get("monto")):
            self._toast("Definiste límites de operación: designa al menos los campos "
                        "de FECHA y MONTO.")
            return
        if self.chk_filtros_op.value and not all(
                op_campos.get(r) for r in ("fecha", "monto", "cuenta", "tipo_operacion")):
            self._toast("Filtros de monto habilitados: designa FECHA, MONTO, CUENTA y "
                        "TIPO OPERACIÓN.")
            return
        _csv = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]
        # Sinónimos de nivel: "alias=nivel, alias=nivel".
        aliases_nivel = {}
        for par in _csv(self.tf_aliases_nivel.value):
            if "=" in par:
                alias, niv = par.split("=", 1)
                if alias.strip() and niv.strip():
                    aliases_nivel[alias.strip()] = niv.strip()

        cfg = EntidadConfig(nombre=nombre, descripcion=(self.nuevo_desc.value or "").strip(),
                            campos_cliente=self.campos_cli, campos_operacion=self.campos_ops,
                            requisitos_cliente=self.requisitos_cli,
                            campo_nivel=campo_nivel,
                            campo_tipo_persona=_designado(self.dd_campo_tipo),
                            campo_modalidad=_designado(self.dd_campo_modalidad),
                            aliases_nivel=aliases_nivel,
                            limites_operacion=self.limites_op, op_campos=op_campos,
                            op_valores_abono=_csv(self.tf_abono.value),
                            op_valores_efectivo=_csv(self.tf_efectivo.value),
                            op_valores_cheque_caja=_csv(self.tf_cheque_caja.value),
                            op_valores_moneda_usd=_csv(self.tf_moneda_usd.value),
                            op_filtros_habilitado=self.chk_filtros_op.value)
        try:
            guardar_entidad(cfg)
        except ValueError as ex:
            self._toast(str(ex))
            return
        # Si se editaba una entidad existente y se cambió el nombre, borra el
        # JSON viejo (equivale a renombrar).
        nombre_original = self._editando_nombre_original
        if nombre_original and nombre_original != nombre:
            eliminar_entidad(nombre_original)
        editando = nombre_original is not None
        self._editando_nombre_original = None
        self._cerrar(self.dlg_constructor)
        self.dd_entidad.value = nombre
        self._refrescar_entidades()
        self._seleccionar_entidad(nombre)
        self._toast(f"Entidad '{nombre}' {'actualizada' if editando else 'creada'}.")
        self.page.update()

    # ================================================================== #
    # Editor de validaciones/limites de Banco (builtin)
    # ================================================================== #
    def _abrir_editor_banco(self):
        from entidades.banco import CAMPOS_CLIENTE, config_efectiva
        from entidades import registro
        from core.validator import DEFAULT_CONFIG as VCFG_DEFAULT, CHECKS_CAMPO, CHECKS_GENERALES

        cfg = config_efectiva()
        # Campos "falsos" (sin reglas) solo para que _editar_requisito_nivel
        # pueda listar los campos de cliente de Banco como checkboxes.
        self.campos_cli = [CampoConfig(logico=c) for c in CAMPOS_CLIENTE]
        self.requisitos_cli: list[RequisitoNivel] = list(cfg["requisitos_cliente"])
        self.limites_op: list[LimiteOperacion] = list(cfg["limites_operacion"])
        self.lista_niveles = ft.Column(spacing=2, controls=[
            ft.Text(f"• Nivel {r.nivel} / {r.tipo_persona} / {r.modalidad}: "
                    f"{', '.join(r.campos)}", size=12) for r in self.requisitos_cli])
        self.lista_limites = ft.Column(spacing=2, controls=[
            ft.Text(f"• {l.concepto} / nivel {l.nivel} / {l.tipo_persona}: "
                    f"{'sin límite' if l.limite is None else f'{l.limite:g} ' + UNIDAD_LIMITE.get(l.concepto, '')}".strip(),
                    size=12) for l in self.limites_op])

        self.tf_abono = ft.TextField(label="Valores de ABONO (coma)", width=300, dense=True,
                                     value=", ".join(cfg["valores_abono"]))
        self.tf_efectivo = ft.TextField(label="Valores de EFECTIVO (coma)", width=300, dense=True,
                                        value=", ".join(cfg["valores_efectivo"]))
        self.tf_cheque_caja = ft.TextField(
            label="Valores de CHEQUE DE CAJA (coma)", width=300, dense=True,
            value=", ".join(cfg["valores_cheque_caja"]))
        self.tf_moneda_usd = ft.TextField(
            label="Valores de moneda = DOLARES (coma)", width=300, dense=True,
            value=", ".join(cfg["valores_moneda_usd"]))

        vcfg = cfg["validator_config"]
        deshabilitados = set(vcfg.get("checks_deshabilitados") or [])

        etiquetas_param = {
            "telefono_min_digitos": "Tel: minimo de digitos",
            "telefono_max_repetidos": "Tel: max. repetidos consecutivos",
            "direccion_min_separadores": "Direccion: minimo de separadores",
            "edad_minima": "Edad minima (fisica)",
            "edad_maxima": "Edad maxima (fisica)",
            "edad_irrealista_max": "Edad irrealista (mayor a)",
            "year_corte_siglo": "Corte de siglo (anios de 2 digitos)",
        }
        param_fields: dict[str, ft.TextField] = {}
        param_rows = []
        for clave, default in VCFG_DEFAULT.items():
            if clave == "checks_deshabilitados":
                continue
            tf = ft.TextField(label=etiquetas_param[clave], width=210, dense=True,
                              value=str(vcfg.get(clave, default)))
            param_fields[clave] = tf
            param_rows.append(tf)

        # Checkbox marcado = validación ACTIVA (se desmarca para desactivarla).
        checks_campo_boxes = {clave: ft.Checkbox(label=etq, value=(clave not in deshabilitados))
                              for clave, etq in CHECKS_CAMPO.items()}
        checks_generales_boxes = {clave: ft.Checkbox(label=etq, value=(clave not in deshabilitados))
                                  for clave, etq in CHECKS_GENERALES.items()}

        def _csv(s):
            return [x.strip() for x in (s or "").split(",") if x.strip()]

        def aceptar(e):
            nuevo_vcfg = {}
            for clave, tf in param_fields.items():
                try:
                    nuevo_vcfg[clave] = int((tf.value or "").strip())
                except ValueError:
                    nuevo_vcfg[clave] = VCFG_DEFAULT[clave]
            nuevo_vcfg["checks_deshabilitados"] = (
                [c for c, chk in checks_campo_boxes.items() if not chk.value]
                + [c for c, chk in checks_generales_boxes.items() if not chk.value])
            data = {
                "requisitos_cliente": [r.to_dict() for r in self.requisitos_cli],
                "limites_operacion": [l.to_dict() for l in self.limites_op],
                "valores_abono": _csv(self.tf_abono.value),
                "valores_efectivo": _csv(self.tf_efectivo.value),
                "valores_cheque_caja": _csv(self.tf_cheque_caja.value),
                "valores_moneda_usd": _csv(self.tf_moneda_usd.value),
                "validator_config": nuevo_vcfg,
            }
            registro.guardar_config_banco(data)
            self._cerrar(dlg)
            self._seleccionar_entidad(self.dd_entidad.value)
            self._toast("Validaciones de Banco actualizadas.")
            self.page.update()

        def restaurar(e):
            registro.restaurar_config_banco()
            self._cerrar(dlg)
            self._seleccionar_entidad(self.dd_entidad.value)
            self._toast("Banco restaurado a sus valores originales.")
            self.page.update()

        cuerpo = ft.Container(width=640, content=ft.Column([
            ft.Text("Requisitos por NIVEL DE CUENTA (clientes)", weight=ft.FontWeight.BOLD),
            self.lista_niveles,
            ft.TextButton("Agregar requisito de nivel", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_requisito_nivel()),
            ft.Divider(),
            ft.Text("Limites de OPERACION por nivel (montos)", weight=ft.FontWeight.BOLD),
            ft.Row([self.tf_abono, self.tf_efectivo, self.tf_cheque_caja, self.tf_moneda_usd],
                  wrap=True),
            self.lista_limites,
            ft.TextButton("Agregar limite de operacion", icon=ft.Icons.ADD,
                          on_click=lambda e: self._editar_limite_op()),
            ft.Divider(),
            ft.Text("Parametros de validacion de clientes", weight=ft.FontWeight.BOLD),
            ft.Row(param_rows, wrap=True),
            ft.Text("Validaciones activas (desmarca para desactivar una validacion):",
                    size=11, color=TEXTO_MUTED),
            ft.Text("Por campo:", size=12, weight=ft.FontWeight.BOLD),
            ft.Column(list(checks_campo_boxes.values()), spacing=0),
            ft.Text("Generales:", size=12, weight=ft.FontWeight.BOLD),
            ft.Column(list(checks_generales_boxes.values()), spacing=0),
        ], scroll=ft.ScrollMode.AUTO, height=460))

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Editar validaciones de Banco"), content=cuerpo,
            actions=[ft.TextButton("Cancelar", on_click=lambda e: self._cerrar(dlg)),
                     ft.TextButton("Restaurar valores originales", on_click=restaurar),
                     ft.FilledButton("Guardar", on_click=aceptar)])
        self._abrir(dlg)

    # ================================================================== #
    # Helpers de dialogo / toast
    # ================================================================== #
    def _abrir(self, dlg):
        self.page.show_dialog(dlg)

    def _cerrar(self, dlg=None):
        self.page.pop_dialog()

    def _toast(self, msg: str):
        self.page.show_dialog(ft.SnackBar(ft.Text(msg)))


SPLASH_WINDOW_SIZE = 320
APP_WINDOW_SIZE = (1300, 860)


async def _mostrar_splash(page: ft.Page) -> None:
    """Pantalla de bienvenida (~3s): ventana sin marco y transparente, para
    que solo se vea el logo circular (assets/splash.png ya tiene fondo
    transparente) flotando sobre el escritorio, con fade-in + zoom, hold y
    fade-out."""
    page.title = "Validacion de BBDD"
    page.padding = 0

    # Ventana sin título/bordes y transparente: sin esto se ve el rectángulo
    # de la ventana detrás del círculo. "shadow=False" evita que quede un
    # contorno/sombra rectangular visible aunque el relleno sea transparente.
    page.window.frameless = True
    page.window.shadow = False
    page.window.bgcolor = ft.Colors.TRANSPARENT
    page.bgcolor = ft.Colors.TRANSPARENT
    page.window.width = SPLASH_WINDOW_SIZE
    page.window.height = SPLASH_WINDOW_SIZE
    page.update()   # aplica el resize ANTES de centrar; si no, center() usa el tamaño viejo
    await asyncio.sleep(0.05)  # deja que el SO termine de aplicar frameless/resize
    await page.window.center()

    logo = ft.Container(
        content=ft.Image(src="splash.png", width=280, fit=ft.BoxFit.CONTAIN),
        opacity=0, scale=0.85,
        animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(500, ft.AnimationCurve.EASE_OUT),
    )
    page.add(ft.Container(content=logo, alignment=ft.Alignment.CENTER, expand=True))
    page.update()

    await asyncio.sleep(0.05)  # deja pintar el primer frame (opacity 0) antes de animar
    logo.opacity = 1
    logo.scale = 1.0
    page.update()

    await asyncio.sleep(2.1)   # logo visible (0.5 + 2.1 + 0.4 = 3s en total)

    logo.opacity = 0
    page.update()
    await asyncio.sleep(0.4)   # fade-out

    page.controls.clear()

    # Deshacer lo específico del splash: la app real necesita ventana normal
    # (con marco, tamaño de trabajo, centrada, no transparente). aplicar_tema()
    # en App.__init__ vuelve a fijar bgcolor/ícono.
    #
    # OJO con el ORDEN: se redimensiona y se CENTRA primero, todavía en modo
    # frameless (geometría simple, sin barra de título de por medio), y RECIÉN
    # DESPUÉS se restaura el marco. Centrar DESPUÉS de quitar "frameless"
    # (como se hacía antes) deja que el cálculo de centrado corra mientras el
    # SO todavía está agregando la barra de título, y la ventana terminaba mal
    # posicionada (el menú "cortado y fuera de la ventana" reportado antes).
    # Restaurar el marco al final puede correr el contenido unos pixeles (alto
    # de la barra de título), pero es un desvío menor vs. quedar mal centrada.
    page.window.width, page.window.height = APP_WINDOW_SIZE
    page.update()
    await asyncio.sleep(0.05)
    await page.window.center()
    await asyncio.sleep(0.05)  # deja asentar la posición antes de agregar el marco
    page.window.frameless = False
    page.window.shadow = True
    page.update()


async def main(page: ft.Page):
    await _mostrar_splash(page)
    App(page)