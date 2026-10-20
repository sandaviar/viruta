#!/usr/bin/env python3
"""Limpia el código G postprocesado (Mach3) para el router CNC de UNAHUR.

Equivale a la limpieza que pide la cátedra:
  - arranca en la primera línea de husillo encendido (ej. "S18000 M3")
  - saca comentarios entre paréntesis, líneas vacías, cambios de herramienta (T# M6) y G28
  - deja el final en M5 / M30

Uso:
  python limpiar_gcode.py ARCHIVO.tap [ARCHIVO2.nc ...] [-o CARPETA_SALIDA]
  python limpiar_gcode.py CARPETA_CON_TAP -o CARPETA_SALIDA

Genera un .txt por archivo (mismo nombre), con fin de línea Windows (CRLF).
"""
import argparse
import glob
import os
import re
import sys

EXTS = ('.tap', '.nc', '.ngc', '.txt', '.gcode')
RE_SPINDLE = re.compile(r'^(N\d+\s+)?S\d+\s*M0?3\b', re.I)


def limpiar(lineas):
    lineas = [l.rstrip() for l in lineas]
    try:
        ini = next(i for i, l in enumerate(lineas) if RE_SPINDLE.match(l.strip()))
    except StopIteration:
        raise ValueError('no se encontró la línea de husillo (ej. "S18000 M3")')
    out = []
    for l in lineas[ini:]:
        s = l.strip()
        if not s or s == '%':
            continue
        if '(' in s:
            s = re.sub(r'\([^)]*\)', '', s).strip()
            if not s:
                continue
        if re.match(r'^(N\d+\s+)?T\d+\s*M0?6\b', s, re.I):
            continue
        if 'G28' in s.upper():
            continue
        out.append(s)
    # sacar G90 sueltos que quedan al final después de quitar G28
    while len(out) >= 2 and out[-2].upper() in ('G90', 'G91'):
        out.pop(-2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('entradas', nargs='+', help='archivos o carpetas')
    ap.add_argument('-o', '--salida', help='carpeta de salida (por defecto, la misma)')
    a = ap.parse_args()

    archivos = []
    for e in a.entradas:
        if os.path.isdir(e):
            for ext in ('.tap', '.nc', '.ngc', '.gcode'):  # .txt no, para no re-limpiar
                archivos += sorted(glob.glob(os.path.join(e, '*' + ext)))
        else:
            archivos.append(e)
    if not archivos:
        sys.exit('No hay archivos para limpiar.')

    for f in archivos:
        dst_dir = a.salida or os.path.dirname(os.path.abspath(f))
        os.makedirs(dst_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(dst_dir, base + '.txt')
        if os.path.abspath(dst) == os.path.abspath(f):
            dst = os.path.join(dst_dir, base + '_limpio.txt')
        with open(f, encoding='utf-8', errors='replace') as fh:
            out = limpiar(fh.readlines())
        with open(dst, 'w', newline='\r\n') as fh:
            fh.write('\n'.join(out) + '\n')
        print(f'{os.path.basename(dst)}: {len(out)} líneas | empieza "{out[0]}" | termina "{out[-1]}"')


if __name__ == '__main__':
    main()
