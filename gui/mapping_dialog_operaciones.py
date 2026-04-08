import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from core.mapper_operaciones import MapperOperaciones

class MappingDialogOperaciones:
    def __init__(self, parent, columnas_disponibles):
        self.columnas_disponibles = columnas_disponibles
        self.mapeo = {}
        self.mapeo_confirmado = False
        self.campos_requeridos = MapperOperaciones.CAMPOS_REQUERIDOS
        self._updating = False

        self.top = ttk.Toplevel(parent)
        self.top.style.theme_use(parent.style.theme_use())
        self.top.title("Asignación de columnas - Operaciones")
        self.top.geometry("850x650")
        self.top.transient(parent)
        self.top.grab_set()

        main_frame = ttk.Frame(self.top, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Asignar columnas para operaciones",
                  font=("Segoe UI", 14, "bold")).pack(pady=(0, 5))
        ttk.Label(main_frame,
                  text="Para cada campo requerido, selecciona la columna correspondiente del archivo.\n"
                       "Si un campo no existe, marca 'No disponible'.\n"
                       "Las columnas ya asignadas desaparecerán de las opciones disponibles.",
                  font=("Segoe UI", 9), foreground="gray", justify="center").pack(pady=(0, 15))

        btn_auto_frame = ttk.Frame(main_frame)
        btn_auto_frame.pack(fill=tk.X, pady=(0, 10))
        auto_btn = ttk.Button(btn_auto_frame, text="🔍 Sugerir mapeo automático",
                              bootstyle="info", command=self.auto_mapping)
        auto_btn.pack()

        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0, bg=parent.style.colors.bg)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.widgets = {}
        self.check_vars = {}
        self.comboboxes = {}

        opciones_iniciales = [""] + self.columnas_disponibles

        for campo in self.campos_requeridos:
            frame_campo = ttk.Frame(scrollable_frame)
            frame_campo.pack(fill=tk.X, pady=2)

            lbl = ttk.Label(frame_campo, text=campo, width=25, anchor="w", font=("Segoe UI", 10))
            lbl.pack(side=tk.LEFT, padx=(0, 10))

            variable = tk.StringVar()
            combobox = ttk.Combobox(frame_campo, textvariable=variable,
                                    values=opciones_iniciales, state="readonly", width=35)
            combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
            combobox.set("")

            check_var = tk.IntVar()
            check = ttk.Checkbutton(frame_campo, text="No disponible", variable=check_var,
                                    bootstyle="danger",
                                    command=lambda c=campo: self.toggle_no_disponible(c))
            check.pack(side=tk.LEFT, padx=5)

            self.widgets[campo] = variable
            self.check_vars[campo] = check_var
            self.comboboxes[campo] = combobox

            variable.trace_add("write", lambda *args, c=campo: self.actualizar_opciones(c))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=15)

        ttk.Button(btn_frame, text="Confirmar asignación", bootstyle="success",
                   command=self.confirmar).pack(side=tk.RIGHT, padx=5)
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

    def auto_mapping(self):
        self._updating = True
        sugerencias = MapperOperaciones.map_columns(self.columnas_disponibles)
        for campo in self.campos_requeridos:
            if self.check_vars[campo].get() == 1:
                self.check_vars[campo].set(0)
                self.comboboxes[campo].config(state="readonly")
        for campo, col_sugerida in sugerencias.items():
            if campo not in self.comboboxes:
                continue
            if col_sugerida:
                self.widgets[campo].set(col_sugerida)
            else:
                self.widgets[campo].set("")
        self._updating = False
        self.refresh_all_comboboxes()
        messagebox.showinfo("Mapeo automático",
                            "Se han sugerido asignaciones según similitud de nombres.\n"
                            "Puedes ajustarlas manualmente o marcar 'No disponible'.",
                            parent=self.top)

    def toggle_no_disponible(self, campo):
        if self.check_vars[campo].get() == 1:
            self.comboboxes[campo].config(state="disabled")
            self.widgets[campo].set("")
        else:
            self.comboboxes[campo].config(state="readonly")
        self.refresh_all_comboboxes()

    def actualizar_opciones(self, campo_modificado):
        if not self._updating:
            self.refresh_all_comboboxes()

    def refresh_all_comboboxes(self):
        seleccionadas = set()
        for campo, var in self.widgets.items():
            if self.check_vars[campo].get() == 1:
                continue
            valor = var.get().strip()
            if valor and valor != "":
                seleccionadas.add(valor)

        for campo, combobox in self.comboboxes.items():
            if self.check_vars[campo].get() == 1:
                continue
            actual = self.widgets[campo].get().strip()
            opciones = [""]
            if actual and actual != "":
                opciones.append(actual)
            for col in self.columnas_disponibles:
                if col not in seleccionadas or col == actual:
                    if col not in opciones:
                        opciones.append(col)
            combobox['values'] = opciones
            if actual and actual not in opciones:
                self.widgets[campo].set("")
                self.top.after(10, self.refresh_all_comboboxes)
                return

    def confirmar(self):
        for campo in self.campos_requeridos:
            if self.check_vars[campo].get() == 1:
                self.mapeo[campo] = None
            else:
                seleccion = self.widgets[campo].get().strip()
                self.mapeo[campo] = seleccion if seleccion else None
        self.mapeo_confirmado = True
        self.top.destroy()

    def cancelar(self):
        self.top.destroy()