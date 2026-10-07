"""Colores y widgets comunes para las dos ventanas."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONDO = "#1f2430"
PANEL = "#2a3040"
CAMPO = "#131722"
TEXTO = "#e8eaf0"
SUAVE = "#9aa3b5"
VERDE = "#2e7d4f"
ROJO = "#b23a3a"
AMBAR = "#b3852a"
AZUL = "#2f5d8a"
CYAN = "#2f7d8a"

COLOR_NIVEL = {"ok": VERDE, "aviso": AMBAR, "error": ROJO, "persona": AZUL}


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
    estilo.map("Treeview", background=[("selected", AZUL)])

    estilo.configure("TNotebook", background=FONDO, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=PANEL, foreground=SUAVE,
                     padding=(18, 9), borderwidth=0)
    estilo.map("TNotebook.Tab", background=[("selected", AZUL)],
               foreground=[("selected", TEXTO)])

    estilo.configure("TCombobox", fieldbackground=CAMPO, background=PANEL,
                     foreground=TEXTO, arrowcolor=SUAVE, borderwidth=0)
    estilo.map("TCombobox", fieldbackground=[("readonly", CAMPO)])
    return estilo


def boton(padre, texto: str, comando, color: str = PANEL, **kwargs) -> tk.Button:
    opciones = dict(bg=color, fg=TEXTO, relief="flat", font=("Segoe UI", 10),
                    padx=14, pady=6, activebackground=AZUL,
                    activeforeground=TEXTO, takefocus=False, cursor="hand2")
    opciones.update(kwargs)
    return tk.Button(padre, text=texto, command=comando, **opciones)


def titulo(padre, texto: str, **kwargs) -> tk.Label:
    return tk.Label(padre, text=texto, bg=kwargs.pop("bg", FONDO), fg=SUAVE,
                    font=("Segoe UI", 9, "bold"), anchor="w", **kwargs)


def entrada(padre, **kwargs) -> tk.Entry:
    return tk.Entry(padre, bg=CAMPO, fg=TEXTO, insertbackground=TEXTO,
                    relief="flat", font=("Segoe UI", 11), **kwargs)


def marco_desplazable(padre, bg: str = PANEL) -> tuple[tk.Widget, tk.Frame]:
    """Devuelve (contenedor, marco_interno). Mete los widgets en marco_interno;
    si no caben en el alto disponible, aparece una barra de scroll sola.
    """
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
