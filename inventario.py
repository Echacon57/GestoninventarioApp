"""
Logica del inventario: altas, escaneos y reportes.

Aqui vive la regla de negocio; ni la ventana de escaneo ni el generador de
etiquetas saben como se actualiza la base, solo llaman a estas funciones.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import db

# Modos de operacion de la ventana de escaneo.
MODO_AUTO = "AUTO"        # articulo unico: alterna salida/entrada. Consumible: salida.
MODO_SALIDA = "SALIDA"    # siempre descuenta / marca como fuera
MODO_ENTRADA = "ENTRADA"  # siempre devuelve / marca como en bodega


def fmt(numero: float) -> str:
    """Muestra 3 en vez de 3.0, pero conserva 2.5 cuando hace falta."""
    numero = float(numero)
    return str(int(numero)) if numero.is_integer() else f"{numero:g}"


def fmt_dinero(numero: float) -> str:
    """Formatea con separador de miles: 12345.5 -> '$12,345.50'."""
    return f"${float(numero or 0):,.2f}"


def valor_articulo(fila) -> float:
    """Valor monetario de un articulo, este o no en la bodega."""
    cantidad = 1 if fila["tipo"] == "UNICO" else fila["existencia"]
    return float(fila["valor_unitario"] or 0) * float(cantidad or 0)


@dataclass
class Resultado:
    """Lo que devuelve un escaneo, listo para pintarse en pantalla."""
    ok: bool
    nivel: str          # 'ok' | 'aviso' | 'error' | 'persona'
    titulo: str
    detalle: str = ""
    articulo: dict = field(default_factory=dict)
    persona: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Consultas basicas
# --------------------------------------------------------------------------

def buscar_articulo(con: sqlite3.Connection, codigo: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM articulos WHERE codigo = ?", (codigo,)
    ).fetchone()


def buscar_persona(con: sqlite3.Connection, codigo: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM personas WHERE codigo = ? AND activo = 1", (codigo,)
    ).fetchone()


def listar_articulos(con: sqlite3.Connection, filtro: str = "",
                     incluir_bajas: bool = False, ubicacion: str = "",
                     estado: str = "") -> list[sqlite3.Row]:
    condiciones = [] if incluir_bajas else ["activo = 1"]
    parametros: list = []
    if filtro:
        patron = f"%{filtro}%"
        condiciones.append(
            "(codigo LIKE ? OR nombre LIKE ? OR categoria LIKE ? "
            " OR ubicacion LIKE ? OR marca LIKE ? OR modelo LIKE ? "
            " OR numero_serie LIKE ?)"
        )
        parametros += [patron] * 7
    if ubicacion:
        condiciones.append("ubicacion = ?")
        parametros.append(ubicacion)
    if estado:
        condiciones.append("estado = ?")
        parametros.append(estado)
    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return con.execute(
        f"SELECT * FROM articulos {donde} ORDER BY codigo", parametros
    ).fetchall()


def listar_personas(con: sqlite3.Connection,
                    incluir_bajas: bool = False) -> list[sqlite3.Row]:
    donde = "" if incluir_bajas else "WHERE activo = 1"
    return con.execute(
        f"SELECT * FROM personas {donde} ORDER BY codigo"
    ).fetchall()


def ultimos_movimientos(con: sqlite3.Connection, limite: int = 25,
                        filtro: str = "") -> list[sqlite3.Row]:
    condicion, parametros = "", []
    if filtro:
        patron = f"%{filtro}%"
        condicion = ("WHERE m.codigo LIKE ? OR a.nombre LIKE ? "
                    "OR p.nombre LIKE ?")
        parametros = [patron, patron, patron]
    return con.execute(
        f"""
        SELECT m.*, a.nombre AS articulo, a.unidad, p.nombre AS persona_nombre
        FROM movimientos m
        LEFT JOIN articulos a ON a.codigo = m.codigo
        LEFT JOIN personas  p ON p.codigo = m.persona
        {condicion}
        ORDER BY m.id DESC LIMIT ?
        """,
        (*parametros, limite),
    ).fetchall()


def pendientes(con: sqlite3.Connection, dias: int = 0) -> list[sqlite3.Row]:
    """Articulos que estan fuera de la bodega, con quien los saco y desde cuando."""
    return con.execute(
        """
        SELECT a.codigo, a.nombre, a.tipo, a.existencia, a.unidad,
               a.valor_unitario,
               m.fecha AS desde, COALESCE(p.nombre, '(sin registrar)') AS quien,
               CAST(julianday('now', 'localtime') - julianday(m.fecha) AS INTEGER) AS dias
        FROM articulos a
        LEFT JOIN movimientos m ON m.id = (
            SELECT id FROM movimientos
            WHERE codigo = a.codigo AND tipo = 'SALIDA'
            ORDER BY id DESC LIMIT 1
        )
        LEFT JOIN personas p ON p.codigo = m.persona
        WHERE a.estado = 'FUERA' AND a.activo = 1
          AND CAST(julianday('now','localtime') - julianday(COALESCE(m.fecha,
              datetime('now','localtime'))) AS INTEGER) >= ?
        ORDER BY dias DESC
        """,
        (dias,),
    ).fetchall()


def bajo_stock(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM articulos "
        "WHERE tipo = 'CONSUMIBLE' AND activo = 1 "
        "AND minimo > 0 AND existencia <= minimo "
        "ORDER BY existencia / NULLIF(minimo, 0)"
    ).fetchall()


def valor_inventario(con: sqlite3.Connection) -> dict:
    """Valor total en bodega y prestado, valuado a costo unitario.

    Una herramienta unica (UNICO) vale su costo este o no en la bodega: su
    'existencia' se pone en 0 en cuanto sale prestada (ese campo solo marca
    presencia, no valor), asi que aqui se usa 1 como su cantidad efectiva
    sin importar el estado. Un consumible sí vale segun lo que quede en
    existencia, este donde este. Solo cuenta lo activo.
    """
    cantidad_efectiva = "(CASE WHEN tipo = 'UNICO' THEN 1 ELSE existencia END)"
    fila = con.execute(
        f"SELECT COALESCE(SUM(valor_unitario * {cantidad_efectiva}), 0)"
        f"   AS total_bodega,"
        f" COALESCE(SUM(CASE WHEN estado='EN_BODEGA' THEN"
        f"     valor_unitario * {cantidad_efectiva} ELSE 0 END), 0) AS en_bodega,"
        f" COALESCE(SUM(CASE WHEN estado='FUERA' THEN"
        f"     valor_unitario * {cantidad_efectiva} ELSE 0 END), 0) AS fuera,"
        f" COUNT(*) AS articulos"
        f" FROM articulos WHERE activo = 1"
    ).fetchone()
    return dict(fila)


def valor_por_categoria(con: sqlite3.Connection) -> list[sqlite3.Row]:
    cantidad_efectiva = "(CASE WHEN tipo = 'UNICO' THEN 1 ELSE existencia END)"
    return con.execute(
        f"SELECT COALESCE(NULLIF(categoria, ''), '(sin categoria)') AS categoria,"
        f" COUNT(*) AS articulos,"
        f" SUM(valor_unitario * {cantidad_efectiva}) AS valor"
        f" FROM articulos WHERE activo = 1"
        f" GROUP BY categoria ORDER BY valor DESC"
    ).fetchall()


# --------------------------------------------------------------------------
# Altas
# --------------------------------------------------------------------------

def agregar_articulo(
    con: sqlite3.Connection,
    nombre: str,
    tipo: str = "UNICO",
    categoria: str = "",
    ubicacion: str = "",
    unidad: str = "pza",
    existencia: float | None = None,
    minimo: float = 0,
    marca: str = "",
    modelo: str = "",
    numero_serie: str = "",
    valor_unitario: float = 0,
    notas: str = "",
    activo: bool = True,
    codigo: str | None = None,
) -> str:
    tipo = tipo.upper()
    if tipo not in ("UNICO", "CONSUMIBLE"):
        raise ValueError("El tipo debe ser UNICO o CONSUMIBLE")

    if existencia is None:
        existencia = 1 if tipo == "UNICO" else 0
    if tipo == "UNICO":
        existencia = 1 if existencia else 0

    if codigo is None:
        prefijo = db.PREFIJO_UNICO if tipo == "UNICO" else db.PREFIJO_CONSUMIBLE
        codigo = db.siguiente_codigo(con, prefijo)
    codigo = codigo.strip().upper()

    con.execute(
        "INSERT INTO articulos "
        "(codigo, nombre, categoria, tipo, ubicacion, unidad, existencia, "
        " minimo, marca, modelo, numero_serie, valor_unitario, estado, "
        " notas, activo) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (codigo, nombre.strip(), categoria.strip(), tipo, ubicacion.strip(),
         unidad.strip() or "pza", float(existencia), float(minimo),
         marca.strip(), modelo.strip(), numero_serie.strip(),
         float(valor_unitario or 0),
         "EN_BODEGA" if existencia > 0 else "FUERA", notas.strip(),
         1 if activo else 0),
    )
    con.commit()
    return codigo


def agregar_persona(con: sqlite3.Connection, nombre: str,
                    codigo: str | None = None) -> str:
    codigo = (codigo or db.siguiente_codigo(con, db.PREFIJO_PERSONA)).strip().upper()
    con.execute("INSERT INTO personas (codigo, nombre) VALUES (?, ?)",
                (codigo, nombre.strip()))
    con.commit()
    return codigo


CAMPOS_EDITABLES = ("nombre", "categoria", "tipo", "ubicacion", "unidad",
                    "existencia", "minimo", "marca", "modelo",
                    "numero_serie", "valor_unitario", "notas")


def actualizar_articulo(con: sqlite3.Connection, codigo: str, **campos) -> None:
    """Modifica un articulo ya existente. Solo toca los campos que le pasas."""
    codigo = codigo.strip().upper()
    cambios = {k: v for k, v in campos.items() if k in CAMPOS_EDITABLES}
    if not cambios:
        return

    if cambios.get("tipo") == "UNICO":
        actual = buscar_articulo(con, codigo)
        cambios["existencia"] = 1 if (actual and actual["estado"] == "EN_BODEGA") else 0
        cambios["minimo"] = 0

    if "existencia" in cambios:
        cambios["estado"] = "EN_BODEGA" if float(cambios["existencia"]) > 0 else "FUERA"

    asignaciones = ", ".join(f"{campo} = ?" for campo in cambios)
    con.execute(f"UPDATE articulos SET {asignaciones} WHERE codigo = ?",
                (*cambios.values(), codigo))
    con.commit()


def baja_articulo(con: sqlite3.Connection, codigo: str, activo: bool = False) -> None:
    """Da de baja (o reactiva) un articulo sin borrar su historial."""
    con.execute("UPDATE articulos SET activo = ? WHERE codigo = ?",
                (1 if activo else 0, codigo.strip().upper()))
    con.commit()


def actualizar_persona(con: sqlite3.Connection, codigo: str, nombre: str) -> None:
    con.execute("UPDATE personas SET nombre = ? WHERE codigo = ?",
                (nombre.strip(), codigo.strip().upper()))
    con.commit()


def baja_persona(con: sqlite3.Connection, codigo: str, activo: bool = False) -> None:
    con.execute("UPDATE personas SET activo = ? WHERE codigo = ?",
                (1 if activo else 0, codigo.strip().upper()))
    con.commit()


def tiene_pendientes(con: sqlite3.Connection, codigo_persona: str) -> list[sqlite3.Row]:
    """Herramientas que siguen fuera a nombre de esta persona."""
    return con.execute(
        """
        SELECT a.codigo, a.nombre FROM articulos a
        WHERE a.estado = 'FUERA' AND a.activo = 1 AND (
            SELECT m.persona FROM movimientos m
            WHERE m.codigo = a.codigo AND m.tipo = 'SALIDA'
            ORDER BY m.id DESC LIMIT 1) = ?
        """,
        (codigo_persona.strip().upper(),),
    ).fetchall()


def importar_csv(con: sqlite3.Connection, ruta: Path) -> tuple[int, list[str]]:
    """Carga articulos desde un CSV. Columnas reconocidas:
    nombre, tipo, categoria, ubicacion, unidad, existencia, minimo,
    marca, modelo, numero_serie, valor_unitario, notas, activo, codigo
    Solo 'nombre' es obligatoria.
    """
    altas, errores = 0, []
    with open(ruta, newline="", encoding="utf-8-sig") as archivo:
        for num, fila in enumerate(csv.DictReader(archivo), start=2):
            fila = {(k or "").strip().lower(): (v or "").strip()
                    for k, v in fila.items()}
            if not fila.get("nombre"):
                continue
            try:
                activo_txt = fila.get("activo", "1").strip().lower()
                agregar_articulo(
                    con,
                    nombre=fila["nombre"],
                    tipo=fila.get("tipo") or "UNICO",
                    categoria=fila.get("categoria", ""),
                    ubicacion=fila.get("ubicacion", ""),
                    unidad=fila.get("unidad") or "pza",
                    existencia=float(fila["existencia"]) if fila.get("existencia") else None,
                    minimo=float(fila["minimo"]) if fila.get("minimo") else 0,
                    marca=fila.get("marca", ""),
                    modelo=fila.get("modelo", ""),
                    numero_serie=fila.get("numero_serie", ""),
                    valor_unitario=float(fila["valor_unitario"]) if fila.get("valor_unitario") else 0,
                    notas=fila.get("notas", ""),
                    activo=activo_txt not in ("0", "false", "no"),
                    codigo=fila.get("codigo") or None,
                )
                altas += 1
            except Exception as err:  # noqa: BLE001
                errores.append(f"linea {num}: {err}")
    return altas, errores


# --------------------------------------------------------------------------
# Sección de escaneo
# --------------------------------------------------------------------------

def registrar_escaneo(
    con: sqlite3.Connection,
    codigo: str,
    persona: str | None = None,
    modo: str = MODO_AUTO,
    cantidad: float = 1,
    nota: str = "",
) -> Resultado:
    """Procesa un codigo leido por el escaner y actualiza la base."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return Resultado(False, "error", "Codigo vacio")

    # Gafete de persona: no mueve inventario, solo cambia quien esta activo.
    quien = buscar_persona(con, codigo)
    if quien:
        return Resultado(True, "persona", f"Operador: {quien['nombre']}",
                         "Escanea ahora las herramientas o materiales.",
                         persona=dict(quien))

    # Si el código no es un gafete, verificamos obligatoriamente que ya 
    # haya un responsable activo en la sesión antes de continuar.
    if not persona:
        return Resultado(False, "error", "Operador no seleccionado",
                         "Escanea primero tu gafete para registrar el movimiento.")

    # Articulos.
    art = buscar_articulo(con, codigo)
    if art is None:
        return Resultado(False, "error", f"{codigo} no esta registrado",
                         "Dalo de alta en el panel de gestion (boton Catalogo).")

    if not art["activo"]:
        return Resultado(False, "error", f"{art['nombre']} esta dado de baja",
                         "Reactivalo en el panel de gestion si vuelve a usarse.",
                         dict(art))

    cantidad = float(cantidad)
    if cantidad <= 0:
        return Resultado(False, "error", "La cantidad debe ser mayor que cero")

    if art["tipo"] == "UNICO":
        return _escanear_unico(con, art, persona, modo, nota)
    return _escanear_consumible(con, art, persona, modo, cantidad, nota)


def _guardar_movimiento(con, codigo, persona, tipo, cantidad, nota) -> None:
    con.execute(
        "INSERT INTO movimientos (codigo, persona, tipo, cantidad, nota) "
        "VALUES (?,?,?,?,?)",
        (codigo, persona, tipo, float(cantidad), nota),
    )


def _escanear_unico(con, art, persona, modo, nota) -> Resultado:
    esta_dentro = art["estado"] == "EN_BODEGA"

    if modo == MODO_AUTO:
        accion = "SALIDA" if esta_dentro else "ENTRADA"
    else:
        accion = modo
        if accion == "SALIDA" and not esta_dentro:
            return Resultado(False, "aviso", f"{art['nombre']} ya estaba fuera",
                             _quien_lo_tiene(con, art["codigo"]), dict(art))
        if accion == "ENTRADA" and esta_dentro:
            return Resultado(False, "aviso", f"{art['nombre']} ya estaba en bodega",
                             "", dict(art))

    nuevo_estado = "FUERA" if accion == "SALIDA" else "EN_BODEGA"
    con.execute(
        "UPDATE articulos SET estado = ?, existencia = ? WHERE codigo = ?",
        (nuevo_estado, 0 if accion == "SALIDA" else 1, art["codigo"]),
    )
    _guardar_movimiento(con, art["codigo"], persona, accion, 1, nota)
    con.commit()

    if accion == "SALIDA":
        detalle = "Registrado como prestado" + (
            f" a {_nombre_persona(con, persona)}" if persona else " (sin operador)")
    else:
        detalle = f"De vuelta en su lugar: {art['ubicacion'] or 'sin ubicacion'}"

    return Resultado(True, "ok", f"{accion}: {art['nombre']}", detalle, dict(art))


def _escanear_consumible(con, art, persona, modo, cantidad, nota) -> Resultado:
    accion = "ENTRADA" if modo == MODO_ENTRADA else "SALIDA"
    existencia = float(art["existencia"])

    if accion == "SALIDA":
        if existencia <= 0:
            return Resultado(False, "error", f"Sin existencia: {art['nombre']}",
                             "Registra una entrada cuando llegue material.",
                             dict(art))
        if cantidad > existencia:
            return Resultado(False, "error",
                             f"Solo hay {fmt(existencia)} {art['unidad']} de "
                             f"{art['nombre']}",
                             f"Intentaste sacar {fmt(cantidad)}.", dict(art))
        nueva = existencia - cantidad
    else:
        nueva = existencia + cantidad

    con.execute(
        "UPDATE articulos SET existencia = ?, estado = ? WHERE codigo = ?",
        (nueva, "EN_BODEGA" if nueva > 0 else "FUERA", art["codigo"]),
    )
    _guardar_movimiento(con, art["codigo"], persona, accion, cantidad, nota)
    con.commit()

    nivel = "ok"
    detalle = f"Quedan {fmt(nueva)} {art['unidad']}"
    if art["minimo"] and nueva <= float(art["minimo"]):
        nivel = "aviso"
        detalle += f"  |  bajo el minimo de {fmt(art['minimo'])}, hay que resurtir"

    titulo = (f"{accion}: {fmt(cantidad)} {art['unidad']} de {art['nombre']}")
    return Resultado(True, nivel, titulo, detalle, dict(art))


def ajustar_existencia(con, codigo: str, nueva: float, nota: str = "") -> Resultado:
    """Correccion manual, por ejemplo despues de un conteo fisico."""
    codigo = codigo.strip().upper()
    art = buscar_articulo(con, codigo)
    if art is None:
        return Resultado(False, "error", f"{codigo} no esta registrado")

    diferencia = float(nueva) - float(art["existencia"])
    con.execute(
        "UPDATE articulos SET existencia = ?, estado = ? WHERE codigo = ?",
        (float(nueva), "EN_BODEGA" if nueva > 0 else "FUERA", codigo),
    )
    _guardar_movimiento(con, codigo, None, "AJUSTE", diferencia,
                        nota or "ajuste manual")
    con.commit()
    return Resultado(True, "ok", f"Ajuste: {art['nombre']}",
                     f"Existencia {fmt(art['existencia'])} -> {fmt(nueva)}",
                     dict(art))


def _nombre_persona(con, codigo) -> str:
    if not codigo:
        return ""
    fila = con.execute("SELECT nombre FROM personas WHERE codigo = ?",
                       (codigo,)).fetchone()
    return fila["nombre"] if fila else codigo


def _quien_lo_tiene(con, codigo) -> str:
    fila = con.execute(
        "SELECT m.fecha, COALESCE(p.nombre, '(sin operador)') AS quien "
        "FROM movimientos m LEFT JOIN personas p ON p.codigo = m.persona "
        "WHERE m.codigo = ? AND m.tipo = 'SALIDA' ORDER BY m.id DESC LIMIT 1",
        (codigo,),
    ).fetchone()
    return f"Lo saco {fila['quien']} el {fila['fecha']}" if fila else ""


# --------------------------------------------------------------------------
# Exportacion
# --------------------------------------------------------------------------

def exportar_csv(con: sqlite3.Connection, carpeta: Path) -> list[Path]:
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    generados = []

    consultas = {
        "articulos.csv": "SELECT * FROM articulos ORDER BY codigo",
        "movimientos.csv": (
            "SELECT m.id, m.fecha, m.codigo, a.nombre, m.tipo, m.cantidad, "
            "a.unidad, COALESCE(p.nombre, '') AS persona, m.nota "
            "FROM movimientos m "
            "LEFT JOIN articulos a ON a.codigo = m.codigo "
            "LEFT JOIN personas p ON p.codigo = m.persona ORDER BY m.id"
        ),
        "personas.csv": "SELECT * FROM personas ORDER BY codigo",
    }

    for nombre, sql in consultas.items():
        filas = con.execute(sql).fetchall()
        ruta = carpeta / nombre
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            if filas:
                escritor.writerow(filas[0].keys())
                escritor.writerows([tuple(f) for f in filas])
        generados.append(ruta)

    return generados

def exportar_excel_nativo(con: sqlite3.Connection, carpeta: Path) -> Path:
    """Exporta todas las tablas a un solo archivo Excel con pestañas.

    pandas y openpyxl se importan aqui adentro (no al inicio del archivo)
    a proposito: son librerias pesadas que solo hacen falta para esto, y asi
    programas que solo leen (como visor.py) no necesitan instalarlas.
    """
    import pandas as pd
    import openpyxl
    from openpyxl.styles import PatternFill

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    
    from datetime import datetime
    marca = datetime.now().strftime("%Y%m%d")
    ruta_salida = carpeta / f"Reporte_Inventario_{marca}.xlsx"
    # Si está abierto en Excel, esta línea lanzará un PermissionError que la app va a atrapar.
    if ruta_salida.exists():
        ruta_salida.unlink()

    df_articulos = pd.read_sql_query("SELECT * FROM articulos ORDER BY codigo", con)
    df_personas = pd.read_sql_query("SELECT * FROM personas ORDER BY codigo", con)
    df_movimientos = pd.read_sql_query("""
        SELECT m.id, m.fecha, m.codigo, a.nombre, m.tipo, m.cantidad, 
               a.unidad, COALESCE(p.nombre, '') AS persona, m.nota 
        FROM movimientos m 
        LEFT JOIN articulos a ON a.codigo = m.codigo 
        LEFT JOIN personas p ON p.codigo = m.persona 
        ORDER BY m.id DESC
    """, con)

    # Definir los colores (verde para EN_BODEGA, rojo para FUERA)
    fondo_verde = PatternFill(start_color='A9D08E', end_color='A9D08E', fill_type='solid')
    fondo_rojo = PatternFill(start_color='FF0000', end_color='FF0000', fill_type='solid')

    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        df_articulos.to_excel(writer, sheet_name='Artículos', index=False)
        df_movimientos.to_excel(writer, sheet_name='Movimientos', index=False)
        df_personas.to_excel(writer, sheet_name='Operadores', index=False)
        
        for sheetname, df in zip(['Artículos', 'Movimientos', 'Operadores'], 
                                 [df_articulos, df_movimientos, df_personas]):
            worksheet = writer.sheets[sheetname]
            
            # Auto-ajustar el ancho de las columnas
            for i, col in enumerate(df.columns):
                largo_datos = df[col].astype(str).map(len).max() if len(df) else 0
                max_len = max(largo_datos, len(col)) + 2
                worksheet.column_dimensions[openpyxl.utils.get_column_letter(i+1)].width = max_len

            # Aplicar colores en la pestaña Artículos
            if sheetname == 'Artículos' and 'estado' in df.columns:
                # Obtener el índice numérico de la columna 'estado'
                col_estado_idx = df.columns.get_loc('estado') + 1
                
                # Iterar sobre las filas (saltando la fila 1 que es el encabezado)
                for row_idx in range(2, len(df) + 2):
                    celda = worksheet.cell(row=row_idx, column=col_estado_idx)
                    if celda.value == 'EN_BODEGA':
                        celda.fill = fondo_verde
                    elif celda.value == 'FUERA':
                        celda.fill = fondo_rojo

    return ruta_salida