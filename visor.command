#!/bin/bash
# Abre el visor de solo lectura (visor.py) en macOS. Se usa con doble clic.
# La primera vez prepara un entorno de Python propio (.venv). El visor no
# necesita pandas ni openpyxl: sin ellos el boton Exportar genera solo el CSV.
#
# Si al guardarlo en Windows queda con fin de linea CRLF deja de funcionar:
# por eso .gitattributes lo fija en LF.

PROGRAMA="visor.py"
REQUISITOS="requirements_visor.txt"
MARCA=".venv/.listo_visor"

cd "$(dirname "$0")" || exit 1

pausa() {
    echo
    read -n 1 -s -r -p "Presiona cualquier tecla para cerrar..."
    echo
}

# Busca un Python 3 con Tkinter 8.6 o mas reciente. Primero el de python.org,
# luego Homebrew y al final el que este en el PATH.
PYTHON=""
for candidato in \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    python3; do
    if command -v "$candidato" >/dev/null 2>&1 && \
       "$candidato" -c 'import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)' \
       >/dev/null 2>&1; then
        PYTHON="$candidato"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "No se encontro un Python 3 con Tkinter 8.6 o mas reciente."
    echo
    echo "Instala Python desde https://www.python.org/downloads/macos/"
    echo
    echo "(El Python que trae Xcode / Command Line Tools tiene un Tk viejo y no"
    echo " sirve. Si usas Homebrew, instala ademas:  brew install python-tk)"
    pausa
    exit 1
fi

if [ ! -f "$MARCA" ]; then
    echo "Primera vez: preparando el entorno..."
    if [ ! -x .venv/bin/python ]; then
        "$PYTHON" -m venv .venv || { echo "No se pudo crear el entorno .venv"; pausa; exit 1; }
    fi
    if ! .venv/bin/pip install -q -r "$REQUISITOS"; then
        echo
        echo "No se pudieron instalar los paquetes de $REQUISITOS."
        echo "Revisa la conexion a internet y vuelve a abrir este archivo."
        pausa
        exit 1
    fi
    touch "$MARCA"
fi

if ! .venv/bin/python "$PROGRAMA"; then
    echo
    echo "El programa se cerro con un error (arriba esta el detalle)."
    pausa
fi
