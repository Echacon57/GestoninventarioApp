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
from tema import AZUL, COLOR_NIVEL, CYAN, FONDO, PANEL, SUAVE, TEXTO

# Si el mismo codigo llega dos veces en menos de este tiempo, se ignora.
# El gatillo del lector a veces dispara doble.
REBOTE_SEG = 1.2


class AppInventario(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.con = db.conectar()          # aqui se dispara el respaldo automatico
        self.persona = None               # codigo del operador activo
        self.persona_nombre = ""
        self.ultimo = ("", 0.0)           # (codigo, momento) para evitar dobles
        self._ventanas_simples = {}       # clave -> Toplevel, para no duplicar

        self.title("Inventario de bodega - escaneo")
        self.geometry("1100x680")
        self.minsize(1100, 600)
        self.configure(bg=FONDO)

        self._construir()
        self._refrescar_tabla()
        self._refrescar_resumen()
        self.after(200, lambda: self.entrada.focus_force())
        self.after(5000, self._publicar_periodico)

    # ---------------------------------------------------------------- UI
    def _construir(self) -> None:
        tema.aplicar_estilo(self)

        # --- barra superior: modo y operador
        barra = tk.Frame(self, bg=FONDO)
        barra.pack(fill="x", padx=16, pady=(14, 6))

        tk.Label(barra, text="MODO", bg=FONDO, fg=SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))

        self.modo = tk.StringVar(value=MODO_AUTO)
        for valor, etiqueta in (
            (MODO_AUTO, "Automatico (F1)"),
            (MODO_SALIDA, "Solo salidas (F2)"),
            (MODO_ENTRADA, "Solo entradas (F3)"),
        ):
            tk.Radiobutton(
                barra, text=etiqueta, value=valor, variable=self.modo,
                bg=FONDO, fg=TEXTO, selectcolor=PANEL, activebackground=FONDO,
                activeforeground=TEXTO, font=("Segoe UI", 10),
                highlightthickness=0, bd=0,
            ).pack(side="left", padx=4)

        self.lbl_persona = tk.Label(barra, text="Operador: (ninguno)", bg=FONDO,
                                    fg=SUAVE, font=("Segoe UI", 10, "bold"))
        self.lbl_persona.pack(side="right")

        # --- caja de escaneo
        caja = tk.Frame(self, bg=PANEL)
        caja.pack(fill="x", padx=16, pady=6)

        tk.Label(caja, text="Escanea aqui", bg=PANEL, fg=SUAVE,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w",
                                             padx=14, pady=(10, 0))
        self.entrada = tk.Entry(caja, font=("Consolas", 26), bg="#131722",
                                fg=TEXTO, insertbackground=TEXTO,
                                relief="flat", justify="center")
        self.entrada.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 12),
                          ipady=8)
        caja.columnconfigure(0, weight=1)

        lado = tk.Frame(caja, bg=PANEL)
        lado.grid(row=0, column=1, rowspan=2, padx=(0, 14))
        tk.Label(lado, text="Cantidad (consumibles)", bg=PANEL, fg=SUAVE,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.cantidad = tk.StringVar(value="1")
        tk.Spinbox(lado, from_=0.5, to=9999, increment=1, width=7,
                   textvariable=self.cantidad, font=("Segoe UI", 16),
                   justify="center", bg="#131722", fg=TEXTO, relief="flat",
                   buttonbackground=PANEL).pack(pady=4)

        # --- banner de resultado
        self.banner = tk.Frame(self, bg=PANEL, height=92)
        self.banner.pack(fill="x", padx=16, pady=6)
        self.banner.pack_propagate(False)
        self.titulo = tk.Label(self.banner, text="Listo para escanear",
                               bg=PANEL, fg=TEXTO, font=("Segoe UI", 20, "bold"),
                               anchor="w")
        self.titulo.pack(fill="x", padx=16, pady=(14, 0))
        self.detalle = tk.Label(self.banner, text="Escanea primero el gafete del "
                                "operador, luego las herramientas o materiales.",
                                bg=PANEL, fg=TEXTO, font=("Segoe UI", 11),
                                anchor="w")
        self.detalle.pack(fill="x", padx=16)

        # --- tabla de movimientos
        marco = tk.Frame(self, bg=FONDO)
        marco.pack(fill="both", expand=True, padx=16, pady=6)
        tk.Label(marco, text="Ultimos movimientos", bg=FONDO, fg=SUAVE,
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
        self.tabla.tag_configure("SALIDA", foreground="#f0a868")
        self.tabla.tag_configure("ENTRADA", foreground="#7fd6a0")
        self.tabla.tag_configure("AJUSTE", foreground="#9aa3b5")

        # --- pie: resumen y botones
        pie = tk.Frame(self, bg=FONDO)
        pie.pack(fill="x", padx=16, pady=(4, 14))
        self.resumen = tk.Label(pie, text="", bg=FONDO, fg=SUAVE,
                                font=("Segoe UI", 10))
        self.resumen.pack(side="left")

        tk.Button(pie, text="Catalogo / dar de alta", command=self.abrir_gestion,
                  bg=AZUL, fg=TEXTO, relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=14, pady=4, activebackground=PANEL,
                  activeforeground=TEXTO, takefocus=False,
                  cursor="hand2").pack(side="right", padx=(12, 4))

        tk.Button(pie, text="Registro manual (F4)", command=self.abrir_manual,
                  bg=CYAN, fg=TEXTO, relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=14, pady=4, activebackground=PANEL,
                  activeforeground=TEXTO, takefocus=False,
                  cursor="hand2").pack(side="right", padx=4)

        for texto, comando in (
            ("Exportar CSV", self.exportar),
            ("Bajo minimo", self.ver_bajo_stock),
            ("Pendientes", self.ver_pendientes),
        ):
            tk.Button(pie, text=texto, command=comando, bg=PANEL, fg=TEXTO,
                      relief="flat", font=("Segoe UI", 9), padx=12, pady=4,
                      activebackground=AZUL, activeforeground=TEXTO,
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
                                fg=TEXTO)

    def limpiar_persona(self) -> None:
        self.persona = None
        self.persona_nombre = ""
        self.lbl_persona.config(text="Operador: (ninguno)", fg=SUAVE)
        self.entrada.focus_set()

    def _mostrar(self, resultado: inventario.Resultado) -> None:
        color = COLOR_NIVEL.get(resultado.nivel, PANEL)
        for widget in (self.banner, self.titulo, self.detalle):
            widget.config(bg=color)
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

    def _refrescar_resumen(self) -> None:
        fila = self.con.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(estado = 'EN_BODEGA') AS dentro,"
            " SUM(estado = 'FUERA') AS fuera FROM articulos"
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
            lineas = [
                f"{f['codigo']:<12} {f['nombre'][:30]:<30} {f['quien'][:18]:<18} "
                f"{f['dias'] or 0:>3} dia(s)  "
                f"{inventario.fmt_dinero(inventario.valor_articulo(f)):>12}"
                for f in filas[:40]
            ]
            total = sum(inventario.valor_articulo(f) for f in filas)
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
                f"quedan {fmt(f['existencia'])} {f['unidad']} "
                f"(minimo {fmt(f['minimo'])})"
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
        top.configure(bg=FONDO)
        top.geometry("760x420")
        caja = tk.Text(top, bg=PANEL, fg=TEXTO, font=("Consolas", 10),
                       relief="flat", wrap="none")
        caja.pack(fill="both", expand=True, padx=12, pady=12)
        caja.insert("1.0", contenido)
        caja.config(state="disabled")
        top.transient(self)
        top.bind("<Escape>", lambda e: top.destroy())
        top.caja = caja
        self._ventanas_simples[clave] = top


if __name__ == "__main__":
    AppInventario().mainloop()
