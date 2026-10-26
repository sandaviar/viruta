# Viruta

**Asistente con IA para pasar piezas de Fusion 360 o Rhino 8 a código G para router CNC.**

Viruta es una skill y un agente para Claude que te acompaña desde la pieza modelada hasta el archivo listo para el pendrive: arma el CAM en Fusion 360 (o genera el código G directo desde Rhino 8), ubica el origen, elige pasadas y pestañas, postprocesa, limpia el archivo y revisa que el código G no tenga errores antes de cortar.

Viruta es un **proyecto personal y de autoría de María Sol Segovia Sánchez**. Trae cargado, como primer perfil, el de la máquina del **Taller 5 de la Universidad Nacional de Hurlingham (UNAHUR)**, para que lo puedan usar los estudiantes que cortan ahí. También sirve para otros talleres: Viruta te pregunta los datos de tu router y arma el perfil con vos.

Antes de empezar, Viruta pregunta **si vas a cortar en el Taller 5 de UNAHUR**: si es así usa las reglas de esa máquina (abajo); si es otra máquina, te pregunta sus datos (controlador, origen, rpm, avances, sujeción) y arma el perfil con vos. También **pregunta qué fresa vas a usar** y adapta pasadas, descargas y avances a esa fresa (por defecto, la del taller: Ø6 mm plana, metal duro, 2 filos).

**Autora y titular de los derechos:** María Sol Segovia Sánchez ([@sandaviar](https://github.com/sandaviar)).

## Qué hace

- Te guía (o lo hace directamente si tiene acceso a tu Fusion) para armar el CAM: configuración por pieza, origen, herramienta, operaciones, pestañas, simulación y postprocesado Mach3.
- **Desde Rhino 8, sin Fusion**: con el conector de Rhino (Rhino-MCP-Platform de McNeel) le pedís a Claude el código G y te deja un `.txt` por pieza en el Escritorio. Acomoda la pieza sola (X lado corto, origen abajo-izquierda en la cara superior) y mecaniza en 2,5D con las **profundidades exactas del modelo**: cajeras, rebajes abiertos al borde, islas, escalones, agujeros (o taladrado si son del tamaño de la fresa) y el contorno al final con pestañas. Entra en rampa, te muestra las trayectorias en Rhino antes de escribir y avisa lo que no se puede hacer (zonas más angostas que la fresa, esquinas vivas, caras inclinadas).
- **Verifica el código contra el modelo**: simula la fresa sobre la placa y avisa si se come material de la pieza, si queda material sin vaciar, si un agujero no se corta o dónde quedan las pestañas.
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
LICENSE.md                             ← licencia
LEEME_VIRUTA.txt                       ← instructivo completo (instalar y usar)
README.md
.claude/
  agents/viruta.md          ← el agente (Claude Code)
  skills/viruta/
    SKILL.md                           ← la skill
    LICENSE.md                         ← copia de la licencia (va con la skill)
    references/
      reglas-router-unahur.md          ← reglas de la cátedra + términos de SolidWorks
      fusion-pasos.md                  ← paso a paso en Fusion (menús en español)
      fresas.md                        ← cómo adaptar todo a otra fresa
    scripts/
      limpiar_gcode.py                 ← .tap → .txt limpio
      revisar_gcode.py                 ← chequeo de un .txt
      fusion_postprocesar.py           ← genera y postprocesa todo desde la API de Fusion
      rhino_gcode.py                   ← código G directo desde Rhino 8 (corre dentro de Rhino)
      verificar_gcode.py               ← simula el código G y lo compara con el modelo
```

## Cómo usarlo

**En Claude (app / claude.ai):** subí la carpeta `.claude/skills/viruta` como skill (Configuración → Capacidades → Skills), o comprimila en .zip y subila.

**En Claude Code:** cloná el repo y abrí Claude Code en la carpeta; el agente y la skill se cargan solos. También podés copiar `.claude/agents` y `.claude/skills` a `~/.claude/` para tenerlos en todos tus proyectos.

**Con Rhino 8:** instalá el conector una vez: en Rhino (abierto normal, no en "Modo seguro") corré `_PackageManager`, instalá **Rhino-MCP-Platform**, reiniciá, corré `_MCPConnect` y copiá lo de la pestaña **mcp.json** en la configuración de la app de escritorio de Claude (Configuración → Desarrollador → Editar configuración). Reiniciá Claude y pedile: *"Sacame el código G de las piezas que tengo en Rhino, para el Taller 5"*. `rhino_gcode.py` también se puede correr a mano desde el ScriptEditor de Rhino.

**Scripts sueltos** (Python 3, sin dependencias):

```bash
python .claude/skills/viruta/scripts/limpiar_gcode.py carpeta_con_tap -o carpeta_salida
python .claude/skills/viruta/scripts/revisar_gcode.py carpeta_salida/1_PATA.txt --diametro 6 --espesor 9
python .claude/skills/viruta/scripts/verificar_gcode.py PIEZA.txt PIEZA.mapa --diametro 6 --espesor 9   # necesita numpy y scipy
```

> Los avances y tiempos son estimados: validalos siempre con el profe y en la máquina.

## Licencia

© 2026 María Sol Segovia Sánchez. Viruta se publica bajo la **[PolyForm Strict License 1.0.0](LICENSE.md)**.

En criollo:

- ✅ **Podés usarlo** para uso **personal, educativo o de investigación**: descargarlo, instalarlo en tu Claude y usarlo para tus cortes. Universidades, escuelas y talleres educativos lo pueden usar libremente.
- ❌ **No** se puede **modificar**, hacer versiones propias ni **redistribuir copias** (subirlo a otro lado, pasarlo en otro repo, etc.). La única versión válida es la de este repositorio.
- ❌ **No** se puede usar con **fines comerciales** (venderlo, cobrar por un servicio basado en él, integrarlo en un producto pago).

Para cualquier cosa fuera de esto (adaptarlo, redistribuirlo o usarlo comercialmente) hace falta un **permiso por escrito de la autora**. Escribime por GitHub ([@sandaviar](https://github.com/sandaviar)).

## Cómo colaborar

Las sugerencias son bienvenidas: abrí un **Issue** en este repo contando qué probaste, qué pasó y qué te gustaría mejorar. La autora decide qué se incorpora y es quien hace los cambios.
