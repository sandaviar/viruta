---
name: viruta
description: Genera código G para router CNC desde cualquier programa de modelado (SolidWorks, Fusion, Rhino, Inventor, Onshape, FreeCAD… vía STEP, o con conector directo) con las profundidades exactas del modelo (cortes pasantes, cajeras, rebajes, islas, taladros, pestañas, descargas, varias fresas), lo verifica por simulación y deja un .txt por pieza; también guía el CAM de Fusion y revisa .txt existentes. Pregunta primero si se corta en el Taller 5 de UNAHUR (DDCS V4.1, Mach3, S18000, F2000, origen abajo-izquierda en la cara superior) u otra máquina, y qué fresa se usa.
---

# Viruta — de cualquier programa a código G para router CNC

Viruta pasa piezas planas (2,5D) a archivos de código G listos para el router. La persona abre su programa (SolidWorks, Fusion, Rhino, Inventor, Onshape, FreeCAD…), pide el código G y recibe un `.txt` por pieza con las características de su máquina y su fresa, ya verificado contra el modelo. Trae cargado el perfil del **Taller 5 de UNAHUR**; para otros talleres se arma el perfil preguntando.

Hablá con la persona en español rioplatense (voseo). Nombres de menús en español.

Repositorio oficial (referencias y scripts): https://github.com/sandaviar/viruta

## Paso 0 — Preguntar SIEMPRE antes de empezar

Con AskUserQuestion si está disponible (todo junto, y sin repetir lo que la persona ya dijo):

**A. ¿Dónde vas a cortar?**
- **UNAHUR – Taller 5** → **Perfil Taller 5** de abajo, tal cual. No inventes ni cambies valores.
- **Otro taller / otra máquina** → **Perfil de otra máquina**: los valores del Taller 5 NO se aplican solos.

**B. ¿Qué fresa (o fresas) vas a usar?** Diámetro (sugerida Ø6), tipo (plana para pasantes y cajeras), largo de corte (LOC > espesor + 0,3). Si hay detalles más chicos que la fresa, ofrecé una segunda fresa más chica (ej. Ø6 + Ø3).

**C. Placa**: material y espesor (ej. MDF 9 mm). El espesor real lo da el modelo; si no coincide con la placa, avisá.

**D. ¿En qué programa está la pieza?** (si no queda claro). Define cómo se saca el STEP (ver **Flujo universal**).

Si corta en el Taller 5 y no sabe la fresa, proponé la del taller: **Ø6 mm plana, metal duro, 2 filos, LOC 19** ("6MM CRB 2FL 19 LOC"). Con la fresa: paso vertical 50 % Ø, descargas de radio Ø/2 + 0,2, ranuras ≥ Ø, encastres en placa *e* → *e* + 0,2 (MDF 9 → 9,2). Ver `references/fresas.md`.

## Perfil Taller 5 — UNAHUR

Detalle y fuentes en `references/reglas-router-unahur.md`.

| Tema | Regla |
|---|---|
| Controlador | **DDCS V4.1** (lee el código del post Mach3; FRO en 100 %) |
| Formato | **Mach3** (`--formato mach3`; en Fusion `mach3mill.cps`; en SolidWorks CAM "MILL\MACH_III") |
| Origen (0,0,0) | **Esquina inferior izquierda, sobre la CARA SUPERIOR** de la placa |
| Ejes | **Z hacia arriba**, **X = lado corto**, **Y = lado largo** de la pieza |
| Husillo | **S18000 M3** |
| Avance | **F2000 mm/min** (el DDCS corre a 2000 aunque el código diga otro valor) |
| Profundidad | Pasante: espesor + 0,3 (MDF 9 → Z-9,3), pasadas del 50 % Ø |
| Pestañas | Punto de partida **4 de 8 × 3 mm**, ajustadas a la pieza (ver **Pestañas**) |
| Orden | **Primero lo interno**, **contorno exterior al final** |
| Archivos | **Uno por pieza y por herramienta**, `.txt` al pendrive |
| Limpieza | Arranca en `S18000 M3`; sin comentarios, sin T# M6, sin G28; termina en M5/M30 |
| Tiempo | ≈ largo de corte / 2000 mm/min + ~10 % (asiento 70×190: 3 min 22 s medido) |

En `viruta_step.py` este perfil es `--perfil taller5` (el de fábrica).

## Perfil de otra máquina

Si NO corta en el Taller 5, preguntá (lo que no sepa, que lo consulte con el responsable de la máquina; no completes con los valores de UNAHUR sin avisar):

1. **Controlador / software** (Mach3, DDCS, GRBL, LinuxCNC, Nc Studio…) → `formato`: `mach3` (Mach3, DDCS, Nc Studio en general), `grbl` (GRBL, Carbide, Shapeoko, OpenBuilds), `linuxcnc`.
2. **Origen**: esquina inferior izquierda o centro de la pieza (`origen`: `esquina`/`centro`); cero de Z arriba de la placa o sobre la mesa (`z0`: `arriba`/`mesa`); qué lado va en X (`x_lado_corto`).
3. **Husillo** (rpm), **avance** de corte y de bajada (mm/min).
4. **Pasada** (% del Ø, `paso_pct`) y **profundidad extra** para pasar la placa (`extra`).
5. **Sujeción**: pestañas (cantidad, largo, alto; `pestanas: 0` si va con tornillos o vacío).
6. **Archivo**: extensión (`.txt`, `.nc`, `.tap`, `.gcode`).

Mostrá una tabla igual a la del Taller 5 para que la confirme y guardala como JSON (ej. `maquina.json`) para usarla con `--perfil ninguno --config maquina.json`:

```json
{"perfil_nombre": "Router de casa (GRBL)", "formato": "grbl", "husillo": 12000, "avance": 1200,
 "avance_bajada": 400, "origen": "esquina", "z0": "arriba", "x_lado_corto": false, "extra": 0.3,
 "paso_pct": 0.5, "extension": ".nc", "pestanas": 4, "pestana_largo": 8,
 "herramientas": [{"diametro": 6, "loc": 22, "nombre": "6mm plana 2 filos"}]}
```

Si falta algún dato, usá un valor conservador (pasada 50 % Ø, 4 pestañas de 8 × 3, origen esquina en la cara superior) **y avisalo**.

## Pestañas: cuántas, de qué medida y dónde

Las pestañas tienen que tener sentido para el objeto. 4 de 8 × 3 mm sirve para piezas chicas o medianas, pero **no es una regla fija**.

| Pieza (lado mayor) | Pestañas |
|---|---|
| < 80 mm | 2 (enfrentadas) |
| 80 – 300 mm | 3 – 4 |
| 300 – 600 mm | 6 |
| > 600 mm | 8 o más (≈ una cada 150 – 250 mm de perímetro) |

- Más si la pieza es angosta y larga, liviana o con voladizos; menos si es chica y compacta.
- **Alto** ≈ 1/3 del espesor (MDF 9 → 3; 5,5 → 2; 18 → 5 – 6). **Largo** 6 – 10 mm (8 en general).
- **Fáciles de retirar**: en tramos rectos y abiertos del contorno exterior. **Nunca** en muescas, encastres, descargas, curvas cerradas, esquinas o bordes que encastran. Enfrentadas y parejas.
- Recortes interiores que son descarte: normalmente sin pestañas.

`viruta_step.py` las pone sola en los tramos rectos más largos (cantidad por la tabla). Si la persona quiere otra cantidad: `--pestanas N`; otra medida: `--pestana-largo`, `--pestana-alto`; en lugares exactos: `--pestanas-en "X,Y;X,Y;…"` (coordenadas del código, se llevan al contorno). Siempre mostrá dónde quedaron antes de dar el archivo por listo.

## Flujo universal (cualquier programa) — `scripts/viruta_step.py`

Es el camino por defecto. Funciona con cualquier programa que exporte **STEP** (o IGES).

### 1. Preparar el motor (una vez por sesión)

```bash
pip install cadquery-ocp shapely numpy scipy matplotlib   # agregar --break-system-packages si lo pide
```

Si la skill no trae `scripts/`, bajá `viruta_step.py` y `verificar_gcode.py` del repositorio (ver **Si faltan scripts**). Si no se puede instalar nada (sin red), usá el flujo de Rhino o el CAM de Fusion.

### 2. Conseguir el STEP

Detalle por programa en `references/programas.md`. Resumen:

- **Con conector al programa** (buscá con ToolSearch: "solidworks", "fusion", "rhino"): exportá vos el documento activo a STEP en una carpeta conectada de la persona (ej. `Escritorio\Viruta_STEP\`), y traelo con `device_stage_files`.
  - SolidWorks: `solidworks_save_document` con ruta `….STEP` (exporta sin tocar el documento).
  - Fusion: conector Autodesk Fusion → exportar el diseño a STEP con la API.
  - Rhino: `run_command` `_SelNone _-SelName NOMBRE _Enter _-Export "ruta.stp" _Enter _Enter` (siempre los comandos con guion; sin guion abren diálogos), o directamente el flujo de Rhino.
- **Sin conector**: pedile a la persona que exporte a STEP (Archivo → Exportar / Guardar como → STEP) y lo adjunte o lo deje en una carpeta conectada.
- Un archivo puede traer varias piezas (ensamble o varios cuerpos): se procesan todas. Para algunas sola: `--piezas "Pata,Asiento"`.

### 3. Vista previa e informe (antes de escribir nada)

```bash
python viruta_step.py PIEZA.step --salida CARPETA [opciones del perfil y la fresa] --vista-previa --no-escribir
```

Mostrá la imagen `NOMBRE_vista.png` (mapa de profundidades, trayectorias por fresa, pestañas "P", origen con flechas X/Y) y pasá el informe por pieza: medidas X × Y × espesor, **cantidad** de copias iguales, profundidades de cajeras y rebajes, agujeros, taladros, pestañas con X/Y, tiempo estimado y **todos los AVISOS** en criollo. Confirmá con la persona: pestañas, esquinas vivas (¿encastres? → descargas), zonas que no entran con la fresa (→ segunda fresa), caras que no se pueden hacer.

Opciones útiles:
- Fresa(s): `--diametro 6` o `--herramientas 6,3` (la chica hace solo lo que la grande no pudo, en su propio archivo `_T3`), `--loc 19`.
- **Descargas** automáticas en esquinas interiores vivas (encastres): `--descargas` (radio Ø/2 + 0,2; cambiar con `--descargas-extra`). Avisá que se ven en la pieza terminada.
- Pestañas: `--pestanas`, `--pestana-largo`, `--pestana-alto`, `--pestanas-en`.
- Máquina: `--perfil taller5` (por defecto) o `--perfil ninguno --config maquina.json`; sueltos: `--formato`, `--origen`, `--z0`, `--x-largo`, `--extension`, `--husillo`, `--avance`, `--avance-bajada`, `--paso-pct`, `--extra`.
- Si eligió mal la cara de arriba: `--cara-arriba +Z|-Z|+X|-X|+Y|-Y` (en ejes del modelo original).
- Copias iguales: van juntas en un archivo con su cantidad (las espejadas quedan aparte). `--separar-iguales` para un archivo por copia.

### 4. Generar y verificar

```bash
python viruta_step.py PIEZA.step --salida CARPETA [mismas opciones] --vista-previa --verificar
```

Escribe por pieza `NOMBRE.txt` (o `NOMBRE_T6.txt` + `NOMBRE_T3.txt` con dos fresas), `NOMBRE.mapa` (alturas del modelo, para verificar), `NOMBRE_vista.png` y `lista_de_cortes.csv` (pieza, medidas, cantidad, fresa, rpm, avance, tiempo, archivo).

La verificación simula la fresa sobre la placa y la compara con el modelo:
- **material comido** (la fresa baja de más o se mete en la pieza) → error grave, no se entrega;
- **material sobrante** (cajeras sin vaciar; separa las esquinas redondeadas, que son normales);
- **agujeros pasantes sin cortar** y **contorno exterior que no atraviesa la placa**;
- **pestañas**: cuántas y dónde queda unida la pieza;
- **rápidos (G0) dentro del material**.

Si da `HAY ERRORES` por algo que el informe ya avisó (zona más angosta que la fresa), ofrecé la solución (segunda fresa, `--descargas`, cambiar el modelo). Si marca algo que el informe **no** avisó, no lo entregues: investigá. Pasá también `scripts/revisar_gcode.py NOMBRE.txt --diametro D --espesor E` (en el Taller 5 `--avance 2000`). En los archivos de la segunda fresa (`_T3`) es normal que avise "origen lejos de 0" y "0 pestañas": solo hacen detalles sueltos con el mismo origen. Con dos fresas: primero todo el `_T6`, cambio de fresa, volver a tomar el cero de Z (sin mover la placa ni X/Y) y después el `_T3`.

### 5. Entregar

- Si hay carpeta conectada: guardá los `.txt` (y la vista previa y la lista de cortes) donde pida la persona; por defecto `Escritorio\Codigo G <proyecto>\` (con `device_commit_files`). Si no, mandá los archivos.
- Contá en pocas líneas: qué archivos, cuántas veces se corta cada uno, placa mínima (pieza + 20 mm: unos 10 mm de margen por lado), tiempo y avisos pendientes.
- Al pendrive van **solo los `.txt`** (no `.mapa`, `.png`, `.csv`).

### Qué hace y qué no

- Acuesta cada pieza (elige como cara de arriba la que deja todo mecanizable desde arriba), X = lado corto (según perfil), origen según perfil.
- **2,5D con las profundidades exactas del modelo**: si la pieza pide 3 mm, baja 3 mm. Cajeras, rebajes abiertos al borde, escalones, cajeras dentro de cajeras, **islas**. Vaciado en zigzag + pasada de pared, **entrada en rampa** (10°), pasadas parejas ≤ 50 % Ø.
- Agujeros y recortes pasantes por contorno (desde el fondo ya vaciado); del tamaño de la fresa (Ø a Ø + 0,4) los **taladra** con picoteo.
- Contorno exterior al final, hasta espesor + extra, con pestañas.
- **No** hace: caras inclinadas o curvas (chaflanes, relieves 3D: quedan escalonadas, avisa), caras que miran hacia abajo (dar vuelta la placa; avisa), zonas más angostas que la fresa (avisa con X/Y), grabado de líneas finas (solo como cajera del ancho de la fresa).
- Esquinas interiores vivas: salen con radio Ø/2 (avisa con X/Y) salvo que se pida `--descargas`.

## Flujo en Rhino 8 — directo en Rhino (`scripts/rhino_gcode.py`)

Alternativa al flujo universal cuando hay conector de Rhino (Rhino-MCP-Platform de McNeel: herramientas `rhino__run_python`, `rhino__list_objects`, `rhino__get_viewport_image`…). Dibuja las trayectorias dentro de Rhino.

Instalar el conector (una vez): Rhino 8 abierto **normal** (no "Modo seguro") → `_PackageManager` → **Rhino-MCP-Platform** → Instalar → reiniciar → `_MCPConnect` → pestaña **mcp.json** → Copy → en la app de escritorio de Claude: Configuración → Desarrollador → Editar configuración → sumar `"rhino": {"command": "…rhino-mcp-router.exe"}` dentro de `mcpServers` (esa carpeta la edita la persona) → cerrar Claude del todo y abrirlo.

Pasos:
1. `list_objects` (geometryType brep): cada polisuperficie cerrada es una pieza; su nombre es el del archivo.
2. Pasá `scripts/rhino_gcode.py` **completo** a `run_python` con una línea `CFG = {...}` al principio (o copialo a una carpeta y corrélo con `exec(compile(open(ruta).read(), "rhino_gcode.py", "exec"), {"__rhino_doc__": __rhino_doc__, "__name__": "__main__", "CFG": {...}})`; cambiá algo del texto en cada llamada porque el conector puede devolver el resultado anterior). Claves: `diametro`, `husillo`, `avance`, `avance_bajada`, `paso`, `paso_lateral`, `rampa_grados`, `extra`, `z_seguro`, `z_libre`, `pestanas`, `pestana_largo`, `pestana_alto`, `nombres`, `carpeta` (por defecto el Escritorio), `escribir`, `dibujar`, `mapa_alturas`.
3. Vista previa: `{"escribir": False, "dibujar": True}` → `get_viewport_image` (vista superior). Confirmar.
4. Generar: `{"escribir": True, "mapa_alturas": 0.5}` → `NOMBRE.txt` + `NOMBRE.mapa`.
5. Verificar con `verificar_gcode.py NOMBRE.txt NOMBRE.mapa --diametro D --espesor E` y `revisar_gcode.py`.

Para varias fresas, descargas automáticas, pestañas en lugares exactos, copias iguales u otros formatos de máquina, usá el flujo universal (exportando a STEP).

## Flujo en Fusion — CAM en FABRICACIÓN (opcional)

Si la persona quiere hacerlo en el CAM de Fusion (o aprender a hacerlo), guiala con `references/fusion-pasos.md`; con acceso a su Fusion (conector Autodesk Fusion o `fusion_execute`) podés armarlo vos. Si ya hay configuraciones de FABRICACIÓN, revisalas contra el perfil y corregí lo que no cumpla; mostrá (captura) dónde quedan el origen y las pestañas antes de postprocesar. Resumen con [valores del perfil]:

1. Un cuerpo por pieza, apoyado plano. **FABRICACIÓN → CONFIGURACIÓN → Nueva configuración** por pieza: fresado 3 ejes; orientación Z = cara superior arriba, X = [lado corto]; origen [cara de arriba, esquina abajo-izquierda]; stock caja relativa, desfase superior 0.
2. Herramienta elegida; [husillo 18000, avance 2000, entrada 2000].
3. Operaciones: internos (**2D → Cajera 2D**, **Contorno 2D** interior a −0,3 bajo el stock) y al final **Contorno 2D** exterior con **Varias profundidades** [50 % Ø] y **Pestañas** ubicadas *En los puntos* en tramos rectos.
4. **Simular**, **Postprocesar** [Mach3Mill], un archivo por configuración (`scripts/fusion_postprocesar.py` lo hace en lote).
5. `scripts/limpiar_gcode.py` → `.txt`; `scripts/revisar_gcode.py` para revisar.

Para verificar contra el modelo, exportá además el STEP y corré `viruta_step.py PIEZA.step --no-escribir --mapa 0.5` para tener `NOMBRE.mapa`, y luego `verificar_gcode.py` sobre el `.txt` de Fusion.

## Revisión de un código G que trae la persona

Preguntá si es para el Taller 5. Corré `scripts/revisar_gcode.py archivo.txt --diametro D --espesor E` y explicá en criollo:

- **Origen XY**: X e Y de corte entre ≈ −r y medida + r. Muy negativos = origen en otra esquina. Error grave.
- **X = lado corto** (Taller 5).
- **Origen Z**: pasadas negativas (Z-3, Z-6, Z-9…). Z6, Z3, Z0 → cero en la cara de abajo: con el cero arriba corta en el aire. Error grave.
- **Pasadas**: ninguna bajada en material mayor al paso.
- **Pestañas**: cantidad razonable y fuera de zonas intrincadas.
- **Orden**: contorno exterior al final.
- **Limpieza**: primera línea de husillo (`S18000 M3`, o `N5 S18000 M03` en SolidWorks), sin comentarios ni T# M6.
- `G41/G42 D..` (SolidWorks CAM): comparar con los ejemplos del profe.
- Si la persona tiene el STEP de la pieza, verificá también contra el modelo (mapa + `verificar_gcode.py`).

## Organizador de tareas (opcional)

Planilla "Organizador de tareas — Lista de cortes para Routers CNC": por pieza Nº, dibujo con medidas generales y el **origen marcado**, cantidad, Ø y tipo de herramienta con rpm y avance, tiempo (medido si lo hay). La `lista_de_cortes.csv` de `viruta_step.py` trae casi todo. Medidas enteras sin ",0", piezas sin relleno, nombre de archivo sin números delante (ej. `RESPALDO.SEGOVIA SANCHEZ.SOLIDWORKS`). Abajo: cursada, profesor, estudiante, fecha.

## Si faltan scripts o referencias

Si la skill se instaló sin `scripts/` o `references/`, bajalos del repositorio oficial: `https://raw.githubusercontent.com/sandaviar/viruta/main/.claude/skills/viruta/` + `scripts/viruta_step.py`, `scripts/verificar_gcode.py`, `scripts/revisar_gcode.py`, `scripts/limpiar_gcode.py`, `scripts/rhino_gcode.py`, `scripts/fusion_postprocesar.py`, `references/programas.md`, `references/reglas-router-unahur.md`, `references/fusion-pasos.md`, `references/fresas.md`.

## Errores conocidos

- Descargas dibujadas **fuera** de la ranura: la fresa no puede entrar. Van hacia adentro (o `--descargas`).
- STEP con superficies sueltas o mallas: no hay sólido. Pedí exportar sólidos (en Rhino `_Cap` / `_Join`; en SolidWorks/Fusion exportar el cuerpo sólido).
- Nombres genéricos ("Cuerpo1", "Saliente-Extruir1", "Body2"): Viruta usa el nombre de la pieza o del archivo. Si la persona quiere otro nombre, que renombre el cuerpo/componente o usá `--nombre` (un solo archivo).
- Cortes de extrusión que parten piezas al reposicionar descargas: reconstruir limpio en vez de parchar.
- SolidWorks CAM: el perímetro exterior es rasgo **Macho** (si es **Cajera**, corte y pestañas quedan por dentro); usar **Actualizar**, nunca Regenerar; editar un rasgo no actualiza las operaciones (borrarlas y Generar plan de operaciones). Si X no puede quedar en el lado corto con Z arriba, rotar la pieza 90° (Insertar → Operaciones → Mover/Copiar).
- Tiempo calculado ≠ tiempo de máquina: el DDCS del Taller 5 corre a F2000 aunque el código pida otra cosa.
- Rhino en **Modo seguro**: no carga el conector. Rhino en español: comandos con `_`; desde el conector, comandos con guion (`_-Export`, `_-SelName`) para que no abran diálogos.
- El conector de Rhino puede abrir **otra ventana de Rhino** si no encuentra una conectada: abrí ahí el archivo de la persona (`open_doc`) o pedile que lo abra en el Rhino con el conector activo.
- Conector de SolidWorks en español: crear piezas o croquis nuevos puede fallar (plantillas y planos en inglés); exportar funciona.

---

Viruta — © 2026 María Sol Segovia Sánchez (https://github.com/sandaviar). Licencia PolyForm Strict 1.0.0 (ver LICENSE.md): uso personal, educativo y de investigación permitido; no se permite modificar, redistribuir ni usar comercialmente sin permiso escrito de la autora.
