# Cómo sacar la pieza de cada programa

Viruta trabaja con un **STEP** (o IGES) de la pieza: sirve cualquier programa que lo exporte. Si Claude tiene un conector con el programa, exporta solo; si no, la persona exporta y adjunta el archivo (o lo deja en una carpeta conectada).

Regla general para el archivo:
- **Sólidos**, no superficies sueltas ni mallas (STL/OBJ no sirven: no tienen caras planas reales).
- Un cuerpo por pieza. Puede venir todo junto (un ensamble o varios cuerpos en un archivo): Viruta separa las piezas, usa sus nombres y junta las iguales.
- Unidades en **mm** (Viruta lee las unidades del STEP; si las medidas dan raras, revisar la exportación).
- La pieza puede estar en cualquier posición o girada: Viruta la acuesta sola. Si dos caras grandes son candidatas a "arriba", se puede forzar con `--cara-arriba`.

## SolidWorks (cualquier versión, también la de estudiante)

**Con conector** (servidor MCP de SolidWorks; herramientas que terminan en `solidworks_save_document`, `solidworks_list_documents`, `solidworks_open_document`):
1. `solidworks_list_documents` → ver qué pieza o ensamble está abierto (o `solidworks_open_document` con la ruta).
2. `solidworks_save_document` con una ruta terminada en **`.STEP`** → exporta sin cerrar ni cambiar el documento. Guardalo en una carpeta conectada (por ejemplo `Escritorio\Viruta_STEP\PIEZA.STEP`).
3. Traer el archivo (`device_stage_files`) y seguir con el flujo universal.
- Para ensambles: exportar el ensamble entero; Viruta toma cada componente con su nombre y cuenta las copias.
- Las herramientas del conector que crean piezas o croquis nuevos pueden fallar en SolidWorks en español (busca la plantilla y los planos en inglés). Para Viruta no hacen falta: solo se usa exportar.

**A mano**: Archivo → Guardar como → Tipo: **STEP AP214 (*.step)** → Guardar. En ensambles, Opciones → "Exportar como un único archivo".

Instalar el conector (una vez, en Windows con la app de escritorio de Claude): servidor `Solidworks-MCP-Server` (HarrierPigeon) con Python y `uv`; se agrega en `claude_desktop_config.json` como `"solidworks"`. Si se instala con `mcp` 2.x y no arranca, fijar `mcp>=1.2,<2`.

## Fusion (Autodesk Fusion / Fusion 360)

**Con conector** (conector oficial **Autodesk Fusion** de Claude; necesita Fusion abierto, *Preferencias → General → API → Fusion MCP Server* activado y la app de escritorio de Claude): pedirle que exporte el diseño activo a STEP con la API (`design.exportManager.createSTEPExportOptions(ruta)` y `exportManager.execute(...)`), en una carpeta conectada. Si el conector no puede escribir archivos, exportar a mano.

**A mano**: Archivo → **Exportar** → Tipo: **Archivos STEP (*.stp)** → Exportar. (O en el navegador del diseño: clic derecho sobre un cuerpo o componente → *Guardar como STEP*.)

También se puede seguir usando el CAM de Fusion (FABRICACIÓN): ver `fusion-pasos.md`.

## Rhino 8

Dos caminos:
- **Directo en Rhino** con `rhino_gcode.py` (conector Rhino-MCP-Platform): ver la sección de Rhino en SKILL.md.
- **Universal**: exportar a STEP y usar `viruta_step.py`. Con el conector: `run_command` con
  `_SelNone _-SelName NOMBRE _Enter _-Export "C:\ruta\NOMBRE.stp" _Enter _Enter`
  (usar siempre los comandos con guion `_-SelName`, `_-Export`: sin guion abren cuadros de diálogo y el conector se queda esperando). A mano: seleccionar → Archivo → *Exportar selección* → STEP.
- El nombre del objeto en Rhino (Propiedades → Nombre) viaja en el STEP y es el nombre del archivo de código G.

## Inventor

Archivo → Exportar → **Formato CAD** → Tipo: STEP (*.stp). En ensambles exporta cada componente con su nombre.

## Onshape

Clic derecho en el Part Studio (o en una pieza) → **Exportar** → Formato **STEP** → Descargar. Para varias piezas: exportar el Part Studio entero ("Exportar como un archivo").

## FreeCAD

Seleccionar los cuerpos en el árbol → Archivo → **Exportar** → *STEP with colors (*.step *.stp)*.

## Solid Edge, CATIA, Creo, NX, SketchUp Pro, otros

Buscar *Guardar como* / *Exportar* → **STEP** (AP203 o AP214) o **IGES**. Si el programa solo exporta mallas (STL, OBJ) o 2D (DXF), Viruta todavía no puede usarlo: hay que pasar la pieza a un programa que exporte sólidos.

## Si no hay acceso a la computadora

La persona adjunta el STEP en el chat. Claude genera los `.txt`, los verifica y los entrega como archivos para descargar.
