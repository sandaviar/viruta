# Reglas del router CNC de UNAHUR — Taller 5

Resumen de las indicaciones de los videos y el PDF de la cátedra (hechos en SolidWorks 2020 CAM), y su equivalente en Fusion 360.

## Máquina y control

- Control: **Mach3** → postprocesador "MILL\MACH_III" en SolidWorks, `mach3mill.cps` ("Mach3Mill") en Fusion.
- Controlador: **DDCS V4.1** (pantalla con FRO/SRO). Lee sin problemas el código del post Mach3 (probado con el asiento: corrió hasta M30).
- Husillo: **S18000** (18000 rpm), sentido horario (**M3**).
- Avance: **2000 mm/min**. El DDCS muestra F 2000 y corre a esa velocidad aunque el código pida otra (el asiento de Fusion con F1200 tardó 3 min 22 s en el aire, que corresponde a 2000 mm/min). Dejar FRO en 100 %.
- Una herramienta por archivo: si una pieza necesita dos fresas, son dos archivos.

## Sistema de coordenadas

- Origen (0,0,0) en la **esquina inferior izquierda** de la pieza, sobre la **cara superior** de la placa.
- **Z+ hacia arriba** (todas las profundidades de corte son negativas).
- **X por el lado corto**, **Y por el lado largo** de la pieza. Es obligatorio.
- En SolidWorks, con la regla de la mano derecha, esto obliga a que el origen quede en la esquina correcta; si no se puede, rotar la pieza 90° (Insertar → Operaciones → Mover/Copiar).

## Herramienta del taller

- Fresa plana de **Ø6 mm**, metal duro, **2 filos**, largo de corte 19 mm, largo total 51 mm ("6MM CRB 2FL 19 LOC").
- Paso vertical: **50 % del diámetro → 3 mm por pasada**.
- Avances a poner en el CAM: corte F2000, husillo S18000. (Antes se usó F1200/bajada F400 en Fusion y SolidWorks saca F1645/F411 por defecto; la máquina igual corre a 2000.)
- Tiempo real ≈ largo de corte / 2000 mm/min + bajadas y rápidos.

## Pestañas (tabs)

- Punto de partida del Taller 5: **4 por pieza**, **8 mm de largo**, **3 mm de alto** (desde el fondo).
- Se ajustan según el tamaño y la forma de la pieza, y van en tramos rectos fáciles de cortar y lijar, nunca en muescas, encastres, descargas o curvas cerradas (ver la sección Pestañas de la skill).
- En SolidWorks: Contorno → "Roscado mecanizado" (traducción errónea de *Tab machining* / Mecanizado de pestaña) → Configuraciones. "Mec. chaflán" destildado.
- En Fusion: Contorno 2D → Pestañas → forma rectangular, ancho 8, alto 3.

## Orden de mecanizado

1. Operaciones internas (agujeros, canales, cajeras, ranuras).
2. **Contorno exterior al final** (con pestañas).

## Limpieza del archivo (.txt para el pendrive)

En SolidWorks, según el profe:
1. Borrar todo lo que está **antes de la primera línea `S18000 M03`** (la de husillo encendido).
2. Buscar (Ctrl+B) otras líneas con `S`; borrar las 2 líneas de arriba de cada una (cambios de herramienta).
3. Borrar las 2 últimas líneas.
4. Borrar el archivo **.SET** que genera el postprocesador.

En Fusion, `scripts/limpiar_gcode.py` hace lo equivalente: arranca en `S18000 M3`, saca comentarios entre paréntesis, líneas vacías, `T# M6` y `G28`, y deja el final en `M5` / `M30`.

## Términos de SolidWorks CAM en español (por si la persona los usa)

- **Macho** = contorno exterior (corta por fuera). **Cajera** = cajera cerrada (corta por dentro). **Cajera abierta** = abierta a un borde.
- **Bucle ext./int.** + **Convertir a bucle**.
- **Rough-Finish** = Desbaste-Acabado.
- Ícono 6 = árbol de rasgos; ícono 7 = árbol de operaciones.
- "Generar plan de operaciones" → **Actualizar** (nunca Regenerar).
