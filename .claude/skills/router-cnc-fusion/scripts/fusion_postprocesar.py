"""Genera trayectorias y postprocesa con Mach3 todas las configuraciones del diseño activo de Fusion 360.

Cómo usarlo:
  - Desde Fusion: UTILIDADES → Complementos → Scripts y complementos → crear un script nuevo
    en Python y pegar este contenido (la función run() la llama Fusion).
  - Desde un agente con acceso a la API de Fusion (por ejemplo una herramienta tipo
    `fusion_execute`): ejecutar el contenido y llamar run(None).

Requisitos: el diseño ya tiene las configuraciones (una por pieza) con sus operaciones,
el origen en la esquina inferior izquierda de la cara superior (X lado corto, Y lado largo)
y la fresa que eligió la persona.

Salida: un .tap por configuración en CARPETA_SALIDA, con el nombre de la configuración.
Después limpiar con limpiar_gcode.py.
"""
import os
import time

import adsk.cam
import adsk.core

# Cambiar a gusto
CARPETA_SALIDA = os.path.join(os.path.expanduser('~'), 'Desktop', 'Codigo G router')
POST = 'mach3mill.cps'          # postprocesador Mach3 de la biblioteca de Fusion
SOLO_CONFIGURACIONES = []        # ej. ['PATA', 'ASIENTO']; vacío = todas


def run(context):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))
    if cam is None:
        print('Este documento no tiene datos de FABRICACIÓN.')
        return

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    setups = [s for s in cam.setups
              if not SOLO_CONFIGURACIONES or s.name in SOLO_CONFIGURACIONES]
    if not setups:
        print('No hay configuraciones para postprocesar.')
        return

    # 1) Generar trayectorias
    for s in setups:
        fut = cam.generateToolpath(s)
        t0 = time.time()
        while not fut.isGenerationCompleted and time.time() - t0 < 300:
            adsk.doEvents()
            time.sleep(0.2)
        print(f'Trayectorias generadas: {s.name} ({s.operations.count} operaciones)')

    # 2) Postprocesar cada configuración a su propio archivo
    post_cfg = os.path.join(cam.genericPostFolder, POST)
    for s in setups:
        con_error = [op.name for op in s.allOperations if not op.hasToolpath or op.hasWarning]
        if con_error:
            print(f'  Atención en {s.name}: revisar {con_error}')
        nombre = s.name.replace(' ', '_')
        pin = adsk.cam.PostProcessInput.create(
            nombre, post_cfg, CARPETA_SALIDA, adsk.cam.PostOutputUnitOptions.MillimetersOutput)
        pin.isOpenInEditor = False
        cam.postProcess(s, pin)
        print(f'Postprocesado: {os.path.join(CARPETA_SALIDA, nombre)}.tap')

    print('Listo. Ahora limpiar con: python limpiar_gcode.py "%s"' % CARPETA_SALIDA)
