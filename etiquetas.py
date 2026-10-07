"""
Generador de etiquetas con codigo de barras.

Crea un archivo HTML de una sola pieza (las imagenes van incrustadas) que se
abre en el navegador y se manda a imprimir con Ctrl+P. La cuadricula esta
pensada para hojas de etiquetas de 3 x 10 (tipo Avery 5160, 2.625 x 1 pulgada),
pero tambien se puede imprimir en papel bond normal y recortar.

Se usa Code 128 porque acepta letras y numeros y es lo que lee sin problema el
lector laser 1D del COM-595.

Ejemplos de uso:
    python etiquetas.py --todos
    python etiquetas.py --personas
    python etiquetas.py --codigos HER-0001 HER-0002 MAT-0015
    python etiquetas.py --filtro taladro --salida etiquetas/taladros.html
"""

from __future__ import annotations

import argparse
import base64
import html
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path

import barcode
from barcode.writer import ImageWriter

import db
import inventario

DIR_SALIDA = db.RAIZ / "etiquetas"

# Valores para las medidas de las etiquetas

COLUMNAS = 4
ANCHO_ETIQUETA = "1.75in"  # Reducido de 2.625in
ALTO_ETIQUETA = "0.5in"    # Reducido de 1in

OPCIONES_BARRAS = {
    "module_width": 0.18,   # Grosor de la barra más delgada (bajamos de 0.26 a 0.18 mm)
    "module_height": 6.0,   # Altura de las barras (bajamos de 11.0 a 6.0 mm)
    "quiet_zone": 2.0,      # IMPORTANTE: No reduzcas esto. El escáner necesita este margen blanco.
    "write_text": False,
}

def imagen_base64(codigo: str) -> str:
    """Devuelve el codigo de barras Code 128 como PNG embebido en un data URI."""
    memoria = BytesIO()
    barcode.get("code128", codigo, writer=ImageWriter()).write(
        memoria, options=OPCIONES_BARRAS
    )
    return "data:image/png;base64," + base64.b64encode(memoria.getvalue()).decode()


PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{titulo}</title>
<style>
  @page {{ size: letter; margin: 0.5in 0.19in; }}
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; }}
  .aviso {{ padding: 10px 16px; background: #fff3cd; border-bottom: 1px solid #e0d5a8;
           font-size: 13px; color: #6b5a12; }}
           
  /* Cuadrícula con espaciado físico entre etiquetas */
  .hoja {{ display: grid; grid-template-columns: repeat({columnas}, {ancho});
           justify-content: center; gap: 6mm 4mm; }}
           
  .etiqueta {{ width: {ancho}; height: {alto}; box-sizing: border-box;
               padding: 1mm; display: flex; flex-direction: column;
               align-items: center; justify-content: center; overflow: hidden;
               page-break-inside: avoid; border: 1px dashed #cccccc; }}
               

  .etiqueta img {{ max-width: 100%; max-height: 80%; object-fit: contain; display: block; }}

  .codigo {{ font-family: "Courier New", monospace; font-size: 8pt;
             font-weight: bold; letter-spacing: 1px; margin-top: 2px; line-height: 1; }}
             
  .nombre, .extra {{ display: none; }}
  
  @media print {{ 
      .aviso {{ display: none; }} 
      .etiqueta {{ border: none; }} 
  }}
</style>
</head>
<body>
<div class="aviso">
  {total} etiqueta(s) &middot; generadas el {fecha} &middot;
  Imprime con Ctrl+P, escala 100% (sin "ajustar a la pagina") y sin margenes extra.
  Haz una prueba en papel normal antes de gastar etiquetas.
</div>
<div class="hoja">
{etiquetas}
</div>
</body>
</html>
"""

ETIQUETA = """  <div class="etiqueta">
    <img src="{img}" alt="{codigo}">
    <div class="codigo">{codigo}</div>
    <div class="nombre">{nombre}</div>
    <div class="extra">{extra}</div>
  </div>"""


def generar_hoja(elementos: list[dict], salida: Path, titulo: str = "Etiquetas") -> Path:
    """elementos: lista de dicts con las llaves codigo, nombre y extra."""
    if not elementos:
        raise ValueError("No hay nada que imprimir con ese filtro.")

    bloques = []
    for elem in elementos:
        if elem.get("seccion"):
            # Separador de ancho completo. Solo para imprimir en papel normal:
            # en hojas de etiquetas precortadas desalinea la cuadricula.
            bloques.append(
                f'  <div class="seccion">{html.escape(elem["seccion"])}</div>')
            continue
        bloques.append(
            ETIQUETA.format(
                img=imagen_base64(elem["codigo"]),
                codigo=html.escape(elem["codigo"]),
                nombre=html.escape(elem.get("nombre", ""))[:40],
                extra=html.escape(elem.get("extra", "")),
            )
        )

    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        PLANTILLA.format(
            titulo=html.escape(titulo),
            columnas=COLUMNAS,
            ancho=ANCHO_ETIQUETA,
            alto=ALTO_ETIQUETA,
            total=sum(1 for e in elementos if not e.get("seccion")),
            fecha=datetime.now().strftime("%d/%m/%Y %H:%M"),
            etiquetas="\n".join(bloques),
        ),
        encoding="utf-8",
    )
    return salida


def _de_articulos(filas) -> list[dict]:
    return [
        {
            "codigo": f["codigo"],
            "nombre": f["nombre"],
            "extra": " | ".join(x for x in (f["categoria"], f["ubicacion"]) if x),
        }
        for f in filas
    ]


def elementos_articulos(con, filtro: str = "") -> list[dict]:
    return _de_articulos(inventario.listar_articulos(con, filtro))


def elementos_personas(con) -> list[dict]:
    return [
        {"codigo": f["codigo"], "nombre": f["nombre"],
         "extra": "gafete de operador"}
        for f in inventario.listar_personas(con)
    ]


def elementos_por_codigo(con, codigos, avisar=print) -> list[dict]:
    elementos = []
    for codigo in codigos:
        codigo = codigo.strip().upper()
        art = inventario.buscar_articulo(con, codigo)
        if art:
            elementos += _de_articulos([art])
            continue
        per = inventario.buscar_persona(con, codigo)
        if per:
            elementos.append({"codigo": per["codigo"], "nombre": per["nombre"],
                              "extra": "gafete de operador"})
        elif avisar:
            avisar(f"  aviso: {codigo} no esta en la base, se omite")
    return elementos


def hoja_completa(con, con_titulos: bool = False) -> list[dict]:
    """Articulos y gafetes juntos, en un solo listado para una sola impresion."""
    articulos = elementos_articulos(con)
    personas = elementos_personas(con)

    elementos: list[dict] = []
    if articulos:
        if con_titulos:
            elementos.append({"seccion": "HERRAMIENTA Y MATERIAL"})
        elementos += articulos
    if personas:
        if con_titulos:
            elementos.append({"seccion": "GAFETES DE OPERADOR"})
        elementos += personas
    return elementos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera etiquetas imprimibles en un solo archivo HTML")
    parser.add_argument("--completo", action="store_true",
                        help="TODO en una sola hoja: articulos + gafetes")
    parser.add_argument("--todos", action="store_true",
                        help="etiquetas de todos los articulos")
    parser.add_argument("--personas", action="store_true",
                        help="gafetes de los operadores")
    parser.add_argument("--codigos", nargs="+", metavar="COD",
                        help="solo estos codigos (articulos o gafetes)")
    parser.add_argument("--filtro", metavar="TEXTO",
                        help="articulos cuyo codigo, nombre, categoria o "
                             "ubicacion contengan el texto")
    parser.add_argument("--con-titulos", action="store_true",
                        help="agrega separadores de seccion (solo para papel "
                             "normal, desalinea las hojas precortadas)")
    parser.add_argument("--salida", type=Path, help="ruta del HTML de salida")
    parser.add_argument("--no-abrir", action="store_true",
                        help="no abrir el navegador al terminar")
    args = parser.parse_args()

    # Sin argumentos se asume la opcion mas util: imprimirlo todo junto.
    if not any((args.completo, args.todos, args.personas, args.codigos,
                args.filtro)):
        args.completo = True

    con = db.conectar()
    elementos: list[dict] = []
    partes: list[str] = []

    if args.completo:
        elementos += hoja_completa(con, args.con_titulos)
        partes.append("completo")
    else:
        if args.todos or args.filtro:
            nuevos = elementos_articulos(con, args.filtro or "")
            if nuevos and args.con_titulos:
                elementos.append({"seccion": "HERRAMIENTA Y MATERIAL"})
            elementos += nuevos
            partes.append("articulos")
        if args.personas:
            nuevos = elementos_personas(con)
            if nuevos and args.con_titulos:
                elementos.append({"seccion": "GAFETES DE OPERADOR"})
            elementos += nuevos
            partes.append("gafetes")
        if args.codigos:
            elementos += elementos_por_codigo(con, args.codigos)
            partes.append("seleccion")

    # Si un codigo aparece dos veces (por ejemplo --todos --codigos HER-0001)
    # se imprime una sola vez.
    vistos, unicos = set(), []
    for elem in elementos:
        clave = elem.get("codigo")
        if clave and clave in vistos:
            continue
        if clave:
            vistos.add(clave)
        unicos.append(elem)

    if not any(e.get("codigo") for e in unicos):
        print("No hay nada que imprimir con esas opciones.")
        return

    marca = datetime.now().strftime("%Y%m%d_%H%M")
    salida = args.salida or DIR_SALIDA / f"{marca}_{'_'.join(partes)}.html"
    ruta = generar_hoja(unicos, salida, titulo="Etiquetas de bodega")

    print(f"Listo: {len(vistos)} etiqueta(s) en un solo archivo -> {ruta}")
    if not args.no_abrir:
        webbrowser.open(ruta.resolve().as_uri())


if __name__ == "__main__":
    main()
