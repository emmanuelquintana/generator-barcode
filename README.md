# Generador de Etiquetas 51×25 mm desde CSV

Este script proporciona una interfaz gráfica para generar etiquetas de producto de 51×25 mm a partir de archivos CSV. Permite ajustar tamaños, márgenes y fuentes, visualizar una vista previa y exportar las etiquetas en PDF, incluyendo código de barras.

## Características

- Vista previa de la etiqueta a escala real.
- Exportación a PDF con equivalencia visual.
- Título y SKU en una sola línea.
- Ajuste de tamaños, márgenes y fuentes mediante controles +/− grandes.
- Detección automática de columnas relevantes en el CSV.
- Generación de códigos de barras (EAN13 o Code128).

## Requisitos

Instala las dependencias con:

```sh
pip install reportlab pandas pillow python-barcode
```

## Uso

1. Ejecuta el script:

    ```sh
    python gui_generate_barcode.py
    ```

2. Selecciona el archivo CSV con los datos de tus productos.
3. Ajusta los parámetros de la etiqueta según tus necesidades.
4. Visualiza la vista previa.
5. Genera el PDF de etiquetas.

## Formato del CSV

El archivo CSV debe contener columnas para nombre, SKU, código de barras y cantidad. El script detecta automáticamente los nombres de columna más comunes, pero puedes especificarlos manualmente si es necesario.

## Autor

Emmanuel

---

Para más detalles revisa el código fuente en [`gui_generate_barcode.py`](gui_generate_barcode.py ).
