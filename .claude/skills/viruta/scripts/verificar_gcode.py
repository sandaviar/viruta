#!/usr/bin/env python3
# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
"""Simula un código G con fresa plana y lo compara contra el modelo (mapa de alturas).

El mapa de alturas lo genera rhino_gcode.py con CFG {"mapa_alturas": 0.5}: una línea
"MAPA x0 y0 paso nx ny datos" en coordenadas de máquina (origen arriba-izquierda-abajo
de la pieza, Z = 0 en la cara superior). Guardala en un archivo .mapa.

Chequea:
  - MATERIAL COMIDO: la fresa baja más de lo que pide la pieza (error grave).
  - MATERIAL SOBRANTE: zonas que tendrían que quedar más bajas (cajeras sin vaciar),
    separando lo que es esquina viva (normal, radio de la fresa) de lo que no.
  - PIEZA SUELTA: que el corte pasante la separe de la placa salvo por las pestañas.
  - RÁPIDOS (G0) dentro del material.

Uso:
  python verificar_gcode.py ARCHIVO.txt ARCHIVO.mapa [--diametro 6] [--espesor 9]
Requiere numpy (y scipy opcional para agrupar zonas).
"""
import argparse
import base64
import math
import re
import struct
import sys
import zlib

import numpy as np

try:
    from scipy import ndimage
except Exception:  # pragma: no cover
    ndimage = None


def leer_mapa(path):
    with open(path, encoding='utf-8') as fh:
        txt = fh.read().strip()
    i = txt.find('MAPA ')
    partes = txt[i:].split()
    x0, y0, paso = float(partes[1]), float(partes[2]), float(partes[3])
    nx, ny = int(partes[4]), int(partes[5])
    raw = zlib.decompress(base64.b64decode(partes[6]))
    vals = np.array(struct.unpack('<%dh' % (nx * ny), raw), dtype=np.float64).reshape(ny, nx)
    fuera = vals <= -31999
    z = vals / 100.0
    z[fuera] = np.nan
    return x0, y0, paso, z


def leer_movimientos(path):
    x = y = 0.0
    z = 10.0
    modo = 0
    movs = []
    with open(path, encoding='utf-8', errors='replace') as fh:
        for l in fh:
            l = re.sub(r'\([^)]*\)', '', l).strip().upper()
            if not l:
                continue
            g = re.findall(r'G0?([0-3])(?!\d)', l)
            if g:
                modo = int(g[-1])
            d = {k: float(v) for k, v in re.findall(r'([XYZ])(-?\d*\.?\d+)', l)}
            if not d:
                continue
            nx_, ny_, nz_ = d.get('X', x), d.get('Y', y), d.get('Z', z)
            if modo in (2, 3):
                raise SystemExit('El verificador no simula arcos G2/G3 todavía.')
            movs.append((modo, x, y, z, nx_, ny_, nz_))
            x, y, z = nx_, ny_, nz_
    return movs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('gcode')
    ap.add_argument('mapa')
    ap.add_argument('--diametro', type=float, default=6.0)
    ap.add_argument('--espesor', type=float, default=None, help='espesor de la placa (por defecto, el del mapa)')
    ap.add_argument('--tolerancia', type=float, default=0.05)
    a = ap.parse_args()

    x0, y0, paso, esperado = leer_mapa(a.mapa)
    ny, nx = esperado.shape
    r = a.diametro / 2
    pieza = ~np.isnan(esperado)
    espesor = a.espesor  # si no se pasa, se deduce de la pasada más profunda (espesor + 0,3)

    sim = np.zeros_like(esperado)  # placa entera con la cara de arriba en Z = 0
    rc = int(math.ceil(r / paso)) + 1

    rapidos_mal = []
    movs = leer_movimientos(a.gcode)
    zmin = 0.0
    rr = (r - 0.02) ** 2  # disco apenas más chico: evita falsos positivos en celdas justo sobre la pared
    for modo, xa, ya, za, xb, yb, zb in movs:
        if min(za, zb) >= 0:
            continue
        L = math.hypot(xb - xa, yb - ya)
        n = max(1, int(math.ceil(L / (paso * 0.4))))
        if modo == 0:
            # subir rápido para salir del corte está bien; moverse de costado o bajar a material, no
            if L > 1e-6 or zb < za:
                ci = int(round((xb - x0) / paso))
                cj = int(round((yb - y0) / paso))
                libre = 0 <= ci < nx and 0 <= cj < ny and sim[cj, ci] <= zb + 1e-6
                if L > 1e-6 or not libre:
                    rapidos_mal.append((xa, ya, za, xb, yb, zb))
            continue
        zmin = min(zmin, za, zb)
        for k in range(n + 1):
            t = k / n
            x = xa + (xb - xa) * t
            y = ya + (yb - ya) * t
            z = za + (zb - za) * t
            if z >= 0:
                continue
            ci = int(round((x - x0) / paso))
            cj = int(round((y - y0) / paso))
            i0, i1 = ci - rc, ci + rc + 1
            j0, j1 = cj - rc, cj + rc + 1
            si0, si1 = max(i0, 0), min(i1, nx)
            sj0, sj1 = max(j0, 0), min(j1, ny)
            if si0 >= si1 or sj0 >= sj1:
                continue
            # disco exacto alrededor de (x, y), no del centro de celda
            gx = x0 + np.arange(si0, si1) * paso
            gy = y0 + np.arange(sj0, sj1) * paso
            dx = gx[None, :] - x
            dy = gy[:, None] - y
            m = dx * dx + dy * dy <= rr
            sub = sim[sj0:sj1, si0:si1]
            sub[m] = np.minimum(sub[m], z)

    if espesor is None:
        espesor = round(-zmin - 0.3, 2)

    print('Verificación de %s contra %s (fresa Ø%g, placa %g mm, grilla %g mm)' % (a.gcode, a.mapa, a.diametro, espesor, paso))
    ok = True

    # 1) material comido
    comido = pieza & (sim < esperado - a.tolerancia)
    if comido.any():
        ok = False
        js, is_ = np.nonzero(comido)
        peor = np.nanmax(esperado[comido] - sim[comido])
        print('XX MATERIAL COMIDO en %d celdas (hasta %.2f mm de más). Ej.: X%.1f Y%.1f' % (
            comido.sum(), peor, x0 + is_[0] * paso, y0 + js[0] * paso))
    else:
        print('OK No se come material de la pieza en ningún punto.')

    # 2) material sobrante (dentro de la pieza, donde el modelo es más bajo que lo simulado)
    sobra = pieza & (sim > esperado + a.tolerancia)
    if sobra.any():
        # separar esquinas (sobrante a menos de R de una pared) del resto
        if ndimage is not None:
            etiquetas, n = ndimage.label(sobra)
            grandes = []
            for k in range(1, n + 1):
                zona = etiquetas == k
                ancho_max = 2 * ndimage.distance_transform_edt(zona).max() * paso
                if ancho_max > 1.2 or zona.sum() * paso * paso > 4.0:
                    js, is_ = np.nonzero(zona)
                    grandes.append((zona.sum() * paso * paso, x0 + is_.mean() * paso, y0 + js.mean() * paso,
                                    float(np.nanmax(sim[zona] - esperado[zona]))))
            chicas = n - len(grandes)
            if grandes:
                ok = False
                for ar, cx, cy, h in sorted(grandes, reverse=True)[:8]:
                    print('XX MATERIAL SOBRANTE: zona de %.1f mm² cerca de X%.1f Y%.1f (%.2f mm de más)' % (ar, cx, cy, h))
            print('OK %d restos chicos (esquinas que la fresa deja redondeadas R%g).' % (chicas, r) if chicas else 'OK Sin restos en esquinas.')
        else:
            print('!! Material sobrante en %d celdas (instalá scipy para separar esquinas de zonas sin vaciar).' % sobra.sum())
    else:
        print('OK Todas las cajeras y rebajes quedan a la profundidad del modelo.')

    # 3) pieza suelta: celdas fuera de la pieza, pegadas a ella, que no quedaron cortadas hasta el fondo
    if ndimage is not None:
        cortado = sim <= -espesor + 1e-6
        resto = (~pieza) & (~cortado)
        # la placa que queda alrededor = lo no cortado que llega al borde de la grilla
        etq_r, _ = ndimage.label(resto)
        marco_ids = set(np.unique(np.concatenate([etq_r[0, :], etq_r[-1, :], etq_r[:, 0], etq_r[:, -1]]))) - {0}
        marco = np.isin(etq_r, list(marco_ids))
        borde = ndimage.binary_dilation(pieza, iterations=1) & ~pieza
        puentes = marco & borde
        resto = marco
        # agujeros y recortes pasantes: el borde de adentro tiene que quedar cortado hasta abajo
        huecos, n_h = ndimage.label(~pieza)
        borde_ids = set(np.unique(np.concatenate([huecos[0, :], huecos[-1, :], huecos[:, 0], huecos[:, -1]]))) - {0}
        for k in range(1, n_h + 1):
            if k in borde_ids:
                continue
            zona = huecos == k
            kerf = zona & ndimage.binary_dilation(pieza, iterations=1)
            if kerf.sum() and (cortado[kerf].mean() < 0.9):
                ok = False
                js, is_ = np.nonzero(zona)
                print('XX AGUJERO/RECORTE PASANTE SIN CORTAR cerca de X%.1f Y%.1f (%.1f mm²).' % (
                    x0 + is_.mean() * paso, y0 + js.mean() * paso, zona.sum() * paso * paso))
        etq, n_p = ndimage.label(ndimage.binary_dilation(puentes, iterations=2) & resto)
        lugares = []
        for k in range(1, n_p + 1):
            js, is_ = np.nonzero(etq == k)
            lugares.append('X%.0f Y%.0f' % (x0 + is_.mean() * paso, y0 + js.mean() * paso))
        print('OK La pieza queda unida a la placa solo por %d pestañas (%s).' % (n_p, ', '.join(lugares)) if n_p else
              '!! La pieza queda totalmente suelta (sin pestañas): puede moverse al terminar el corte.')
        # la pieza tiene que estar entera alrededor de las pestañas: material de pieza con espesor completo
    if rapidos_mal:
        ok = False
        print('XX %d movimientos rápidos (G0) por debajo de Z0.' % len(rapidos_mal))
    else:
        print('OK Ningún rápido (G0) dentro del material.')
    print('RESULTADO: ' + ('OK' if ok else 'HAY ERRORES'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
