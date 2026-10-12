"""Colores y widgets comunes para las dos ventanas.

Hay dos paletas, "oscuro" y "claro". La elegida se guarda en datos/tema.txt
y se carga sola al importar este modulo, asi que cualquier ventana (escaneo,
catalogo, visor...) abre con el tema que el usuario dejo la ultima vez.

Los demas modulos leen los colores como tema.FONDO, tema.PANEL, etc. (no con
"from tema import ..."), para que siempre tomen la paleta vigente.

Cambiar de tema no repinta widget por widget: guarda la preferencia, cierra
la ventana y la vuelve a construir con la paleta nueva (ver cambiar_tema y
ejecutar). Es mas simple y fiable, y tarda un instante.

Tambien concentra lo que cambia entre Windows y macOS (fuentes, rueda del
mouse, botones de color, traer la ventana al frente). Todo va protegido con
ES_MAC / sys.platform: en Windows el resultado es el mismo de siempre.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

RAIZ = Path(__file__).resolve().parent
RUTA_PREFERENCIA = RAIZ / "datos" / "tema.txt"
RUTA_ICONO = RAIZ / "Inventario.ico"

# ------------------------------------------------------------ plataforma
ES_MAC = sys.platform == "darwin"
ES_WINDOWS = sys.platform.startswith("win")
ES_LINUX = sys.platform.startswith("linux")


def config_fuentes(plataforma: str = sys.platform) -> tuple[str, str, float]:
    """(fuente de interfaz, fuente monoespaciada, escala) para la plataforma.

    "Segoe UI" y "Consolas" no existen en Mac (Tk usaria otra sin avisar), y
    Tk en Mac trabaja a 72 dpi, asi que los mismos puntos se ven ~0.75x mas
    chicos que en Windows: por eso la escala. Ajustala aqui si hace falta.
    """
    if plataforma == "darwin":
        return "Helvetica Neue", "Menlo", 1.3
    if plataforma.startswith("win"):
        return "Segoe UI", "Consolas", 1.0
    return "DejaVu Sans", "DejaVu Sans Mono", 1.0


FUENTE_UI, FUENTE_MONO, ESCALA_FUENTE = config_fuentes()


def fuente(tam: int, *estilo: str) -> tuple:
    """Fuente de interfaz: tema.fuente(10) o tema.fuente(9, "bold")."""
    return (FUENTE_UI, round(tam * ESCALA_FUENTE), *estilo)


def fuente_mono(tam: int, *estilo: str) -> tuple:
    """Fuente monoespaciada (codigos, reportes en texto)."""
    return (FUENTE_MONO, round(tam * ESCALA_FUENTE), *estilo)

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
                try:
                    ventana.state("zoomed")
                except tk.TclError:
                    pass  # en Linux no existe "zoomed"
            traer_al_frente(ventana)
        ventana.mainloop()
        reapertura = getattr(ventana, "reapertura", None)
        if reapertura is None:
            break
        estado = reapertura["estado"]


def traer_al_frente(ventana: tk.Misc) -> None:
    """En Mac, al abrir desde Terminal la ventana puede quedar detras o sin
    foco, y el lector (que escribe como teclado) mandaria los codigos a la
    Terminal. Aqui se sube al frente y se toma el foco. En Windows no hace
    nada."""
    if not ES_MAC:
        return
    ventana.update_idletasks()
    ventana.lift()
    ventana.attributes("-topmost", True)
    ventana.after(300, lambda: ventana.attributes("-topmost", False))
    ventana.focus_force()


def poner_icono(ventana: tk.Misc) -> None:
    """Icono .ico de la ventana. Solo Windows: en Mac/Linux iconbitmap no
    acepta .ico y lanzaria un error."""
    if not ES_WINDOWS:
        return
    try:
        ventana.iconbitmap(str(RUTA_ICONO))
    except tk.TclError:
        pass  # sin icono, pero la ventana abre igual


def pasos_rueda(delta: int, plataforma: str = sys.platform) -> int:
    """Unidades para yview_scroll segun el delta de <MouseWheel>.

    En Windows delta viene en multiplos de 120; en Mac en valores chicos
    (+-1, +-2...). Positivo = rueda hacia arriba = desplazar hacia arriba.
    """
    if not delta:
        return 0
    if plataforma == "darwin":
        return -int(delta)
    return -(int(delta / 120) or (1 if delta > 0 else -1))


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


class BotonColor(tk.Label):
    """Boton de color hecho con un Label, para macOS.

    En Mac tk.Button es el boton nativo (Aqua): ignora bg, relief y
    activebackground, y todos los botones de color saldrian blancos. Este
    se comporta como el tk.Button que usa tema.boton(): command al soltar el
    clic dentro, invoke(), config(text=..., bg=...), estado "disabled" y
    color de presionado (activebackground / activeforeground).
    """

    def __init__(self, padre, command=None, activebackground=None,
                 activeforeground=None, state="normal", **kwargs) -> None:
        manita = kwargs.get("cursor") in (None, "hand2")
        if manita:
            kwargs["cursor"] = "hand2"
        kwargs.setdefault("disabledforeground", SUAVE)
        super().__init__(padre, state=state, **kwargs)
        if manita and ES_MAC:
            try:
                super().configure(cursor="pointinghand")  # manita nativa de Mac
            except tk.TclError:
                pass  # este Tk no la conoce: se queda hand2
        self._comando = command
        self._bg_normal = super().cget("bg")
        self._fg_normal = super().cget("fg")
        self._bg_activo = activebackground or AZUL
        self._fg_activo = activeforeground or SOBRE_COLOR
        self._presionado = False
        self.bind("<ButtonPress-1>", self._al_presionar)
        self.bind("<ButtonRelease-1>", self._al_soltar)
        self.bind("<Leave>", lambda e: self._pintar(False))
        self.bind("<Enter>", lambda e: self._pintar(self._presionado))

    def _habilitado(self) -> bool:
        return str(super().cget("state")) != "disabled"

    def _pintar(self, activo: bool) -> None:
        if activo and self._habilitado():
            super().configure(bg=self._bg_activo, fg=self._fg_activo)
        else:
            super().configure(bg=self._bg_normal, fg=self._fg_normal)

    def _al_presionar(self, _evento=None) -> None:
        if not self._habilitado():
            return
        self._presionado = True
        self._pintar(True)

    def _al_soltar(self, evento) -> None:
        if not self._presionado:
            return
        self._presionado = False
        self._pintar(False)
        dentro = (0 <= evento.x < self.winfo_width()
                  and 0 <= evento.y < self.winfo_height())
        if dentro:
            self.invoke()

    def invoke(self):
        """Ejecuta el comando, como tk.Button.invoke()."""
        if self._comando is None or not self._habilitado():
            return None
        return self._comando()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs = {**cnf, **kwargs}
        if "command" in kwargs:
            self._comando = kwargs.pop("command")
        if "activebackground" in kwargs:
            self._bg_activo = kwargs.pop("activebackground")
        if "activeforeground" in kwargs:
            self._fg_activo = kwargs.pop("activeforeground")
        # El color nuevo pasa a ser el normal (p. ej. "Dar de baja" en rojo
        # cambia a "Reactivar" en verde).
        for clave in ("bg", "background"):
            if clave in kwargs:
                self._bg_normal = kwargs[clave]
        for clave in ("fg", "foreground"):
            if clave in kwargs:
                self._fg_normal = kwargs[clave]
        if not kwargs:
            return super().configure()
        return super().configure(**kwargs)

    config = configure

    def cget(self, clave):
        if clave == "command":
            return self._comando
        if clave == "activebackground":
            return self._bg_activo
        if clave == "activeforeground":
            return self._fg_activo
        return super().cget(clave)

    __getitem__ = cget


def boton(padre, texto: str, comando, color: str | None = None,
          **kwargs) -> tk.Button:
    color = color or PANEL
    opciones = dict(bg=color, fg=color_texto_sobre(color), relief="flat",
                    font=fuente(10), padx=14, pady=6,
                    activebackground=AZUL, activeforeground=SOBRE_COLOR,
                    takefocus=False, cursor="hand2")
    opciones.update(kwargs)
    if ES_MAC:
        return BotonColor(padre, text=texto, command=comando, **opciones)
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
                    font=fuente(9, "bold"), anchor="w", **kwargs)


def entrada(padre, **kwargs) -> tk.Entry:
    return tk.Entry(padre, bg=CAMPO, fg=TEXTO, insertbackground=TEXTO,
                    relief="flat", font=fuente(11), **kwargs)


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
        pasos = pasos_rueda(evento.delta)
        if pasos:
            lienzo.yview_scroll(pasos, "units")

    def _vincular(_evento=None) -> None:
        lienzo.bind_all("<MouseWheel>", _rueda)
        if ES_LINUX:  # en Linux la rueda llega como botones 4 y 5
            lienzo.bind_all("<Button-4>", lambda e: lienzo.yview_scroll(-1, "units"))
            lienzo.bind_all("<Button-5>", lambda e: lienzo.yview_scroll(1, "units"))

    def _desvincular(_evento=None) -> None:
        lienzo.unbind_all("<MouseWheel>")
        if ES_LINUX:
            lienzo.unbind_all("<Button-4>")
            lienzo.unbind_all("<Button-5>")

    for widget in (lienzo, interno):
        widget.bind("<Enter>", _vincular)
        widget.bind("<Leave>", _desvincular)

    return contenedor, interno
