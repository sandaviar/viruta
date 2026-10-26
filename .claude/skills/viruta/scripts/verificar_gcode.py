#!/usr/bin/env python3
# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
"""Simula uno o más códigos G con fresa plana y los compara contra el modelo (mapa de alturas).

El mapa (.mapa) lo escriben viruta_step.py y rhino_gcode.py: alturas de la pieza vista desde
arriba, en coordenadas de máquina con el origen en la esquina inferior izquierda y Z = 0 en la
cara de arriba. Si el código usa otro origen (centro de la pieza, o Z0 sobre la mesa), pasá el
corrimiento con --dx/--dy/--dz (lo que se sumó a las coordenadas al escribir el código).

Chequea:
  - MATERIAL COMIDO: la fresa baja más de lo que pide la pieza o se mete en ella (error grave).
  - MATERIAL SOBRANTE: zonas que tendrían que quedar más bajas (separa las esquinas redondeadas).
  - AGUJEROS PASANTES SIN CORTAR.
  - PESTAÑAS: por dónde queda unida la pieza a la placa.
  - RÁPIDOS (G0) dentro del material.

Uso:
  python verificar_gcode.py ARCHIVO.txt ARCHIVO.mapa [--diametro 6] [--espesor 9]
         [--extra OTRO.txt:3 ...] [--dx 0 --dy 0 --dz 0]
Requiere numpy (y scipy para agrupar zonas y contar pestañas).
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
    partes = txt[txt.find('MAPA '):].split()
    x0, y0, paso = float(partes[1]), float(partes[2]), float(partes[3])
    nx, ny = int(partes[4]), int(partes[5])
    raw = zlib.decompress(base64.b64decode(partes[6]))
    vals = np.array(struct.unpack('<%dh' % (nx * ny), raw), dtype=np.float64).reshape(ny, nx)
    z = vals / 100.0
    z[vals <= -31999] = np.nan
    return x0, y0, paso, z


def leer_movimientos(path, dx=0.0, dy=0.0, dz=0.0):
    """Movimientos lineales en coordenadas del mapa (se resta el corrimiento de origen)."""
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
            nx_ = d['X'] - dx if 'X' in d else x
            ny_ = d['Y'] - dy if 'Y' in d else y
            nz_ = d['Z'] - dz if 'Z' in d else z
            if modo in (2, 3):
                raise SystemExit('El verificador no simula arcos G2/G3 todavía.')
            movs.append((modo, x, y, z, nx_, ny_, nz_))
            x, y, z = nx_, ny_, nz_
    return movs


def simular(movs, sim, x0, y0, paso, r):
    """Baja la placa simulada con una fresa plana de radio r. Devuelve rápidos mal hechos y Z mínima."""
    ny, nx = sim.shape
    rc = int(math.ceil(r / paso)) + 1
    rr = (r - 0.02) ** 2  # disco apenas más chico: evita falsos positivos en celdas justo sobre la pared
    malos, zmin = [], 0.0
    for modo, xa, ya, za, xb, yb, zb in movs:
        if min(za, zb) >= 0:
            continue
        L = math.hypot(xb - xa, yb - ya)
        if modo == 0:
            if L > 1e-6 or zb < za:
                ci, cj = int(round((xb - x0) / paso)), int(round((yb - y0) / paso))
                libre = 0 <= ci < nx and 0 <= cj < ny and sim[cj, ci] <= zb + 1e-6
                if L > 1e-6 or not libre:
                    malos.append((xa, ya, za, xb, yb, zb))
            continue
        zmin = min(zmin, za, zb)
        n = max(1, int(math.ceil(L / (paso * 0.4))))
        for k in range(n + 1):
            t = k / n
            x, y, z = xa + (xb - xa) * t, ya + (yb - ya) * t, za + (zb - za) * t
            if z >= 0:
                continue
            ci, cj = int(round((x - x0) / paso)), int(round((y - y0) / paso))
            si0, si1 = max(ci - rc, 0), min(ci + rc + 1, nx)
            sj0, sj1 = max(cj - rc, 0), min(cj + rc + 1, ny)
            if si0 >= si1 or sj0 >= sj1:
                continue
            gx = x0 + np.arange(si0, si1) * paso
            gy = y0 + np.arange(sj0, sj1) * paso
            m = (gx[None, :] - x) ** 2 + (gy[:, None] - y) ** 2 <= rr
            sub = sim[sj0:sj1, si0:si1]
            sub[m] = np.minimum(sub[m], z)
    return malos, zmin


def verificar(pares, mapa_path, espesor=None, desplazamiento=(0.0, 0.0, 0.0), tolerancia=0.05, salida=print):
    """pares: [(archivo, diámetro), ...] en el orden en que se cortan. Devuelve True si no hay errores."""
    x0, y0, paso, esperado = leer_mapa(mapa_path)
    pieza = ~np.isnan(esperado)
    sim = np.zeros_like(esperado)
    malos, zmin = [], 0.0
    dx, dy, dz = desplazamiento
    for archivo, d in pares:
        m, zm = simular(leer_movimientos(archivo, dx, dy, dz), sim, x0, y0, paso, d / 2)
        malos += m
        zmin = min(zmin, zm)
    if not espesor:
        espesor = round(-zmin - 0.3, 2)
    rmin = min(d for _, d in pares) / 2
    salida('Verificación de %s contra %s (fresa%s %s, placa %g mm, grilla %g mm)' % (
        ', '.join(p for p, _ in pares), mapa_path, 's' if len(pares) > 1 else '',
        ' + '.join('Ø%g' % d for _, d in pares), espesor, paso))
    ok = True

    comido = pieza & (sim < esperado - tolerancia)
    if comido.any():
        ok = False
        js, is_ = np.nonzero(comido)
        salida('XX MATERIAL COMIDO en %d celdas (hasta %.2f mm de más). Ej.: X%.1f Y%.1f' % (
            comido.sum(), np.nanmax(esperado[comido] - sim[comido]), x0 + is_[0] * paso + dx, y0 + js[0] * paso + dy))
    else:
        salida('OK No se come material de la pieza en ningún punto.')

    sobra = pieza & (sim > esperado + tolerancia)
    if sobra.any() and ndimage is not None:
        etq, n = ndimage.label(sobra)
        grandes = []
        for k in range(1, n + 1):
            zona = etq == k
            ancho = 2 * ndimage.distance_transform_edt(zona).max() * paso
            if ancho > 1.2 or zona.sum() * paso * paso > 4.0:
                js, is_ = np.nonzero(zona)
                grandes.append((zona.sum() * paso * paso, x0 + is_.mean() * paso + dx, y0 + js.mean() * paso + dy,
                                float(np.nanmax(sim[zona] - esperado[zona]))))
        if grandes:
            ok = False
            for ar, cx, cy, h in sorted(grandes, reverse=True)[:8]:
                salida('XX MATERIAL SOBRANTE: zona de %.1f mm² cerca de X%.1f Y%.1f (%.2f mm de más)' % (ar, cx, cy, h))
        chicas = n - len(grandes)
        salida('OK %d restos chicos (esquinas que la fresa deja redondeadas R%g).' % (chicas, rmin) if chicas else 'OK Sin restos en esquinas.')
    elif sobra.any():
        salida('!! Material sobrante en %d celdas (instalá scipy para separar esquinas de zonas sin vaciar).' % sobra.sum())
    else:
        salida('OK Todas las cajeras y rebajes quedan a la profundidad del modelo.')

    if ndimage is not None:
        cortado = sim <= -espesor + 1e-6
        resto = (~pieza) & (~cortado)
        etq_r, _ = ndimage.label(resto)
        borde_ids = set(np.unique(np.concatenate([etq_r[0, :], etq_r[-1, :], etq_r[:, 0], etq_r[:, -1]]))) - {0}
        marco = np.isin(etq_r, list(borde_ids))
        huecos, n_h = ndimage.label(~pieza)
        h_borde = set(np.unique(np.concatenate([huecos[0, :], huecos[-1, :], huecos[:, 0], huecos[:, -1]]))) - {0}
        for k in range(1, n_h + 1):
            if k in h_borde:
                continue
            zona = huecos == k
            kerf = zona & ndimage.binary_dilation(pieza, iterations=1)
            # una celda de tolerancia: la grilla puede caer justo entre la pared y el filo de la fresa
            cortado_t = ndimage.binary_dilation(cortado, iterations=1) & zona
            if kerf.sum() and cortado_t[kerf].mean() < 0.9:
                ok = False
                js, is_ = np.nonzero(zona)
                salida('XX AGUJERO/RECORTE PASANTE SIN CORTAR cerca de X%.1f Y%.1f (%.1f mm²).' % (
                    x0 + is_.mean() * paso + dx, y0 + js.mean() * paso + dy, zona.sum() * paso * paso))
        borde = ndimage.binary_dilation(pieza, iterations=1) & ~pieza
        afuera = np.isin(huecos, list(h_borde))
        kerf_ext = borde & afuera
        if kerf_ext.sum():
            frac = (ndimage.binary_dilation(cortado, iterations=1) & afuera)[kerf_ext].mean()
            if frac < 0.6:
                ok = False
                salida('XX EL CONTORNO EXTERIOR NO ATRAVIESA LA PLACA: solo el %d %% del borde queda cortado a fondo.' % round(frac * 100))
        puentes = marco & borde
        etq, n_p = ndimage.label(ndimage.binary_dilation(puentes, iterations=2) & marco)
        lugares = []
        for k in range(1, n_p + 1):
            js, is_ = np.nonzero(etq == k)
            lugares.append('X%.0f Y%.0f' % (x0 + is_.mean() * paso + dx, y0 + js.mean() * paso + dy))
        salida('OK La pieza queda unida a la placa solo por %d pestañas (%s).' % (n_p, ', '.join(lugares)) if n_p else
               '!! La pieza queda totalmente suelta (sin pestañas): sujetala con tornillos o vacío.')
    if malos:
        ok = False
        salida('XX %d movimientos rápidos (G0) dentro del material.' % len(malos))
    else:
        salida('OK Ningún rápido (G0) dentro del material.')
    salida('RESULTADO: ' + ('OK' if ok else 'HAY ERRORES'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archivo')
    ap.add_argument('mapa')
    ap.add_argument('--diametro', type=float, default=6.0)
    ap.add_argument('--espesor', type=float, default=None, help='espesor de la placa (por defecto, se deduce)')
    ap.add_argument('--extra', action='append', default=[], help='otro archivo de la misma pieza, ARCHIVO:DIAMETRO')
    ap.add_argument('--dx', type=float, default=0.0)
    ap.add_argument('--dy', type=float, default=0.0)
    ap.add_argument('--dz', type=float, default=0.0)
    ap.add_argument('--tolerancia', type=float, default=0.05)
    a = ap.parse_args()
    pares = [(a.archivo, a.diametro)]
    for e in a.extra:
        f, d = e.rsplit(':', 1)
        pares.append((f, float(d)))
    ok = verificar(pares, a.mapa, a.espesor, (a.dx, a.dy, a.dz), a.tolerancia)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
