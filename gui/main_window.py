import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from core.file_reader import FileReader
from gui.mapping_dialog import MappingDialog
from core.validator import Validator
from core.report_generator import ReportGenerator
from gui.column_selector import ColumnSelectorDialog

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Validador de Clientes")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        # Variables (ahora se crean después de que root exista)
        self.file_path = tk.StringVar()
        self.df = None
        self.mapeo = None
        
        # Frame principal con padding
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = ttk.Label(
            main_frame, 
            text="Validador de Bases de Datos de Clientes",
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Subtítulo / instrucciones
        instr_label = ttk.Label(
            main_frame, 
            text="Selecciona un archivo con los datos de clientes.\n"
                 "Formatos soportados: Excel (.xlsx, .xls), CSV, XML",
            font=("Segoe UI", 10),
            foreground="gray"
        )
        instr_label.pack(pady=(0, 20))
        
        # Frame para selección de archivo
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=10)
        
        file_entry = ttk.Entry(
            file_frame, 
            textvariable=self.file_path,
            font=("Segoe UI", 10)
        )
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_btn = ttk.Button(
            file_frame,
            text="📂 Examinar",
            bootstyle="info-outline",
            command=self.browse_file
        )
        browse_btn.pack(side=tk.RIGHT)
        
        # Botón de cargar (acentuado)
        self.load_btn = ttk.Button(
            main_frame,
            text="Cargar y Analizar",
            bootstyle="success",
            command=self.load_file,
            state="disabled"
        )
        self.load_btn.pack(pady=20, ipadx=20, ipady=5)
        
        # Etiqueta de estado
        self.status_label = ttk.Label(
            main_frame,
            text="",
            font=("Segoe UI", 9)
        )
        self.status_label.pack(pady=(0, 10))
        
        # Barra de progreso (inicialmente oculta)
        self.progress = ttk.Progressbar(
            main_frame,
            mode='indeterminate',
            bootstyle="info-striped"
        )
        
        # Centrar ventana
        self.center_window()
        
        # Habilitar/deshabilitar botón según haya ruta
        self.file_path.trace_add("write", self.check_file_selected)
    
    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def check_file_selected(self, *args):
        if self.file_path.get():
            self.load_btn.config(state="normal")
        else:
            self.load_btn.config(state="disabled")
    
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Seleccionar archivo",
            filetypes=[("Archivos soportados", "*.xlsx *.xls *.csv *.xml"), ("Todos", "*.*")]
        )
        if filename:
            self.file_path.set(filename)
    
    def load_file(self):
        path = self.file_path.get()
        if not path:
            return
        
        # Mostrar progreso
        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.status_label.config(text="Cargando archivo...")
        self.load_btn.config(state="disabled")
        self.root.update()
        
        try:
            self.df = FileReader.read(path)
            self.progress.stop()
            self.progress.pack_forget()
            self.status_label.config(text=f"✅ Archivo cargado: {len(self.df)} filas, {len(self.df.columns)} columnas")
            self.show_mapping_dialog()
        except Exception as e:
            self.progress.stop()
            self.progress.pack_forget()
            self.load_btn.config(state="normal")
            messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{str(e)}")
            self.status_label.config(text="❌ Error al cargar el archivo")
    
    def show_mapping_dialog(self):
        self.root.attributes('-disabled', True)
        dialog = MappingDialog(self.root, list(self.df.columns))
        self.root.wait_window(dialog.top)
        self.root.attributes('-disabled', False)
        
        if dialog.mapeo_confirmado:
            self.mapeo = dialog.mapeo
            
            tipo_persona_default = None
            if self.mapeo.get('tipo de persona') is None:
                respuesta = messagebox.askyesno(
                    "Tipo de persona",
                    "No se asignó la columna 'tipo de persona'.\n\n"
                    "¿Todos los registros son de personas físicas?\n"
                    "Selecciona Sí para personas físicas, No para personas morales."
                )
                if respuesta:
                    tipo_persona_default = 'Física'
                else:
                    tipo_persona_default = 'Moral'
            
            self.ejecutar_validaciones(tipo_persona_default)
        else:
            self.status_label.config(text="Mapeo cancelado por el usuario")
            self.load_btn.config(state="normal")
    
    def ejecutar_validaciones(self, tipo_persona_default=None):
        self.status_label.config(text="Ejecutando validaciones...")
        self.progress.pack(pady=10, fill=tk.X)
        self.progress.start(10)
        self.root.update()
        
        validator = Validator(self.df, self.mapeo, tipo_persona_default)
        errores_dataframes, errores_totales = validator.validar_todo()
        
        # Selector de columnas adicionales
        selector = ColumnSelectorDialog(self.root, list(self.df.columns))
        self.root.wait_window(selector.top)
        columnas_adicionales = selector.columnas_seleccionadas if selector.confirmado else []
        
        # Guardar reporte
        archivo_salida = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos Excel", "*.xlsx")],
            initialfile="reporte_validacion.xlsx",
            title="Guardar reporte de validación"
        )
        if not archivo_salida:
            self.progress.stop()
            self.progress.pack_forget()
            self.status_label.config(text="Operación cancelada")
            self.load_btn.config(state="normal")
            return
        
        ReportGenerator.generar_reporte(
            errores_dataframes,
            self.df,
            self.mapeo,
            archivo_salida,
            columnas_adicionales
        )
        
        self.progress.stop()
        self.progress.pack_forget()
        messagebox.showinfo("Validaciones completadas",
                           f"Reporte generado en:\n{archivo_salida}")
        self.status_label.config(text=f"✅ Reporte guardado: {archivo_salida}")
        self.load_btn.config(state="normal")