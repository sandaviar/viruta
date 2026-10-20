---
name: viruta
description: Genera código G para router CNC desde Fusion 360 (CAM 2D de piezas planas) y revisa .txt de código G. Pregunta primero si se corta en el Taller 5 de UNAHUR (DDCS V4.1, post Mach3, S18000, F2000, origen abajo-izquierda en la cara superior, 4 pestañas) o en otra máquina, y qué fresa se usa.
---

# Viruta — de Fusion 360 a código G para router CNC

Skill para pasar piezas planas modeladas en Fusion 360 a archivos de código G listos para un router CNC. Trae cargado el perfil de la máquina del **Taller 5 de UNAHUR** (indicaciones de los videos de la cátedra, hechos en SolidWorks CAM, traducidas a Fusion y verificadas en la máquina). Para otros talleres, se arma el perfil preguntando.

Hablá con la persona en español rioplatense (voseo) y usá los nombres de menús de Fusion en español (FABRICACIÓN, CONFIGURACIÓN, 2D, ACCIONES, Postprocesar…).

## Paso 0 — Preguntar SIEMPRE antes de empezar

Con AskUserQuestion si está disponible (las dos preguntas juntas):

**A. ¿Dónde vas a cortar?**
- **UNAHUR – Taller 5** → usá el **Perfil Taller 5** de abajo tal cual. No inventes ni cambies valores.
- **Otro taller / otra máquina** → pasá al **Perfil de otra máquina**: los valores del Taller 5 NO se aplican automáticamente.

**B. ¿Qué fresa vas a usar?**
1. Diámetro (mm). Sugerida: 6 mm.
2. Tipo: plana/recta, bola, en V, compresión. Para cortes pasantes: plana.
3. Material y filos (metal duro/HSS; 1–3 filos).
4. Largo de corte (LOC) y largo total: el LOC tiene que superar el espesor de la placa + 0,3 mm.
5. Material y espesor de la placa (ej. MDF 9 mm).

Usá exactamente la fresa que diga la persona. Si corta en el Taller 5 y no sabe, proponé la del taller: **Ø6 mm plana, metal duro, 2 filos, LOC 19, largo total 51** ("6MM CRB 2FL 19 LOC").

Con la fresa calculá (ver `references/fresas.md`):
- **Paso vertical** = 50 % del diámetro (Ø6 → 3 mm).
- **Descargas (dogbones)**: círculo de radio Ø/2 + 0,2 mm, centrado sobre la bisectriz y metido **dentro** de la ranura, para que la fresa pueda **entrar y salir**. Avisá si hay esquinas interiores más chicas que el radio de la fresa.
- Ranuras/encastres: ancho ≥ Ø; encastres en placa de espesor e → e + 0,2 (MDF 9 → 9,2).

## Perfil Taller 5 — UNAHUR

Detalle y fuentes en `references/reglas-router-unahur.md`.

| Tema | Regla |
|---|---|
| Controlador | **DDCS V4.1** (lee bien el código del post Mach3; FRO en 100 %) |
| Postprocesador | **Mach3** (`mach3mill.cps` en Fusion; "MILL\MACH_III" en SolidWorks) |
| Origen (0,0,0) | **Esquina inferior izquierda, sobre la CARA SUPERIOR** de la placa |
| Ejes | **Z hacia arriba**, **X = lado corto**, **Y = lado largo** de la pieza (obligatorio) |
| Husillo | **S18000 M3** (18000 rpm) |
| Avance | **F2000 mm/min** (el DDCS corre a 2000 aunque el código diga otro valor) |
| Profundidad | Pasante: espesor + 0,3 mm (MDF 9 → Z-9,3), pasadas del 50 % Ø |
| Pestañas | Punto de partida: **4 de 8 × 3 mm**, pero la cantidad, la medida y el lugar se deciden según la pieza (ver **Pestañas** abajo) |
| Orden | **Primero lo interno** (agujeros, canales, ranuras), **contorno exterior al final** |
| Archivos | **Uno por pieza y por herramienta**, .txt al pendrive |
| Limpieza | Arranca en `S18000 M3`; sin comentarios, sin T# M6, sin G28; termina en M5/M30 |
| Tiempo | ≈ largo de corte / 2000 mm/min + ~10 % (asiento 70×190: 3 min 22 s medido) |

## Pestañas: cuántas, de qué medida y dónde

Las pestañas tienen que tener sentido para el objeto que se corta. 4 de 8 × 3 mm es una buena medida para piezas chicas o medianas (como un banquito de 70 × 190 mm en MDF 9), pero **no es una regla fija**: decidí con la persona según el tamaño y la forma.

**Cantidad** (orientativo, ajustar a la forma):

| Pieza (lado mayor) | Pestañas |
|---|---|
| < 80 mm | 2 (enfrentadas) |
| 80 – 300 mm | 3 – 4 |
| 300 – 600 mm | 6 |
| > 600 mm | 8 o más (≈ una cada 150 – 250 mm de perímetro) |

Más pestañas si la pieza es angosta y larga, liviana, o si hay que sostener partes que quedan en voladizo. Menos si la pieza es chica y compacta: cada pestaña es trabajo de terminación.

**Medida**:
- Alto ≈ 1/3 del espesor de la placa (MDF 9 → 3 mm; 5,5 → 2 mm; 18 → 5 – 6 mm).
- Largo 6 – 10 mm (8 mm en general); más largo en piezas grandes y pesadas.

**Ubicación — tienen que ser fáciles de retirar**:
- En **tramos rectos y abiertos** del contorno exterior, donde se llegue cómodo con trincheta, serrucho, formón o lija.
- **Nunca** en zonas intrincadas: muescas, encastres, descargas (dogbones), curvas cerradas, esquinas, ranuras angostas o bordes entre detalles. Si la posición automática cae ahí, movela a otro tramo recto cercano.
- Evitá los **bordes que encastran o que tienen que quedar a medida** (lijar la pestaña ahí cambia el ajuste) y, si se puede, los cantos que quedan a la vista.
- Repartilas **enfrentadas y parejas** alrededor de la pieza, para que no se mueva ni vibre al cortar el último tramo.
- En Fusion, ubicarlas con **Posicionamiento: En los puntos** (clic en cada lugar) en vez de por distancia, así quedan donde se eligió.
- Recortes interiores que son descarte (agujeros, la ranura del cable) normalmente van **sin pestañas**; si son grandes y pueden salir despedidos, conviene ponerles 1 – 2.

Antes de postprocesar, mostrale a la persona dónde quedaron las pestañas (simulación o captura) y confirmá.

## Perfil de otra máquina

Si NO corta en el Taller 5, antes de crear operaciones preguntá (lo que la persona no sepa, que lo consulte con el responsable de la máquina; no lo completes con los valores de UNAHUR sin avisar):

1. **Controlador / software** de la máquina (Mach3, DDCS, GRBL, LinuxCNC, Nc Studio…) → define el **postprocesador** de Fusion (Mach3Mill, GRBL, LinuxCNC/EMC2, Nc Studio…).
2. **Origen y ejes**: en qué esquina y en qué cara se toma el cero (arriba de la placa o sobre la mesa), y si hay convención de qué lado va en X.
3. **Husillo**: rpm (y si el código tiene que llevar la S o se ajusta a mano).
4. **Avances**: avance de corte y de bajada, y si el controlador respeta la F del código.
5. **Pasada máxima** y **profundidad extra** para pasar la placa.
6. **Sujeción**: pestañas (cantidad y medida), tornillos o vacío.
7. **Formato del archivo**: extensión (.txt, .nc, .tap, .gcode), si hay que limpiar encabezados, si acepta cambio de herramienta.

Armá una tabla igual a la del Taller 5 con esas respuestas, mostrásela a la persona para que la confirme, y usala en el resto del flujo. Si falta algún dato, usá un valor conservador (pasada 50 % Ø, 4 pestañas de 8 × 3, origen en la cara superior) **y avisalo**. Ajustá `limpiar_gcode.py` y `revisar_gcode.py` con `--avance` / `--espesor` / `--diametro` según corresponda.

## Flujo en Fusion 360

Hay dos caminos: guiar a la persona paso a paso en su Fusion, o hacerlo directamente si hay acceso a Fusion (herramienta `fusion_execute` o control del equipo). Pasos detallados de interfaz en `references/fusion-pasos.md`. Los valores entre [corchetes] salen del perfil elegido (Taller 5 o la otra máquina).

1. **Preparar el modelo**: un cuerpo por pieza, apoyado plano (cara grande hacia +Z). Para ensambles, un diseño aparte "piezas en plano".
2. **FABRICACIÓN → CONFIGURACIÓN → Nueva configuración** (una por pieza):
   - Máquina genérica de 3 ejes, Fresado, modelo = el cuerpo de esa pieza.
   - **Orientación**: "Seleccionar el eje Z y el eje X" → Z = cara superior hacia arriba; X = [arista corta en el Taller 5].
   - **Origen**: "Punto del cuadro de stock" → [cara de arriba, esquina abajo-izquierda en el Taller 5]. Verificá en pantalla la terna.
   - Stock: caja de tamaño relativo, desfase superior 0.
3. **Herramienta**: la fresa que eligió la persona. Datos de corte: [Taller 5: husillo 18000, avance de corte 2000, avance de entrada 2000; bajada la que indique el profe].
4. **Operaciones**, en este orden:
   - Interiores: **2D → Cajera 2D** (canales/rebajes) y **2D → Contorno 2D** interior (agujeros/ranuras pasantes, altura inferior: parte inferior del stock −0,3).
   - Al final: **2D → Contorno 2D** exterior: altura inferior −0,3; **Varias profundidades** con paso [50 % Ø]; **Pestañas** rectangulares con la cantidad y medida que salgan de la sección **Pestañas**, ubicadas a mano con *En los puntos* en tramos rectos y accesibles; Entrada/Salida activadas.
5. **Simular** (ACCIONES → Simular, con stock): pieza unida por pestañas **por fuera**, en lugares fáciles de cortar y lijar, sin zonas sin cortar, sin colisiones.
6. **Postprocesar** (ACCIONES → Postprocesar): [Taller 5: Mach3Mill], mm, un archivo por configuración (`1_PATA`, `2_ASIENTO`…).
7. **Limpiar** cada archivo con `scripts/limpiar_gcode.py` → `.txt`.
8. **Revisar** cada `.txt` con `scripts/revisar_gcode.py` (en el Taller 5: `--avance 2000`).
9. Entregar los `.txt` (y guardarlos en la carpeta de la persona si hay una conectada). Al pendrive van los .txt, **no** el .SET ni el .tap original.

### Hacerlo directo en el Fusion de la persona

Si la persona pide "entrá a mi Fusion y sacá el código G" y hay acceso a su computadora (herramienta de Fusion como `fusion_execute`, o control del equipo):

1. Si ya dijo dónde corta y qué fresa usa, no lo vuelvas a preguntar. Preguntá solo lo que falte y **en qué carpeta y con qué nombre** guardar los archivos (sugerí una carpeta con el nombre del proyecto, ej. `Codigo G <Proyecto>`, y archivos `1_PIEZA.txt`, `2_PIEZA.txt`…).
2. Abrí el diseño activo, identificá las piezas (cuerpos) y, si no hay configuraciones de FABRICACIÓN, crealas vos con el perfil elegido (una por pieza: orientación, origen, stock, herramienta, operaciones internas, contorno exterior con pestañas). Si ya existen, revisalas contra el perfil y corregí lo que no cumpla.
3. Mostrá a la persona (captura) dónde quedan el origen y las pestañas antes de postprocesar.
4. Generá y postprocesá (`scripts/fusion_postprocesar.py` sirve para regenerar y postprocesar en lote; cambiá `POST` si no es la máquina del Taller 5), limpiá con `limpiar_gcode.py`, revisá con `revisar_gcode.py` y guardá los `.txt` finales en la carpeta pedida.
5. Contá en una línea qué archivos quedaron y dónde.

Si no hay acceso a Fusion, guiá a la persona paso a paso con `references/fusion-pasos.md`.

### Si los scripts o las referencias no están junto a la skill

Si la skill se instaló sin las carpetas `scripts/` o `references/`, leelas del repositorio oficial (`https://raw.githubusercontent.com/sandaviar/viruta/main/.claude/skills/viruta/references/` + `reglas-router-unahur.md`, `fusion-pasos.md` o `fresas.md`) y descargá los scripts de ahí:
- `https://raw.githubusercontent.com/sandaviar/viruta/main/.claude/skills/viruta/scripts/limpiar_gcode.py`
- `https://raw.githubusercontent.com/sandaviar/viruta/main/.claude/skills/viruta/scripts/revisar_gcode.py`
- `https://raw.githubusercontent.com/sandaviar/viruta/main/.claude/skills/viruta/scripts/fusion_postprocesar.py`

## Revisión de un código G que trae la persona

Preguntá también si es para el Taller 5. Corré `scripts/revisar_gcode.py archivo.txt --diametro D --espesor E` y explicá en criollo:

- **Origen XY**: X e Y de corte entre ≈ −r y medida + r (r = radio de fresa). Valores muy negativos = origen en otra esquina. Error grave.
- **X = lado corto** (Taller 5).
- **Origen Z**: las pasadas tienen que ser negativas (Z-3, Z-6, Z-9…). Z6, Z3, Z0 → cero en la cara de abajo: con el cero arriba corta en el aire. Error grave.
- **Pasadas**: ninguna bajada en material mayor al paso (ej. `G01 Z-7` desde arriba con Ø6 es demasiado).
- **Pestañas**: las que detecta el script en la última pasada; revisá que la cantidad tenga sentido para el tamaño de la pieza y que no caigan en zonas intrincadas (muescas, encastres, curvas cerradas).
- **Orden**: contorno exterior al final; operaciones repetidas sobran.
- **Limpieza**: primera línea de husillo (`S18000 M3`, o `N5 S18000 M03` en SolidWorks), sin comentarios ni T# M6.
- `G41/G42 D..` (compensación, típico de SolidWorks CAM): que lo compare con los ejemplos del profe.
- **Tiempo**: el del script es estimado; si la persona lo midió en la máquina, vale el medido.

## Organizador de tareas (opcional)

Planilla "Organizador de tareas — Lista de cortes para Routers CNC": por pieza Nº, dibujo con medidas generales y el **origen marcado** (esquina inferior izquierda, X lado corto, Y lado largo), cantidad, Ø y tipo de herramienta con rpm y avance, tiempo (medido en máquina si lo hay). Medidas enteras sin ",0", piezas sin relleno de color, nombre de archivo sin números delante (ej. `RESPALDO.SEGOVIA SANCHEZ.SOLIDWORKS`). Abajo: cursada, profesor, estudiante, fecha.

## Errores conocidos y cómo evitarlos

- Descargas dibujadas **fuera** de la ranura: la fresa no puede entrar ni salir. Van centradas hacia adentro.
- Cortes de extrusión que parten piezas al reposicionar descargas: reconstruir limpio en vez de parchar.
- Vistas de plano "torcidas": hacer un diseño con las piezas acostadas en plano.
- SolidWorks CAM: el perímetro exterior es rasgo **Macho** (si es **Cajera**, corte y pestañas quedan por dentro); usar **Actualizar**, nunca Regenerar; editar un rasgo no actualiza las operaciones (borrarlas y Generar plan de operaciones). Si X no puede quedar en el lado corto con Z arriba, rotar la pieza 90° (Insertar → Operaciones → Mover/Copiar).
- Tiempo calculado ≠ tiempo de máquina: el DDCS del Taller 5 corre a F2000 aunque el código pida F1200.

---

Viruta — © 2026 María Sol Segovia Sánchez (https://github.com/sandaviar). Licencia PolyForm Strict 1.0.0 (ver LICENSE.md): uso personal, educativo y de investigación permitido; no se permite modificar, redistribuir ni usar comercialmente sin permiso escrito de la autora.
