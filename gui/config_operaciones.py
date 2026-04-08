import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
import pandas as pd

class ConfigOperacionesDialog:
    def __init__(self, parent):
        self.config = {}
        self.confirmado = False
        self.archivo_udis = None
        self.archivo_tc = None
        self.mapeo_udis = None
        self.mapeo_tc = None

        self.top = ttk.Toplevel(parent)
        self.top.title("Configurar validación de operaciones")
        self.top.geometry("650x600")
        self.top.transient(parent)
        self.top.grab_set()

        notebook = ttk.Notebook(self.top)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ========== Pestaña 1: Moneda ==========
        frame_moneda = ttk.Frame(notebook)
        notebook.add(frame_moneda, text="Moneda")
        
        self.moneda_var = tk.StringVar(value="MONEDA NACIONAL")
        ttk.Label(frame_moneda, text="Selecciona la moneda de análisis:").pack(pady=10)
        for op in ["MONEDA NACIONAL", "UDIS", "DOLARES", "TODAS"]:
            ttk.Radiobutton(frame_moneda, text=op, variable=self.moneda_var, value=op).pack(anchor=tk.W, padx=20, pady=2)

        # ========== Pestaña 2: Archivos de conversión ==========
        frame_archivos = ttk.Frame(notebook)
        notebook.add(frame_archivos, text="Archivos de conversión")
        
        # Marco para UDIS
        self.udis_frame = ttk.LabelFrame(frame_archivos, text="UDIS")
        self.udis_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Marco para Tipo de cambio
        self.tc_frame = ttk.LabelFrame(frame_archivos, text="Tipo de cambio USD/MXN")
        self.tc_frame.pack(fill=tk.X, padx=5, pady=5)

        self.udis_path_var = tk.StringVar()
        self.tc_path_var = tk.StringVar()

        # Contenido UDIS
        ttk.Label(self.udis_frame, text="Archivo Excel con valores UDIS:").pack(anchor=tk.W, padx=5, pady=2)
        f1 = ttk.Frame(self.udis_frame)
        f1.pack(fill=tk.X, padx=5, pady=2)
        ttk.Entry(f1, textvariable=self.udis_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(f1, text="Examinar", command=self.cargar_udis).pack(side=tk.RIGHT)
        self.udis_status = ttk.Label(self.udis_frame, text="", foreground="gray")
        self.udis_status.pack(anchor=tk.W, padx=5)

        # Contenido Tipo de cambio
        ttk.Label(self.tc_frame, text="Archivo Excel con tipo de cambio (USD/MXN):").pack(anchor=tk.W, padx=5, pady=2)
        f2 = ttk.Frame(self.tc_frame)
        f2.pack(fill=tk.X, padx=5, pady=2)
        ttk.Entry(f2, textvariable=self.tc_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(f2, text="Examinar", command=self.cargar_tc).pack(side=tk.RIGHT)
        self.tc_status = ttk.Label(self.tc_frame, text="", foreground="gray")
        self.tc_status.pack(anchor=tk.W, padx=5)

        # ========== Pestaña 3: Agrupación ==========
        frame_agrup = ttk.Frame(notebook)
        notebook.add(frame_agrup, text="Agrupación")
        
        self.agrup_var = tk.StringVar(value="por_instrumento")
        ttk.Label(frame_agrup, text="¿Agrupar por instrumento monetario?").pack(pady=10)
        ttk.Radiobutton(frame_agrup, text="Sí, agrupar por instrumento", variable=self.agrup_var, value="por_instrumento").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(frame_agrup, text="No, agrupar todas las operaciones", variable=self.agrup_var, value="todas").pack(anchor=tk.W, padx=20)

        # ========== Pestaña 4: Filtros de monto ==========
        frame_filtros = ttk.Frame(notebook)
        notebook.add(frame_filtros, text="Filtros de monto")
        
        self.filtros = []
        ttk.Label(frame_filtros, text="Define reglas de monto máximo por grupo (cliente-mes-tipo)").pack(anchor=tk.W, padx=5)
        ttk.Label(frame_filtros, text="Ejemplo: Monto total > 100,000 o < 5,000").pack(anchor=tk.W, padx=5, pady=5)

        self.listbox_filtros = tk.Listbox(frame_filtros, height=5)
        self.listbox_filtros.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        frame_add = ttk.Frame(frame_filtros)
        frame_add.pack(fill=tk.X, pady=5)
        self.filtro_operador = ttk.Combobox(frame_add, values=[">", "<", ">=", "<="], state="readonly", width=5)
        self.filtro_operador.pack(side=tk.LEFT, padx=5)
        self.filtro_valor = ttk.Entry(frame_add, width=15)
        self.filtro_valor.pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_add, text="Agregar filtro", command=self.agregar_filtro).pack(side=tk.LEFT, padx=5)

        # ========== Botones finales ==========
        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Confirmar", bootstyle="success", command=self.confirmar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", bootstyle="secondary", command=self.cancelar).pack(side=tk.RIGHT, padx=5)

        # Control de visibilidad de archivos según moneda
        self.actualizar_visibilidad_archivos()
        self.moneda_var.trace_add("write", lambda *a: self.actualizar_visibilidad_archivos())

    def actualizar_visibilidad_archivos(self):
        moneda = self.moneda_var.get()
        if moneda in ["UDIS", "TODAS"]:
            self.udis_frame.pack(fill=tk.X, padx=5, pady=5)
        else:
            self.udis_frame.pack_forget()
        if moneda in ["DOLARES", "TODAS"]:
            self.tc_frame.pack(fill=tk.X, padx=5, pady=5)
        else:
            self.tc_frame.pack_forget()

    def cargar_udis(self):
        archivo = filedialog.askopenfilename(title="Seleccionar archivo UDIS", filetypes=[("Excel", "*.xlsx *.xls")])
        if archivo:
            self.udis_path_var.set(archivo)
            self.archivo_udis = archivo
            self.mapeo_udis = self.mapear_columnas_conversion("UDIS", archivo)
            if self.mapeo_udis:
                self.udis_status.config(text="✅ Archivo cargado y mapeado", foreground="green")
            else:
                self.udis_path_var.set("")
                self.archivo_udis = None

    def cargar_tc(self):
        archivo = filedialog.askopenfilename(title="Seleccionar archivo tipo de cambio", filetypes=[("Excel", "*.xlsx *.xls")])
        if archivo:
            self.tc_path_var.set(archivo)
            self.archivo_tc = archivo
            self.mapeo_tc = self.mapear_columnas_conversion("Tipo de cambio", archivo)
            if self.mapeo_tc:
                self.tc_status.config(text="✅ Archivo cargado y mapeado", foreground="green")
            else:
                self.tc_path_var.set("")
                self.archivo_tc = None

    def mapear_columnas_conversion(self, nombre, archivo):
        """Diálogo simple para mapear columna fecha y columna valor."""
        try:
            df_temp = pd.read_excel(archivo, nrows=5)
            columnas = list(df_temp.columns)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer {archivo}\n{str(e)}")
            return None

        top = tk.Toplevel(self.top)
        top.title(f"Mapear columnas - {nombre}")
        top.geometry("400x250")
        top.transient(self.top)
        top.grab_set()

        ttk.Label(top, text="Selecciona la columna de FECHA:").pack(pady=5)
        fecha_var = tk.StringVar()
        fecha_combo = ttk.Combobox(top, textvariable=fecha_var, values=columnas, state="readonly")
        fecha_combo.pack(pady=5, padx=10, fill=tk.X)
        
        ttk.Label(top, text="Selecciona la columna de VALOR (tasa):").pack(pady=5)
        valor_var = tk.StringVar()
        valor_combo = ttk.Combobox(top, textvariable=valor_var, values=columnas, state="readonly")
        valor_combo.pack(pady=5, padx=10, fill=tk.X)

        mapeo = {}

        def aceptar():
            if not fecha_var.get() or not valor_var.get():
                messagebox.showwarning("Incompleto", "Debes seleccionar ambas columnas")
                return
            mapeo['fecha'] = fecha_var.get()
            mapeo['valor'] = valor_var.get()
            top.destroy()

        btn_frame = ttk.Frame(top)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Aceptar", command=aceptar, bootstyle="success").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=top.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

        self.top.wait_window(top)
        return mapeo if mapeo else None

    def agregar_filtro(self):
        op = self.filtro_operador.get()
        val = self.filtro_valor.get().strip()
        if not op or not val:
            messagebox.showwarning("Filtro incompleto", "Selecciona operador y valor.")
            return
        try:
            val_num = float(val)
        except:
            messagebox.showerror("Error", "El valor debe ser numérico.")
            return
        self.filtros.append((op, val_num))
        self.listbox_filtros.insert(tk.END, f"{op} {val_num}")

    def confirmar(self):
        moneda = self.moneda_var.get()
        # Validar archivos necesarios
        if moneda in ["UDIS", "TODAS"] and not self.archivo_udis:
            messagebox.showerror("Error", "Para UDIS debes cargar el archivo de valores UDIS")
            return
        if moneda in ["DOLARES", "TODAS"] and not self.archivo_tc:
            messagebox.showerror("Error", "Para DÓLARES debes cargar el archivo de tipo de cambio")
            return

        self.config = {
            'moneda': moneda,
            'agrupacion': self.agrup_var.get(),
            'filtros': self.filtros,
            'archivo_udis': self.archivo_udis,
            'archivo_tc': self.archivo_tc,
            'mapeo_udis': self.mapeo_udis,
            'mapeo_tc': self.mapeo_tc
        }
        self.confirmado = True
        self.top.destroy()

    def cancelar(self):
        self.top.destroy()