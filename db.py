"""
Base de datos del inventario de bodega.

Se encarga de tres cosas:
  1. Crear el archivo SQLite y su esquema si no existen.
  2. Abrir la conexion ya configurada (claves foraneas, filas por nombre).
  3. Hacer un respaldo automatico del archivo cada vez que arranca el programa.

No requiere instalar nada: sqlite3 viene incluido en Python.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIR_DATOS = RAIZ / "datos"
DIR_RESPALDOS = DIR_DATOS / "respaldos"
RUTA_DB = DIR_DATOS / "inventario.db"

# Cuantos respaldos conservar antes de empezar a borrar los mas viejos.
MAX_RESPALDOS = 30

PREFIJO_PERSONA = "PER"
PREFIJO_UNICO = "HER"
PREFIJO_CONSUMIBLE = "MAT"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS articulos (
    codigo      TEXT PRIMARY KEY,
    nombre      TEXT NOT NULL,
    categoria   TEXT NOT NULL DEFAULT '',
    tipo        TEXT NOT NULL DEFAULT 'UNICO'
                CHECK (tipo IN ('UNICO', 'AGRUPADO', 'CONSUMIBLE')),
    ubicacion   TEXT NOT NULL DEFAULT '',
    unidad      TEXT NOT NULL DEFAULT 'pza',
    existencia  REAL NOT NULL DEFAULT 1,
    minimo      REAL NOT NULL DEFAULT 0,
    marca       TEXT NOT NULL DEFAULT '',
    modelo      TEXT NOT NULL DEFAULT '',
    numero_serie TEXT NOT NULL DEFAULT '',
    valor_unitario REAL NOT NULL DEFAULT 0,
    estado      TEXT NOT NULL DEFAULT 'EN_BODEGA'
                CHECK (estado IN ('EN_BODEGA', 'FUERA')),
    notas       TEXT NOT NULL DEFAULT '',
    activo      INTEGER NOT NULL DEFAULT 1,
    creado      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS personas (
    codigo  TEXT PRIMARY KEY,
    nombre  TEXT NOT NULL,
    activo  INTEGER NOT NULL DEFAULT 1,
    creado  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS movimientos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo    TEXT NOT NULL REFERENCES articulos(codigo) ON DELETE CASCADE,
    persona   TEXT REFERENCES personas(codigo),
    tipo      TEXT NOT NULL CHECK (tipo IN ('SALIDA', 'ENTRADA', 'AJUSTE')),
    cantidad  REAL NOT NULL DEFAULT 1,
    fecha     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    nota      TEXT NOT NULL DEFAULT ''
);

-- Quien tiene cuantas piezas de cada herramienta AGRUPADO. Una fila por
-- articulo y persona; si la persona regresa todo, la fila se borra.
-- 'desde' es cuando esa persona empezo a deber piezas (para los dias fuera).
CREATE TABLE IF NOT EXISTS prestamos (
    codigo    TEXT NOT NULL REFERENCES articulos(codigo) ON DELETE CASCADE,
    persona   TEXT NOT NULL REFERENCES personas(codigo),
    cantidad  REAL NOT NULL CHECK (cantidad > 0),
    desde     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (codigo, persona)
);

CREATE INDEX IF NOT EXISTS idx_mov_codigo ON movimientos(codigo);
CREATE INDEX IF NOT EXISTS idx_mov_fecha  ON movimientos(fecha);
CREATE INDEX IF NOT EXISTS idx_art_estado ON articulos(estado);
CREATE INDEX IF NOT EXISTS idx_prest_persona ON prestamos(persona);
"""

# Tipos de articulo que acepta la columna articulos.tipo.
TIPOS = ("UNICO", "AGRUPADO", "CONSUMIBLE")

_respaldo_hecho = False


def respaldar(ruta_db: Path = RUTA_DB, forzar: bool = False,
              sufijo: str = "") -> Path | None:
    """Copia el archivo .db a la carpeta 'respaldos' junto a la base, con
    fecha y hora en el nombre (para la base normal es datos/respaldos/).

    Solo se ejecuta una vez por arranque del programa, salvo con forzar=True
    (lo usa la migracion: siempre respalda justo antes de tocar el esquema).
    Conserva los ultimos MAX_RESPALDOS y borra los mas antiguos.
    """
    global _respaldo_hecho
    ruta_db = Path(ruta_db)
    if (_respaldo_hecho and not forzar) or not ruta_db.exists():
        return None

    carpeta = ruta_db.parent / DIR_RESPALDOS.name
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = carpeta / f"inventario_{marca}{sufijo}.db"
    shutil.copy2(ruta_db, destino)
    if not forzar:
        _respaldo_hecho = True

    viejos = sorted(carpeta.glob("inventario_*.db"))
    for archivo in viejos[:-MAX_RESPALDOS]:
        archivo.unlink(missing_ok=True)

    return destino


def conectar(ruta_db: Path = RUTA_DB, con_respaldo: bool = True) -> sqlite3.Connection:
    """Devuelve una conexion lista para usar, creando la base si hace falta."""
    ruta_db = Path(ruta_db)
    ruta_db.parent.mkdir(parents=True, exist_ok=True)

    if con_respaldo:
        respaldar(ruta_db)

    con = sqlite3.connect(ruta_db)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    _migrar(con)
    con.commit()
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Pone al dia bases creadas con versiones anteriores.

    Se puede correr cuantas veces sea: cada paso revisa primero si hace falta.
    (La tabla 'prestamos' ya la crea ESQUEMA con CREATE TABLE IF NOT EXISTS.)
    """
    columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(articulos)")}
    if "activo" not in columnas:
        con.execute(
            "ALTER TABLE articulos ADD COLUMN activo INTEGER NOT NULL DEFAULT 1"
        )
    for columna, tipo, defecto in (
        ("marca", "TEXT", "''"),
        ("modelo", "TEXT", "''"),
        ("numero_serie", "TEXT", "''"),
        ("valor_unitario", "REAL", "0"),
    ):
        if columna not in columnas:
            con.execute(
                f"ALTER TABLE articulos ADD COLUMN {columna} {tipo} "
                f"NOT NULL DEFAULT {defecto}"
            )

    _ampliar_tipos(con)


# Encuentra el CHECK de la columna tipo dentro del CREATE TABLE guardado.
_REGEX_CHECK_TIPO = re.compile(r"CHECK\s*\(\s*tipo\s+IN\s*\(([^)]*)\)\s*\)",
                               re.IGNORECASE)


def _ampliar_tipos(con: sqlite3.Connection) -> None:
    """Agrega 'AGRUPADO' al CHECK de articulos.tipo en bases viejas.

    SQLite no deja modificar un CHECK, asi que se recrea la tabla siguiendo
    el procedimiento que recomienda su documentacion: tabla nueva con el
    mismo CREATE (solo cambia el CHECK), copiar las filas tal cual, borrar la
    vieja, renombrar la nueva y volver a crear sus indices y triggers. Todo
    en una sola transaccion: si algo falla no queda nada a medias. Antes se
    respalda el archivo.
    """
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'articulos'"
    ).fetchone()[0]
    encontrado = _REGEX_CHECK_TIPO.search(sql)
    if encontrado is None or "AGRUPADO" in encontrado.group(1).upper():
        return  # sin CHECK o ya ampliado: nada que hacer

    con.commit()
    ruta = con.execute("PRAGMA database_list").fetchone()["file"]
    if ruta:
        respaldar(Path(ruta), forzar=True, sufijo="_antes_migracion")

    tipos = ", ".join(f"'{t}'" for t in TIPOS)
    sql_nuevo = (sql[:encontrado.start(1)] + tipos + sql[encontrado.end(1):])
    sql_nuevo = re.sub(r"^\s*CREATE\s+TABLE\s+(\"?articulos\"?|'articulos')",
                       "CREATE TABLE articulos_nuevo", sql_nuevo, count=1,
                       flags=re.IGNORECASE)
    columnas = ", ".join(f'"{f["name"]}"' for f in
                         con.execute("PRAGMA table_info(articulos)"))
    extras = [f["sql"] for f in con.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = 'articulos' "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL")]

    # Las claves foraneas se apagan durante el cambio (si no, borrar la
    # tabla vieja borraria en cascada los movimientos). No se puede cambiar
    # dentro de una transaccion, por eso va antes del BEGIN.
    nivel_previo = con.isolation_level
    con.isolation_level = None
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN")
        con.execute(sql_nuevo)
        # rowid incluido: las filas conservan hasta su numero interno.
        con.execute(f"INSERT INTO articulos_nuevo (rowid, {columnas}) "
                    f"SELECT rowid, {columnas} FROM articulos")
        con.execute("DROP TABLE articulos")
        con.execute("ALTER TABLE articulos_nuevo RENAME TO articulos")
        for sentencia in extras:
            con.execute(sentencia)
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError(
                "La migracion dejaria claves foraneas rotas; se cancela.")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")
        con.isolation_level = nivel_previo


def siguiente_codigo(con: sqlite3.Connection, prefijo: str) -> str:
    """Genera el siguiente codigo libre de una serie, por ejemplo HER-0043."""
    prefijo = prefijo.upper().strip("- ")
    tabla = "personas" if prefijo == PREFIJO_PERSONA else "articulos"
    filas = con.execute(
        f"SELECT codigo FROM {tabla} WHERE codigo LIKE ?", (f"{prefijo}-%",)
    ).fetchall()

    mayor = 0
    for fila in filas:
        sufijo = fila["codigo"].split("-", 1)[-1]
        if sufijo.isdigit():
            mayor = max(mayor, int(sufijo))

    return f"{prefijo}-{mayor + 1:04d}"


if __name__ == "__main__":
    con = conectar()
    print(f"Base de datos lista en: {RUTA_DB}")
    for tabla in ("articulos", "personas", "movimientos", "prestamos"):
        total = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        print(f"  {tabla}: {total} registros")
