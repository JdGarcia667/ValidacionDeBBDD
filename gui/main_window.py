import os
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
from core.file_reader import FileReader
from core.multi_file_loader import MultiFileLoader
from core.sqlite_validator import SQLiteValidator
from core.sqlite_validator_operaciones import SQLiteValidatorOperaciones
from gui.mapping_dialog import MappingDialog
from gui.mapping_dialog_operaciones import MappingDialogOperaciones
from core.validator import Validator
from core.validator_operaciones import ValidatorOperaciones
from core.report_generator import ReportGenerator
from gui.column_selector import ColumnSelectorDialog
from gui.config_operaciones import ConfigOperacionesDialog

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Validador de Clientes / Operaciones")
        self.root.geometry("700x600")
        self.root.resizable(False, False)

        # Variables de estado
        self.archivos = []               # lista de rutas de archivos seleccionados
        self.df = None                   # DataFrame si se carga en memoria
        self.db_path = None              # ruta de la base SQLite temporal
        self.table_name = None           # nombre de la tabla en SQLite
        self.mapeo = None
        self.tipo_base = tk.StringVar(value="clientes")
        self.use_sqlite_var = tk.BooleanVar(value=False)

        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Título
        ttk.Label(main_frame, text="Validador de Bases de Datos",
                  font=("Segoe UI", 16, "bold")).pack(pady=(0, 15))

        # Selector de tipo de base
        tipo_frame = ttk.Frame(main_frame)
        tipo_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(tipo_frame, text="Tipo de base:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 10))
        tipo_menu = ttk.Combobox(tipo_frame, textvariable=self.tipo_base,
                                 values=["clientes", "operaciones"], state="readonly", width=20)
        tipo_menu.pack(side=tk.LEFT)

        # Lista de archivos
        ttk.Label(main_frame, text="Archivos a procesar:", font=("Segoe UI", 10)).pack(anchor=tk.W, pady=(10,0))
        self.archivos_listbox = tk.Listbox(main_frame, height=5, selectmode=tk.EXTENDED)
        self.archivos_listbox.pack(fill=tk.X, pady=5)

        # Botones de gestión de archivos
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="➕ Agregar archivos", command=self.agregar_archivos).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="❌ Quitar seleccionados", command=self.quitar_archivos).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 Limpiar lista", command=self.limpiar_lista).pack(side=tk.LEFT, padx=2)

        # Checkbox para SQLite
        ttk.Checkbutton(main_frame, text="Usar SQLite para grandes volúmenes (recomendado si >500k filas)",
                        variable=self.use_sqlite_var, bootstyle="info").pack(anchor=tk.W, pady=5)

        # Botón de carga
        self.load_btn = ttk.Button(main_frame, text="Cargar y Analizar", bootstyle="success",
                                   command=self.load_files, state="normal")
        self.load_btn.pack(pady=15, ipadx=20, ipady=5)

        # Estado y progreso
        self.status_label = ttk.Label(main_frame, text="", font=("Segoe UI", 9))
        self.status_label.pack(pady=(0, 10))
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate', bootstyle="info-striped")

        self.center_window()

    # ------------------------------------------------------------
    # Gestión de la lista de archivos
    # ------------------------------------------------------------
    def agregar_archivos(self):
        filenames = filedialog.askopenfilenames(
            title="Seleccionar archivos",
            filetypes=[("Archivos soportados", "*.xlsx *.xls *.csv *.xml"), ("Todos", "*.*")]
        )
        for f in filenames:
            if f not in self.archivos:
                self.archivos.append(f)
                self.archivos_listbox.insert(tk.END, f)

    def quitar_archivos(self):
        seleccion = self.archivos_listbox.curselection()
        for i in reversed(seleccion):
            del self.archivos[i]
            self.archivos_listbox.delete(i)

    def limpiar_lista(self):
        self.archivos.clear()
        self.archivos_listbox.delete(0, tk.END)

    # ------------------------------------------------------------
    # Carga de archivos (memoria o SQLite)
    # ------------------------------------------------------------
    def load_files(self):
        if not self.archivos:
            messagebox.showwarning("Sin archivos", "Agrega al menos un archivo a la lista.")
            return

        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.status_label.config(text="Cargando archivos...")
        self.load_btn.config(state="disabled")
        self.root.update()

        try:
            use_sqlite = self.use_sqlite_var.get()
            if use_sqlite:
                db_path, table_name, total_rows = MultiFileLoader.load_files(self.archivos, use_sqlite=True)
                self.df = None
                self.db_path = db_path
                self.table_name = table_name
                self.status_label.config(text=f"✅ Datos cargados en SQLite: {total_rows} filas")
            else:
                self.df, _, total_rows = MultiFileLoader.load_files(self.archivos, use_sqlite=False)
                self.db_path = None
                self.status_label.config(text=f"✅ Archivos cargados: {total_rows} filas totales")
            self.progress.stop()
            self.progress.pack_forget()
            self.show_mapping_dialog()
        except MemoryWarning as e:
            self.progress.stop()
            self.progress.pack_forget()
            respuesta = messagebox.askyesno("Memoria insuficiente",
                str(e) + "\n¿Deseas usar SQLite para procesar los datos?")
            if respuesta:
                self.use_sqlite_var.set(True)
                self.load_files()
            else:
                self.load_btn.config(state="normal")
        except Exception as e:
            self.progress.stop()
            self.progress.pack_forget()
            self.load_btn.config(state="normal")
            messagebox.showerror("Error", f"No se pudo cargar:\n{str(e)}")

    # ------------------------------------------------------------
    # Diálogo de mapeo de columnas
    # ------------------------------------------------------------
    def show_mapping_dialog(self):
        # Obtener columnas (de una muestra)
        if self.db_path:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            muestra = pd.read_sql_query(f"SELECT * FROM {self.table_name} LIMIT 1", conn)
            columnas = list(muestra.columns)
            conn.close()
        else:
            columnas = list(self.df.columns)

        self.root.attributes('-disabled', True)
        if self.tipo_base.get() == "clientes":
            dialog = MappingDialog(self.root, columnas)
        else:
            dialog = MappingDialogOperaciones(self.root, columnas)
        self.root.wait_window(dialog.top)
        self.root.attributes('-disabled', False)

        if dialog.mapeo_confirmado:
            self.mapeo = dialog.mapeo
            if self.tipo_base.get() == "clientes":
                tipo_persona_default = None
                if self.mapeo.get('tipo de persona') is None:
                    respuesta = messagebox.askyesno(
                        "Tipo de persona",
                        "No se asignó la columna 'tipo de persona'.\n\n¿Todos los registros son personas físicas?"
                    )
                    tipo_persona_default = 'Física' if respuesta else 'Moral'
                self.ejecutar_validaciones_clientes(tipo_persona_default)
            else:
                self.ejecutar_validaciones_operaciones()
        else:
            self.status_label.config(text="Mapeo cancelado por el usuario")
            self.load_btn.config(state="normal")

    # ------------------------------------------------------------
    # Validación de CLIENTES (memoria o SQLite)
    # ------------------------------------------------------------
    def ejecutar_validaciones_clientes(self, tipo_persona_default=None):
        self.status_label.config(text="Ejecutando validaciones...")
        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.root.update()

        if self.db_path:
            validator = SQLiteValidator(self.db_path, self.table_name, self.mapeo, tipo_persona_default)
            errores_dataframes, _ = validator.validar_todo(update_callback=self.actualizar_estado)
        else:
            validator = Validator(self.df, self.mapeo, tipo_persona_default)
            errores_dataframes, _ = validator.validar_todo()

        self.progress.stop()
        self.progress.pack_forget()

        # Selección de columnas adicionales (solo si se usó memoria)
        columnas_adicionales = []
        if not self.db_path:
            selector = ColumnSelectorDialog(self.root, list(self.df.columns))
            self.root.wait_window(selector.top)
            columnas_adicionales = selector.columnas_seleccionadas if selector.confirmado else []

        archivo_salida = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            initialfile="reporte_validacion_clientes.xlsx",
            title="Guardar reporte de validación"
        )
        if not archivo_salida:
            self.status_label.config(text="Operación cancelada")
            self.load_btn.config(state="normal")
            return

        df_muestra = self.df if self.df is not None else pd.DataFrame()
        ReportGenerator.generar_reporte(errores_dataframes, df_muestra, self.mapeo, archivo_salida, columnas_adicionales)

        # Eliminar archivo temporal SQLite si se usó
        if self.db_path and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
                self.db_path = None
            except Exception as e:
                print(f"No se pudo eliminar {self.db_path}: {e}")

        self.status_label.config(text=f"✅ Reporte guardado: {archivo_salida}")
        self.load_btn.config(state="normal")

    # ------------------------------------------------------------
    # Validación de OPERACIONES (memoria o SQLite)
    # ------------------------------------------------------------
    def ejecutar_validaciones_operaciones(self):
        self.status_label.config(text="Configurando validación de operaciones...")
        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.root.update()

        config_dialog = ConfigOperacionesDialog(self.root)
        self.root.wait_window(config_dialog.top)
        if not config_dialog.confirmado:
            self.progress.stop()
            self.progress.pack_forget()
            self.status_label.config(text="Configuración cancelada")
            self.load_btn.config(state="normal")
            return

        config = config_dialog.config
        self.progress.stop()
        self.progress.pack_forget()

        self.status_label.config(text="Validando operaciones...")
        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.root.update()

        def actualizar_estado(mensaje):
            self.status_label.config(text=mensaje)
            self.root.update_idletasks()

        if self.db_path:
            validator = SQLiteValidatorOperaciones(self.db_path, self.table_name, self.mapeo, config, chunksize=50000)
            errores_dataframes, _ = validator.validar_todo(update_callback=actualizar_estado)
        else:
            validator = ValidatorOperaciones(self.df, self.mapeo, config, update_callback=actualizar_estado)
            errores_dataframes, _ = validator.validar_todo()

        self.progress.stop()
        self.progress.pack_forget()
        self.root.update()

        archivo_salida = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            initialfile="reporte_operaciones.xlsx",
            title="Guardar reporte de operaciones"
        )
        if not archivo_salida:
            self.status_label.config(text="Operación cancelada")
            self.load_btn.config(state="normal")
            return

        df_muestra = self.df if self.df is not None else pd.DataFrame()
        ReportGenerator.generar_reporte(errores_dataframes, df_muestra, self.mapeo, archivo_salida, [])

        # Eliminar archivo temporal SQLite si se usó
        if self.db_path and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
                self.db_path = None
            except Exception as e:
                print(f"No se pudo eliminar {self.db_path}: {e}")

        self.status_label.config(text=f"✅ Reporte guardado: {archivo_salida}")
        self.load_btn.config(state="normal")

    # ------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def actualizar_estado(self, mensaje):
        self.status_label.config(text=mensaje)
        self.root.update_idletasks()