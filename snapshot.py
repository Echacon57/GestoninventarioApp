"""
Comparte el inventario con otras computadoras en modo solo lectura, usando
una carpeta sincronizada (OneDrive, Google Drive, Dropbox, o una carpeta de
red) como intermediario.

Como SQLite no soporta que dos computadoras escriban al mismo archivo a la
vez de forma segura, este modulo NO comparte el archivo real de la base.
En vez de eso, la computadora que escanea publica cada cierto tiempo una
"foto" (una copia consistente, tomada con la API de respaldo de SQLite, que
nunca queda a medio escribir) en esa carpeta compartida. Las demas
computadoras solo leen esa foto, por lo tanto, nunca abren ni modifican el original.

Esto significa que las otras computadoras siempre ven el inventario de hace
unos segundos o minutos, no al instante. Es una limitacion aceptada a
cambio de algo mucho mas simple y seguro(y barato) que sincronizar una base de datos
en vivo.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import db

NOMBRE_SNAPSHOT = "inventario_snapshot.db"
NOMBRE_METADATA = "ultima_actualizacion.txt"

RUTA_CONFIG_ORIGEN = db.DIR_DATOS / "carpeta_compartida.txt"
DIR_VISOR = db.RAIZ / "datos_visor"
RUTA_CONFIG_VISOR = DIR_VISOR / "carpeta_compartida.txt"
RUTA_CACHE_VISOR = DIR_VISOR / "cache.db"

# Cada cuanto se vuelve a publicar por temporizador (ademas de despues de
# cada movimiento). En segundos.
INTERVALO_PUBLICACION_SEG = 120


def leer_carpeta_configurada(ruta_config: Path) -> Path | None:
    if not ruta_config.exists():
        return None
    texto = ruta_config.read_text(encoding="utf-8").strip()
    return Path(texto) if texto else None


def guardar_carpeta_configurada(ruta_config: Path, carpeta: Path) -> None:
    ruta_config.parent.mkdir(parents=True, exist_ok=True)
    ruta_config.write_text(str(carpeta), encoding="utf-8")


def publicar(con: sqlite3.Connection, carpeta_destino: Path) -> datetime:
    """Copia un estado consistente de la base a la carpeta compartida.

    Usa la API de respaldo de SQLite en vez de copiar el
    archivo directamente: eso garantiza una copia sin corrupción aunque la base
    este siendo escrita en ese momento. Ademas escribe primero con un
    nombre temporal y al final renombra, para que la carpeta sincronizada
    nunca vea un archivo a medio escribir.
    """
    carpeta_destino = Path(carpeta_destino)
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    ruta_final = carpeta_destino / NOMBRE_SNAPSHOT
    ruta_temporal = carpeta_destino / f".{NOMBRE_SNAPSHOT}.tmp"

    # Si una publicacion anterior se interrumpio (corte de luz, cierre
    # abrupto) puede haber quedado un .tmp corrupto. Sin este borrado,
    # con.backup() fallaria contra un destino invalido y todas las
    # publicaciones futuras se romperian en silencio.
    ruta_temporal.unlink(missing_ok=True)

    destino = sqlite3.connect(ruta_temporal)
    try:
        con.backup(destino)
    finally:
        destino.close()
    ruta_temporal.replace(ruta_final)  # renombrado atomico

    ahora = datetime.now()
    (carpeta_destino / NOMBRE_METADATA).write_text(
        ahora.isoformat(), encoding="utf-8")
    return ahora


def ultima_publicacion(carpeta: Path) -> datetime | None:
    ruta = Path(carpeta) / NOMBRE_METADATA
    if not ruta.exists():
        return None
    try:
        return datetime.fromisoformat(ruta.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


class ErrorSincronizacion(Exception):
    """La carpeta compartida no esta lista o no se pudo leer todavia."""


def sincronizar(carpeta_origen: Path, ruta_cache: Path = RUTA_CACHE_VISOR
               ) -> tuple[Path, datetime]:
    """Copia el snapshot de la carpeta compartida a una cache local y la
    abre. Copiar antes de abrir evita problemas si OneDrive todavia esta
    bajando el archivo o lo tiene como "solo en la nube".
    """
    carpeta_origen = Path(carpeta_origen)
    origen = carpeta_origen / NOMBRE_SNAPSHOT
    if not origen.exists():
        raise ErrorSincronizacion(
            f"Todavia no hay nada publicado en {carpeta_origen}.\n\n"
            "Verifica que la carpeta sea la correcta y que la computadora "
            "que escanea ya haya publicado al menos una vez.")

    ruta_cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(origen, ruta_cache)
    except OSError as err:
        raise ErrorSincronizacion(
            f"No pude leer el archivo compartido ({err}). Si OneDrive lo "
            "muestra con una nube (no descargado), ábrelo una vez desde el "
            "explorador de archivos para forzar la descarga.") from err

    momento = ultima_publicacion(carpeta_origen)
    return ruta_cache, (momento or datetime.now())


def conectar_solo_lectura(ruta_cache: Path) -> sqlite3.Connection:
    con = sqlite3.connect(ruta_cache)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")  # cinturon de seguridad extra
    return con
