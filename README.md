# Router CNC UNAHUR — agente y skill para Claude

Agente y skill para generar **código G para el router CNC de UNAHUR desde Fusion 360**, siguiendo las indicaciones de la cátedra (los videos usan SolidWorks CAM; acá está traducido a Fusion).

Antes de empezar, el agente pregunta **si vas a cortar en el Taller 5 de UNAHUR**: si es así usa las reglas de esa máquina (abajo); si es otra máquina, te pregunta sus datos (controlador, origen, rpm, avances, sujeción) y arma el perfil con vos. También **pregunta qué fresa vas a usar** y adapta pasadas, descargas y avances a esa fresa (por defecto, la del taller: Ø6 mm plana, metal duro, 2 filos).

## Qué hace

- Te guía (o lo hace directamente si tiene acceso a tu Fusion) para armar el CAM: configuración por pieza, origen, herramienta, operaciones, pestañas, simulación y postprocesado Mach3.
- Limpia los archivos para el pendrive (`.txt` que empieza en `S18000 M3`).
- Revisa cualquier `.txt` (de Fusion o de SolidWorks CAM) y te avisa si el origen, las profundidades, las pasadas o las pestañas están mal.
- Ayuda a completar el organizador "Lista de cortes para Routers CNC".

## Reglas de la máquina (Taller 5 — UNAHUR)

| | |
|---|---|
| Postprocesador | Mach3 (`mach3mill`) |
| Origen | esquina inferior izquierda, cara superior, Z arriba |
| Ejes | X = lado corto, Y = lado largo |
| Husillo | S18000 M3 |
| Avance | 2000 mm/min |
| Controlador | DDCS V4.1 (lee el código del post Mach3) |
| Pasadas | 50 % del diámetro (Ø6 → 3 mm) |
| Pestañas | según la pieza (punto de partida 4 de 8 × 3 mm), en tramos rectos fáciles de retirar |
| Orden | internos primero, contorno exterior al final |

## Estructura

```
.claude/
  agents/router-cnc-unahur.md          ← el agente (Claude Code)
  skills/router-cnc-fusion/
    SKILL.md                           ← la skill
    references/
      reglas-router-unahur.md          ← reglas de la cátedra + términos de SolidWorks
      fusion-pasos.md                  ← paso a paso en Fusion (menús en español)
      fresas.md                        ← cómo adaptar todo a otra fresa
    scripts/
      limpiar_gcode.py                 ← .tap → .txt limpio
      revisar_gcode.py                 ← chequeo de un .txt
      fusion_postprocesar.py           ← genera y postprocesa todo desde la API de Fusion
```

## Cómo usarlo

**En Claude (app / claude.ai):** subí la carpeta `.claude/skills/router-cnc-fusion` como skill (Configuración → Capacidades → Skills), o comprimila en .zip y subila.

**En Claude Code:** cloná el repo y abrí Claude Code en la carpeta; el agente y la skill se cargan solos. También podés copiar `.claude/agents` y `.claude/skills` a `~/.claude/` para tenerlos en todos tus proyectos.

**Scripts sueltos** (Python 3, sin dependencias):

```bash
python .claude/skills/router-cnc-fusion/scripts/limpiar_gcode.py carpeta_con_tap -o carpeta_salida
python .claude/skills/router-cnc-fusion/scripts/revisar_gcode.py carpeta_salida/1_PATA.txt --diametro 6 --espesor 9
```

> Los avances y tiempos son estimados: validalos siempre con el profe y en la máquina.
