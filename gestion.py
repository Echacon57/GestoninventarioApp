"""
Panel de gestion del catalogo.
Esta parte puede abrirse sin necesidad de abrir app.py anteriormente,
pero en un ciclo natural, esta parte siempre es abierta por un botón en app.py.

Ventana con dos pestanas (Herramienta y material / Personal) donde se dan de
alta, se editan, se dan de baja y se imprimen las etiquetas sin escribir un
solo comando.

Se abre solo:               python gestion.py
o desde la ventana de escaneo con el boton "Catalogo".
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import db
import etiquetas
import inventario
import snapshot
import tema
from inventario import fmt


def _imprimir(elementos: list[dict], nombre: str, ventana) -> None:
    """Genera el HTML de etiquetas y lo abre en el navegador."""
    if not elementos:
        messagebox.showinfo("Nada que imprimir",
                            "No hay etiquetas para esa seleccion.",
                            parent=ventana)
        return
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = etiquetas.generar_hoja(
        elementos, etiquetas.DIR_SALIDA / f"{marca}_{nombre}.html",
        titulo="Etiquetas de bodega")
    webbrowser.open(Path(ruta).resolve().as_uri())


# Pestaña de articulos

class FichaArticulos(tk.Frame):
    def __init__(self, padre, con, al_cambiar=None):
        super().__init__(padre, bg=tema.FONDO)
        self.con = con
        self.al_cambiar = al_cambiar
        self.codigo_actual: str | None = None
        self._construir()
        self.refrescar()
        self.limpiar()

    # ------------------------------------------------------------ montaje
    def _construir(self) -> None:
        self.columnconfigure(0, weight=1, minsize=560)
        self.columnconfigure(1, weight=0, minsize=380)
        self.rowconfigure(0, weight=1)

        # ---- izquierda: buscador y lista
        izq = tk.Frame(self, bg=tema.FONDO)
        izq.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=14)
        izq.rowconfigure(2, weight=1)
        izq.columnconfigure(0, weight=1)

        barra = tk.Frame(izq, bg=tema.FONDO)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew")
        tema.titulo(barra, "Buscar").pack(side="left", padx=(0, 8))
        self.busqueda = tk.StringVar()
        self.busqueda.trace_add("write", lambda *_: self.refrescar())
        caja = tema.entrada(barra, textvariable=self.busqueda)
        caja.pack(side="left", fill="x", expand=True, ipady=4)

        fila_filtros = tk.Frame(izq, bg=tema.FONDO)
        fila_filtros.grid(row=1, column=0, columnspan=2, sticky="ew",
                          pady=(6, 4))

        self.ver_bajas = tk.BooleanVar(value=False)
        tk.Checkbutton(fila_filtros, text="Mostrar tambien los dados de baja",
                       variable=self.ver_bajas, command=self.refrescar,
                       bg=tema.FONDO, fg=tema.SUAVE, selectcolor=tema.PANEL, bd=0,
                       activebackground=tema.FONDO, activeforeground=tema.TEXTO,
                       font=("Segoe UI", 9), highlightthickness=0
                       ).pack(side="left")

        tk.Label(fila_filtros, text="Estado:", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(18, 4))
        self.filtro_estado = ttk.Combobox(
            fila_filtros, state="readonly", width=16, font=("Segoe UI", 9),
            values=["Todos", "En bodega", "Fuera de la bodega"])
        self.filtro_estado.current(0)
        self.filtro_estado.pack(side="left")
        self.filtro_estado.bind("<<ComboboxSelected>>",
                                lambda e: self.refrescar())

        tk.Label(fila_filtros, text="Ubicacion:", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
        self.filtro_ubicacion = ttk.Combobox(
            fila_filtros, state="readonly", width=16, font=("Segoe UI", 9),
            values=["Todas"])
        self.filtro_ubicacion.current(0)
        self.filtro_ubicacion.pack(side="left")
        self.filtro_ubicacion.bind("<<ComboboxSelected>>",
                                   lambda e: self.refrescar())

        columnas = ("codigo", "nombre", "tipo", "exist", "ubicacion", "estado")
        titulos = {"codigo": "Codigo", "nombre": "Nombre", "tipo": "Tipo",
                   "exist": "Exist.", "ubicacion": "Ubicacion",
                   "estado": "Estado"}
        anchos = {"codigo": 80, "nombre": 196, "tipo": 86, "exist": 112,
                  "ubicacion": 100, "estado": 78}
        self.tabla = ttk.Treeview(izq, columns=columnas, show="headings")
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col], minwidth=60,
                              stretch=(col == "nombre"),
                              anchor="center" if col in ("exist", "tipo",
                                                         "estado") else "w")
        self.tabla.grid(row=2, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(izq, orient="vertical", command=self.tabla.yview)
        barra_v.grid(row=2, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=barra_v.set)
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)
        self.tabla.tag_configure("baja", foreground=tema.TXT_BAJA)
        self.tabla.tag_configure("fuera", foreground=tema.TXT_SALIDA)

        barra_inf = tk.Frame(izq, bg=tema.FONDO)
        barra_inf.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        tema.boton(barra_inf, "Imprimir etiquetas de la lista",
                   self.imprimir_lista).pack(side="left")
        self.conteo = tk.Label(barra_inf, text="", bg=tema.FONDO, fg=tema.SUAVE,
                               font=("Segoe UI", 9))
        self.conteo.pack(side="right")

        # ---- formulario nuevo articulo
        contenedor_der, self.der = tema.marco_desplazable(self, tema.PANEL)
        contenedor_der.grid(row=0, column=1, sticky="nsew", padx=(8, 14),
                            pady=14)
        self.der.columnconfigure(1, weight=1)

        self.encabezado = tk.Label(self.der, text="Nuevo articulo", bg=tema.PANEL,
                                   fg=tema.TEXTO, font=("Segoe UI", 15, "bold"),
                                   anchor="w")
        self.encabezado.grid(row=0, column=0, columnspan=2, sticky="ew",
                             padx=16, pady=(16, 2))
        self.lbl_codigo = tk.Label(self.der, text="El codigo se asigna solo",
                                   bg=tema.PANEL, fg=tema.SUAVE,
                                   font=("Consolas", 11), anchor="w")
        self.lbl_codigo.grid(row=1, column=0, columnspan=2, sticky="ew",
                             padx=16, pady=(0, 10))

        fila = 2
        self.nombre = self._campo("Nombre", fila); fila += 1

        tk.Label(self.der, text="Tipo", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).grid(row=fila, column=0,
                                                    sticky="nw", padx=16,
                                                    pady=(3, 0))
        self.tipo = tk.StringVar(value="UNICO")
        marco_tipo = tk.Frame(self.der, bg=tema.PANEL)
        marco_tipo.grid(row=fila, column=1, sticky="w", padx=(0, 16), pady=3)
        for valor in inventario.TIPOS:
            tk.Radiobutton(marco_tipo, text=inventario.NOMBRE_TIPO[valor],
                           value=valor,
                           variable=self.tipo, command=self._ajustar_tipo,
                           bg=tema.PANEL, fg=tema.TEXTO, selectcolor=tema.CAMPO, bd=0,
                           activebackground=tema.PANEL, activeforeground=tema.TEXTO,
                           font=("Segoe UI", 10), highlightthickness=0,
                           anchor="w", justify="left", wraplength=190
                           ).pack(anchor="w")
        fila += 1

        # Linea de ayuda: explica el tipo elegido.
        self.ayuda_tipo = tk.Label(self.der, text="", bg=tema.PANEL,
                                   fg=tema.SUAVE, font=("Segoe UI", 9),
                                   anchor="w", justify="left", wraplength=320)
        self.ayuda_tipo.grid(row=fila, column=0, columnspan=2, sticky="ew",
                             padx=16, pady=(0, 6))
        fila += 1

        self.categoria = self._combo("Categoria", fila); fila += 1
        self.ubicacion = self._combo("Ubicacion", fila); fila += 1
        self.unidad = self._campo("Unidad", fila); fila += 1
        self.existencia = self._campo("Existencia", fila); fila += 1
        self.minimo = self._campo("Minimo para avisar", fila); fila += 1

        self.marca, self.modelo = self._campo_doble(
            "Marca", "Modelo", fila); fila += 1
        self.numero_serie, self.valor_unitario = self._campo_doble(
            "N. de serie", "Valor unitario ($)", fila); fila += 1

        tk.Label(self.der, text="Notas", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).grid(row=fila, column=0,
                                                    sticky="nw", padx=16,
                                                    pady=(6, 0))
        self.notas = tk.Text(self.der, height=3, width=26, bg=tema.CAMPO, fg=tema.TEXTO, bd=0,
                             insertbackground=tema.TEXTO, font=("Segoe UI", 10),
                             relief="flat", wrap="word")
        self.notas.grid(row=fila, column=1, sticky="ew", padx=(0, 16), pady=6)
        fila += 1

        self.aviso = tk.Label(self.der, text="", bg=tema.PANEL, fg=tema.TXT_AVISO,
                              font=("Segoe UI", 9), anchor="w", wraplength=300,
                              justify="left")
        self.aviso.grid(row=fila, column=0, columnspan=2, sticky="ew",
                        padx=16, pady=(4, 0))
        fila += 1

        botones = tk.Frame(self.der, bg=tema.PANEL)
        botones.grid(row=fila, column=0, columnspan=2, sticky="ew",
                     padx=16, pady=14)
        self.btn_guardar = tema.boton(botones, "Guardar", self.guardar, tema.VERDE)
        self.btn_guardar.pack(side="left")

        #tema.boton(botones, "Nuevo", self.limpiar).pack(side="left", padx=6)

        self.btn_nuevo = tema.boton(botones, "Nuevo", self.limpiar, tema.CYAN)
        self.btn_nuevo.pack(side="left")

        self.btn_baja = tema.boton(botones, "Dar de baja", self.dar_baja, tema.ROJO)
        self.btn_baja.pack(side="left")
        fila += 1

        self.btn_etiqueta = tema.boton(self.der, "Imprimir esta etiqueta",
                                       self.imprimir_actual, tema.CYAN)
        self.btn_etiqueta.grid(row=fila, column=0, columnspan=2, sticky="w",
                               padx=16, pady=(0, 16))

    def _campo(self, etiqueta: str, fila: int) -> tk.Entry:
        rotulo = tk.Label(self.der, text=etiqueta, bg=tema.PANEL, fg=tema.SUAVE,
                          font=("Segoe UI", 9, "bold"))
        rotulo.grid(row=fila, column=0, sticky="w", padx=16)
        campo = tema.entrada(self.der)
        campo.rotulo = rotulo  # para cambiar el texto segun el tipo
        campo.grid(row=fila, column=1, sticky="ew", padx=(0, 16), pady=3,
                   ipady=3)
        return campo

    def _campo_doble(self, etiqueta_izq: str, etiqueta_der: str,
                     fila: int) -> tuple[tk.Entry, tk.Entry]:
        """Dos campos cortos en la misma fila, para no alargar el formulario."""
        marco = tk.Frame(self.der, bg=tema.PANEL)
        marco.grid(row=fila, column=0, columnspan=2, sticky="ew",
                   padx=16, pady=3)
        marco.columnconfigure(0, weight=1)
        marco.columnconfigure(1, weight=1)

        sub_izq = tk.Frame(marco, bg=tema.PANEL)
        sub_izq.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Label(sub_izq, text=etiqueta_izq, bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        campo_izq = tema.entrada(sub_izq)
        campo_izq.pack(fill="x", ipady=3)

        sub_der = tk.Frame(marco, bg=tema.PANEL)
        sub_der.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        tk.Label(sub_der, text=etiqueta_der, bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        campo_der = tema.entrada(sub_der)
        campo_der.pack(fill="x", ipady=3)

        return campo_izq, campo_der

    def _combo(self, etiqueta: str, fila: int) -> ttk.Combobox:
        tk.Label(self.der, text=etiqueta, bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).grid(row=fila, column=0,
                                                    sticky="w", padx=16)
        combo = ttk.Combobox(self.der, font=("Segoe UI", 11))
        combo.grid(row=fila, column=1, sticky="ew", padx=(0, 16), pady=3)
        return combo

    # ------------------------------------------------------------ datos
    def refrescar(self) -> None:
        self.tabla.delete(*self.tabla.get_children())
        estado_map = {"En bodega": "EN_BODEGA", "Fuera de la bodega": "FUERA"}
        ubic = self.filtro_ubicacion.get()
        filas = inventario.listar_articulos(
            self.con, self.busqueda.get().strip(), self.ver_bajas.get(),
            estado=estado_map.get(self.filtro_estado.get(), ""),
            ubicacion="" if ubic in ("", "Todas") else ubic)
        for f in filas:
            prestado = f["tipo"] == "AGRUPADO" and f["prestado"] > 0
            etiquetas_fila = []
            if not f["activo"]:
                etiquetas_fila.append("baja")
            elif f["estado"] == "FUERA" or prestado:
                etiquetas_fila.append("fuera")
            estado = ("baja" if not f["activo"]
                      else "parcial" if prestado and f["estado"] == "EN_BODEGA"
                      else "bodega" if f["estado"] == "EN_BODEGA" else "fuera")
            self.tabla.insert(
                "", "end", iid=f["codigo"],
                values=(f["codigo"], f["nombre"],
                        inventario.TIPO_CORTO.get(f["tipo"], f["tipo"]),
                        inventario.texto_existencia(f),
                        f["ubicacion"], estado),
                tags=tuple(etiquetas_fila))
        valor_total = sum(inventario.valor_articulo(f) for f in filas)
        self.conteo.config(
            text=f"{len(filas)} articulo(s)   ·   "
                 f"{inventario.fmt_dinero(valor_total)}")
        self._cargar_sugerencias()

    def _cargar_sugerencias(self) -> None:
        for campo, columna in ((self.categoria, "categoria"),
                               (self.ubicacion, "ubicacion")):
            valores = [f[0] for f in self.con.execute(
                f"SELECT DISTINCT {columna} FROM articulos "
                f"WHERE {columna} <> '' ORDER BY 1")]
            campo["values"] = valores

        ubicaciones = [f[0] for f in self.con.execute(
            "SELECT DISTINCT ubicacion FROM articulos "
            "WHERE ubicacion <> '' ORDER BY 1")]
        seleccion_previa = self.filtro_ubicacion.get()
        self.filtro_ubicacion["values"] = ["Todas"] + ubicaciones
        if seleccion_previa in ubicaciones or seleccion_previa == "Todas":
            self.filtro_ubicacion.set(seleccion_previa)
        else:
            self.filtro_ubicacion.current(0)

    def _al_seleccionar(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if seleccion:
            self.cargar(seleccion[0])

    def cargar(self, codigo: str) -> None:
        art = inventario.buscar_articulo(self.con, codigo)
        if art is None:
            return
        self.codigo_actual = art["codigo"]
        self.encabezado.config(text=art["nombre"][:34])
        self.lbl_codigo.config(text=art["codigo"], fg=tema.TEXTO)

        self._poner(self.nombre, art["nombre"])
        self.tipo.set(art["tipo"])
        self.categoria.set(art["categoria"])
        self.ubicacion.set(art["ubicacion"])
        self._poner(self.unidad, art["unidad"])
        self._poner(self.existencia, fmt(art["existencia"]))
        self._poner(self.minimo, fmt(art["minimo"]))
        self._poner(self.marca, art["marca"])
        self._poner(self.modelo, art["modelo"])
        self._poner(self.numero_serie, art["numero_serie"])
        self._poner(self.valor_unitario, fmt(art["valor_unitario"]))
        self.notas.delete("1.0", "end")
        self.notas.insert("1.0", art["notas"])

        activo = bool(art["activo"])
        self.btn_baja.config(text="Dar de baja" if activo else "Reactivar",
                             bg=tema.ROJO if activo else tema.VERDE)
        texto_aviso = "" if activo else ("Este articulo esta dado de baja: el "
                                         "escaner lo rechaza hasta que lo reactives.")
        if art["tipo"] == "AGRUPADO" and art["prestado"] > 0:
            quienes = ", ".join(f"{p['nombre']} ({fmt(p['cantidad'])})"
                                for p in inventario.prestamos_de(self.con, codigo))
            texto_aviso = (f"Prestadas: {fmt(art['prestado'])}  ·  {quienes}  ·  "
                           f"total {fmt(art['existencia'] + art['prestado'])}"
                           + (f"\n{texto_aviso}" if texto_aviso else ""))
        self.aviso.config(text=texto_aviso, fg=tema.TXT_AVISO)
        self._ajustar_tipo()

    def limpiar(self) -> None:
        self.codigo_actual = None
        self.tabla.selection_remove(*self.tabla.selection())
        self.encabezado.config(text="Nuevo articulo")
        self.lbl_codigo.config(text="El codigo se asigna solo al guardar",
                               fg=tema.SUAVE)
        for campo in (self.nombre, self.unidad, self.existencia, self.minimo,
                     self.marca, self.modelo, self.numero_serie,
                     self.valor_unitario):
            self._poner(campo, "")
        self.categoria.set("")
        self.ubicacion.set("")
        self.tipo.set("UNICO")
        self._poner(self.unidad, "pza")
        self._poner(self.existencia, "1")
        self._poner(self.minimo, "0")
        self._poner(self.valor_unitario, "0")
        self.notas.delete("1.0", "end")
        self.btn_baja.config(text="Dar de baja", bg=tema.ROJO)
        self.aviso.config(text="")
        self._ajustar_tipo()
        self.nombre.focus_set()

    @staticmethod
    def _poner(campo: tk.Entry, valor) -> None:
        """Escribe en el campo aunque este bloqueado, y lo deja como estaba.

        Sin esto, al seleccionar un consumible los campos de cantidad
        seguian mostrando los valores del articulo anterior.
        """
        estado = str(campo.cget("state"))
        campo.config(state="normal")
        campo.delete(0, "end")
        campo.insert(0, str(valor))
        if estado != "normal":
            campo.config(state=estado)

    def _avisar_cambio(self) -> None:
        """Notifica a quien creo este panel que hubo un alta/edicion/baja,
        para que publique una foto actualizada si hay carpeta compartida."""
        if self.al_cambiar:
            self.al_cambiar()

    AYUDA_TIPO = {
        "UNICO": "Una sola pieza con su propia etiqueta. Al escanearla se "
                 "alterna entre prestada y en bodega.",
        "AGRUPADO": "Varias piezas iguales con UNA etiqueta (extensiones, "
                    "cintas de medir...). Al escanear se elige cuantas se "
                    "sacan o regresan y queda registrado quien las tiene. "
                    "Existencia = piezas disponibles en bodega.",
        "CONSUMIBLE": "Material que se gasta (cable, taquetes...). Al sacarlo "
                      "baja la existencia y no se espera que regrese.",
    }

    def _ajustar_tipo(self) -> None:
        """Una herramienta unica no lleva cantidad ni minimo: se bloquean."""
        tipo = self.tipo.get()
        con_cantidad = tipo in ("CONSUMIBLE", "AGRUPADO")
        self.ayuda_tipo.config(text=self.AYUDA_TIPO.get(tipo, ""))
        self.existencia.rotulo.config(
            text="Disponibles en bodega" if tipo == "AGRUPADO" else "Existencia")
        estado = "normal" if con_cantidad else "disabled"
        for campo in (self.unidad, self.existencia, self.minimo):
            campo.config(state=estado,
                         disabledbackground=tema.PANEL, disabledforeground=tema.SUAVE)
        if not con_cantidad and self.codigo_actual is None:
            for campo, valor in ((self.unidad, "pza"), (self.existencia, "1"),
                                 (self.minimo, "0")):
                self._poner(campo, valor)

    # ------------------------------------------------------------ acciones
    def guardar(self) -> None:
        nombre = self.nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Falta el nombre",
                                   "Escribe al menos el nombre del articulo.",
                                   parent=self)
            self.nombre.focus_set()
            return

        tipo = self.tipo.get()
        try:
            if tipo in ("CONSUMIBLE", "AGRUPADO"):
                existencia = float((self.existencia.get() or "0").replace(",", "."))
                minimo = float((self.minimo.get() or "0").replace(",", "."))
                unidad = self.unidad.get().strip() or "pza"
            else:
                existencia, minimo, unidad = None, 0, "pza"
            valor_unitario = float((self.valor_unitario.get() or "0")
                                   .replace(",", "."))
        except ValueError:
            messagebox.showwarning("Cantidad invalida",
                                   "Existencia, minimo y valor unitario deben "
                                   "ser numeros.", parent=self)
            return
        if min(existencia or 0, minimo, valor_unitario) < 0:
            messagebox.showwarning("Cantidad invalida",
                                   "Existencia, minimo y valor unitario no "
                                   "pueden ser negativos.", parent=self)
            return

        # Cambio de tipo de un articulo que ya existe: se avisa que pasara
        # (por ejemplo, los prestamos que se reconstruyen) y se confirma.
        if self.codigo_actual is not None:
            permitido, mensaje, confirmar = inventario.resumen_cambio_tipo(
                self.con, self.codigo_actual, tipo)
            if not permitido:
                messagebox.showwarning("No se puede cambiar el tipo", mensaje,
                                       parent=self)
                return
            if confirmar and not messagebox.askyesno("Cambiar tipo", mensaje,
                                                     parent=self):
                return

        datos = dict(nombre=nombre, tipo=tipo,
                     categoria=self.categoria.get().strip(),
                     ubicacion=self.ubicacion.get().strip(),
                     unidad=unidad, minimo=minimo,
                     marca=self.marca.get().strip(),
                     modelo=self.modelo.get().strip(),
                     numero_serie=self.numero_serie.get().strip(),
                     valor_unitario=valor_unitario,
                     notas=self.notas.get("1.0", "end").strip())

        if self.codigo_actual is None:
            codigo = inventario.agregar_articulo(
                self.con, existencia=existencia, **datos)
            self.refrescar()
            self.cargar(codigo)
            self.tabla.selection_set(codigo)
            self.tabla.see(codigo)
            self._avisar_cambio()
            if messagebox.askyesno(
                    "Articulo guardado",
                    f"Se dio de alta como {codigo}.\n\n"
                    "¿Imprimo su etiqueta ahora?", parent=self):
                self.imprimir_actual()
        else:
            if existencia is not None:
                datos["existencia"] = existencia
            try:
                inventario.actualizar_articulo(self.con, self.codigo_actual,
                                               **datos)
            except ValueError as err:
                messagebox.showwarning("No se guardo", str(err), parent=self)
                return
            codigo = self.codigo_actual
            self.refrescar()
            self.cargar(codigo)
            self._avisar_cambio()
            self.aviso.config(text="Cambios guardados.", fg=tema.TXT_OK)
            self.after(2500, lambda: self.aviso.config(text="", fg=tema.TXT_AVISO))

    def dar_baja(self) -> None:
        if self.codigo_actual is None:
            return
        art = inventario.buscar_articulo(self.con, self.codigo_actual)
        activo = bool(art["activo"]) # type: ignore

        if activo:
            extra = ""
            if art["estado"] == "FUERA": # type: ignore
                extra = "\n\nOjo: ahora mismo esta FUERA de la bodega."
            if art["tipo"] == "AGRUPADO" and art["prestado"] > 0: # type: ignore
                extra = (f"\n\nOjo: tiene {fmt(art['prestado'])} pieza(s) " # type: ignore
                         "prestadas que dejaran de verse en Pendientes.")
            if not messagebox.askyesno(
                    "Dar de baja",
                    f"¿Dar de baja {art['nombre']}?\n\n" # type: ignore
                    "No se borra nada: el historial se conserva y el escaner "
                    "dejara de aceptarlo." + extra, parent=self):
                return

        inventario.baja_articulo(self.con, self.codigo_actual, activo=not activo)
        codigo = self.codigo_actual
        self.refrescar()
        self._avisar_cambio()
        if self.ver_bajas.get() or activo is False:
            self.cargar(codigo)
        else:
            self.limpiar()

    def imprimir_actual(self) -> None:
        if self.codigo_actual is None:
            messagebox.showinfo("Sin seleccion",
                                "Selecciona un articulo de la lista.",
                                parent=self)
            return
        elementos = etiquetas.elementos_por_codigo(
            self.con, [self.codigo_actual], avisar=None)
        _imprimir(elementos, "etiqueta", self)

    def imprimir_lista(self) -> None:
        codigos = list(self.tabla.get_children())
        elementos = etiquetas.elementos_por_codigo(self.con, codigos,
                                                   avisar=None)
        _imprimir(elementos, "articulos", self)



# Pestaña de personal
class FichaPersonas(tk.Frame):
    def __init__(self, padre, con, al_cambiar=None):
        super().__init__(padre, bg=tema.FONDO)
        self.con = con
        self.al_cambiar = al_cambiar
        self.codigo_actual: str | None = None
        self._construir()
        self.refrescar()
        self.limpiar()

    def _construir(self) -> None:
        self.columnconfigure(0, weight=1, minsize=560)
        self.columnconfigure(1, weight=0, minsize=380)
        self.rowconfigure(0, weight=1)

        izq = tk.Frame(self, bg=tema.FONDO)
        izq.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=14)
        izq.rowconfigure(1, weight=1)
        izq.columnconfigure(0, weight=1)

        self.ver_bajas = tk.BooleanVar(value=False)
        tk.Checkbutton(izq, text="Mostrar tambien al personal dado de baja",
                       variable=self.ver_bajas, command=self.refrescar,
                       bg=tema.FONDO, fg=tema.SUAVE, selectcolor=tema.PANEL, bd=0,
                       activebackground=tema.FONDO, activeforeground=tema.TEXTO,
                       font=("Segoe UI", 9), highlightthickness=0
                       ).grid(row=0, column=0, columnspan=2, sticky="w",
                              pady=(0, 6))

        columnas = ("codigo", "nombre", "estado", "pendientes")
        titulos = {"codigo": "Gafete", "nombre": "Nombre", "estado": "Estado",
                   "pendientes": "Fuera"}
        anchos = {"codigo": 86, "nombre": 240, "estado": 110, "pendientes": 90}
        self.tabla = ttk.Treeview(izq, columns=columnas, show="headings")
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col], minwidth=60,
                              stretch=(col == "nombre"),
                              anchor="center" if col in ("estado", "pendientes")
                              else "w")
        self.tabla.grid(row=1, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(izq, orient="vertical", command=self.tabla.yview)
        barra_v.grid(row=1, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=barra_v.set)
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)
        self.tabla.tag_configure("baja", foreground=tema.TXT_BAJA)
        self.tabla.tag_configure("debe", foreground=tema.TXT_SALIDA)

        pie = tk.Frame(izq, bg=tema.FONDO)
        pie.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        tema.boton(pie, "Imprimir todos los gafetes",
                   self.imprimir_todos).pack(side="left")
        self.conteo = tk.Label(pie, text="", bg=tema.FONDO, fg=tema.SUAVE,
                               font=("Segoe UI", 9))
        self.conteo.pack(side="right")

        der = tk.Frame(self, bg=tema.PANEL)
        der.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=14)
        der.columnconfigure(0, weight=1)

        self.encabezado = tk.Label(der, text="Nuevo operador", bg=tema.PANEL,
                                   fg=tema.TEXTO, font=("Segoe UI", 15, "bold"),
                                   anchor="w")
        self.encabezado.pack(fill="x", padx=16, pady=(16, 2))
        self.lbl_codigo = tk.Label(der, text="El gafete se asigna solo",
                                   bg=tema.PANEL, fg=tema.SUAVE, font=("Consolas", 11),
                                   anchor="w")
        self.lbl_codigo.pack(fill="x", padx=16, pady=(0, 12))

        tk.Label(der, text="Nombre completo", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x",
                                                                padx=16)
        self.nombre = tema.entrada(der)
        self.nombre.pack(fill="x", padx=16, pady=(2, 10), ipady=4)
        self.nombre.bind("<Return>", lambda e: self.guardar())

        self.aviso = tk.Label(der, text="", bg=tema.PANEL, fg=tema.TXT_AVISO,
                              font=("Segoe UI", 9), anchor="w", wraplength=300,
                              justify="left")
        self.aviso.pack(fill="x", padx=16)

        botones = tk.Frame(der, bg=tema.PANEL)
        botones.pack(fill="x", padx=16, pady=14)
        tema.boton(botones, "Guardar", self.guardar, tema.VERDE).pack(side="left")
        tema.boton(botones, "Nuevo", self.limpiar,tema.CYAN).pack(side="left", padx=6)
        self.btn_baja = tema.boton(botones, "Dar de baja", self.dar_baja, tema.ROJO)
        self.btn_baja.pack(side="left")

        tema.boton(der, "Imprimir este gafete",
                   self.imprimir_actual,tema.CYAN).pack(anchor="w", padx=16, pady=(0, 16))

    def refrescar(self) -> None:
        self.tabla.delete(*self.tabla.get_children())
        filas = inventario.listar_personas(self.con, self.ver_bajas.get())
        for f in filas:
            pendientes = inventario.tiene_pendientes(self.con, f["codigo"])
            marcas = []
            if not f["activo"]:
                marcas.append("baja")
            elif pendientes:
                marcas.append("debe")
            self.tabla.insert(
                "", "end", iid=f["codigo"],
                values=(f["codigo"], f["nombre"],
                        "activo" if f["activo"] else "dado de baja",
                        len(pendientes) or ""),
                tags=tuple(marcas))
        self.conteo.config(text=f"{len(filas)} persona(s)")

    def _al_seleccionar(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if seleccion:
            self.cargar(seleccion[0])

    def cargar(self, codigo: str) -> None:
        fila = self.con.execute("SELECT * FROM personas WHERE codigo = ?",
                                (codigo,)).fetchone()
        if fila is None:
            return
        self.codigo_actual = fila["codigo"]
        self.encabezado.config(text=fila["nombre"][:30])
        self.lbl_codigo.config(text=fila["codigo"], fg=tema.TEXTO)
        self.nombre.delete(0, "end")
        self.nombre.insert(0, fila["nombre"])

        activo = bool(fila["activo"])
        self.btn_baja.config(text="Dar de baja" if activo else "Reactivar",
                             bg=tema.ROJO if activo else tema.VERDE)

        pendientes = inventario.tiene_pendientes(self.con, fila["codigo"])
        if pendientes:
            lista = ", ".join(p["nombre"] for p in pendientes[:4])
            self.aviso.config(
                text=f"Tiene {len(pendientes)} articulo(s) sin devolver: {lista}",
                fg=tema.TXT_AVISO)
        elif not activo:
            self.aviso.config(text="Dado de baja: el escaner ya no lo reconoce.",
                              fg=tema.SUAVE)
        else:
            self.aviso.config(text="")

    def limpiar(self) -> None:
        self.codigo_actual = None
        self.tabla.selection_remove(*self.tabla.selection())
        self.encabezado.config(text="Nuevo operador")
        self.lbl_codigo.config(text="El gafete se asigna solo al guardar",
                               fg=tema.SUAVE)
        self.nombre.delete(0, "end")
        self.aviso.config(text="")
        self.btn_baja.config(text="Dar de baja", bg=tema.ROJO)
        self.nombre.focus_set()

    def _avisar_cambio(self) -> None:
        if self.al_cambiar:
            self.al_cambiar()

    def guardar(self) -> None:
        nombre = self.nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Falta el nombre",
                                   "Escribe el nombre de la persona.",
                                   parent=self)
            return

        if self.codigo_actual is None:
            codigo = inventario.agregar_persona(self.con, nombre)
            self.refrescar()
            self.cargar(codigo)
            self.tabla.selection_set(codigo)
            self._avisar_cambio()
            if messagebox.askyesno("Operador dado de alta",
                                   f"Gafete asignado: {codigo}\n\n"
                                   "¿Imprimo su gafete ahora?", parent=self):
                self.imprimir_actual()
        else:
            inventario.actualizar_persona(self.con, self.codigo_actual, nombre)
            codigo = self.codigo_actual
            self.refrescar()
            self.cargar(codigo)
            self._avisar_cambio()
            self.aviso.config(text="Cambios guardados.", fg=tema.TXT_OK)
            self.after(2500, lambda: self.aviso.config(text="", fg=tema.TXT_AVISO))

    def dar_baja(self) -> None:
        if self.codigo_actual is None:
            return
        fila = self.con.execute("SELECT * FROM personas WHERE codigo = ?",
                                (self.codigo_actual,)).fetchone()
        activo = bool(fila["activo"])

        if activo:
            pendientes = inventario.tiene_pendientes(self.con,
                                                     self.codigo_actual)
            extra = ""
            if pendientes:
                lista = "\n".join(f"  - {p['codigo']}  {p['nombre']}"
                                  for p in pendientes)
                extra = (f"\n\nTodavia tiene {len(pendientes)} articulo(s) "
                         f"sin devolver:\n{lista}")
            if not messagebox.askyesno(
                    "Dar de baja",
                    f"¿Dar de baja a {fila['nombre']}?\n\n"
                    "Su historial se conserva, pero su gafete dejara de "
                    "funcionar en el escaner." + extra, parent=self):
                return

        inventario.baja_persona(self.con, self.codigo_actual, activo=not activo)
        codigo = self.codigo_actual
        self.refrescar()
        self._avisar_cambio()
        if self.ver_bajas.get() or not activo:
            self.cargar(codigo)
        else:
            self.limpiar()

    def imprimir_actual(self) -> None:
        if self.codigo_actual is None:
            messagebox.showinfo("Sin seleccion",
                                "Selecciona una persona de la lista.",
                                parent=self)
            return
        fila = self.con.execute("SELECT * FROM personas WHERE codigo = ?",
                                (self.codigo_actual,)).fetchone()
        _imprimir([{"codigo": fila["codigo"], "nombre": fila["nombre"],
                    "extra": "gafete de operador"}], "gafete", self)

    def imprimir_todos(self) -> None:
        _imprimir(etiquetas.elementos_personas(self.con), "gafetes", self)


# ==========================================================================
# Ventana contenedora
# ==========================================================================

class PanelGestion(tk.Toplevel):
    def __init__(self, maestro=None, con=None, al_cerrar=None):
        super().__init__(maestro)
        self.con = con or db.conectar()
        self.al_cerrar = al_cerrar

        self.title("Catalogo - herramienta, material y personal")
        self.geometry("1120x700")
        self.minsize(960, 620)
        self.configure(bg=tema.FONDO)
        tema.aplicar_estilo(self)

        cuaderno = ttk.Notebook(self)
        cuaderno.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        self.articulos = FichaArticulos(cuaderno, self.con,
                                        al_cambiar=self._publicar_snapshot)
        self.personas = FichaPersonas(cuaderno, self.con,
                                      al_cambiar=self._publicar_snapshot)
        cuaderno.add(self.articulos, text="  Herramienta y material  ")
        cuaderno.add(self.personas, text="  Personal  ")

        pie = tk.Frame(self, bg=tema.FONDO)
        pie.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(pie, bg=tema.FONDO, fg=tema.SUAVE, font=("Segoe UI", 9),
                 text="Dar de baja no borra nada: el historial se conserva y el "
                      "articulo se puede reactivar cuando quieras.",
                 ).pack(side="left")
        tema.boton(pie, "Importar desde CSV", self.importar).pack(side="right",
                                                                  padx=4)
        tema.boton(pie, "Imprimir TODO en una hoja", self.imprimir_todo,
                   tema.AZUL).pack(side="right", padx=4)
        tema.boton(pie, "Compartir (solo lectura)",
                   self.configurar_carpeta_compartida).pack(side="right",
                                                            padx=4)

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Escape>", lambda e: self.cerrar())

    # ------------------------------------------------------- compartir
    def _publicar_snapshot(self) -> None:
        """Publica una foto de la base para las computadoras de solo
        lectura, si hay una carpeta compartida configurada. Silencioso si
        falla: nunca debe interrumpir el trabajo normal del panel.
        """
        carpeta = snapshot.leer_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN)
        if carpeta is None:
            return
        try:
            snapshot.publicar(self.con, carpeta)
        except OSError:
            pass

    def configurar_carpeta_compartida(self) -> None:
        actual = snapshot.leer_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN)
        ultima = snapshot.ultima_publicacion(actual) if actual else None

        estado = "Todavia no se ha configurado ninguna carpeta."
        if actual:
            estado = f"Carpeta actual:\n{actual}\n\n"
            estado += (f"Ultima publicacion: {ultima:%d/%m/%Y %H:%M}"
                       if ultima else "Aun no se ha publicado nada en ella.")

        elegir = messagebox.askyesno(
            "Compartir en modo solo lectura",
            "Esto publica una copia del inventario, cada pocos minutos y "
            "despues de cada cambio, en una carpeta que elijas (por ejemplo "
            "una carpeta dentro de tu OneDrive). Otras computadoras pueden "
            "leer esa copia con el programa 'visor.py', sin poder "
            "modificarla.\n\n" + estado + "\n\n"
            "¿Quieres elegir/cambiar la carpeta ahora?", parent=self)
        if not elegir:
            return

        carpeta = filedialog.askdirectory(
            title="Elige o crea una carpeta dentro de tu OneDrive/Drive/Dropbox",
            parent=self)
        if not carpeta:
            return
        snapshot.guardar_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN,
                                             Path(carpeta))
        self._publicar_snapshot()
        messagebox.showinfo(
            "Listo",
            f"Se configuro:\n{carpeta}\n\n"
            "Ya se publico una primera copia. En la otra computadora, abre "
            "'visor.py' y apunta a esta misma carpeta (debe verse igual "
            "desde las dos, por ejemplo porque ambas tienen sincronizada la "
            "misma carpeta de OneDrive).", parent=self)

    def imprimir_todo(self) -> None:
        """Articulos y gafetes juntos, en un solo archivo para una impresion."""
        con_titulos = messagebox.askyesno(
            "Separadores",
            "¿Agrego un titulo antes de cada bloque (herramienta / gafetes)?\n\n"
            "Si -> recomendado si vas a imprimir en papel normal y recortar.\n"
            "No -> recomendado si usas hojas de etiquetas precortadas, "
            "porque el titulo desalinea la cuadricula.", parent=self)
        _imprimir(etiquetas.hoja_completa(self.con, con_titulos),
                  "todo", self)

    def importar(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Selecciona el CSV", parent=self,
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if not ruta:
            return
        altas, errores = inventario.importar_csv(self.con, Path(ruta))
        self.articulos.refrescar()
        self._publicar_snapshot()
        mensaje = f"Se cargaron {altas} articulo(s)."
        if errores:
            mensaje += "\n\nLineas con problema:\n" + "\n".join(errores[:10])
        messagebox.showinfo("Importacion terminada", mensaje, parent=self)

    def cerrar(self) -> None:
        if self.al_cerrar:
            self.al_cerrar()
        self.destroy()


def main() -> None:
    raiz = tk.Tk()
    raiz.withdraw()
    panel = PanelGestion(raiz, al_cerrar=raiz.destroy)
    panel.protocol("WM_DELETE_WINDOW", panel.cerrar)
    raiz.mainloop()


if __name__ == "__main__":
    main()
