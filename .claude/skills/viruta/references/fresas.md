# Cómo adaptar el proceso a la fresa que use la persona

Siempre se pregunta la fresa antes de empezar y se usa la que la persona elija. Con esos datos se ajustan estos parámetros:

| Parámetro | Regla | Ø3 | Ø4 | **Ø6 (taller)** | Ø8 |
|---|---|---|---|---|---|
| Paso vertical (stepdown) | 50 % Ø | 1,5 | 2 | **3** | 4 |
| Radio de descarga (dogbone) | Ø/2 + 0,2 | 1,7 | 2,2 | **3,2** | 4,2 |
| Radio interior mínimo | ≥ Ø/2 | 1,5 | 2 | **3** | 4 |
| Ancho mínimo de ranura | ≥ Ø | 3 | 4 | **6** | 8 |
| Pasadas en MDF 9 (Z-9,3) | ⌈9,3 / paso⌉ | 7 | 5 | **4** | 3 |

Notas:
- El **largo de corte (LOC)** tiene que superar el espesor de la placa + 0,3 mm. Si no alcanza, avisar.
- **Pestañas**: la medida depende del espesor de la placa y del tamaño de la pieza, no de la fresa (ver la sección Pestañas de la skill). Con fresas chicas el canal es angosto y la pieza vibra más: en piezas grandes conviene alguna pestaña más.
- **Velocidades de la máquina**: S18000 y F2000 mm/min (así está configurado el DDCS del taller). Para otra fresa, preguntá a la persona o al profe los avances; si no los saben, usá S18000 / F2000 como en la máquina y avisá que con fresas chicas (≤ 4 mm) conviene bajar el paso vertical y validar en la máquina.
- **Tipo**: plana/recta para cortes pasantes y cajeras de fondo plano. Bola solo para relieves 3D. En V para grabado/chaflán. Compresión si la persona la tiene (mejor canto en MDF/terciado).
- Encastres entre piezas de placa de espesor *e*: ranura de *e* + 0,2 mm (MDF 9 → 9,2).
