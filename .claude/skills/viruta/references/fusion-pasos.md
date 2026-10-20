# Paso a paso en Fusion 360 (interfaz en español)

## 1. Pasar a FABRICACIÓN

Selector de espacio de trabajo (arriba a la izquierda) → **FABRICACIÓN** → pestaña **FRESADO**.

## 2. Configuración (una por pieza)

**CONFIGURACIÓN → Nueva configuración**

Pestaña **Configuración**:
- Tipo de operación: **Fresado**.
- Modelo: seleccionar solo el cuerpo de la pieza.
- **Orientación**: *Seleccionar el eje Z y el eje X*.
  - Eje Z: clic en la **cara superior** (o una arista vertical); la flecha tiene que apuntar hacia arriba. Si apunta abajo, tildá "Invertir eje Z".
  - Eje X: clic en una **arista del lado corto**. Si queda al revés, "Invertir eje X".
- **Origen**: *Punto del cuadro de stock* → elegí el punto de la **cara de arriba, esquina de abajo a la izquierda** (en la vista superior, abajo-izquierda).
- Verificar la terna en pantalla: X roja por el lado corto, Y verde por el lado largo, Z azul hacia arriba, todo saliendo de la esquina inferior izquierda de arriba.

Pestaña **Stock**:
- Modo: *Caja de tamaño relativo*. Desfase lateral 0–5 mm, **desfase superior 0**, desfase inferior 0.

## 3. Herramienta

**GESTIONAR → Biblioteca de herramientas** → nueva herramienta de fresado → **Fresa plana**:
- Pestaña Cuchilla: Diámetro (el de la persona, ej. 6), N.º de filos (2), Longitud de flauta / de corte (19), Longitud total (51), Material: Carburo.
- Pestaña Datos de corte: Velocidad del husillo **18000**, Velocidad de avance de corte **2000**, Velocidad de avance de entrada **2000**, Velocidad de carga (bajada): la que indique el profe (el DDCS hoy corre todo a 2000), Paso hacia abajo máximo = 50 % Ø.

## 4. Operaciones

Orden: internas primero, perímetro al final (se reordenan arrastrando en el árbol del navegador).

**Cajera 2D** (canales/rebajes no pasantes):
- Geometría: el fondo de la cajera.
- Alturas: inferior = fondo seleccionado.
- Pasadas: varias profundidades, paso máx. 50 % Ø.

**Contorno 2D interior** (agujeros, ranuras pasantes):
- Geometría: el borde inferior del agujero (la flecha roja tiene que quedar del lado de adentro).
- Alturas: Altura inferior → *Parte inferior del stock*, desfase **−0,3**.
- Pasadas: varias profundidades.

**Contorno 2D exterior** (el último):
- Geometría: el borde inferior del perímetro, corte por fuera.
- Alturas: inferior = parte inferior del stock −0,3.
- Pasadas: **Varias profundidades**, paso máximo 50 % Ø.
- **Pestañas**: tildar *Pestañas*; Forma: Rectangular; Ancho y Altura según la pieza (ej. 8 × 3 en MDF 9); Posicionamiento: preferí *En los puntos* y hacé clic en tramos rectos y accesibles del contorno (no en muescas, encastres, descargas ni curvas cerradas). La cantidad depende del tamaño de la pieza.
- Entrada/Salida: activadas (arco o rampa).

## 5. Simular

Seleccionar la configuración → **ACCIONES → Simular** → tildar *Stock* → reproducir. Revisar que la pieza quede unida por las pestañas, que no queden zonas sin cortar y que no haya colisiones (rojo).

## 6. Postprocesar

Seleccionar la configuración → **ACCIONES → Postprocesar**:
- Configuración de post: buscar **Mach3** → *Mach3Mill / mach3mill.cps*.
- Unidades: milímetros.
- Nombre de programa / archivo: `1_PATA` etc. Carpeta de salida: la carpeta de la persona.
- Postprocesar → genera `.tap`.

## 7. Limpiar y revisar

```
python limpiar_gcode.py carpeta_con_tap carpeta_salida
python revisar_gcode.py carpeta_salida/1_PATA.txt --diametro 6 --espesor 9
```
