# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
# Generador de código G desde Rhino 8 para router CNC (perfil Taller 5 UNAHUR).
# Se ejecuta DENTRO de Rhino (herramienta run_python del MCP de Rhino, o ScriptEditor).
#
# Qué hace, por cada pieza (polisuperficie cerrada / extrusión) del documento:
#   1. La acuesta (espesor en Z), la gira para que X sea el lado corto y pone el
#      origen en la esquina inferior izquierda de la CARA SUPERIOR.
#   2. Corta la pieza a media altura y saca los contornos: el más grande es el
#      exterior, los demás son agujeros / recortes pasantes.
#   3. Desfasa los contornos el radio de la fresa (afuera el exterior, adentro los agujeros).
#   4. Pasadas del 50 % del Ø hasta espesor + 0,3 mm, repartidas parejas.
#   5. Primero lo interno, el contorno exterior al final, con pestañas en tramos rectos.
#   6. Escribe un .txt por pieza en CARPETA_SALIDA (por defecto el Escritorio), limpio:
#      arranca en S18000 M3, sin comentarios, sin T# M6, sin G28, termina en M5 / M30.
#
# Limitaciones (avisa en el informe): no hace cajeras ni rebajes a media profundidad,
# no hace grabados; los agujeros más chicos que la fresa se saltean.

import math
import os
import System
import System.Drawing
import Rhino
import Rhino.Geometry as rg
from Rhino.Geometry.Intersect import Intersection

# ---------------- CONFIGURACIÓN (perfil Taller 5) ----------------
CFG = globals().get("CFG", {}) or {}
DIAMETRO = float(CFG.get("diametro", 6.0))        # fresa plana Ø6
HUSILLO = int(CFG.get("husillo", 18000))           # S18000
AVANCE = float(CFG.get("avance", 2000.0))          # F2000 corte
AVANCE_BAJADA = float(CFG.get("avance_bajada", 2000.0))
PASO = float(CFG.get("paso", DIAMETRO * 0.5))      # 50 % del Ø
EXTRA = float(CFG.get("extra", 0.3))               # pasante: espesor + 0,3
Z_SEGURO = float(CFG.get("z_seguro", 10.0))        # altura de traslados
PESTANA_LARGO = float(CFG.get("pestana_largo", 8.0))
PESTANA_ALTO = CFG.get("pestana_alto", None)       # None = ≈ 1/3 del espesor
PESTANAS_CANT = CFG.get("pestanas", None)          # None = según tamaño
NOMBRES = CFG.get("nombres", None)                 # lista de nombres de objeto a procesar (None = todas)
CARPETA_SALIDA = CFG.get("carpeta", None) or System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
DEVOLVER_CODIGO = bool(CFG.get("devolver_codigo", False))
ESCRIBIR = bool(CFG.get("escribir", True))          # False = vista previa, no escribe el .txt
DIBUJAR = bool(CFG.get("dibujar", True))            # dibuja trayectorias y pestañas en la capa "Viruta"
TOL = 0.01

doc = __rhino_doc__
R = DIAMETRO / 2.0


def obtener_capa(nombre):
    i = doc.Layers.FindByFullPath(nombre, -1)
    if i >= 0:
        return i
    ly = Rhino.DocObjects.Layer()
    ly.Name = nombre
    ly.Color = System.Drawing.Color.FromArgb(230, 90, 20)
    return doc.Layers.Add(ly)


def limpiar_dibujos():
    i = doc.Layers.FindByFullPath("Viruta", -1)
    if i >= 0:
        for o in doc.Objects.FindByLayer(doc.Layers[i]) or []:
            doc.Objects.Delete(o, True)


def fmt(v):
    s = "%.3f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def obtener_piezas():
    piezas = []
    for o in doc.Objects:
        if not o.Visible or o.IsDeleted:
            continue
        g = o.Geometry
        if isinstance(g, rg.Extrusion):
            g = g.ToBrep(True)
        if not isinstance(g, rg.Brep) or not g.IsSolid:
            continue
        nombre = o.Attributes.Name or ""
        if NOMBRES and nombre not in NOMBRES:
            continue
        piezas.append((nombre, g.DuplicateBrep()))
    return piezas


def orientar(brep):
    """Acuesta la pieza (dim. menor en Z), X = lado corto, origen esquina inf. izq. cara superior.
    Devuelve también la transformación aplicada (para dibujar las trayectorias sobre la pieza original)."""
    total = rg.Transform.Identity
    bb = brep.GetBoundingBox(True)
    d = bb.Diagonal
    dims = [d.X, d.Y, d.Z]
    menor = dims.index(min(dims))
    c = bb.Center
    pasos = []
    if menor == 0:
        pasos.append(rg.Transform.Rotation(math.pi / 2, rg.Vector3d.YAxis, c))
    elif menor == 1:
        pasos.append(rg.Transform.Rotation(math.pi / 2, rg.Vector3d.XAxis, c))
    for t in pasos:
        brep.Transform(t)
        total = t * total
    bb = brep.GetBoundingBox(True)
    if bb.Diagonal.X > bb.Diagonal.Y + 1e-6:
        t = rg.Transform.Rotation(math.pi / 2, rg.Vector3d.ZAxis, bb.Center)
        brep.Transform(t)
        total = t * total
        bb = brep.GetBoundingBox(True)
    t = rg.Transform.Translation(-bb.Min.X, -bb.Min.Y, -bb.Max.Z)
    brep.Transform(t)
    total = t * total
    bb = brep.GetBoundingBox(True)
    return brep, bb, total


def avisos_geometria(brep, espesor):
    av = []
    for f in brep.Faces:
        ok, pl = f.TryGetPlane(0.01)
        if ok and abs(abs(pl.Normal.Z) - 1) < 1e-3:
            z = pl.Origin.Z
            if -espesor + 0.05 < z < -0.05:
                av.append("Hay una cara horizontal a %s mm de profundidad (cajera o rebaje): este generador solo hace cortes pasantes, no se mecanizó." % fmt(-z))
                break
    return av


def area(c):
    amp = rg.AreaMassProperties.Compute(c)
    return amp.Area if amp else 0.0


def desfasar(c, hacia_afuera):
    plano = rg.Plane.WorldXY
    a0 = area(c)
    estilo = rg.CurveOffsetCornerStyle.Round if hacia_afuera else rg.CurveOffsetCornerStyle.Sharp
    for signo in (1, -1):
        res = c.Offset(plano, signo * R, TOL, estilo)
        if not res:
            continue
        uni = rg.Curve.JoinCurves(res, TOL * 5)
        if len(uni) != 1 or not uni[0].IsClosed:
            continue
        a1 = area(uni[0])
        if (hacia_afuera and a1 > a0) or (not hacia_afuera and 0 < a1 < a0):
            return uni[0]
    return None


def a_polilinea(c):
    pc = c.ToPolyline(TOL, math.radians(3), 0, 0)
    ok, pl = pc.TryGetPolyline()
    pts = [rg.Point3d(p.X, p.Y, 0) for p in pl]
    if pts[0].DistanceTo(pts[-1]) > 1e-6:
        pts.append(pts[0])
    return pts


def orientar_sentido(c, horario):
    o = c.ClosedCurveOrientation(rg.Vector3d.ZAxis)
    es_horario = (o == rg.CurveOrientation.Clockwise)
    if es_horario != horario:
        c.Reverse()
    return c


def esquinas_vivas(c, es_exterior):
    """Esquinas interiores (cóncavas) de la pieza que la fresa deja redondeadas con radio R."""
    cc = c.DuplicateCurve()
    o = cc.ClosedCurveOrientation(rg.Vector3d.ZAxis)
    antihorario = (o == rg.CurveOrientation.CounterClockwise)
    if antihorario != es_exterior:  # material siempre a la izquierda
        cc.Reverse()
    pts = a_polilinea(cc)
    n = len(pts) - 1
    res = []
    for i in range(n):
        p_prev = pts[i - 1] if i > 0 else pts[n - 1]
        p, p_next = pts[i], pts[i + 1]
        v1, v2 = p - p_prev, p_next - p
        if v1.Length < 1e-6 or v2.Length < 1e-6:
            continue
        cruz = v1.X * v2.Y - v1.Y * v2.X
        if cruz < 0 and rg.Vector3d.VectorAngle(v1, v2) > math.radians(20):
            res.append(p)
    return res


def tramos_rectos(pts):
    """Agrupa segmentos casi colineales. Devuelve [(s_ini, s_fin)] en largo de recorrido."""
    tramos = []
    s = 0.0
    ini = 0.0
    prev = None
    for i in range(len(pts) - 1):
        v = pts[i + 1] - pts[i]
        L = v.Length
        if L < 1e-9:
            continue
        v.Unitize()
        if prev is not None and rg.Vector3d.VectorAngle(prev, v) > math.radians(1.0):
            tramos.append((ini, s))
            ini = s
        prev = v
        s += L
    tramos.append((ini, s))
    return tramos, s


def cant_pestanas(lado_mayor, perimetro):
    if PESTANAS_CANT is not None:
        return int(PESTANAS_CANT)
    if lado_mayor < 80:
        return 2
    if lado_mayor <= 300:
        return 4
    if lado_mayor <= 600:
        return 6
    return max(8, int(math.ceil(perimetro / 200.0)))


def ubicar_pestanas(pts, n):
    hueco = PESTANA_LARGO + DIAMETRO
    margen = DIAMETRO
    tramos, total = tramos_rectos(pts)
    utiles = [(a, b) for a, b in tramos if (b - a) >= hueco + 2 * margen]
    if not utiles:  # pieza toda curva: repartir parejo
        return [((k + 0.5) * total / n - hueco / 2, (k + 0.5) * total / n + hueco / 2) for k in range(n)], total, False
    largos = [b - a for a, b in utiles]
    tot = sum(largos)
    cuotas = [n * L / tot for L in largos]
    asign = [int(math.floor(q)) for q in cuotas]
    resto = n - sum(asign)
    orden = sorted(range(len(utiles)), key=lambda i: (cuotas[i] - asign[i], largos[i]), reverse=True)
    for i in orden[:resto]:
        asign[i] += 1
    centros = []
    for (a, b), k in zip(utiles, asign):
        if k == 0:
            continue
        a2, b2 = a + margen + hueco / 2, b - margen - hueco / 2
        maxk = max(1, int((b2 - a2) // (hueco + DIAMETRO)) + 1)
        k = min(k, maxk)
        for j in range(k):
            centros.append(a2 + (b2 - a2) * (j + 0.5) / k if k > 1 else (a2 + b2) / 2)
    centros.sort()
    return [(cc - hueco / 2, cc + hueco / 2) for cc in centros], total, True


def recorrido_con_pestanas(pts, z, z_pestana, intervalos):
    """Devuelve lista de (x,y,z) siguiendo pts a profundidad z, subiendo a z_pestana en los intervalos."""
    out = []
    usar = z < z_pestana - 1e-6 and intervalos
    cortes = sorted(set([x for iv in intervalos for x in iv])) if usar else []

    def en_pestana(s):
        return usar and any(a < s < b for a, b in intervalos)

    s = 0.0
    out.append((pts[0].X, pts[0].Y, z_pestana if en_pestana(0.0) else z))
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        L = p0.DistanceTo(p1)
        if L < 1e-9:
            continue
        internos = [c for c in cortes if s < c < s + L]
        for c in internos:
            t = (c - s) / L
            x = p0.X + (p1.X - p0.X) * t
            y = p0.Y + (p1.Y - p0.Y) * t
            antes = en_pestana(c - 1e-6)
            despues = en_pestana(c + 1e-6)
            out.append((x, y, z_pestana if antes else z))
            out.append((x, y, z_pestana if despues else z))
        s += L
        out.append((p1.X, p1.Y, z_pestana if en_pestana(s) else z))
    return out


def niveles(prof):
    n = int(math.ceil(prof / PASO - 1e-9))
    return [-prof * k / n for k in range(1, n + 1)]


def mecanizar_contorno(lineas, pts, zs, z_pestana=None, intervalos=None):
    x0, y0 = pts[0].X, pts[0].Y
    if lineas[-1] != "G0 Z%s" % fmt(Z_SEGURO):
        lineas.append("G0 Z%s" % fmt(Z_SEGURO))
    lineas.append("G0 X%s Y%s" % (fmt(x0), fmt(y0)))
    lineas.append("G0 Z1")
    largo = 0.0
    cz = 1.0
    cx, cy = x0, y0
    for z in zs:
        camino = recorrido_con_pestanas(pts, z, z_pestana if z_pestana is not None else -1e9, intervalos or [])
        zi = camino[0][2]
        lineas.append("G1 Z%s F%s" % (fmt(zi), fmt(AVANCE_BAJADA)))
        largo += abs(cz - zi)
        cz = zi
        primero = True
        for (x, y, zz) in camino[1:]:
            if abs(x - cx) < 1e-6 and abs(y - cy) < 1e-6 and abs(zz - cz) < 1e-6:
                continue
            partes = ["G1"]
            if abs(x - cx) > 1e-6:
                partes.append("X" + fmt(x))
            if abs(y - cy) > 1e-6:
                partes.append("Y" + fmt(y))
            if abs(zz - cz) > 1e-6:
                partes.append("Z" + fmt(zz))
            if primero:
                partes.append("F" + fmt(AVANCE))
                primero = False
            lineas.append(" ".join(partes))
            largo += math.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (zz - cz) ** 2)
            cx, cy, cz = x, y, zz
    lineas.append("G0 Z%s" % fmt(Z_SEGURO))
    return largo


def procesar(nombre, brep, idx):
    informe = []
    brep, bb, xf = orientar(brep)
    ok_inv, xf_inv = xf.TryGetInverse()
    dibujos = []  # polilíneas en coordenadas de máquina, para dibujar sobre la pieza
    espesor = bb.Diagonal.Z
    ancho, largo_p = bb.Diagonal.X, bb.Diagonal.Y
    prof = espesor + EXTRA
    alto_pest = float(PESTANA_ALTO) if PESTANA_ALTO is not None else max(1.0, round(espesor / 3.0 * 2) / 2.0)
    z_pest = -prof + alto_pest
    informe += avisos_geometria(brep, espesor)

    ok, curvas, _ = Intersection.BrepPlane(brep, rg.Plane(rg.Point3d(0, 0, -espesor / 2), rg.Vector3d.ZAxis), TOL)
    curvas = rg.Curve.JoinCurves(curvas, TOL * 5) if curvas else []
    curvas = [c for c in curvas if c.IsClosed]
    if not curvas:
        return None, ["No se pudo leer el contorno de la pieza."], None
    for c in curvas:
        c.Transform(rg.Transform.Translation(0, 0, espesor / 2))
    curvas.sort(key=area, reverse=True)
    exterior, interiores = curvas[0], curvas[1:]

    lineas = ["S%d M3" % HUSILLO, "G90 G17 G21"]
    largo_total = 0.0
    zs = niveles(prof)

    hechos = 0
    for k, c in enumerate(interiores):
        d = desfasar(c, False)
        if d is None:
            bbc = c.GetBoundingBox(True)
            informe.append("Agujero/recorte interior en X%s Y%s (%s × %s mm) más chico que la fresa Ø%s: no se puede cortar, se salteó." % (
                fmt(bbc.Center.X), fmt(bbc.Center.Y), fmt(bbc.Diagonal.X), fmt(bbc.Diagonal.Y), fmt(DIAMETRO)))
            continue
        d = orientar_sentido(d, horario=False)  # interior: antihorario (concordante con M3)
        pts = a_polilinea(d)
        largo_total += mecanizar_contorno(lineas, pts, zs)
        dibujos.append(pts)
        hechos += 1

    d = desfasar(exterior, True)
    if d is None:
        return None, informe + ["No se pudo desfasar el contorno exterior."], None
    d = orientar_sentido(d, horario=True)  # exterior: horario (concordante con M3)
    pts = a_polilinea(d)
    tramos, perim = tramos_rectos(pts)
    # arrancar al principio del tramo recto más largo (la costura no cae en una pestaña)
    mejor = max(tramos, key=lambda t: t[1] - t[0])
    s = 0.0
    idx_ini = 0
    for i in range(len(pts) - 1):
        if abs(s - mejor[0]) < 1e-6:
            idx_ini = i
            break
        s += pts[i].DistanceTo(pts[i + 1])
    base = pts[:-1]
    base = base[idx_ini:] + base[:idx_ini]
    pts = base + [base[0]]

    vivas = []
    for c in [exterior] + interiores:
        vivas += esquinas_vivas(c, c is exterior)
    if vivas:
        ej = ", ".join("X%s Y%s" % (fmt(p.X), fmt(p.Y)) for p in vivas[:6])
        informe.append("%d esquinas interiores vivas (%s%s): la fresa Ø%s las deja redondeadas R%s. Si son encastres, agregá descargas (dogbones) en Rhino antes de cortar." % (
            len(vivas), ej, "…" if len(vivas) > 6 else "", fmt(DIAMETRO), fmt(R)))

    n = cant_pestanas(max(ancho, largo_p), perim)
    intervalos, perim, en_rectas = ubicar_pestanas(pts, n)
    largo_total += mecanizar_contorno(lineas, pts, zs, z_pest, intervalos)
    dibujos.append(pts)
    lineas += ["M5", "M30"]

    # posiciones de pestañas para el informe
    pos = []
    for a, b in intervalos:
        cpar = (a + b) / 2
        s = 0.0
        for i in range(len(pts) - 1):
            L = pts[i].DistanceTo(pts[i + 1])
            if s + L >= cpar:
                t = (cpar - s) / L
                pos.append((pts[i].X + (pts[i + 1].X - pts[i].X) * t, pts[i].Y + (pts[i + 1].Y - pts[i].Y) * t))
                break
            s += L

    nombre_arch = (nombre or "pieza_%d" % idx).strip().replace(" ", "_")
    nombre_arch = "".join(ch for ch in nombre_arch if ch.isalnum() or ch in "_-.")
    ruta = os.path.join(CARPETA_SALIDA, nombre_arch + ".txt")
    if ESCRIBIR:
        with open(ruta, "w", newline="\r\n") as fh:
            fh.write("\n".join(lineas) + "\n")

    if DIBUJAR and ok_inv:
        capa = obtener_capa("Viruta")
        at = Rhino.DocObjects.ObjectAttributes()
        at.LayerIndex = capa
        at.Name = "viruta_" + nombre_arch
        for p in dibujos:
            pl = rg.PolylineCurve(p)
            pl.Transform(xf_inv)
            doc.Objects.AddCurve(pl, at)
        for x, y in pos:
            pt = rg.Point3d(x, y, 0)
            pt.Transform(xf_inv)
            doc.Objects.AddTextDot("P", pt, at)
        doc.Views.Redraw()

    minutos = largo_total / AVANCE * 1.1
    resumen = {
        "archivo": ruta if ESCRIBIR else "(vista previa: no se escribió)",
        "pieza_mm": "%s (X) x %s (Y) x %s (espesor)" % (fmt(ancho), fmt(largo_p), fmt(espesor)),
        "profundidad": fmt(prof),
        "pasadas": [fmt(z) for z in zs],
        "interiores_cortados": hechos,
        "pestanas": "%d de %s x %s mm (%s)" % (len(intervalos), fmt(PESTANA_LARGO), fmt(alto_pest), "en tramos rectos" if en_rectas else "pieza curva: repartidas parejo"),
        "pestanas_xy": ["X%s Y%s" % (fmt(x), fmt(y)) for x, y in pos],
        "lineas": len(lineas),
        "tiempo_min": round(minutos, 1),
    }
    return resumen, informe, ("\n".join(lineas) if DEVOLVER_CODIGO else None)


def main():
    if DIBUJAR:
        limpiar_dibujos()
    piezas = obtener_piezas()
    if not piezas:
        print("No encontré piezas sólidas (polisuperficies cerradas) visibles en el documento.")
        return
    for i, (nombre, b) in enumerate(piezas, 1):
        res, avisos, codigo = procesar(nombre, b, i)
        print("=== %s ===" % (nombre or "pieza_%d" % i))
        if res:
            for k, v in res.items():
                print("%s: %s" % (k, v))
        for a in avisos:
            print("AVISO: " + a)
        if codigo:
            print("---CODIGO---")
            print(codigo)
            print("---FIN---")


main()
