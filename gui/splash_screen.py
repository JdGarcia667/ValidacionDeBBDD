import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk
import time

class SplashScreen:
    def __init__(self, parent, min_display_time=2.0):
        self.parent = parent
        self.min_display_time = min_display_time
        self.start_time = None
        
        # Crear ventana de splash (Toplevel sin bordes)
        self.splash = tk.Toplevel(parent)
        self.splash.overrideredirect(True)
        self.splash.configure(bg='#2c3e50')  # Color de fondo
        
        # Dimensiones
        self.width = 500
        self.height = 300
        
        # Centrar en pantalla
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        x = (screen_width - self.width) // 2
        y = (screen_height - self.height) // 2
        self.splash.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        # Contenido
        self.frame = ttk.Frame(self.splash, padding="20")
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        ttk.Label(
            self.frame,
            text="Validador de Clientes",
            font=("Segoe UI", 20, "bold"),
            foreground="#3498db"
        ).pack(pady=(0, 20))
        
        # Subtítulo
        ttk.Label(
            self.frame,
            text="Sistema de Validación de Bases de Datos",
            font=("Segoe UI", 12),
            foreground="#ecf0f1"
        ).pack(pady=(0, 30))
        
        # Barra de progreso
        self.progress = ttk.Progressbar(
            self.frame,
            mode='indeterminate',
            bootstyle="info-striped"
        )
        self.progress.pack(fill=tk.X, pady=10)
        self.progress.start(10)
        
        # Mensaje de estado
        self.status_label = ttk.Label(
            self.frame,
            text="Cargando aplicación...",
            font=("Segoe UI", 9),
            foreground="#bdc3c7"
        )
        self.status_label.pack()
        
        # Ocultar ventana principal mientras se muestra splash
        self.parent.withdraw()
        
    def show(self):
        self.start_time = time.time()
        self.splash.update()
    
    def close(self):
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            if elapsed < self.min_display_time:
                time.sleep(self.min_display_time - elapsed)
        self.splash.destroy()
        self.parent.deiconify()  # Mostrar ventana principal
    
    def update_status(self, message):
        self.status_label.config(text=message)
        self.splash.update()