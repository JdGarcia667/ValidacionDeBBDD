import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk

class ColumnSelectorDialog:
    def __init__(self, parent, columnas_disponibles):
        self.columnas_seleccionadas = []
        self.confirmado = False

        self.top = tk.Toplevel(parent)
        self.top.title("Seleccionar columnas adicionales para el reporte")
        self.top.geometry("500x400")
        self.top.transient(parent)
        self.top.grab_set()

        # Aplicar tema heredado
        main_frame = ttk.Frame(self.top, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Selecciona las columnas adicionales que deseas incluir en el reporte de errores:",
                  font=("Segoe UI", 10)).pack(pady=(0, 10))

        frame_list = ttk.Frame(main_frame)
        frame_list.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(frame_list)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(frame_list, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set,
                                  font=("Segoe UI", 9))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        for col in sorted(columnas_disponibles):
            self.listbox.insert(tk.END, col)

        ttk.Label(main_frame, text="Puedes seleccionar varias columnas manteniendo presionada la tecla Ctrl (Windows) o Cmd (Mac).",
                  font=("Segoe UI", 8), foreground="gray").pack(pady=5)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="Aceptar", bootstyle="success",
                   command=self.aceptar).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", bootstyle="secondary",
                   command=self.cancelar).pack(side=tk.RIGHT, padx=5)

        self.center_window()

    def center_window(self):
        self.top.update_idletasks()
        width = self.top.winfo_width()
        height = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top.winfo_screenheight() // 2) - (height // 2)
        self.top.geometry(f'{width}x{height}+{x}+{y}')

    def aceptar(self):
        seleccion = self.listbox.curselection()
        self.columnas_seleccionadas = [self.listbox.get(i) for i in seleccion]
        self.confirmado = True
        self.top.destroy()

    def cancelar(self):
        self.top.destroy()