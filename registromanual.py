"""
Ventana de registro manual de entradas y salidas.

Para cuando el escaner no esta disponible: se busca el articulo en la lista,
se selecciona y se marca con un boton, sin teclear codigos. Por dentro hace
exactamente lo mismo que un escaneo (inventario.registrar_escaneo), asi que
aplican las mismas reglas: operador obligatorio, no sacar lo que ya esta
fuera, no sacar mas de lo que hay, etc.

Se abre desde la ventana de escaneo (app.py) con el boton "Registro manual"
o con F4.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

import inventario
import tema
from inventario import MODO_ENTRADA, MODO_SALIDA, fmt

if TYPE_CHECKING:  # solo para el editor; importarlo de verdad seria circular
    from app import AppInventario


class VentanaManual(tk.Toplevel):
    """Registro de entradas y salidas sin lector.

    Necesita la ventana de escaneo para compartir su conexion, su operador
    activo y para que refresque su tabla despues de cada movimiento.
    """

    def __init__(self, app: AppInventario) -> None:
        super().__init__(app)
        self.app = app
        self.con = app.con
        self._personas: dict[str, str] = {}   # texto del combo -> codigo

        self.title("Registro manual de entradas y salidas")
        self.configure(bg=tema.FONDO)
        self.geometry("920x600")
        self.minsize(740, 480)
        self.transient(app)

        self._construir()
        self._cargar_personas()
        self._filtrar()
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(100, self.buscador.focus_set)

    def _construir(self) -> None:
        # --- operador y buscador
        arriba = tk.Frame(self, bg=tema.FONDO)
        arriba.pack(fill="x", padx=16, pady=(14, 6))

        tema.titulo(arriba, "OPERADOR").pack(side="left", padx=(0, 8))
        self.operador = tk.StringVar()
        combo = ttk.Combobox(arriba, textvariable=self.operador, state="readonly",
                             width=30, font=("Segoe UI", 10))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._al_elegir_operador)
        self.combo_operador = combo

        self.texto_busqueda = tk.StringVar()
        self.texto_busqueda.trace_add("write", lambda *_: self._filtrar())
        self.buscador = tema.entrada(arriba, textvariable=self.texto_busqueda,
                                     width=30)
        self.buscador.pack(side="right", ipady=4)
        tema.titulo(arriba, "BUSCAR").pack(side="right", padx=(16, 8))

        # --- lista de articulos
        marco = tk.Frame(self, bg=tema.FONDO)
        marco.pack(fill="both", expand=True, padx=16, pady=6)
        columnas = ("codigo", "nombre", "tipo", "disponible", "ubicacion")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings",
                                  selectmode="browse")
        anchos = {"codigo": 100, "nombre": 320, "tipo": 110,
                  "disponible": 120, "ubicacion": 160}
        titulos = {"codigo": "Codigo", "nombre": "Articulo", "tipo": "Tipo",
                   "disponible": "Disponible", "ubicacion": "Ubicacion"}
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col],
                              anchor="center" if col in ("tipo", "disponible")
                              else "w")
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tabla.tag_configure("FUERA", foreground=tema.TXT_SALIDA)
        self.tabla.bind("<<TreeviewSelect>>", lambda e: self._al_seleccionar())

        # --- seleccion, cantidad y botones
        abajo = tk.Frame(self, bg=tema.PANEL)
        abajo.pack(fill="x", padx=16, pady=6)

        self.lbl_seleccion = tk.Label(abajo, text="Selecciona un articulo de la lista",
                                      bg=tema.PANEL, fg=tema.SUAVE, anchor="w",
                                      font=("Segoe UI", 11, "bold"))
        self.lbl_seleccion.pack(side="left", fill="x", expand=True,
                                padx=14, pady=12)

        tema.boton(abajo, "Registrar ENTRADA", lambda: self._registrar(MODO_ENTRADA),
                   color=tema.VERDE, font=("Segoe UI", 10, "bold")
                   ).pack(side="right", padx=(4, 14), pady=10)
        tema.boton(abajo, "Registrar SALIDA", lambda: self._registrar(MODO_SALIDA),
                   color=tema.AMBAR, font=("Segoe UI", 10, "bold")
                   ).pack(side="right", padx=4, pady=10)

        self.cantidad = tk.StringVar(value="1")
        self.spin_cantidad = tk.Spinbox(
            abajo, from_=0.5, to=9999, increment=1, width=6,
            textvariable=self.cantidad, font=("Segoe UI", 14), justify="center",
            bg=tema.CAMPO, fg=tema.TEXTO, relief="flat", buttonbackground=tema.PANEL,
            disabledbackground=tema.PANEL, disabledforeground=tema.SUAVE)
        self.spin_cantidad.pack(side="right", padx=(4, 12))
        tk.Label(abajo, text="Cantidad", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="right")

        # --- resultado del ultimo registro
        self.resultado = tk.Label(self, text="", bg=tema.FONDO, fg=tema.TEXTO, anchor="w",
                                  font=("Segoe UI", 11, "bold"), padx=14, pady=8)
        self.resultado.pack(fill="x", padx=16, pady=(0, 14))

    # ------------------------------------------------------------ datos
    def _cargar_personas(self) -> None:
        self._personas = {
            f"{p['nombre']}  ({p['codigo']})": p["codigo"]
            for p in inventario.listar_personas(self.con)
        }
        self.combo_operador["values"] = list(self._personas)
        # Si ya hay un operador activo en la ventana de escaneo, se respeta.
        for texto, codigo in self._personas.items():
            if codigo == self.app.persona:
                self.operador.set(texto)
                break

    def _filtrar(self) -> None:
        seleccion = self.tabla.selection()
        self.tabla.delete(*self.tabla.get_children())
        for art in inventario.listar_articulos(self.con,
                                               self.texto_busqueda.get().strip()):
            if art["tipo"] == "UNICO":
                tipo = "Herramienta"
                disponible = "En bodega" if art["estado"] == "EN_BODEGA" else "Fuera"
            elif art["tipo"] == "AGRUPADO":
                tipo = "Con cantidad"
                disponible = inventario.texto_existencia(art)
            else:
                tipo = "Material"
                disponible = f"{fmt(art['existencia'])} {art['unidad']}"
            self.tabla.insert("", "end", iid=art["codigo"], tags=(art["estado"],),
                              values=(art["codigo"], art["nombre"], tipo,
                                      disponible, art["ubicacion"] or ""))
        if seleccion and self.tabla.exists(seleccion[0]):
            self.tabla.selection_set(seleccion[0])
            self.tabla.see(seleccion[0])
        self._al_seleccionar()

    # ------------------------------------------------------------ eventos
    def _al_elegir_operador(self, _evento=None) -> None:
        texto = self.operador.get()
        codigo = self._personas.get(texto)
        if codigo:
            self.app.fijar_persona(codigo, texto.rsplit("  (", 1)[0])

    def _al_seleccionar(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            self.lbl_seleccion.config(text="Selecciona un articulo de la lista",
                                      fg=tema.SUAVE)
            self.spin_cantidad.config(state="normal")
            return
        valores = self.tabla.item(seleccion[0], "values")
        self.lbl_seleccion.config(text=f"{valores[0]}  {valores[1]}", fg=tema.TEXTO)
        # Una herramienta es pieza unica: la cantidad no aplica.
        if valores[2] == "Herramienta":
            self.cantidad.set("1")
            self.spin_cantidad.config(state="disabled")
        else:
            self.spin_cantidad.config(state="normal")

    def _registrar(self, modo: str) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Sin articulo",
                                   "Selecciona primero un articulo de la lista.",
                                   parent=self)
            return
        persona = self._personas.get(self.operador.get())
        if not persona:
            messagebox.showwarning("Sin operador",
                                   "Elige el operador que hace el movimiento.",
                                   parent=self)
            self.combo_operador.focus_set()
            return
        try:
            cantidad = float(str(self.cantidad.get()).replace(",", "."))
        except ValueError:
            messagebox.showwarning("Cantidad invalida",
                                   "Escribe una cantidad numerica.", parent=self)
            return

        # Herramienta con cantidad: el mismo dialogo que al escanear, para
        # elegir cuantas y, al regresar, de quien son.
        if self.tabla.item(seleccion[0], "values")[2] == "Con cantidad":
            self.app.abrir_agrupado(seleccion[0], modo, cantidad=cantidad,
                                    operador=persona, padre=self,
                                    nota="registro manual",
                                    al_terminar=self._tras_agrupado)
            return

        resultado = inventario.registrar_escaneo(
            self.con, seleccion[0], persona=persona, modo=modo, cantidad=cantidad,
            nota="registro manual",
        )
        self.app.tras_movimiento(resultado)
        self._mostrar_resultado(resultado)

    def _tras_agrupado(self, resultado) -> None:
        if resultado is not None:
            self._mostrar_resultado(resultado)
        else:
            self._filtrar()

    def _mostrar_resultado(self, resultado) -> None:
        color = tema.COLOR_NIVEL.get(resultado.nivel, tema.PANEL)
        self.resultado.config(
            bg=color, fg=tema.color_texto_sobre(color),
            text=resultado.titulo + (f"   |   {resultado.detalle}"
                                     if resultado.detalle else ""))
        if resultado.ok:
            self.cantidad.set("1")
        self._filtrar()
