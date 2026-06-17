import logging
import tkinter as tk

import ttkbootstrap as ttk

from gui.main_window import MainWindow
from gui.splash_screen import SplashScreen


def _configurar_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("validador.log", encoding="utf-8"),
        ],
    )


def main():
    _configurar_logging()
    # Crear ventana raíz de ttkbootstrap (tema moderno)
    root = ttk.Window(themename="superhero")  # Puedes cambiar el tema
    root.title("Validador de Clientes")
    root.geometry("600x400")
    
    # Mostrar splash screen
    splash = SplashScreen(root)
    splash.show()
    
    # Inicializar aplicación principal
    app = MainWindow(root)
    
    # Cerrar splash después de un breve retraso (simula carga)
    root.after(2000, splash.close)  # 2 segundos de splash
    
    # Iniciar el bucle de eventos
    root.mainloop()

if __name__ == "__main__":
    main()