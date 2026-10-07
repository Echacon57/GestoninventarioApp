from PIL import Image, ImageDraw

ruta_imagen = r"C:\Users\-ARQUITECTURA\OneDrive\Desktop\SISTEMAS\inventario_bodega\Logo1.jpg"
ruta_salida = r"C:\Users\-ARQUITECTURA\OneDrive\Desktop\SISTEMAS\inventario_bodega\Inventario_Limpio.ico"

img = Image.open(ruta_imagen).convert("RGBA")

# 1. Convertir a escala de grises para analizar la luz
gray = img.convert("L")

# 2. Umbral muy estricto: el azul oscuro tiene un valor de luz muy bajo.
# Todo lo más claro que 100 (incluyendo el fondo gris claro y blanco) se ignora por completo.
mask = gray.point(lambda p: 255 if p < 100 else 0)

# 3. Obtener la caja delimitadora exacta del círculo azul oscuro
caja = mask.getbbox()

if caja:
    # Recortar al borde exacto del azul
    img = img.crop(caja)
    
    # Forzar a que sea un cuadrado perfecto para evitar deformaciones
    ancho, alto = img.size
    lado = max(ancho, alto)
    img = img.resize((lado, lado), Image.Resampling.LANCZOS)
    
    # 4. Crear una máscara circular perfecta del mismo tamaño
    mascara = Image.new("L", (lado, lado), 0)
    dibujo = ImageDraw.Draw(mascara)
    dibujo.ellipse((0, 0, lado, lado), fill=255)
    
    # 5. Aplicar la transparencia a las esquinas
    img.putalpha(mascara)

# 6. Guardar el icono empaquetado para Windows
img.save(
    ruta_salida,
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
print("Ícono perfecto generado.")