"""
Convierte un Excel de inventario existente al formato CSV que entiende
`admin.py importar` / el boton "Importar desde CSV" del panel.

Pensado para hojas tipo "control de inventario" con columnas como:
    Código / ID, Descripción, Categoría, Marca, Modelo, Número de Serie,
    Ubicación, Estado, Estatus, Cant. Total, Valor Unitario ($), Observaciones

No necesitas que tu Excel tenga exactamente esas columnas: el script busca
por nombre parecido (sin acentos, mayusculas/minusculas) y avisa si no
encuentra alguna. Lo que sí es obligatorio es una columna con el nombre o
descripción del artículo.

Uso:
    python convertir_excel.py MiInventario.xlsx
    python convertir_excel.py MiInventario.xlsx --hoja "Inventario" --salida datos.csv

Reglas de conversion (ajusta AJUSTES abajo si tu caso es distinto):
  - Si la fila no tiene descripcion, se ignora (suele ser una fila vacia
    o una celda de totales que se coló en el rango de la tabla).
  - El codigo original se conserva tal cual si existe. Si esta vacio o
    duplicado, se deja en blanco y el sistema le asigna uno nuevo (HER-/MAT-)
    al importar.
  - Si Cant. Total es 1 o no viene especificada, se trata como UNICO
    (herramienta individual con su propio codigo).
  - Si es mayor a 1 y parece material (su unidad es de material, como m,
    kg o rollo, o el nombre/categoria tiene una palabra de PALABRAS_MATERIAL)
    se marca CONSUMIBLE (material que se gasta).
  - Si es mayor a 1, la unidad es "pza" (o no viene) y no parece material,
    se marca AGRUPADO (varias herramientas iguales que se prestan y se
    devuelven, con una sola etiqueta). Como es una suposicion, esas filas
    llevan "si" en la columna 'revisar' y se listan al final para que las
    confirmes.
  - Si "Cant. Total" viene vacia se asume 1 y se anota en observaciones
    para que lo confirmes despues.
  - Valores como "N/A", "F/S", "-" en marca/modelo/serie/categoria se
    tratan como vacios.
  - Si las observaciones mencionan "no funciona" (en cualquier variante),
    el articulo se importa dado de baja (activo=0): aparece en el sistema
    y conserva su historial, pero no se puede escanear hasta reactivarlo.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

# Nombres esperados -> lista de alias que se buscan en el Excel (sin acentos,
# en minusculas). Ajusta esta tabla si tu encabezado usa otras palabras.
ALIAS = {
    "codigo": ["codigo", "id", "codigo / id", "clave"],
    "nombre": ["descripcion", "nombre", "articulo", "herramienta",
               "descripcion de la herramienta"],
    "categoria": ["categoria", "tipo de articulo", "rubro"],
    "marca": ["marca"],
    "modelo": ["modelo"],
    "numero_serie": ["numero de serie", "no. de serie", "serie", "n serie"],
    "ubicacion": ["ubicacion", "estante", "almacen"],
    "estado_cond": ["estado", "condicion"],
    "estatus": ["estatus", "status", "disponibilidad"],
    "existencia": ["cant. total", "cantidad", "existencia", "cant total",
                   "cant"],
    "unidad": ["unidad", "unidad de medida", "u.m.", "um", "medida"],
    "valor_unitario": ["valor unitario ($)", "valor unitario", "costo",
                       "precio unitario", "precio"],
    "notas": ["observaciones", "notas", "comentarios"],
}

PLACEHOLDER = {"n/a", "na", "f/s", "fs", "-", "", "s/n", "sin dato"}

# Palabras que delatan MATERIAL (se gasta) en el nombre o la categoria, sin
# acentos y en minusculas. Agrega o quita las que hagan falta. Ojo con las
# muy generales: "cinta" sola tambien atraparia la cinta de medir.
PALABRAS_MATERIAL = [
    "cable", "alambre", "tornillo", "taquete", "pija", "rondana", "tuerca",
    "clavo", "remache", "abrazadera", "cincho", "cinta aislante",
    "cinta de aislar", "cinta teflon", "cinta masking", "pintura", "thinner",
    "solvente", "silicon", "pegamento", "resistol", "lija", "disco de corte",
    "soldadura", "electrodo", "terminal", "grapa", "material", "consumible",
]

# Unidades de material. Con cualquiera de estas, una cantidad > 1 es
# CONSUMIBLE aunque el nombre no lo diga.
UNIDADES_MATERIAL = {
    "m", "mt", "mts", "metro", "metros", "kg", "kgs", "kilo", "kilos", "g",
    "gr", "l", "lt", "lts", "litro", "litros", "rollo", "rollos", "caja",
    "cajas", "paquete", "paquetes", "bolsa", "bolsas", "galon", "galones",
    "cubeta", "cubetas", "saco", "sacos", "bulto", "bultos", "ml", "cm",
}

# Unidades de "pieza": con estas (o sin unidad) puede ser AGRUPADO.
UNIDADES_PIEZA = {"", "pza", "pzas", "pz", "pzs", "pieza", "piezas", "u",
                  "unidad", "unidades"}

_REGEX_MATERIAL = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in PALABRAS_MATERIAL) + r")",
    re.IGNORECASE)

REGEX_NO_FUNCIONA = re.compile(r"no\s+funcion|fuera\s+de\s+servicio|"
                               r"da(ñ|n)ad|inservible", re.IGNORECASE)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().lower()


def _limpio(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip()
    return "" if _normalizar(texto) in PLACEHOLDER else texto


def tipo_por_cantidad(existencia: float, unidad: str, nombre: str,
                      categoria: str = "") -> str:
    """UNICO, AGRUPADO o CONSUMIBLE segun la cantidad, unidad y nombre."""
    if existencia <= 1:
        return "UNICO"
    unidad_n = _normalizar(unidad).rstrip(".")
    if unidad_n in UNIDADES_MATERIAL:
        return "CONSUMIBLE"
    if _REGEX_MATERIAL.search(_normalizar(f"{nombre} {categoria}")):
        return "CONSUMIBLE"
    if unidad_n in UNIDADES_PIEZA:
        return "AGRUPADO"
    return "CONSUMIBLE"  # unidad rara (juego, par...): se trata como material


def _mapear_columnas(columnas_excel: list[str]) -> dict[str, str]:
    """Empareja cada columna del Excel con nuestro nombre interno."""
    normalizadas = {_normalizar(c): c for c in columnas_excel}
    encontradas: dict[str, str] = {}
    for interno, alias in ALIAS.items():
        for candidato in alias:
            if candidato in normalizadas:
                encontradas[interno] = normalizadas[candidato]
                break
    return encontradas


def convertir(ruta_excel: Path, hoja: str | int = 0,
             fila_encabezado: int | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Devuelve (dataframe_listo_para_csv, avisos)."""
    avisos: list[str] = []

    if fila_encabezado is None:
        # Busca automaticamente en las primeras 6 filas cual parece el
        # encabezado real (muchas plantillas traen 1-2 filas de titulo arriba).
        crudo = pd.read_excel(ruta_excel, sheet_name=hoja, header=None,
                              nrows=6)
        mejor_fila, mejor_puntaje = 0, -1
        for i in range(len(crudo)):
            valores = [_normalizar(v) for v in crudo.iloc[i] if pd.notna(v)]
            puntaje = sum(
                1 for interno, alias in ALIAS.items()
                for a in alias if a in valores
            )
            if puntaje > mejor_puntaje:
                mejor_fila, mejor_puntaje = i, puntaje
        fila_encabezado = mejor_fila
        avisos.append(f"Encabezado detectado en la fila {fila_encabezado + 1} "
                      f"de la hoja.")

    df = pd.read_excel(ruta_excel, sheet_name=hoja, header=fila_encabezado)
    df = df.dropna(how="all")
    mapa = _mapear_columnas(list(df.columns))

    if "nombre" not in mapa:
        raise ValueError(
            "No encontre una columna de nombre/descripcion del articulo. "
            f"Columnas disponibles: {list(df.columns)}\n"
            "Usa --hoja o revisa ALIAS['nombre'] en este script.")

    faltantes = [k for k in ("codigo", "categoria", "existencia",
                             "valor_unitario") if k not in mapa]
    if faltantes:
        avisos.append("No se encontraron columnas para: " +
                      ", ".join(faltantes) + " (se dejan vacias / en 0).")

    def val(fila, clave, defecto=""):
        col = mapa.get(clave)
        return fila[col] if col and col in fila else defecto

    filas_salida = []
    vistos: set[str] = set()
    codigos_duplicados = 0
    sin_cantidad = 0
    dados_de_baja = 0
    agrupados: list[str] = []

    for _, fila in df.iterrows():
        nombre = _limpio(val(fila, "nombre"))
        if not nombre:
            continue  # fila vacia o de relleno (p. ej. una celda de totales)

        categoria = _limpio(val(fila, "categoria"))
        ubicacion = _limpio(val(fila, "ubicacion"))
        marca = _limpio(val(fila, "marca"))
        modelo = _limpio(val(fila, "modelo"))
        serie = _limpio(val(fila, "numero_serie"))
        estado_cond = _limpio(val(fila, "estado_cond"))
        obs = _limpio(val(fila, "notas"))

        cantidad_cruda = val(fila, "existencia", None)
        if cantidad_cruda is None or pd.isna(cantidad_cruda) or \
                _normalizar(cantidad_cruda) in PLACEHOLDER:
            existencia = 1
            sin_cantidad += 1
            obs = (obs + " " if obs else "") + "(cantidad no especificada, verificar)"
        else:
            try:
                existencia = float(cantidad_cruda)
            except (TypeError, ValueError):
                existencia = 1
                sin_cantidad += 1
                obs = (obs + " " if obs else "") + "(cantidad no especificada, verificar)"

        unidad = _limpio(val(fila, "unidad")) or "pza"
        tipo = tipo_por_cantidad(existencia, unidad, nombre, categoria)
        revisar = ""
        if tipo == "AGRUPADO":
            revisar = "si"
            agrupados.append(f"{nombre} ({existencia:g} {unidad})")

        valor_crudo = val(fila, "valor_unitario", 0)
        try:
            valor_unitario = float(valor_crudo)
        except (TypeError, ValueError):
            valor_unitario = 0.0

        notas_partes = []
        if estado_cond:
            notas_partes.append(f"Estado: {estado_cond}.")
        if obs:
            notas_partes.append(obs)
        notas = " ".join(notas_partes).strip()

        activo = 1
        if REGEX_NO_FUNCIONA.search(notas) or REGEX_NO_FUNCIONA.search(nombre):
            activo = 0
            dados_de_baja += 1

        codigo = _limpio(val(fila, "codigo")).upper()
        if codigo:
            if codigo in vistos:
                codigos_duplicados += 1
                codigo = ""  # se le asignara uno nuevo al importar
            else:
                vistos.add(codigo)

        filas_salida.append({
            "codigo": codigo,
            "nombre": nombre,
            "tipo": tipo,
            "categoria": categoria,
            "ubicacion": ubicacion,
            "unidad": unidad,
            "existencia": existencia,
            "minimo": 0,
            "marca": marca,
            "modelo": modelo,
            "numero_serie": serie,
            "valor_unitario": valor_unitario,
            "notas": notas,
            "activo": activo,
            "revisar": revisar,
        })

    if sin_cantidad:
        avisos.append(f"{sin_cantidad} articulo(s) sin cantidad especificada: "
                      f"se asumio 1 (revisalos, quedan marcados en notas).")
    if codigos_duplicados:
        avisos.append(f"{codigos_duplicados} codigo(s) repetido(s) en el Excel: "
                      f"se les asignara uno nuevo al importar.")
    if agrupados:
        avisos.append(
            f"{len(agrupados)} articulo(s) se marcaron AGRUPADO (herramienta "
            "con cantidad que se presta y se devuelve) porque tienen mas de 1 "
            "pieza y no parecen material. Confirmalos (columna 'revisar' = "
            "si); si alguno es material, cambia su tipo a CONSUMIBLE:\n      "
            + "\n      ".join(agrupados))
    if dados_de_baja:
        avisos.append(f"{dados_de_baja} articulo(s) se marcan dados de baja "
                      f"(la descripcion u observaciones dicen que no funcionan).")

    return pd.DataFrame(filas_salida), avisos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte un Excel de inventario a CSV importable")
    parser.add_argument("excel", type=Path, help="archivo .xlsx de entrada")
    parser.add_argument("--hoja", default=0,
                        help="nombre o numero de la hoja (por defecto, la "
                             "primera)")
    parser.add_argument("--fila-encabezado", type=int, default=None,
                        help="numero de fila (1 = primera) donde estan los "
                             "titulos de columna, si la deteccion automatica "
                             "falla")
    parser.add_argument("--salida", type=Path, default=None,
                        help="ruta del CSV de salida")
    args = parser.parse_args()

    hoja = args.hoja
    try:
        hoja = int(hoja)
    except (TypeError, ValueError):
        pass

    fila_enc = (args.fila_encabezado - 1) if args.fila_encabezado else None
    df, avisos = convertir(args.excel, hoja=hoja, fila_encabezado=fila_enc)

    salida = args.salida or args.excel.with_suffix(".csv")
    df.to_csv(salida, index=False, encoding="utf-8-sig")

    print(f"Listo: {len(df)} articulo(s) escritos en {salida}\n")
    for aviso in avisos:
        print("  -", aviso)
    print(f"\nRevisa el CSV (especialmente 'tipo' y las filas marcadas para "
          f"verificar) y luego carga con:\n"
          f"  python admin.py importar {salida}")


if __name__ == "__main__":
    main()
