"""
Base de datos del inventario de bodega.

Se encarga de tres cosas:
  1. Crear el archivo SQLite y su esquema si no existen.
  2. Abrir la conexion ya configurada (claves foraneas, filas por nombre).
  3. Hacer un respaldo automatico del archivo cada vez que arranca el programa.

No requiere instalar nada: sqlite3 viene incluido en Python.
"""

from __future__ import annotations

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
                CHECK (tipo IN ('UNICO', 'CONSUMIBLE')),
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

CREATE INDEX IF NOT EXISTS idx_mov_codigo ON movimientos(codigo);
CREATE INDEX IF NOT EXISTS idx_mov_fecha  ON movimientos(fecha);
CREATE INDEX IF NOT EXISTS idx_art_estado ON articulos(estado);
"""

_respaldo_hecho = False


def respaldar(ruta_db: Path = RUTA_DB) -> Path | None:
    """Copia el archivo .db a datos/respaldos/ con fecha y hora en el nombre.

    Solo se ejecuta una vez por arranque del programa. Conserva los ultimos
    MAX_RESPALDOS y borra los mas antiguos.
    """
    global _respaldo_hecho
    if _respaldo_hecho or not ruta_db.exists():
        return None

    DIR_RESPALDOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = DIR_RESPALDOS / f"inventario_{marca}.db"
    shutil.copy2(ruta_db, destino)
    _respaldo_hecho = True

    viejos = sorted(DIR_RESPALDOS.glob("inventario_*.db"))
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
    """Agrega columnas nuevas a bases creadas con versiones anteriores."""
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
    for tabla in ("articulos", "personas", "movimientos"):
        total = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        print(f"  {tabla}: {total} registros")
