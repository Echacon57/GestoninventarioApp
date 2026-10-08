"""
Visor de solo lectura del inventario.

Para computadoras que NO tienen el lector conectado pero necesitan consultar
el inventario: existencias, quien tiene que, devoluciones, valor total, etc.

No puede escanear ni modificar nada — ni siquiera por accidente: se conecta
a una copia local de solo lectura (PRAGMA query_only), nunca al archivo
original. Lee de una carpeta compartida (OneDrive, Drive, Dropbox, o una
carpeta de red) donde la computadora que SI escanea publica una foto del
inventario cada pocos minutos. Ver snapshot.py para entender como funciona eso.

Se abre con:  python visor.py
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import inventario
import snapshot
import tema
from inventario import fmt, fmt_dinero

# Cada cuanto se refresca solo, ademas del boton manual. En segundos.
INTERVALO_REFRESCO_SEG = 60


def _hace(momento: datetime) -> str:
    """'hace 3 minutos', 'hace 2 horas'... para no mostrar timestamps secos."""
    delta = datetime.now() - momento
    segundos = delta.total_seconds()
    if segundos < 60:
        return "hace un momento"
    if segundos < 3600:
        return f"hace {int(segundos // 60)} min"
    if segundos < 86400:
        return f"hace {int(segundos // 3600)} h"
    return f"hace {int(segundos // 86400)} dia(s)"


class VisorInventario(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.con = None
        self.momento_datos: datetime | None = None
        self.carpeta = snapshot.leer_carpeta_configurada(
            snapshot.RUTA_CONFIG_VISOR)

        self.title("Inventario de bodega - solo lectura")
        self.geometry("1040x680")
        self.minsize(880, 560)
        self.configure(bg=tema.FONDO)
        tema.aplicar_estilo(self)

        self._construir()

        if self.carpeta is None:
            self.after(300, self.cambiar_carpeta)
        else:
            self.after(300, self.actualizar)
        self.after(INTERVALO_REFRESCO_SEG * 1000, self._refresco_automatico)

    # ---------------------------------------------------------------- Interfaz de Usuario
    def _construir(self) -> None:
        cabecera = tk.Frame(self, bg=tema.PANEL)
        cabecera.pack(fill="x")
        interior = tk.Frame(cabecera, bg=tema.PANEL)
        interior.pack(fill="x", padx=16, pady=10)

        tk.Label(interior, text="Inventario de bodega — solo lectura",
                 bg=tema.PANEL, fg=tema.TEXTO, font=("Segoe UI", 13, "bold")
                 ).pack(side="left")

        self.lbl_estado = tk.Label(interior, text="", bg=tema.PANEL, fg=tema.SUAVE,
                                   font=("Segoe UI", 10))
        self.lbl_estado.pack(side="right", padx=(0, 12))
        tema.boton(interior, "Actualizar ahora", self.actualizar
                  ).pack(side="right", padx=4)
        tema.boton(interior, "Cambiar carpeta", self.cambiar_carpeta
                  ).pack(side="right", padx=4)
        tema.boton(interior, "Exportar", self.exportar).pack(side="right",
                                                              padx=4)
        tema.boton_tema(interior, self, self._estado_para_reabrir
                        ).pack(side="right", padx=4)

        cuaderno = ttk.Notebook(self)
        cuaderno.pack(fill="both", expand=True, padx=12, pady=12)

        self.pestana_inventario = self._construir_inventario(cuaderno)
        self.pestana_movimientos = self._construir_movimientos(cuaderno)
        self.pestana_reportes = self._construir_reportes(cuaderno)
        cuaderno.add(self.pestana_inventario, text="  Inventario  ")
        cuaderno.add(self.pestana_movimientos, text="  Movimientos  ")
        cuaderno.add(self.pestana_reportes, text="  Reportes y personal  ")

    def _construir_inventario(self, cuaderno) -> tk.Frame:
        marco = tk.Frame(cuaderno, bg=tema.FONDO)
        marco.columnconfigure(0, weight=3)
        marco.columnconfigure(1, weight=2, minsize=320)
        marco.rowconfigure(2, weight=1)

        barra = tk.Frame(marco, bg=tema.FONDO)
        barra.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(14, 6))
        tema.titulo(barra, "Buscar").pack(side="left", padx=(0, 8))
        self.busqueda = tk.StringVar()
        self.busqueda.trace_add("write", lambda *_: self._refrescar_lista())
        tema.entrada(barra, textvariable=self.busqueda).pack(
            side="left", fill="x", expand=True, ipady=4)

        fila_filtros = tk.Frame(marco, bg=tema.FONDO)
        fila_filtros.grid(row=1, column=0, sticky="ew", padx=(14, 8),
                          pady=(0, 6))

        tk.Label(fila_filtros, text="Estado:", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self.filtro_estado = ttk.Combobox(
            fila_filtros, state="readonly", width=16, font=("Segoe UI", 9),
            values=["Todos", "En bodega", "Fuera de la bodega"])
        self.filtro_estado.current(0)
        self.filtro_estado.pack(side="left")
        self.filtro_estado.bind("<<ComboboxSelected>>",
                                lambda e: self._refrescar_lista())

        tk.Label(fila_filtros, text="Ubicacion:", bg=tema.FONDO, fg=tema.SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
        self.filtro_ubicacion = ttk.Combobox(
            fila_filtros, state="readonly", width=16, font=("Segoe UI", 9),
            values=["Todas"])
        self.filtro_ubicacion.current(0)
        self.filtro_ubicacion.pack(side="left")
        self.filtro_ubicacion.bind("<<ComboboxSelected>>",
                                   lambda e: self._refrescar_lista())

        columnas = ("codigo", "nombre", "tipo", "exist", "ubicacion", "estado")
        titulos = {"codigo": "Codigo", "nombre": "Nombre", "tipo": "Tipo",
                   "exist": "Exist.", "ubicacion": "Ubicacion",
                   "estado": "Estado"}
        anchos = {"codigo": 80, "nombre": 220, "tipo": 90, "exist": 112,
                  "ubicacion": 110, "estado": 84}
        izq = tk.Frame(marco, bg=tema.FONDO)
        izq.grid(row=2, column=0, sticky="nsew", padx=(14, 8), pady=(0, 14))
        izq.rowconfigure(0, weight=1)
        izq.columnconfigure(0, weight=1)

        self.tabla = ttk.Treeview(izq, columns=columnas, show="headings")
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col], minwidth=60,
                              stretch=(col == "nombre"),
                              anchor="center" if col in ("exist", "tipo",
                                                         "estado") else "w")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(izq, orient="vertical",
                                command=self.tabla.yview)
        barra_v.grid(row=0, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=barra_v.set)
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)
        self.tabla.tag_configure("baja", foreground=tema.TXT_BAJA)
        self.tabla.tag_configure("fuera", foreground=tema.TXT_SALIDA)

        self.conteo = tk.Label(izq, text="", bg=tema.FONDO, fg=tema.SUAVE,
                               font=("Segoe UI", 9))
        self.conteo.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.detalle = tk.Frame(marco, bg=tema.PANEL)
        self.detalle.grid(row=2, column=1, sticky="nsew", padx=(8, 14),
                          pady=(0, 14))
        self._mostrar_detalle(None)

        return marco

    def _construir_movimientos(self, cuaderno) -> tk.Frame:
        marco = tk.Frame(cuaderno, bg=tema.FONDO)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(1, weight=1)

        barra = tk.Frame(marco, bg=tema.FONDO)
        barra.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        tema.titulo(barra, "Buscar (codigo, articulo u operador)").pack(
            side="left", padx=(0, 8))
        self.busqueda_movs = tk.StringVar()
        self.busqueda_movs.trace_add(
            "write", lambda *_: self._refrescar_movimientos())
        tema.entrada(barra, textvariable=self.busqueda_movs).pack(
            side="left", fill="x", expand=True, ipady=4)

        columnas = ("fecha", "tipo", "codigo", "articulo", "cant", "persona")
        titulos = {"fecha": "Fecha", "tipo": "Tipo", "codigo": "Codigo",
                   "articulo": "Articulo", "cant": "Cant.",
                   "persona": "Operador"}
        anchos = {"fecha": 140, "tipo": 80, "codigo": 90, "articulo": 260,
                  "cant": 90, "persona": 150}

        cont = tk.Frame(marco, bg=tema.FONDO)
        cont.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)

        self.tabla_movs = ttk.Treeview(cont, columns=columnas, show="headings")
        for col in columnas:
            self.tabla_movs.heading(col, text=titulos[col])
            self.tabla_movs.column(col, width=anchos[col], minwidth=60,
                                   stretch=(col == "articulo"),
                                   anchor="center" if col in ("tipo", "cant")
                                   else "w")
        self.tabla_movs.grid(row=0, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(cont, orient="vertical",
                                command=self.tabla_movs.yview)
        barra_v.grid(row=0, column=1, sticky="ns")
        self.tabla_movs.configure(yscrollcommand=barra_v.set)
        self.tabla_movs.tag_configure("SALIDA", foreground=tema.TXT_SALIDA)
        self.tabla_movs.tag_configure("ENTRADA", foreground=tema.TXT_ENTRADA)
        self.tabla_movs.tag_configure("AJUSTE", foreground=tema.SUAVE)

        self.conteo_movs = tk.Label(marco, text="", bg=tema.FONDO, fg=tema.SUAVE,
                                    font=("Segoe UI", 9))
        self.conteo_movs.grid(row=2, column=0, sticky="w", padx=14,
                              pady=(0, 14))

        return marco

    def _construir_reportes(self, cuaderno) -> tk.Frame:
        marco = tk.Frame(cuaderno, bg=tema.FONDO)

        resumen = tk.Frame(marco, bg=tema.PANEL)
        resumen.pack(fill="x", padx=14, pady=14)
        self.lbl_valor = tk.Label(resumen, text="", bg=tema.PANEL, fg=tema.TEXTO,
                                  font=("Segoe UI", 13, "bold"), anchor="w",
                                  justify="left")
        self.lbl_valor.pack(fill="x", padx=16, pady=12)

        columnas_2 = tk.Frame(marco, bg=tema.FONDO)
        columnas_2.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        # "Fuera de la bodega" lleva mas columnas (persona, dias, valor):
        # se le da mas ancho para que el valor se vea sin desplazar.
        columnas_2.columnconfigure(0, weight=3, uniform="reportes")
        columnas_2.columnconfigure(1, weight=2, uniform="reportes")
        columnas_2.rowconfigure(0, weight=1)

        self.texto_pendientes = self._caja_texto(columnas_2,
                                                  "Fuera de la bodega", 0)
        self.texto_bajo_stock = self._caja_texto(columnas_2,
                                                  "Por debajo del minimo", 1)

        return marco

    def _caja_texto(self, padre, titulo: str, columna: int) -> tk.Text:
        marco = tk.Frame(padre, bg=tema.PANEL)
        marco.grid(row=0, column=columna, sticky="nsew",
                  padx=(0, 8) if columna == 0 else (8, 0))
        tema.titulo(marco, titulo, bg=tema.PANEL).pack(anchor="w", padx=12,
                                                   pady=(10, 4))
        cont = tk.Frame(marco, bg=tema.PANEL)
        cont.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        caja = tk.Text(cont, bg=tema.CAMPO, fg=tema.TEXTO, font=("Consolas", 9),
                       relief="flat", wrap="none", height=10)
        caja.grid(row=0, column=0, sticky="nsew")
        # Barras por si las lineas no caben en media ventana.
        barra_v = ttk.Scrollbar(cont, orient="vertical", command=caja.yview)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h = ttk.Scrollbar(cont, orient="horizontal", command=caja.xview)
        barra_h.grid(row=1, column=0, sticky="ew")
        caja.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        caja.config(state="disabled")
        return caja

    def _mostrar_detalle(self, art) -> None:
        for widget in self.detalle.winfo_children():
            widget.destroy()

        if art is None:
            tk.Label(self.detalle, text="Selecciona un articulo de la lista",
                     bg=tema.PANEL, fg=tema.SUAVE, font=("Segoe UI", 10),
                     wraplength=260).pack(padx=16, pady=16)
            return

        tk.Label(self.detalle, text=art["nombre"], bg=tema.PANEL, fg=tema.TEXTO,
                 font=("Segoe UI", 14, "bold"), anchor="w", wraplength=300,
                 justify="left").pack(fill="x", padx=16, pady=(16, 2))
        tk.Label(self.detalle, text=art["codigo"], bg=tema.PANEL, fg=tema.SUAVE,
                 font=("Consolas", 11), anchor="w").pack(fill="x", padx=16,
                                                         pady=(0, 10))

        if not art["activo"]:
            tk.Label(self.detalle, text="DADO DE BAJA", bg=tema.PANEL, fg=tema.TXT_ERROR,
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(0, 8))

        if art["tipo"] == "AGRUPADO":
            prestamos = inventario.prestamos_de(self.con, art["codigo"])
            existencia = [
                ("Disponibles", f"{fmt(art['existencia'])} {art['unidad']}"),
                ("Prestadas", ", ".join(f"{p['nombre']} ({fmt(p['cantidad'])})"
                                        for p in prestamos) or "ninguna"),
                ("Total", f"{fmt(art['existencia'] + art['prestado'])} "
                          f"{art['unidad']}"),
            ]
        else:
            existencia = [("Existencia", f"{fmt(art['existencia'])} {art['unidad']}")]
        campos = [
            ("Tipo", inventario.NOMBRE_TIPO.get(art["tipo"], art["tipo"])),
            ("Estado", "en bodega" if art["estado"] == "EN_BODEGA" else "fuera"),
            *existencia,
            ("Categoria", art["categoria"] or "—"),
            ("Ubicacion", art["ubicacion"] or "—"),
            ("Marca", art["marca"] or "—"),
            ("Modelo", art["modelo"] or "—"),
            ("N. de serie", art["numero_serie"] or "—"),
            ("Valor unitario", fmt_dinero(art["valor_unitario"])),
        ]
        for etiqueta, valor in campos:
            fila = tk.Frame(self.detalle, bg=tema.PANEL)
            fila.pack(fill="x", padx=16, pady=2)
            tk.Label(fila, text=etiqueta, bg=tema.PANEL, fg=tema.SUAVE,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(
                side="left")
            tk.Label(fila, text=valor, bg=tema.PANEL, fg=tema.TEXTO,
                     font=("Segoe UI", 9), anchor="w", wraplength=170,
                     justify="left").pack(side="left", fill="x", expand=True)

        if art["notas"]:
            tk.Label(self.detalle, text="Notas", bg=tema.PANEL, fg=tema.SUAVE,
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(10, 0))
            tk.Label(self.detalle, text=art["notas"], bg=tema.PANEL, fg=tema.TEXTO,
                     font=("Segoe UI", 9), anchor="w", wraplength=280,
                     justify="left").pack(fill="x", padx=16, pady=(0, 12))

    # ------------------------------------------------------------ datos
    def _ruta_config_exportacion(self) -> Path:
        return snapshot.DIR_VISOR / "export_path.txt"

    def exportar(self) -> None:
        if self.con is None:
            messagebox.showinfo(
                "Sin datos todavia",
                "Primero actualiza para tener algo que exportar.",
                parent=self)
            return

        archivo_conf = self._ruta_config_exportacion()
        carpeta = (archivo_conf.read_text(encoding="utf-8").strip()
                  if archivo_conf.exists() else "")
        if not carpeta or not Path(carpeta).exists():
            carpeta = filedialog.askdirectory(
                title="Donde guardar el reporte", parent=self)
            if not carpeta:
                return
            archivo_conf.parent.mkdir(parents=True, exist_ok=True)
            archivo_conf.write_text(carpeta, encoding="utf-8")

        generados = []
        avisos = []
        try:
            generados += inventario.exportar_csv(self.con, carpeta)
        except Exception as err:  # noqa: BLE001
            avisos.append(f"No se pudo generar el CSV: {err}")

        try:
            generados.append(inventario.exportar_excel_nativo(self.con, carpeta))
        except ImportError:
            avisos.append(
                "El reporte en Excel necesita 'pandas' y 'openpyxl' "
                "instalados en esta computadora (pip install pandas "
                "openpyxl). El CSV sí se generó")
        except PermissionError:
            avisos.append(
                "El Excel no se pudo escribir porque esta abierto en otro "
                "programa. Cierralo e intenta de nuevo.")
        except Exception as err:  # noqa: BLE001
            avisos.append(f"No se pudo generar el Excel: {err}")

        mensaje = ""
        if generados:
            mensaje += "Se generaron:\n" + "\n".join(str(r) for r in generados)
        if avisos:
            mensaje += ("\n\n" if mensaje else "") + "\n".join(avisos)
        messagebox.showinfo("Exportar" if generados else "No se pudo exportar",
                            mensaje or "No se genero nada.", parent=self)

    def cambiar_carpeta(self) -> None:
        messagebox.showinfo(
            "Carpeta compartida",
            "Elige la misma carpeta que se configuró en la computadora que "
            "escanea. Debe "
            "verse igual desde esta computadora.", parent=self)
        carpeta = filedialog.askdirectory(
            title="Carpeta compartida del inventario", parent=self)
        if not carpeta:
            if self.carpeta is None:
                self.lbl_estado.config(text="Sin carpeta configurada",
                                       fg=tema.TXT_AVISO)
            return
        self.carpeta = Path(carpeta)
        snapshot.guardar_carpeta_configurada(snapshot.RUTA_CONFIG_VISOR,
                                             self.carpeta)
        self.actualizar()

    def _estado_para_reabrir(self) -> dict:
        """Al cambiar de tema la ventana se reconstruye y vuelve a leer la
        carpeta compartida; la copia local actual ya no se usa."""
        if self.con is not None:
            self.con.close()
            self.con = None
        return {}

    def actualizar(self) -> None:
        if self.carpeta is None:
            self.lbl_estado.config(text="Sin carpeta configurada", fg=tema.TXT_AVISO)
            return
        try:
            ruta_cache, momento = snapshot.sincronizar(self.carpeta)
        except snapshot.ErrorSincronizacion as err:
            self.lbl_estado.config(text="No se pudo actualizar", fg=tema.TXT_ERROR)
            messagebox.showwarning("No se pudo actualizar", str(err),
                                   parent=self)
            return

        if self.con is not None:
            self.con.close()
        self.con = snapshot.conectar_solo_lectura(ruta_cache)
        self.momento_datos = momento
        # Una foto publicada por una version anterior no trae la tabla de
        # prestamos: se muestra igual, solo sin herramientas con cantidad.
        self.foto_vieja = not inventario.tiene_tabla_prestamos(self.con)

        self._cargar_ubicaciones()
        self._refrescar_lista()
        self._refrescar_movimientos()
        self._refrescar_reportes()
        self._actualizar_lbl_estado()

    def _refresco_automatico(self) -> None:
        if self.carpeta is not None:
            self.actualizar()
        self.after(INTERVALO_REFRESCO_SEG * 1000, self._refresco_automatico)

    def _actualizar_lbl_estado(self) -> None:
        if self.momento_datos is None:
            return
        color = tema.TEXTO
        antiguedad = datetime.now() - self.momento_datos
        if antiguedad.total_seconds() > 30 * 60:
            color = tema.TXT_ERROR
        elif antiguedad.total_seconds() > 10 * 60:
            color = tema.TXT_AVISO
        aviso = ("   ·   foto de una version anterior (sin prestamos)"
                 if getattr(self, "foto_vieja", False) else "")
        self.lbl_estado.config(
            text=f"Datos de {_hace(self.momento_datos)} "
                 f"({self.momento_datos:%d/%m %H:%M}){aviso}", fg=color)

    def _refrescar_lista(self) -> None:
        if self.con is None:
            return
        self.tabla.delete(*self.tabla.get_children())
        estado_map = {"En bodega": "EN_BODEGA", "Fuera de la bodega": "FUERA"}
        ubic = self.filtro_ubicacion.get()
        filas = inventario.listar_articulos(
            self.con, self.busqueda.get().strip(),
            estado=estado_map.get(self.filtro_estado.get(), ""),
            ubicacion="" if ubic in ("", "Todas") else ubic)
        for f in filas:
            prestado = f["tipo"] == "AGRUPADO" and f["prestado"] > 0
            marcas = []
            if f["estado"] == "FUERA" or prestado:
                marcas.append("fuera")
            estado = ("parcial" if prestado and f["estado"] == "EN_BODEGA"
                      else "en bodega" if f["estado"] == "EN_BODEGA" else "fuera")
            self.tabla.insert(
                "", "end", iid=f["codigo"],
                values=(f["codigo"], f["nombre"],
                        inventario.TIPO_CORTO.get(f["tipo"], f["tipo"]),
                        inventario.texto_existencia(f),
                        f["ubicacion"], estado),
                tags=tuple(marcas))
        valor_total = sum(inventario.valor_articulo(f) for f in filas)
        self.conteo.config(
            text=f"{len(filas)} articulo(s)   ·   {fmt_dinero(valor_total)}")

    def _cargar_ubicaciones(self) -> None:
        if self.con is None:
            return
        ubicaciones = [f[0] for f in self.con.execute(
            "SELECT DISTINCT ubicacion FROM articulos "
            "WHERE ubicacion <> '' ORDER BY 1")]
        seleccion_previa = self.filtro_ubicacion.get()
        self.filtro_ubicacion["values"] = ["Todas"] + ubicaciones
        if seleccion_previa in ubicaciones or seleccion_previa == "Todas":
            self.filtro_ubicacion.set(seleccion_previa)
        else:
            self.filtro_ubicacion.current(0)

    def _refrescar_movimientos(self) -> None:
        if self.con is None:
            return
        self.tabla_movs.delete(*self.tabla_movs.get_children())
        movs = inventario.ultimos_movimientos(
            self.con, limite=300, filtro=self.busqueda_movs.get().strip())
        for m in movs:
            self.tabla_movs.insert(
                "", "end",
                values=(m["fecha"], m["tipo"], m["codigo"],
                        m["articulo"] or "",
                        f"{fmt(m['cantidad'])} {m['unidad'] or ''}".strip(),
                        m["persona_nombre"] or ""),
                tags=(m["tipo"],))
        self.conteo_movs.config(text=f"{len(movs)} movimiento(s) mas recientes")

    def _al_seleccionar(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if not seleccion or self.con is None:
            self._mostrar_detalle(None)
            return
        art = inventario.buscar_articulo(self.con, seleccion[0])
        self._mostrar_detalle(art)

    def _refrescar_reportes(self) -> None:
        if self.con is None:
            return

        total = inventario.valor_inventario(self.con)
        self.lbl_valor.config(
            text=f"Valor en bodega: {fmt_dinero(total['en_bodega'])}   ·   "
                 f"Prestado: {fmt_dinero(total['fuera'])}   ·   "
                 f"Total: {fmt_dinero(total['total_bodega'])}   "
                 f"({total['articulos']} articulos activos)")

        pendientes = inventario.pendientes(self.con)
        texto = "\n".join(
            f"{f['codigo']:<9} {f['nombre'][:20]:<20} {_quien(f)[:22]:<22} "
            f"{f['dias'] or 0:>3}d "
            f"{fmt_dinero(f['valor']):>11}"
            for f in pendientes
        ) or "Nada fuera de la bodega."
        if pendientes:
            texto += (f"\n\nValor total prestado: "
                      f"{fmt_dinero(sum(f['valor'] or 0 for f in pendientes))}")
        if getattr(self, "foto_vieja", False):
            texto += ("\n\n(Foto de una version anterior del programa: no "
                      "incluye herramientas con cantidad.)")
        self._llenar_texto(self.texto_pendientes, texto)

        bajos = inventario.bajo_stock(self.con)
        texto2 = "\n".join(
            f"{f['codigo']:<9} {f['nombre'][:24]:<24} "
            f"{fmt(f['existencia'])}/{fmt(f['minimo'])} {f['unidad']}"
            + (f" disp. ({fmt(f['prestado'])} prestadas)"
               if f["tipo"] == "AGRUPADO" else "")
            for f in bajos
        ) or "Nada por debajo de su minimo."
        self._llenar_texto(self.texto_bajo_stock, texto2)

    @staticmethod
    def _llenar_texto(caja: tk.Text, contenido: str) -> None:
        caja.config(state="normal")
        caja.delete("1.0", "end")
        caja.insert("1.0", contenido)
        caja.config(state="disabled")


def _quien(fila) -> str:
    """Columna 'quien' de Fuera de la bodega: con cantidad para AGRUPADO."""
    if fila["tipo"] == "AGRUPADO":
        return f"{fmt(fila['cantidad'])} con {fila['quien']}"
    return fila["quien"]


if __name__ == "__main__":
    tema.ejecutar(VisorInventario)
