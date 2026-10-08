# Inventario de bodega con lector de código de barras

Sistema local (con implementaciones básicas de compartirlo con más computadoras) 
para inventariar herramienta y material, imprimir sus etiquetas y 
registrar entradas y salidas con el lector Steren COM-595 o cualquier otro lector USB.

Todo se guarda en un archivo SQLite (`datos/inventario.db`) que se respalda solo
cada vez que abres el programa.

---

## 1. Instalación

Necesitas Python 3.10 o superior. Al instalarlo en Windows marca la casilla
**"Add Python to PATH"**.

```bash
pip install -r requirements.txt
```

Eso instala `python-barcode` y `Pillow` para las etiquetas, y `pandas` +
`openpyxl` para los reportes en Excel y para convertir un inventario existente
(ver sección 8). El resto usa la librería estándar.

## 2. Configurar el lector (una sola vez)

El COM-595 se comporta como un teclado: no necesita drivers. Antes de usarlo:

1. Conéctalo y dispara sobre cualquier código de barras con el Bloc de notas
   abierto. Deben aparecer los dígitos escritos solos.
2. Si **no** salta de renglón al terminar, busca en el manual del lector el
   código de configuración de *"Enter / CR sufijo"* y escanéalo. Ese Enter es lo
   que hace que la app procese la lectura sin que nadie toque el teclado.

## 3. Primeros pasos

```bash
python admin.py demo   # carga datos de ejemplo para probar (opcional)
python app.py          # ventana de escaneo (el día a día)
python gestion.py      # panel de catálogo: altas, bajas y etiquetas
```

Desde la ventana de escaneo, el botón azul **"Catálogo / dar de alta"** abre el
mismo panel, así que en la práctica basta con dejar `app.py` abierto todo el día.

Para borrar los datos de ejemplo y empezar en limpio, cierra el programa y
elimina el archivo `datos/inventario.db`.

---

## 4. Los archivos

| Archivo | Para qué sirve |
|---|---|
| `app.py` | **Ventana de escaneo**: el uso diario |
| `registromanual.py` | Ventana para registrar entradas y salidas sin lector (se abre desde `app.py`) |
| `gestion.py` | **Panel de catálogo**: altas, edición, bajas e impresión, todo visual |
| `etiquetas.py` | Genera las etiquetas Code 128 en un HTML listo para imprimir |
| `convertir_excel.py` | Convierte un Excel de inventario existente al CSV que se importa |
| `visor.py` | Ventana de solo lectura para consultar desde otra computadora |
| `snapshot.py` | Publica y lee las "fotos" del inventario que usa `visor.py` |
| `inventario.py` | Toda la lógica: altas, escaneos, reportes, exportación |
| `db.py` | Crea la base, define las tablas y hace el respaldo automático |
| `tema.py` | Colores y estilo compartido entre las ventanas |
| `admin.py` | Lo mismo desde la línea de comandos, por si lo prefieres |

---

## 5. El panel de catálogo (altas y bajas)

Se abre con `python gestion.py` o con el botón **"Catálogo / dar de alta"** de la
ventana de escaneo. Tiene dos pestañas:

**Herramienta y material.** A la izquierda la lista con buscador (filtra
mientras escribes, por código, nombre, categoría, ubicación, marca, modelo o
número de serie); a la derecha la ficha del artículo seleccionado. Botón
*Nuevo* para limpiar y dar de alta, y al guardar te ofrece imprimir la
etiqueta en ese momento.

Junto al buscador hay dos filtros que se combinan con él: **Estado**
("En bodega" / "Fuera de la bodega") y **Ubicación**. Filtrar por "Fuera de
la bodega" es, en la práctica, la forma de ver todo lo que anda prestado en
ese momento — junto con su valor total, que se muestra abajo a la derecha de
la lista.

Hay tres tipos de artículo (debajo del selector hay una línea de ayuda que
explica el elegido):

| Tipo | Para qué | Al escanear |
|---|---|---|
| *Herramienta única (1 pieza)* | Una pieza con su propia etiqueta (un taladro, un multímetro) | Alterna entre prestada y en bodega |
| *Herramienta con cantidad (varias iguales, se devuelven)* | Varias piezas iguales con **una sola etiqueta** (5 extensiones, 3 cintas de medir, 2 rotomartillos idénticos) | Aparece un diálogo para **sacar o regresar** cuántas |
| *Material (se gasta)* | Cable, taquetes, discos… | Descuenta (o suma) existencia; no se espera que regrese |

Con *Herramienta única* los campos de cantidad se bloquean solos, porque no
lleva existencia ni mínimo. Con los otros dos se habilitan; en una
herramienta con cantidad el campo se llama *"Disponibles en bodega"*.

**Herramienta con cantidad, en detalle.** El sistema registra quién tiene
cuántas piezas: al escanearla se abre un diálogo pequeño con las piezas
disponibles y quién tiene las demás; se elige *Sacar* o *Regresar* y la
cantidad (y, al regresar, de quién son las piezas, porque cualquiera puede
devolver lo de otro). No deja sacar más de las disponibles ni regresar más de
lo que esa persona tiene. En la lista se ve como `3 disp. / 2 fuera`, aparece
en *Pendientes* y en el filtro "Fuera de la bodega" una línea por persona
(`2 con Emerson…`), y **su valor total no cambia al prestar**: solo pasa de
"Valor en bodega" a "Prestado".

Si cambias el tipo de un artículo que ya tiene movimientos a *Herramienta con
cantidad*, el sistema reconstruye quién tiene piezas a partir del historial
(salidas menos entradas de cada persona), te muestra el resumen y pide
confirmación antes de guardar; la existencia no se toca. Al revés no deja
cambiarlo mientras haya piezas prestadas.

Marca, modelo, número de serie y valor unitario son opcionales: llénalos si
te sirven para identificar el equipo o para saber cuánto vale lo que hay en
bodega. El contador de la lista suma el valor de lo que se está mostrando
($existencia × valor unitario$), y se actualiza con cada filtro.

**Personal.** Igual, pero más corto: nombre y ya. La columna *Fuera* muestra
cuántas herramientas tiene sin devolver cada persona, y si intentas darla de
baja teniendo pendientes, el sistema te los lista antes de confirmar.

### Dar de baja no borra

La baja marca el artículo como inactivo: desaparece de las listas y el escáner
lo rechaza, pero el historial de movimientos se conserva íntegro y puedes
reactivarlo cuando quieras (marca *"Mostrar también los dados de baja"* para
encontrarlo). Esto evita el problema clásico de borrar una herramienta y perder
el registro de quién la tuvo.

## 6. Cómo se organizan los códigos

| Prefijo | Qué es | Comportamiento al escanear |
|---|---|---|
| `HER-0001` | Herramienta **única** o herramienta **con cantidad** | Única: alterna entre salida y entrada. Con cantidad: diálogo para sacar o regresar cuántas |
| `MAT-0001` | Material **consumible** con cantidad | Descuenta o suma existencia |
| `PER-0001` | Gafete de operador | No mueve inventario, solo fija quién está usando el sistema |

Los códigos se asignan solos y de forma consecutiva. También puedes forzar uno
propio si ya tienes etiquetas hechas. Una herramienta con cantidad lleva
**una sola etiqueta** para todo el grupo. Si conviertes un material ya
existente (por ejemplo `MAT-0131`) en herramienta con cantidad, conserva su
código.

## 7. El flujo diario

1. La persona escanea **su gafete**. Arriba a la derecha aparece su nombre.
2. Escanea cada herramienta o material que se lleva. Se registra a su nombre.
3. Al devolver, vuelve a escanear. En modo automático el sistema entiende que
   una herramienta que estaba fuera ahora regresa.
4. `Esc` borra el operador activo para que el siguiente empiece limpio.

Para consumibles, pon la cantidad en la casilla de la derecha **antes** de
escanear. Vuelve sola a 1 después de cada lectura. Las herramientas con
cantidad abren su propio diálogo (Sacar / Regresar, cantidad y de quién);
`Enter` acepta y `Esc` cancela.

### Modos

| Tecla | Modo | Qué hace |
|---|---|---|
| `F1` | Automático | Herramienta: alterna. Consumible: descuenta |
| `F2` | Solo salidas | Todo se registra como salida (útil al surtir una orden grande) |
| `F3` | Solo entradas | Todo se registra como entrada (devoluciones o material que llega) |

### Sin lector: registro manual

Si el escáner no está disponible, el botón **"Registro manual (F4)"** abre una
ventana con la lista de artículos y un buscador. Se elige el operador, se
selecciona el artículo, se pone la cantidad (solo para material) y se presiona
**Registrar SALIDA** o **Registrar ENTRADA**. Se aplican las mismas reglas que
al escanear (no sacar lo que ya está fuera, no sacar más de lo que hay) y el
movimiento queda en el historial con la nota *"registro manual"*.

---

## 8. Cargar un inventario existente (Excel) o una lista en CSV

### Si ya tienes un Excel de control de inventario

`convertir_excel.py` lee un Excel real —con sus columnas en el orden y
nombres que sea, títulos arriba, filas vacías, "N/A" regados por todos
lados— y genera un CSV limpio, listo para importar. No necesitas acomodar
nada a mano primero:

```bash
python convertir_excel.py "Mi Inventario.xlsx" --hoja "Nombre de la hoja"
```

Genera un CSV junto al Excel y te imprime un resumen de lo que hizo, por
ejemplo:

```
Listo: 283 articulo(s) escritos en Mi Inventario.csv

  - Encabezado detectado en la fila 3 de la hoja.
  - 3 articulo(s) sin cantidad especificada: se asumio 1 (revisalos).
  - 1 codigo(s) repetido(s): se les asignara uno nuevo al importar.
  - 7 articulo(s) se marcan dados de baja (dicen que no funcionan).
```

Reglas que aplica automáticamente (ajustables editando `ALIAS` al inicio del
script si tu Excel usa otros nombres de columna):

- **Tipo:** si la cantidad es 1 (o no viene), entra como *herramienta
  única*. Si es mayor a 1 y parece material (unidad como m, kg, rollo, caja,
  o una palabra de `PALABRAS_MATERIAL` en el nombre o categoría: cable,
  taquete, disco, broca…), entra como *material*. Si es mayor a 1 en piezas y
  no parece material, entra como *herramienta con cantidad*; como eso es una
  suposición, esas filas llevan `si` en la columna `revisar` del CSV y se
  listan al final para que las confirmes.
- **Código:** si la fila ya traía uno, se conserva tal cual (así lo que ya
  esté anotado en otros documentos sigue sirviendo). Si está vacío o
  repetido, se deja en blanco y el sistema le asigna uno nuevo al importar.
- **Baja automática:** si la descripción o las observaciones dicen "no
  funciona", "dañado" o similar, el artículo entra ya dado de baja: queda en
  el sistema con su historial pero el escáner lo rechaza hasta que lo
  reactives desde el panel.
- **Vacíos:** celdas con "N/A", "F/S", "-" se tratan como vacías, no como
  texto real.

Revisa el CSV generado (ábrelo en Excel, o con `admin.py lista` después de
importar) y luego cárgalo:

```bash
python admin.py importar "Mi Inventario.csv"
```

Si algo no calzó bien (por ejemplo, todo quedó marcado como "material" cuando
debería ser "herramienta"), corrige el CSV o los artículos ya importados
desde el panel, y vuelve a intentar — importar de nuevo no borra lo que ya
había, solo agrega.

**Lo que el conversor no puede inventar:** si tu Excel no traía un punto de
reorden (mínimo) para los consumibles, nadie va a recibir avisos de "bajo
stock" hasta que lo configures artículo por artículo desde el panel. Tampoco
corrige inconsistencias que ya traía la fuente (un modelo mal capturado, una
cantidad ambigua); el conversor las señala en las notas para que las revises,
pero no las adivina por ti.

### Si prefieres armar el CSV tú mismo

```
nombre,tipo,categoria,ubicacion,unidad,existencia,minimo,marca,modelo,numero_serie,valor_unitario,notas,activo,codigo
```

Solo `nombre` es obligatoria; el resto se puede omitir. `activo` acepta
`0`/`1` (o vacío = activo). Hay un archivo de muestra en
`ejemplo_articulos.csv`.

```bash
python admin.py importar mi_lista.csv
python etiquetas.py --todos
```

## 9. Impresión de etiquetas

Todas las etiquetas salen **en un solo archivo HTML** con las imágenes
incrustadas: se abre en el navegador y se imprime con `Ctrl+P`. La cuadrícula
está armada para hojas de 3 × 10 etiquetas (Avery 5160, 2.625 × 1 pulgada).

Desde el panel de catálogo tienes el botón **"Imprimir TODO en una hoja"**, que
junta artículos y gafetes en un mismo archivo. Te pregunta si quieres
separadores de sección: dile que sí solo si vas a imprimir en papel normal y
recortar, porque en hojas precortadas el título desalinea la cuadrícula.

También están *"Imprimir etiquetas de la lista"* (respeta el filtro de búsqueda,
útil para reimprimir un rack completo) y *"Imprimir esta etiqueta"*.

Desde la terminal, las opciones se pueden combinar y siempre generan un archivo
único:

```bash
python etiquetas.py                                # todo junto: artículos + gafetes
python etiquetas.py --completo --con-titulos       # con separadores de sección
python etiquetas.py --todos --personas             # equivalente a --completo
python etiquetas.py --filtro "rack a" --personas   # un rack + todos los gafetes
python etiquetas.py --codigos HER-0001 MAT-0015    # reimprimir sueltas
```

Si un código aparece en dos opciones a la vez, se imprime una sola vez.

**Importante al imprimir:** escala al 100%, sin *"ajustar a la página"*. Si el
navegador reescala, las barras se deforman y el lector falla. Haz siempre una
prueba en papel normal y escanéala antes de gastar etiquetas.

Si tus etiquetas son de otra medida, cambia `COLUMNAS`, `ANCHO_ETIQUETA` y
`ALTO_ETIQUETA` al inicio de `etiquetas.py`.

## 10. Reportes

```bash
python admin.py pendientes --dias 3   # lo que lleva más de 3 días fuera
python admin.py bajo-stock            # consumibles bajo su mínimo
python admin.py lista taladro         # buscar
python admin.py valor                 # valor total del inventario, por categoría
python admin.py ajustar MAT-0001 250  # corregir tras un conteo físico
python admin.py exportar              # todo a CSV para Excel
```

Los mismos reportes están en los botones de abajo de la ventana de escaneo.

## 11. Respaldos

Cada vez que arranca cualquiera de los programas se copia la base a
`datos/respaldos/` con fecha y hora, y se conservan los últimos 30. Para
restaurar, cierra todo y copia el respaldo que quieras encima de
`datos/inventario.db`.

Aun así, **copia la carpeta `datos/` a una USB o a la nube de vez en cuando**:
un respaldo en el mismo disco no te salva si se muere el disco.

---

## 12. Consultar el inventario desde otra computadora

`visor.py` es un programa aparte de solo lectura: muestra existencias,
el historial de movimientos, quién tiene qué prestado, artículos bajo el
mínimo y el valor del inventario, pero **no puede escanear ni modificar
nada** — ni por error. La conexión se abre en modo `PRAGMA query_only`, así
que aunque alguien editara el código por accidente, SQLite rechaza cualquier
escritura de todas formas.

### Por qué no es "la misma base de datos, nada más compartida"

La forma obvia de resolver esto sería poner el archivo `datos/inventario.db`
en una carpeta de OneDrive y ya. **No lo hagas** — SQLite advierte
explícitamente contra usarse sobre una carpeta sincronizada en la nube o de
red: OneDrive sincroniza archivos completos, no transacciones, así que si dos
computadoras escriben cerca del mismo momento, el resultado es corrupción
silenciosa o una copia "en conflicto" que pisa cambios sin avisar.

Lo que hace este proyecto en cambio: la computadora que escanea (la que
corre `app.py` / `gestion.py`) publica cada pocos minutos —y después de cada
movimiento— una **copia consistente** del inventario en la carpeta que tú
seas elijas (por ejemplo, dentro de tu OneDrive). Esa copia se escribe con
nombre temporal y se renombra al final, así que la carpeta sincronizada
nunca ve un archivo a medio escribir. `visor.py`, en la otra computadora,
solo lee esa copia — nunca el archivo original.

La consecuencia práctica: **lo que ves en `visor.py` puede tener unos
minutos de retraso** respecto a lo que acaba de pasar en la bodega. La
ventana te dice siempre cuándo se generó ese dato ("hace 3 min", en rojo si
ya pasaron más de 30). Si necesitas que dos computadoras escaneen a la vez
en tiempo real, eso es un problema distinto — ver la sección "Si más
adelante crece" al final.

### Configurar la computadora que escanea

Desde el panel de catálogo (`gestion.py`), botón **"Compartir (solo
lectura)"**: elige o crea una carpeta — lo más simple es una carpeta dentro
de tu OneDrive/Google Drive/Dropbox ya sincronizada — y a partir de ahí se
publica sola. También puedes hacerlo por comandos:

```bash
python admin.py compartir "C:\Users\TuNombre\OneDrive\Bodega"
python admin.py compartir   # vuelve a publicar en la carpeta ya configurada
```

### Configurar la(s) computadora(s) que solo consultan


1. Python instalado (con Tkinter; en Windows/Mac ya viene incluido).
2. Copiar estos 5 archivos: `visor.py`, `inventario.py`, `snapshot.py`,
   `db.py`, `tema.py`.
3. Tener sincronizada la **misma carpeta** que configuraste en el paso
   anterior (por ejemplo, iniciar sesión con la misma cuenta de OneDrive, o
   una carpeta compartida contigo).
4. Haber instalado requirements.txt como se mencionó anteriormente-  

```bash
python visor.py
```

La primera vez te pide elegir esa carpeta; después la recuerda. Tiene un
botón "Actualizar ahora" y se refresca solo cada minuto.

Si la computadora que escanea todavía tiene una versión anterior del
programa, la foto que publica no trae la tabla `prestamos` (herramientas con
cantidad). El visor la abre igual, sin errores, y avisa discretamente en la
barra de arriba ("foto de una versión anterior").

La pestaña **"Movimientos"** muestra los últimos movimientos en orden, con
fecha, cantidad exacta y quién los hizo, y se puede filtrar por código,
artículo u operador. Sirve sobre todo para los materiales que se retiran en
cantidades chicas (unos metros de cable, unos tornillos): la existencia
apenas cambia y no se nota a simple vista en la lista de inventario, pero
cada retiro individual sí queda registrado ahí.

El visor también tiene su propio botón **"Exportar"**, igual que la ventana
de escaneo: genera los CSV y el reporte en Excel de lo que esté viendo en
ese momento. El CSV siempre funciona porque no necesita nada especial; el
Excel sí necesita `pandas` y `openpyxl` instalados en esa computadora
(ver `requirements_visor.txt`) — si no los tiene, el CSV se genera igual y
el Excel se salta con un aviso, sin errores feos.

---

## Detalles que ahorran problemas

- **Doble lectura:** el gatillo a veces dispara dos veces. La app ignora el
  mismo código si llega dos veces en menos de 1.2 segundos. Con el diálogo
  de una herramienta con cantidad abierto, si se escanea otro código su
  `Enter` tampoco acepta el diálogo: solo un `Enter` tecleado a mano.
- **Modo claro / oscuro:** el botón *"Modo claro"* / *"Modo oscuro"* de la
  ventana de escaneo y del visor cambia los colores al instante. La
  preferencia se guarda en `datos/tema.txt` y todas las ventanas abren con
  ella la próxima vez.
- **Etiquetas:** protégelas con cinta transparente o lamínalas. En bodega, el
  papel sin proteger dura semanas.
- **Siempre imprime el código en texto** debajo de las barras (ya viene así):
  si la etiqueta se maltrata, se puede teclear a mano.
- **El campo de escaneo recupera el foco solo**, incluso si alguien hace clic en
  otro lado de la ventana.
