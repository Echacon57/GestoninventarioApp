"""Colores y widgets comunes para las dos ventanas.

Hay dos paletas, "oscuro" y "claro". La elegida se guarda en datos/tema.txt
y se carga sola al importar este modulo, asi que cualquier ventana (escaneo,
catalogo, visor...) abre con el tema que el usuario dejo la ultima vez.

Los demas modulos leen los colores como tema.FONDO, tema.PANEL, etc. (no con
"from tema import ..."), para que siempre tomen la paleta vigente.

Cambiar de tema no repinta widget por widget: guarda la preferencia, cierra
la ventana y la vuelve a construir con la paleta nueva (ver cambiar_tema y
ejecutar). Es mas simple y fiable, y tarda un instante.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

RUTA_PREFERENCIA = Path(__file__).resolve().parent / "datos" / "tema.txt"

# Todos los pares texto/fondo de ambas paletas cumplen WCAG AA (contraste
# >= 4.5:1).
# VERDE/ROJO/AMBAR/AZUL/CYAN son fondos (botones, banner de resultado, fila
# seleccionada) y llevan encima SOBRE_COLOR.
# TXT_* son colores de texto sobre FONDO/PANEL: TXT_OK/AVISO/ERROR para
# mensajes y estados, TXT_SALIDA/ENTRADA/BAJA para las filas de las tablas.
# En el tema oscuro un mismo tono no sirve para las dos cosas (de fondo con
# texto claro tiene que ser oscuro; como texto sobre gris oscuro, claro), por
# eso van separados.
PALETAS = {
    "oscuro": {
        "FONDO": "#1f2430",
        "PANEL": "#2a3040",
        "CAMPO": "#131722",
        "TEXTO": "#e8eaf0",
        "SUAVE": "#9aa3b5",
        "SOBRE_COLOR": "#e8eaf0",
        "VERDE": "#2b754a",
        "ROJO": "#b23a3a",
        "AMBAR": "#84621f",
        "AZUL": "#2f5d8a",
        "CYAN": "#3a4254",
        "TXT_OK": "#7fd6a0",
        "TXT_AVISO": "#e6b85c",
        "TXT_ERROR": "#f28b82",
        "TXT_SALIDA": "#f0a868",
        "TXT_ENTRADA": "#7fd6a0",
        "TXT_BAJA": "#6b7285",
    },

    "claro": {
        "FONDO": "#eef1f6",
        "PANEL": "#ffffff",
        "CAMPO": "#e3e8f0",
        "TEXTO": "#1b2330",
        "SUAVE": "#4a5568",
        "SOBRE_COLOR": "#ffffff",
        "VERDE": "#1d6b3f",
        "ROJO": "#b42318",
        "AMBAR": "#8a5a00",
        "AZUL": "#1f4f8f",
        "CYAN": "#00727f",
        "TXT_OK": "#1d6b3f",
        "TXT_AVISO": "#8a5a00",
        "TXT_ERROR": "#b42318",
        "TXT_SALIDA": "#a84a00",
        "TXT_ENTRADA": "#1d6b3f",
        "TXT_BAJA": "#6b7280",
    },
}
TEMA_POR_DEFECTO = "oscuro"

ACTUAL = TEMA_POR_DEFECTO
FONDO = PANEL = CAMPO = TEXTO = SUAVE = SOBRE_COLOR = ""
VERDE = ROJO = AMBAR = AZUL = CYAN = ""
TXT_OK = TXT_AVISO = TXT_ERROR = ""
TXT_SALIDA = TXT_ENTRADA = TXT_BAJA = ""
COLOR_NIVEL: dict[str, str] = {}


def aplicar_tema(nombre: str) -> None:
    """Carga la paleta `nombre` en las constantes del modulo. Las ventanas que
    se construyan despues ya salen con esos colores."""
    global ACTUAL, COLOR_NIVEL
    if nombre not in PALETAS:
        nombre = TEMA_POR_DEFECTO
    globals().update(PALETAS[nombre])
    ACTUAL = nombre
    COLOR_NIVEL = {"ok": VERDE, "aviso": AMBAR, "error": ROJO, "persona": AZUL}


def leer_preferencia() -> str:
    try:
        nombre = RUTA_PREFERENCIA.read_text(encoding="utf-8").strip()
    except OSError:
        return TEMA_POR_DEFECTO
    return nombre if nombre in PALETAS else TEMA_POR_DEFECTO


def guardar_preferencia(nombre: str) -> None:
    try:
        RUTA_PREFERENCIA.parent.mkdir(parents=True, exist_ok=True)
        RUTA_PREFERENCIA.write_text(nombre, encoding="utf-8")
    except OSError:
        pass  # si no se puede guardar, el cambio vale solo por esta sesion


def otro_tema() -> str:
    return "claro" if ACTUAL == "oscuro" else "oscuro"


def texto_cambio() -> str:
    """Rotulo del boton: dice a que modo se va a cambiar."""
    return "Modo claro" if ACTUAL == "oscuro" else "Modo oscuro"


def color_texto_sobre(fondo: str) -> str:
    """Texto legible encima de `fondo`: normal sobre los fondos neutros,
    SOBRE_COLOR encima de los colores fuertes."""
    return TEXTO if fondo in (FONDO, PANEL, CAMPO) else SOBRE_COLOR


aplicar_tema(leer_preferencia())


# ------------------------------------------------------------ cambio de tema
def cambiar_tema(ventana: tk.Tk, **estado) -> None:
    """Pasa al otro tema y pide reconstruir `ventana`.

    `estado` es lo que la ventana nueva debe recibir para continuar donde
    estaba (conexion, operador...). Solo funciona si la ventana se abrio con
    ejecutar().
    """
    nuevo = otro_tema()
    guardar_preferencia(nuevo)
    aplicar_tema(nuevo)
    ventana.reapertura = {
        "geometria": ventana.geometry(),
        "maximizada": ventana.state() == "zoomed",
        "estado": estado,
    }
    # Los after() pendientes (focos, refrescos periodicos) se cancelan para
    # que no disparen sobre widgets que ya no existen.
    for pendiente in ventana.tk.splitlist(ventana.tk.call("after", "info")):
        ventana.tk.call("after", "cancel", pendiente)
    ventana.destroy()


def ejecutar(crear) -> None:
    """Abre la ventana principal y la vuelve a abrir cada vez que se cambia
    de tema. `crear(**estado)` debe devolver una ventana tk.Tk nueva."""
    estado: dict = {}
    reapertura = None
    while True:
        ventana = crear(**estado)
        if reapertura:
            ventana.geometry(reapertura["geometria"])
            if reapertura["maximizada"]:
                ventana.state("zoomed")
        ventana.mainloop()
        reapertura = getattr(ventana, "reapertura", None)
        if reapertura is None:
            break
        estado = reapertura["estado"]


# ------------------------------------------------------------------ widgets
def aplicar_estilo(ventana: tk.Misc) -> ttk.Style:
    """Deja los widgets ttk a juego con el resto de la ventana."""
    estilo = ttk.Style(ventana)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass

    estilo.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=TEXTO, rowheight=24, borderwidth=0)
    estilo.configure("Treeview.Heading", background=FONDO, foreground=SUAVE,
                     borderwidth=0)
    estilo.map("Treeview", background=[("selected", AZUL)],
               foreground=[("selected", SOBRE_COLOR)])

    estilo.configure("TNotebook", background=FONDO, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=PANEL, foreground=SUAVE,
                     padding=(18, 9), borderwidth=0)
    estilo.map("TNotebook.Tab", background=[("selected", AZUL)],
               foreground=[("selected", SOBRE_COLOR)])

    estilo.configure("TCombobox", fieldbackground=CAMPO, background=PANEL,
                     foreground=TEXTO, arrowcolor=SUAVE, borderwidth=0)
    estilo.map("TCombobox", fieldbackground=[("readonly", CAMPO)],
               foreground=[("readonly", TEXTO)])

    # La lista desplegable del combobox es un Listbox clasico de Tk.
    ventana.option_add("*TCombobox*Listbox.background", CAMPO)
    ventana.option_add("*TCombobox*Listbox.foreground", TEXTO)
    ventana.option_add("*TCombobox*Listbox.selectBackground", AZUL)
    ventana.option_add("*TCombobox*Listbox.selectForeground", SOBRE_COLOR)
    return estilo


def boton(padre, texto: str, comando, color: str | None = None,
          **kwargs) -> tk.Button:
    color = color or PANEL
    opciones = dict(bg=color, fg=color_texto_sobre(color), relief="flat",
                    font=("Segoe UI", 10), padx=14, pady=6,
                    activebackground=AZUL, activeforeground=SOBRE_COLOR,
                    takefocus=False, cursor="hand2")
    opciones.update(kwargs)
    return tk.Button(padre, text=texto, command=comando, **opciones)


def boton_tema(padre, ventana: tk.Tk, obtener_estado=None,
               **kwargs) -> tk.Button:
    """Boton "Modo claro/oscuro". `obtener_estado()` devuelve lo que la
    ventana reconstruida debe recibir (ver cambiar_tema)."""
    def _cambiar() -> None:
        estado = obtener_estado() if obtener_estado else {}
        cambiar_tema(ventana, **estado)
    return boton(padre, texto_cambio(), _cambiar, **kwargs)


def titulo(padre, texto: str, **kwargs) -> tk.Label:
    return tk.Label(padre, text=texto, bg=kwargs.pop("bg", FONDO), fg=SUAVE,
                    font=("Segoe UI", 9, "bold"), anchor="w", **kwargs)


def entrada(padre, **kwargs) -> tk.Entry:
    return tk.Entry(padre, bg=CAMPO, fg=TEXTO, insertbackground=TEXTO,
                    relief="flat", font=("Segoe UI", 11), **kwargs)


def marco_desplazable(padre, bg: str | None = None) -> tuple[tk.Widget, tk.Frame]:
    """Devuelve (contenedor, marco_interno). Mete los widgets en marco_interno;
    si no caben en el alto disponible, aparece una barra de scroll sola.
    """
    bg = bg or PANEL
    contenedor = tk.Frame(padre, bg=bg)
    lienzo = tk.Canvas(contenedor, bg=bg, highlightthickness=0, bd=0)
    barra = ttk.Scrollbar(contenedor, orient="vertical", command=lienzo.yview)
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    interno = tk.Frame(lienzo, bg=bg)
    ventana = lienzo.create_window((0, 0), window=interno, anchor="nw")

    def _al_cambiar_tamano(_evento=None) -> None:
        lienzo.configure(scrollregion=lienzo.bbox("all"))
        lienzo.itemconfig(ventana, width=lienzo.winfo_width())

    interno.bind("<Configure>", _al_cambiar_tamano)
    lienzo.bind("<Configure>", _al_cambiar_tamano)

    def _rueda(evento) -> None:
        lienzo.yview_scroll(-1 * (evento.delta // 120 or 1), "units")

    for widget in (lienzo, interno):
        widget.bind("<Enter>", lambda e: lienzo.bind_all("<MouseWheel>", _rueda))
        widget.bind("<Leave>", lambda e: lienzo.unbind_all("<MouseWheel>"))

    return contenedor, interno
