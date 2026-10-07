"""
Administracion del inventario desde la linea de comandos.

    python admin.py nuevo                  alta guiada de un articulo
    python admin.py persona "Juan Perez"   da de alta un operador
    python admin.py importar articulos.csv carga masiva desde CSV
    python admin.py lista [texto]          muestra el inventario
    python admin.py pendientes [--dias 3]  lo que esta fuera de la bodega
    python admin.py bajo-stock             consumibles por resurtir
    python admin.py ajustar MAT-0001 12    corrige una existencia
    python admin.py exportar [carpeta]     saca todo a CSV
    python admin.py compartir [carpeta]    publica una foto de solo lectura
    python admin.py demo                   carga datos de ejemplo para probar
"""

from __future__ import annotations

import argparse
from pathlib import Path

import db
import inventario
import snapshot
from inventario import fmt


def cmd_nuevo(con, args) -> None:
    print("Alta de articulo (Enter deja el valor entre corchetes)\n")
    nombre = input("Nombre: ").strip()
    if not nombre:
        print("Sin nombre no hay alta.")
        return

    tipo = (input("Tipo  UNICO (herramienta) / CONSUMIBLE (material) [UNICO]: ")
            .strip().upper() or "UNICO")
    categoria = input("Categoria []: ").strip()
    ubicacion = input("Ubicacion (estante, rack) []: ").strip()

    if tipo == "CONSUMIBLE":
        unidad = input("Unidad [pza]: ").strip() or "pza"
        existencia = float(input("Existencia actual [0]: ").strip() or 0)
        minimo = float(input("Minimo para alertar [0]: ").strip() or 0)
    else:
        unidad, existencia, minimo = "pza", 1, 0

    codigo = inventario.agregar_articulo(
        con, nombre=nombre, tipo=tipo, categoria=categoria, ubicacion=ubicacion,
        unidad=unidad, existencia=existencia, minimo=minimo,
    )
    print(f"\nListo. Codigo asignado: {codigo}")
    print(f"Imprime su etiqueta con:  python etiquetas.py --codigos {codigo}")


def cmd_persona(con, args) -> None:
    codigo = inventario.agregar_persona(con, args.nombre)
    print(f"Operador dado de alta: {codigo}  {args.nombre}")
    print(f"Imprime su gafete con:  python etiquetas.py --codigos {codigo}")


def cmd_importar(con, args) -> None:
    altas, errores = inventario.importar_csv(con, args.archivo)
    print(f"{altas} articulo(s) cargados.")
    for err in errores:
        print("  ERROR", err)
    if altas:
        print("Imprime todas las etiquetas con:  python etiquetas.py --todos")


def cmd_lista(con, args) -> None:
    filas = inventario.listar_articulos(con, args.texto or "")
    if not filas:
        print("Sin resultados.")
        return
    print(f"{'CODIGO':<11} {'NOMBRE':<34} {'TIPO':<11} {'EXIST':>7}  "
          f"{'ESTADO':<10} UBICACION")
    print("-" * 96)
    for f in filas:
        print(f"{f['codigo']:<11} {f['nombre'][:34]:<34} {f['tipo']:<11} "
              f"{fmt(f['existencia']):>7}  {f['estado']:<10} {f['ubicacion']}")
    print(f"\n{len(filas)} articulo(s).")


def cmd_pendientes(con, args) -> None:
    filas = inventario.pendientes(con, args.dias)
    if not filas:
        print("No hay nada fuera de la bodega.")
        return
    print(f"{'CODIGO':<11} {'ARTICULO':<32} {'QUIEN':<22} {'DESDE':<20} DIAS")
    print("-" * 95)
    for f in filas:
        print(f"{f['codigo']:<11} {f['nombre'][:32]:<32} {f['quien'][:22]:<22} "
              f"{str(f['desde'] or ''):<20} {f['dias'] or 0}")


def cmd_bajo_stock(con, args) -> None:
    filas = inventario.bajo_stock(con)
    if not filas:
        print("Ningun consumible esta por debajo de su minimo.")
        return
    for f in filas:
        print(f"{f['codigo']:<11} {f['nombre'][:34]:<34} "
              f"quedan {fmt(f['existencia'])} {f['unidad']} "
              f"(minimo {fmt(f['minimo'])})")


def cmd_valor(con, args) -> None:
    total = inventario.valor_inventario(con)
    print(f"Articulos activos:  {total['articulos']}")
    print(f"En bodega:          {inventario.fmt_dinero(total['en_bodega'])}")
    print(f"Fuera (prestado):   {inventario.fmt_dinero(total['fuera'])}")
    print(f"Valor total:        {inventario.fmt_dinero(total['total_bodega'])}")
    print()
    print(f"{'CATEGORIA':<28} {'ARTICULOS':>10}   VALOR")
    print("-" * 60)
    for fila in inventario.valor_por_categoria(con):
        print(f"{fila['categoria'][:28]:<28} {fila['articulos']:>10}   "
              f"{inventario.fmt_dinero(fila['valor'])}")


def cmd_ajustar(con, args) -> None:
    res = inventario.ajustar_existencia(con, args.codigo, args.cantidad,
                                        args.nota)
    print(res.titulo, "-", res.detalle)


def cmd_exportar(con, args) -> None:
    rutas = inventario.exportar_csv(con, args.carpeta)
    for ruta in rutas:
        print("generado:", ruta)


def cmd_compartir(con, args) -> None:
    if args.carpeta:
        snapshot.guardar_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN,
                                             args.carpeta)
        print(f"Carpeta configurada: {args.carpeta}")

    carpeta = snapshot.leer_carpeta_configurada(snapshot.RUTA_CONFIG_ORIGEN)
    if carpeta is None:
        print("No hay ninguna carpeta compartida configurada todavia.")
        print("Usa:  python admin.py compartir /ruta/a/tu/OneDrive/Bodega")
        return

    momento = snapshot.publicar(con, carpeta)
    print(f"Publicado en: {carpeta}")
    print(f"Hora: {momento:%d/%m/%Y %H:%M:%S}")


def cmd_demo(con, args) -> None:
    if con.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]:
        print("La base ya tiene articulos; no se cargan datos de ejemplo.")
        return

    for nombre in ("Juan Perez", "Maria Lopez", "Bodega (general)"):
        inventario.agregar_persona(con, nombre)

    herramientas = [
        ("Taladro DeWalt 1/2", "Electricas", "Rack A-1"),
        ("Rotomartillo Bosch", "Electricas", "Rack A-1"),
        ("Esmeriladora 4 1/2", "Electricas", "Rack A-2"),
        ("Juego de llaves mixtas", "Manuales", "Gaveta 3"),
        ("Multimetro Fluke 117", "Medicion", "Gaveta 1"),
        ("Escalera tijera 6 escalones", "Acceso", "Pared norte"),
    ]
    for nombre, cat, ubi in herramientas:
        inventario.agregar_articulo(con, nombre, "UNICO", cat, ubi)

    consumibles = [
        ("Cable THW cal. 12 negro", "Electrico", "Rack C-1", "m", 320, 50),
        ("Taquete expansion 1/4", "Fijacion", "Gaveta 5", "pza", 480, 100),
        ("Cinta de aislar 3M", "Electrico", "Gaveta 5", "pza", 24, 6),
        ("Broca concreto 3/8", "Consumible", "Gaveta 2", "pza", 8, 4),
        ("Disco de corte 4 1/2", "Consumible", "Gaveta 2", "pza", 15, 5),
    ]
    for nombre, cat, ubi, unidad, exist, minimo in consumibles:
        inventario.agregar_articulo(con, nombre, "CONSUMIBLE", cat, ubi,
                                    unidad=unidad, existencia=exist,
                                    minimo=minimo)

    print("Datos de ejemplo cargados. Prueba con:")
    print("  python admin.py lista")
    print("  python etiquetas.py --todos")
    print("  python app.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Administracion del inventario de bodega")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("nuevo", help="alta guiada de un articulo").set_defaults(
        func=cmd_nuevo)

    p = sub.add_parser("persona", help="da de alta un operador")
    p.add_argument("nombre")
    p.set_defaults(func=cmd_persona)

    p = sub.add_parser("importar", help="carga articulos desde un CSV")
    p.add_argument("archivo", type=Path)
    p.set_defaults(func=cmd_importar)

    p = sub.add_parser("lista", help="muestra el inventario")
    p.add_argument("texto", nargs="?", default="")
    p.set_defaults(func=cmd_lista)

    p = sub.add_parser("pendientes", help="articulos fuera de la bodega")
    p.add_argument("--dias", type=int, default=0)
    p.set_defaults(func=cmd_pendientes)

    sub.add_parser("bajo-stock", help="consumibles por resurtir").set_defaults(
        func=cmd_bajo_stock)

    sub.add_parser("valor", help="valor total del inventario, por categoria"
                   ).set_defaults(func=cmd_valor)

    p = sub.add_parser("compartir", help="publica una foto de solo lectura "
                       "en una carpeta compartida (ej. OneDrive)")
    p.add_argument("carpeta", nargs="?", type=Path,
                   help="carpeta a configurar; si se omite, solo publica "
                        "de nuevo en la ya configurada")
    p.set_defaults(func=cmd_compartir)

    p = sub.add_parser("ajustar", help="corrige la existencia de un articulo")
    p.add_argument("codigo")
    p.add_argument("cantidad", type=float)
    p.add_argument("--nota", default="")
    p.set_defaults(func=cmd_ajustar)

    p = sub.add_parser("exportar", help="exporta todo a CSV")
    p.add_argument("carpeta", nargs="?", type=Path,
                   default=db.RAIZ / "exportado")
    p.set_defaults(func=cmd_exportar)

    sub.add_parser("demo", help="carga datos de ejemplo").set_defaults(
        func=cmd_demo)

    args = parser.parse_args()
    con = db.conectar()
    args.func(con, args)


if __name__ == "__main__":
    main()
