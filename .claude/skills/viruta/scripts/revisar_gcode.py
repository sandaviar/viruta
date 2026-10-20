#!/usr/bin/env python3
# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
"""Revisa un archivo de código G para el router CNC de UNAHUR.

Chequea: línea inicial, origen XY (esquina inferior izquierda), origen Z (cara
superior), pasadas máximas, profundidad final, pestañas, medidas de la pieza,
compensación G41/G42 y restos sin limpiar. Estima el tiempo de mecanizado.

Uso:
  python revisar_gcode.py ARCHIVO.txt [--diametro 6] [--espesor 9] [--avance 2000] [--rapido 3000]
"""
import argparse
import math
import re

OK, WARN, ERR = 'OK ', '!! ', 'XX '


def parsear(path):
    x = y = z = 0.0
    modo = 0
    feed = 1000.0
    movs = []  # (modo, x0,y0,z0, x1,y1,z1, largo, feed)
    with open(path, encoding='utf-8', errors='replace') as fh:
        lineas = [l.strip() for l in fh if l.strip()]
    for l in lineas:
        sin_n = re.sub(r'^N\d+\s*', '', l)
        g = re.findall(r'G0?([0-3])(?!\d)', sin_n)
        if g:
            modo = int(g[-1])
        if re.search(r'G9[01]', sin_n) and 'G91' in sin_n:
            continue  # movimientos incrementales (G91 G28) se ignoran
        d = {k: float(v) for k, v in re.findall(r'([XYZFIJ])(-?\d*\.?\d+)', sin_n)}
        if 'F' in d:
            feed = d['F']
        if 'G28' in sin_n or not any(k in d for k in 'XYZ'):
            continue
        nx, ny, nz = d.get('X', x), d.get('Y', y), d.get('Z', z)
        largo = math.dist((x, y, z), (nx, ny, nz))
        if modo in (2, 3) and ('I' in d or 'J' in d):
            cx, cy = x + d.get('I', 0), y + d.get('J', 0)
            r = math.hypot(x - cx, y - cy)
            a1, a2 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
            da = a2 - a1
            if modo == 2:
                da = da if da < 0 else da - 2 * math.pi
            else:
                da = da if da > 0 else da + 2 * math.pi
            if math.dist((x, y), (nx, ny)) < 1e-6:
                da = 2 * math.pi
            largo = math.hypot(abs(da) * r, nz - z)
        movs.append((modo, x, y, z, nx, ny, nz, largo, feed))
        x, y, z = nx, ny, nz
    return lineas, movs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archivo')
    ap.add_argument('--diametro', type=float, default=6.0, help='Ø de la fresa en mm (def. 6)')
    ap.add_argument('--espesor', type=float, default=9.0, help='espesor de la placa en mm (def. 9)')
    ap.add_argument('--avance', type=float, default=2000.0,
                    help='avance real de la máquina en mm/min (el DDCS del taller corre a 2000); 0 = usar el F del archivo')
    ap.add_argument('--rapido', type=float, default=3000.0, help='velocidad de G0 en mm/min para estimar tiempo')
    a = ap.parse_args()
    r = a.diametro / 2
    paso_max = a.diametro / 2 + 0.05

    lineas, movs = parsear(a.archivo)
    corte = [m for m in movs if m[0] != 0]
    res = []

    # Inicio / limpieza
    primera = re.sub(r'^N\d+\s*', '', lineas[0]) if lineas else ''
    res.append((OK if re.match(r'S\d+\s*M0?3', primera, re.I) else ERR,
                f'Primera línea: "{lineas[0] if lineas else ""}" (husillo encendido, ej. S18000 M3)'))
    if any('(' in l for l in lineas):
        res.append((WARN, 'Quedan comentarios entre paréntesis: falta limpiar.'))
    if any(re.search(r'\bT\d+\s*M0?6', l) for l in lineas):
        res.append((WARN, 'Hay cambio de herramienta (T# M6): un archivo por herramienta.'))
    if any('G28' in l for l in lineas):
        res.append((WARN, 'Tiene G28 (ir a home): revisá si el profe lo deja o lo borra.'))
    if any(re.search(r'G4[12]', l) for l in lineas):
        res.append((WARN, 'Usa compensación de radio G41/G42: comparalo con los códigos de ejemplo del profe.'))
    if not any(re.search(r'\bM30\b', l) for l in lineas):
        res.append((WARN, 'No termina con M30.'))

    if not corte:
        res.append((ERR, 'No hay movimientos de corte.'))
        for t, m in res:
            print(t + m)
        return

    xs = [p for m in corte for p in (m[1], m[4])]
    ys = [p for m in corte for p in (m[2], m[5])]
    zs = [m[6] for m in corte]
    zmin, zmax_corte = min(zs), max(zs)
    ancho, largo = max(xs) - min(xs) - 2 * r, max(ys) - min(ys) - 2 * r

    # Origen XY
    if min(xs) < -r - 1 or min(ys) < -r - 1:
        res.append((ERR, f'Origen XY: hay X/Y de corte muy negativos (X mín {min(xs):.1f}, Y mín {min(ys):.1f}). '
                         'El origen no está en la esquina inferior izquierda.'))
    elif min(xs) > r + 1 or min(ys) > r + 1:
        res.append((WARN, f'Origen XY: el corte empieza lejos de 0 (X mín {min(xs):.1f}, Y mín {min(ys):.1f}).'))
    else:
        res.append((OK, f'Origen XY en la esquina inferior izquierda (X {min(xs):.1f}…{max(xs):.1f}, Y {min(ys):.1f}…{max(ys):.1f}).'))
    if ancho > largo + 0.5:
        res.append((ERR, f'X tiene que ser el lado corto: X ≈ {ancho:.1f} y Y ≈ {largo:.1f}.'))
    else:
        res.append((OK, f'Pieza ≈ {ancho:.1f} (X, corto) × {largo:.1f} (Y, largo) mm.'))

    # Origen Z
    if zmin >= -0.01:
        res.append((ERR, f'Origen Z: ningún corte es negativo (Z mín {zmin:.2f}). El cero está en la cara de ABAJO: '
                         'con el cero arriba la fresa corta en el aire.'))
    else:
        prof = -zmin
        if prof < a.espesor:
            res.append((WARN, f'Profundidad máxima {prof:.2f} mm: menor que el espesor {a.espesor} (no pasa la placa).'))
        elif prof > a.espesor + 1:
            res.append((WARN, f'Profundidad máxima {prof:.2f} mm: más de 1 mm por debajo de la placa.'))
        else:
            res.append((OK, f'Profundidad final {prof:.2f} mm (placa {a.espesor} mm).'))

    # Pasadas: para cada bajada vertical, cuánto material hay debajo según lo ya cortado cerca
    pts = []  # puntos (x, y, z) ya cortados
    peor = 0.0
    for m in movs:
        modo, x0, y0, z0, x1, y1, z1, *_ = m
        if modo != 0 and z1 < z0 - 1e-6 and abs(x1 - x0) < 1e-6 and abs(y1 - y0) < 1e-6 and z1 < 0:
            cerca = [pz for (px, py, pz) in pts if math.hypot(px - x1, py - y1) <= r * 0.9]
            tope = min([0.0] + cerca)
            peor = max(peor, tope - z1)
        if modo != 0 and z1 < 0:
            n = max(1, int(m[7] // 2))
            for k in range(n + 1):
                pts.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, min(z0, z1)))
    if peor > paso_max * 1.6:
        res.append((ERR, f'Hay una bajada de {peor:.2f} mm de una vez en material (paso recomendado {a.diametro/2:g} mm). '
                         'Revisá el orden de operaciones y las pasadas.'))
    elif peor > paso_max:
        res.append((WARN, f'Bajada máxima {peor:.2f} mm (recomendado ≤ {a.diametro/2:g} mm).'))
    else:
        res.append((OK, f'Pasadas de hasta {peor:.2f} mm.'))

    # Pestañas: en la pasada final, cada vez que la fresa sale del fondo y vuelve a bajar
    # cerca de donde salió (menos de 8 mm + 4 Ø) cuenta como una pestaña.
    pest, salida, ant = 0, None, False
    for m in movs:
        en_fondo = m[0] != 0 and abs(m[3] - zmin) < 1e-3 and abs(m[6] - zmin) < 1e-3
        if en_fondo and not ant and salida is not None:
            if math.dist(salida, (m[1], m[2])) < 8 + 4 * a.diametro:
                pest += 1
        if ant and not en_fondo:
            salida = (m[1], m[2])
        ant = en_fondo
    res.append((OK if pest >= 2 else WARN,
                f'Pestañas detectadas: {pest}. Revisá que la cantidad tenga sentido para el tamaño de la pieza ({ancho:.0f} × {largo:.0f} mm) y que estén en tramos rectos fáciles de retirar.'))

    # Tiempo
    t = sum(m[7] / (a.rapido if m[0] == 0 else (a.avance or max(m[8], 1))) for m in movs)
    res.append((OK, f'Tiempo estimado de mecanizado: ≈ {t:.1f} min (a {"F del archivo" if not a.avance else f"{a.avance:g} mm/min"}, sin aceleraciones ni cambio de placa).'))

    print(f'Revisión de {a.archivo}  (fresa Ø{a.diametro:g}, placa {a.espesor:g} mm)')
    for tipo, msg in res:
        print(tipo + msg)


if __name__ == '__main__':
    main()
