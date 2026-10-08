"""
Ventana de escaneo.

El lector COM-595 se comporta como un teclado: escribe el codigo y (si esta
configurado con sufijo Enter) presiona Enter. Por eso todo lo que hace esta
ventana es mantener el cursor dentro de la caja de texto y reaccionar al Enter.
Además del lector es una vista más interactiva de todo el inventario, además de
ayudar a la gestión del mismo, haciendolo más amigable, sin necesidad de comandos
en consola y de una manera comerciable.

Se abre con:  python app.py
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import db
import gestion
import inventario
import snapshot
import tema
from inventario import MODO_AUTO, MODO_ENTRADA, MODO_SALIDA, fmt
from registromanual import VentanaManual

# Si el mismo codigo llega dos veces en menos de este tiempo, se ignora.
# El gatillo del lector a veces dispara doble.
REBOTE_SEG = 1.2


class AppInventario(tk.Tk):
    def __init__(self, con=None, persona=None, persona_nombre="",
                 modo=MODO_AUTO) -> None:
        """Los argumentos solo se usan al reconstruir la ventana tras cambiar
        de tema, para seguir con la misma conexion, operador y modo."""
        super().__init__()
        # aqui se dispara el respaldo automatico (solo la primera vez)
        self.con = con or db.conectar()
        self.persona = None               # codigo del operador activo
        self.persona_nombre = ""
        self._modo_inicial = modo
        self.ultimo = ("", 0.0)           # (codigo, momento) para evitar dobles
        self._ventanas_simples = {}       # clave -> Toplevel, para no duplicar

        self.title("Inventario de bodega - escaneo")
        self.geometry("1100x680")
        self.minsize(1100, 600)
        self.configure(bg=tema.FONDO)

        self._construir()
        if persona:
            self.fijar_persona(persona, persona_nombre)
        self._refrescar_tabla()
        self._refrescar_resumen()
        self.after(200, lambda: self.entrada.focus_force())
        self.after(5000, self._publicar_periodico)

    # ---------------------------------------------------------------- UI
    def _construir(self) -> None:
        tema.aplicar_estilo(self)

        # --- barra superior: modo y operador
        barra = tk.Frame(self, bg=tema.FONDO)
        barra.pack(fill="x", padx=16, pady=(14, 6))

        tk.Label(barra, text="MODO", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))

        self.modo = tk.StringVar(value=self._modo_inicial)
        for valor, etiqueta in (
            (MODO_AUTO, "Automatico (F1)"),
            (MODO_SALIDA, "Solo salidas (F2)"),
            (MODO_ENTRADA, "Solo entradas (F3)"),
        ):
            tk.Radiobutton(
                barra, text=etiqueta, value=valor, variable=self.modo,
                bg=tema.FONDO, fg=tema.TEXTO, selectcolor=tema.PANEL, activebackground=tema.FONDO,
                activeforeground=tema.TEXTO, font=("Segoe UI", 10),
                highlightthickness=0, bd=0,
            ).pack(side="left", padx=4)

        tema.boton_tema(barra, self, self._estado_para_reabrir,
                        font=("Segoe UI", 9), pady=3
                        ).pack(side="right", padx=(12, 0))

        self.lbl_persona = tk.Label(barra, text="Operador: (ninguno)", bg=tema.FONDO,
                                    fg=tema.SUAVE, font=("Segoe UI", 10, "bold"))
        self.lbl_persona.pack(side="right")

        # --- caja de escaneo
        caja = tk.Frame(self, bg=tema.PANEL)
        caja.pack(fill="x", padx=16, pady=6)

        tk.Label(caja, text="Escanea aqui", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w",
                                             padx=14, pady=(10, 0))
        self.entrada = tk.Entry(caja, font=("Consolas", 26), bg=tema.CAMPO,
                                fg=tema.TEXTO, insertbackground=tema.TEXTO,
                                relief="flat", justify="center")
        self.entrada.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 12),
                          ipady=8)
        caja.columnconfigure(0, weight=1)

        lado = tk.Frame(caja, bg=tema.PANEL)
        lado.grid(row=0, column=1, rowspan=2, padx=(0, 14))
        tk.Label(lado, text="Cantidad (consumibles)", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.cantidad = tk.StringVar(value="1")
        tk.Spinbox(lado, from_=0.5, to=9999, increment=1, width=7,
                   textvariable=self.cantidad, font=("Segoe UI", 16),
                   justify="center", bg=tema.CAMPO, fg=tema.TEXTO, relief="flat",
                   buttonbackground=tema.PANEL).pack(pady=4)

        # --- banner de resultado
        self.banner = tk.Frame(self, bg=tema.PANEL, height=92)
        self.banner.pack(fill="x", padx=16, pady=6)
        self.banner.pack_propagate(False)
        self.titulo = tk.Label(self.banner, text="Listo para escanear",
                               bg=tema.PANEL, fg=tema.TEXTO, font=("Segoe UI", 20, "bold"),
                               anchor="w")
        self.titulo.pack(fill="x", padx=16, pady=(14, 0))
        self.detalle = tk.Label(self.banner, text="Escanea primero el gafete del "
                                "operador, luego las herramientas o materiales.",
                                bg=tema.PANEL, fg=tema.TEXTO, font=("Segoe UI", 11),
                                anchor="w")
        self.detalle.pack(fill="x", padx=16)

        # --- tabla de movimientos
        marco = tk.Frame(self, bg=tema.FONDO)
        marco.pack(fill="both", expand=True, padx=16, pady=6)
        tk.Label(marco, text="Ultimos movimientos", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        columnas = ("fecha", "tipo", "codigo", "articulo", "cant", "persona")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings",
                                  height=10)
        anchos = {"fecha": 140, "tipo": 80, "codigo": 100, "articulo": 300,
                  "cant": 70, "persona": 160}
        titulos = {"fecha": "Fecha", "tipo": "Tipo", "codigo": "Codigo",
                   "articulo": "Articulo", "cant": "Cant.", "persona": "Operador"}
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col],
                              anchor="center" if col in ("tipo", "cant") else "w")
        self.tabla.pack(fill="both", expand=True)
        self.tabla.tag_configure("SALIDA", foreground=tema.TXT_SALIDA)
        self.tabla.tag_configure("ENTRADA", foreground=tema.TXT_ENTRADA)
        self.tabla.tag_configure("AJUSTE", foreground=tema.SUAVE)

        # --- pie: resumen y botones
        pie = tk.Frame(self, bg=tema.FONDO)
        pie.pack(fill="x", padx=16, pady=(4, 14))
        self.resumen = tk.Label(pie, text="", bg=tema.FONDO, fg=tema.SUAVE,
                                font=("Segoe UI", 10))
        self.resumen.pack(side="left")

        tk.Button(pie, text="Catalogo / dar de alta", command=self.abrir_gestion,
                  bg=tema.AZUL, fg=tema.SOBRE_COLOR, relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=14, pady=4, activebackground=tema.PANEL,
                  activeforeground=tema.TEXTO, takefocus=False,
                  cursor="hand2").pack(side="right", padx=(12, 4))

        tk.Button(pie, text="Registro manual (F4)", command=self.abrir_manual,
                  bg=tema.CYAN, fg=tema.SOBRE_COLOR, relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=14, pady=4, activebackground=tema.PANEL,
                  activeforeground=tema.TEXTO, takefocus=False,
                  cursor="hand2").pack(side="right", padx=4)

        for texto, comando in (
            ("Exportar CSV", self.exportar),
            ("Bajo minimo", self.ver_bajo_stock),
            ("Pendientes", self.ver_pendientes),
        ):
            tk.Button(pie, text=texto, command=comando, bg=tema.PANEL, fg=tema.TEXTO,
                      relief="flat", font=("Segoe UI", 9), padx=12, pady=4,
                      activebackground=tema.AZUL, activeforeground=tema.TEXTO,
                      takefocus=False).pack(side="right", padx=4)

        # --- atajos
        self.entrada.bind("<Return>", self.al_escanear)
        self.bind("<F1>", lambda e: self.modo.set(MODO_AUTO))
        self.bind("<F2>", lambda e: self.modo.set(MODO_SALIDA))
        self.bind("<F3>", lambda e: self.modo.set(MODO_ENTRADA))
        self.bind("<F4>", lambda e: self.abrir_manual())
        self.bind("<Escape>", lambda e: self.limpiar_persona())
        self.bind("<Button-1>", lambda e: self.after(50, self.entrada.focus_set))

    # ------------------------------------------------------------ eventos
    def al_escanear(self, _evento=None) -> None:
        codigo = self.entrada.get().strip().upper().replace("'", "-")
        self.entrada.delete(0, "end")
        if not codigo:
            return

        ahora = time.monotonic()
        if codigo == self.ultimo[0] and ahora - self.ultimo[1] < REBOTE_SEG:
            return  # lectura duplicada del gatillo, se ignora en silencio
        self.ultimo = (codigo, ahora)

        try:
            cantidad = float(str(self.cantidad.get()).replace(",", "."))
        except ValueError:
            cantidad = 1.0

        # Herramienta con cantidad: antes de mover nada se pregunta si se
        # sacan o se regresan piezas, cuantas y de quien. Sin operador, o si
        # esta dado de baja, sigue el camino normal para que salga el error.
        art = inventario.buscar_articulo(self.con, codigo)
        if (art is not None and art["tipo"] == "AGRUPADO" and art["activo"]
                and self.persona
                and inventario.buscar_persona(self.con, codigo) is None):
            self.cantidad.set("1")
            self.abrir_agrupado(codigo, self.modo.get(), cantidad=cantidad)
            return

        resultado = inventario.registrar_escaneo(
            self.con, codigo, persona=self.persona,
            modo=self.modo.get(), cantidad=cantidad,
        )

        if resultado.nivel == "persona":
            self.fijar_persona(resultado.persona["codigo"],
                               resultado.persona["nombre"])
            self._mostrar(resultado)
        else:
            self.cantidad.set("1")
            self.tras_movimiento(resultado)
        self.entrada.focus_set()

    def tras_movimiento(self, resultado: inventario.Resultado) -> None:
        """Lo que sigue a un movimiento, venga del lector o del registro manual."""
        self._refrescar_tabla()
        self._refrescar_resumen()
        if resultado.ok:
            self._publicar_snapshot()
        self._mostrar(resultado)

    def fijar_persona(self, codigo: str, nombre: str) -> None:
        self.persona = codigo
        self.persona_nombre = nombre
        self.lbl_persona.config(text=f"Operador: {nombre}  (Esc para quitar)",
                                fg=tema.TEXTO)

    def limpiar_persona(self) -> None:
        self.persona = None
        self.persona_nombre = ""
        self.lbl_persona.config(text="Operador: (ninguno)", fg=tema.SUAVE)
        self.entrada.focus_set()

    def _mostrar(self, resultado: inventario.Resultado) -> None:
        color = tema.COLOR_NIVEL.get(resultado.nivel, tema.PANEL)
        # El banner es un Frame: solo acepta bg (con fg Tk lanza un error y
        # el mensaje no se actualizaba).
        self.banner.config(bg=color)
        for widget in (self.titulo, self.detalle):
            widget.config(bg=color, fg=tema.color_texto_sobre(color))
        self.titulo.config(text=resultado.titulo)
        self.detalle.config(text=resultado.detalle)
        if not resultado.ok:
            self.bell()

    def _refrescar_tabla(self) -> None:
        self.tabla.delete(*self.tabla.get_children())
        for mov in inventario.ultimos_movimientos(self.con, 40):
            self.tabla.insert(
                "", "end",
                values=(
                    mov["fecha"],
                    mov["tipo"],
                    mov["codigo"],
                    mov["articulo"] or "",
                    f"{fmt(mov['cantidad'])} {mov['unidad'] or ''}".strip(),
                    mov["persona_nombre"] or "",
                ),
                tags=(mov["tipo"],),
            )

    def abrir_agrupado(self, codigo: str, modo: str, cantidad: float = 1,
                       operador: str | None = None, padre=None, nota: str = "",
                       al_terminar=None) -> None:
        """Abre el dialogo Sacar/Regresar de una herramienta con cantidad.
        Tambien lo usa el registro manual (con su propio operador y padre)."""
        abierto = getattr(self, "_dialogo_agrupado", None)
        if abierto is not None and abierto.winfo_exists():
            abierto.lift()
            abierto.focus_force()
            return
        self._dialogo_agrupado = DialogoAgrupado(
            self, codigo, modo, cantidad=cantidad,
            operador=operador or self.persona, padre=padre, nota=nota,
            al_terminar=al_terminar)

    def _refrescar_resumen(self) -> None:
        # Un AGRUPADO con piezas prestadas cuenta como "fuera" aunque le
        # queden otras en la bodega.
        prestado = inventario._sql_prestado(self.con, "articulos")
        fila = self.con.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(estado = 'EN_BODEGA') AS dentro,"
            " SUM(estado = 'FUERA' OR (tipo = 'AGRUPADO' AND "
            f"{prestado} > 0)) AS fuera FROM articulos"
        ).fetchone()
        bajos = len(inventario.bajo_stock(self.con))
        self.resumen.config(
            text=f"{fila['total'] or 0} articulos   |   "
                 f"{fila['dentro'] or 0} en bodega   |   "
                 f"{fila['fuera'] or 0} fuera   |   "
                 f"{bajos} bajo el minimo"
        )

    # ------------------------------------------------------------ botones
    def obtener_carpeta_exportacion(self) -> str:
        """Lee la carpeta guardada de un archivo de configuración."""
        from pathlib import Path
        archivo_conf = db.DIR_DATOS / "export_path.txt"
        if archivo_conf.exists():
            return archivo_conf.read_text(encoding="utf-8").strip()
        return ""

    def guardar_carpeta_exportacion(self, ruta: str) -> None:
        """Guarda la carpeta elegida para no volver a preguntar."""
        archivo_conf = db.DIR_DATOS / "export_path.txt"
        archivo_conf.write_text(str(ruta), encoding="utf-8")

    def exportar(self) -> None:
        from pathlib import Path
        
        carpeta = self.obtener_carpeta_exportacion()
        
        # Si no hay carpeta guardada, o si la carpeta fue eliminada de la PC, preguntamos
        if not carpeta or not Path(carpeta).exists():
            carpeta = filedialog.askdirectory(title="Dónde guardar el reporte Excel")
            if not carpeta:
                return # El usuario canceló
            self.guardar_carpeta_exportacion(carpeta)
            
        try:
            # Intentamos exportar
            rutas = inventario.exportar_csv(self.con, carpeta)
            ruta = inventario.exportar_excel_nativo(self.con, carpeta)
            messagebox.showinfo("Exportado", f"Se generó el reporte en:\n{ruta}")
            messagebox.showinfo("Exportado",
                            "Se generaron:\n" + "\n".join(str(r) for r in rutas))
        except PermissionError:
            # Este error salta si el Excel está abierto
            messagebox.showerror(
                "Archivo bloqueado", 
                "El reporte Excel actualmente está abierto.\n\nPor favor, cierra Excel e intenta exportar de nuevo para poder actualizarlo."
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar el archivo:\n{e}")
            
        self.entrada.focus_set()

    def abrir_gestion(self) -> None:
        """Abre el panel de catalogo compartiendo la misma conexion."""
        if getattr(self, "_panel", None) and self._panel.winfo_exists():
            self._panel.lift()
            self._panel.focus_force()
            return
        self._panel = gestion.PanelGestion(self, con=self.con,
                                           al_cerrar=self._tras_gestion)

    def abrir_manual(self) -> None:
        """Abre la ventana de registro sin lector."""
        if getattr(self, "_manual", None) and self._manual.winfo_exists():
            self._manual.lift()
            self._manual.focus_force()
            return
        self._manual = VentanaManual(self)

    def _estado_para_reabrir(self) -> dict:
        """Lo que conserva la ventana al reconstruirse por cambio de tema."""
        return {"con": self.con, "persona": self.persona,
                "persona_nombre": self.persona_nombre, "modo": self.modo.get()}

    def _tras_gestion(self) -> None:
        self._refrescar_tabla()
        self._refrescar_resumen()
        self._publicar_snapshot()
        self.after(150, self.entrada.focus_set)

    # ------------------------------------------------------- compartir
    def _publicar_snapshot(self) -> None:
        """Publica una foto de la base en la carpeta compartida, si hay una
        configurada. Nunca interrumpe al usuario: si falla (sin red, carpeta
        de OneDrive no disponible en este momento, etc.) se ignora en
        silencio y se reintenta en la siguiente ocasion.
        """
        carpeta = snapshot.leer_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN)
        if carpeta is None:
            return
        try:
            snapshot.publicar(self.con, carpeta)
        except OSError:
            pass  # carpeta no disponible ahora mismo (ej. OneDrive offline)

    def _publicar_periodico(self) -> None:
        self._publicar_snapshot()
        self.after(snapshot.INTERVALO_PUBLICACION_SEG * 1000,
                  self._publicar_periodico)

    def ver_pendientes(self) -> None:
        filas = inventario.pendientes(self.con)
        if not filas:
            texto = "No hay nada fuera de la bodega."
        else:
            # Un AGRUPADO sale una vez por persona: "2 con Emerson ..."
            lineas = [
                f"{f['codigo']:<12} {f['nombre'][:24]:<24} {_quien(f)[:22]:<22} "
                f"{f['dias'] or 0:>3} dia(s)  "
                f"{inventario.fmt_dinero(f['valor']):>12}"
                for f in filas[:40]
            ]
            total = sum(f["valor"] or 0 for f in filas)
            aviso_recorte = (f"  (mostrando 40 de {len(filas)})"
                             if len(filas) > 40 else "")
            lineas += ["", f"Valor total prestado: "
                          f"{inventario.fmt_dinero(total)}{aviso_recorte}"]
            texto = "\n".join(lineas)
        self._ventana_texto("pendientes", "Articulos fuera de la bodega", texto)

    def ver_bajo_stock(self) -> None:
        filas = inventario.bajo_stock(self.con)
        if not filas:
            texto = "Ningun consumible esta por debajo de su minimo."
        else:
            texto = "\n".join(
                f"{f['codigo']}  {f['nombre'][:32]:<32} "
                + (f"disponibles {fmt(f['existencia'])} {f['unidad']} "
                   f"(minimo {fmt(f['minimo'])}, {fmt(f['prestado'])} prestadas)"
                   if f["tipo"] == "AGRUPADO" else
                   f"quedan {fmt(f['existencia'])} {f['unidad']} "
                   f"(minimo {fmt(f['minimo'])})")
                for f in filas
            )
        self._ventana_texto("bajo_stock", "Material por resurtir", texto)

    def _ventana_texto(self, clave: str, titulo: str, contenido: str) -> None:
        """Muestra una ventana simple de solo texto, una sola vez por clave.

        Si ya hay una abierta con esa clave, solo actualiza su contenido y la
        trae al frente, en vez de abrir otra encima (lo que antes permitia
        acumular pestanas identicas sin limite).
        """
        existente = self._ventanas_simples.get(clave)
        if existente is not None and existente.winfo_exists():
            existente.title(titulo)
            existente.caja.config(state="normal")
            existente.caja.delete("1.0", "end")
            existente.caja.insert("1.0", contenido)
            existente.caja.config(state="disabled")
            existente.lift()
            existente.focus_force()
            return

        top = tk.Toplevel(self)
        top.title(titulo)
        top.configure(bg=tema.FONDO)
        top.geometry("760x420")
        marco = tk.Frame(top, bg=tema.FONDO)
        marco.pack(fill="both", expand=True, padx=12, pady=12)
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        caja = tk.Text(marco, bg=tema.PANEL, fg=tema.TEXTO, font=("Consolas", 10),
                       relief="flat", wrap="none")
        caja.grid(row=0, column=0, sticky="nsew")
        # Barras por si alguna linea o la lista no caben en la ventana.
        barra_v = ttk.Scrollbar(marco, orient="vertical", command=caja.yview)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h = ttk.Scrollbar(marco, orient="horizontal", command=caja.xview)
        barra_h.grid(row=1, column=0, sticky="ew")
        caja.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        caja.insert("1.0", contenido)
        caja.config(state="disabled")
        top.transient(self)
        top.bind("<Escape>", lambda e: top.destroy())
        top.caja = caja
        self._ventanas_simples[clave] = top


def _quien(fila) -> str:
    """Columna 'quien' de Pendientes: con cantidad para los AGRUPADO."""
    if fila["tipo"] == "AGRUPADO":
        return f"{fmt(fila['cantidad'])} con {fila['quien']}"
    return fila["quien"]


class DialogoAgrupado(tk.Toplevel):
    """Dialogo pequeno para una herramienta con cantidad (AGRUPADO).

    Muestra cuantas piezas hay en la bodega y quien tiene las demas, y deja
    elegir Sacar o Regresar y cuantas. Al regresar se elige de quien son las
    piezas (por omision, del operador si tiene). La regla de negocio sigue
    en inventario.registrar_escaneo; aqui solo se pregunta.
    """

    def __init__(self, app: AppInventario, codigo: str, modo: str,
                 cantidad: float = 1, operador: str | None = None, padre=None,
                 nota: str = "", al_terminar=None) -> None:
        super().__init__(padre or app)
        self.app = app
        self.codigo = codigo
        self.operador = operador
        self.nota = nota
        self.al_terminar = al_terminar
        self.padre = padre or app
        # El gatillo a veces dispara doble: un Enter que llegue antes de
        # REBOTE_SEG no debe aceptar el dialogo con los valores por omision.
        self.abierto_en = time.monotonic()
        # Momentos de las ultimas teclas: el lector escribe un codigo entero
        # y un Enter en una rafaga; ese Enter no debe aceptar el dialogo.
        self._teclas: list[float] = []

        art = inventario.buscar_articulo(app.con, codigo)
        prestamos = inventario.prestamos_de(app.con, codigo)
        self._de = {f"{p['nombre']}  (tiene {fmt(p['cantidad'])})": p["persona"]
                    for p in prestamos}
        unidad = art["unidad"] or "pza"
        disponibles = float(art["existencia"])

        self.title("Herramienta con cantidad")
        self.configure(bg=tema.PANEL)
        self.resizable(False, False)
        self.transient(self.padre)

        tk.Label(self, text=art["nombre"], bg=tema.PANEL, fg=tema.TEXTO,
                 font=("Segoe UI", 14, "bold"), anchor="w", wraplength=420,
                 justify="left").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(self, text=codigo, bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Consolas", 10), anchor="w").pack(fill="x", padx=18)
        tk.Label(self, text=f"Disponibles en bodega: {fmt(disponibles)} {unidad}",
                 bg=tema.PANEL, fg=tema.TEXTO, font=("Segoe UI", 10),
                 anchor="w").pack(fill="x", padx=18, pady=(10, 0))
        quienes = ", ".join(f"{p['nombre']} ({fmt(p['cantidad'])})"
                            for p in prestamos)
        tk.Label(self, text=f"Prestadas: {quienes}" if quienes
                 else "Nadie tiene piezas prestadas.",
                 bg=tema.PANEL, fg=tema.TXT_SALIDA if quienes else tema.SUAVE,
                 font=("Segoe UI", 10), anchor="w", wraplength=420,
                 justify="left").pack(fill="x", padx=18, pady=(2, 10))

        # Accion sugerida: la del modo fijo, o en automatico "Regresar" si el
        # operador tiene piezas (o si ya no queda ninguna en la bodega).
        if modo == MODO_SALIDA:
            sugerida = MODO_SALIDA
        elif modo == MODO_ENTRADA:
            sugerida = MODO_ENTRADA
        else:
            tiene = any(p["persona"] == operador for p in prestamos)
            sugerida = (MODO_ENTRADA if prestamos and (tiene or disponibles <= 0)
                        else MODO_SALIDA)
        self.accion = tk.StringVar(value=sugerida)

        fila = tk.Frame(self, bg=tema.PANEL)
        fila.pack(fill="x", padx=18)
        for valor, texto, permitido in (
            (MODO_SALIDA, "Sacar", disponibles > 0),
            (MODO_ENTRADA, "Regresar", bool(prestamos)),
        ):
            tk.Radiobutton(fila, text=texto, value=valor, variable=self.accion,
                           command=self._ajustar, bg=tema.PANEL, fg=tema.TEXTO,
                           selectcolor=tema.CAMPO, activebackground=tema.PANEL,
                           activeforeground=tema.TEXTO, font=("Segoe UI", 11),
                           highlightthickness=0, bd=0,
                           state="normal" if permitido else "disabled",
                           ).pack(side="left", padx=(0, 16))

        tk.Label(fila, text="Cantidad", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(12, 6))
        self.cantidad = tk.StringVar(value=fmt(cantidad if cantidad > 0 else 1))
        tk.Spinbox(fila, from_=1, to=9999, increment=1, width=6,
                   textvariable=self.cantidad, font=("Segoe UI", 13),
                   justify="center", bg=tema.CAMPO, fg=tema.TEXTO, relief="flat",
                   buttonbackground=tema.PANEL).pack(side="left")

        self.fila_de = tk.Frame(self, bg=tema.PANEL)
        tk.Label(self.fila_de, text="De quien son", bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.de = tk.StringVar()
        ttk.Combobox(self.fila_de, textvariable=self.de, state="readonly",
                     values=list(self._de), width=34,
                     font=("Segoe UI", 10)).pack(side="left")
        for texto, persona in self._de.items():
            if persona == operador:
                self.de.set(texto)
                break
        else:
            if self._de:
                self.de.set(next(iter(self._de)))

        self.aviso = tk.Label(self, text="", bg=tema.PANEL, fg=tema.TXT_ERROR,
                              font=("Segoe UI", 9), anchor="w", wraplength=420,
                              justify="left")
        self.aviso.pack(fill="x", padx=18, pady=(8, 0))

        botones = tk.Frame(self, bg=tema.PANEL)
        botones.pack(fill="x", padx=18, pady=(8, 16))
        tema.boton(botones, "Aceptar (Enter)", self.aceptar, tema.VERDE
                   ).pack(side="left")
        tema.boton(botones, "Cancelar (Esc)", lambda: self.cerrar(None)
                   ).pack(side="left", padx=6)

        self._ajustar()
        self.bind("<Return>", self._al_enter)
        self.bind("<KP_Enter>", self._al_enter)
        self.bind("<Key>", self._anotar_tecla)
        self.bind("<Escape>", lambda e: self.cerrar(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self.cerrar(None))
        # El foco va al dialogo, no a la cantidad: si el lector dispara de
        # nuevo, sus teclas no se escriben en ningun campo.
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # la ventana aun no se ve; sin grab funciona igual
        self.focus_force()

    def _ajustar(self) -> None:
        """La lista 'De quien son' solo aplica al regresar."""
        if self.accion.get() == MODO_ENTRADA:
            self.fila_de.pack(fill="x", padx=18, pady=(10, 0), before=self.aviso)
        else:
            self.fila_de.pack_forget()

    def _anotar_tecla(self, _evento=None) -> None:
        ahora = time.monotonic()
        self._teclas = [t for t in self._teclas if ahora - t < 0.5] + [ahora]

    def _al_enter(self, _evento=None) -> None:
        if time.monotonic() - self.abierto_en < REBOTE_SEG:
            return  # Enter del mismo disparo del lector, se ignora
        ahora = time.monotonic()
        if sum(1 for t in self._teclas if ahora - t < 0.5) >= 4:
            return  # ráfaga de teclas + Enter = otro código leído por el lector
        self.aceptar()

    def aceptar(self) -> None:
        try:
            cantidad = float(str(self.cantidad.get()).replace(",", "."))
        except ValueError:
            self.aviso.config(text="Escribe una cantidad numerica.")
            self.bell()
            return
        accion = self.accion.get()
        de = self._de.get(self.de.get()) if accion == MODO_ENTRADA else None
        resultado = inventario.registrar_escaneo(
            self.app.con, self.codigo, persona=self.operador, modo=accion,
            cantidad=cantidad, nota=self.nota, de_persona=de)
        if not resultado.ok:
            # No cambio nada: se deja el dialogo abierto para corregir.
            self.aviso.config(text=f"{resultado.titulo}. {resultado.detalle}")
            self.bell()
            return
        self.cerrar(resultado)

    def cerrar(self, resultado: inventario.Resultado | None) -> None:
        self.grab_release()
        self.destroy()
        # Una lectura repetida justo al cerrar tampoco debe reabrirlo.
        self.app.ultimo = (self.codigo, time.monotonic())
        if resultado is not None:
            self.app.tras_movimiento(resultado)
        elif self.padre is self.app:
            self.app._mostrar(inventario.Resultado(
                True, "aviso", "Sin cambios", f"Se cancelo el movimiento de "
                                              f"{self.codigo}."))
        if self.al_terminar:
            self.al_terminar(resultado)
        destino = self.app.entrada if self.padre is self.app else self.padre
        self.padre.after(50, destino.focus_set)


if __name__ == "__main__":
    tema.ejecutar(AppInventario)
