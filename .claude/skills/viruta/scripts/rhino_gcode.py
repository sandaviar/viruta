# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
# Generador de código G desde Rhino 8 para router CNC (perfil Taller 5 UNAHUR).
# Se ejecuta DENTRO de Rhino (herramienta run_python del MCP de Rhino, o ScriptEditor).
#
# Mecanizado 2,5D desde arriba (paredes verticales y fondos planos), por cada pieza
# (polisuperficie cerrada / extrusión) del documento:
#   1. La acuesta (espesor en Z), la gira para que X sea el lado corto y pone el
#      origen en la esquina inferior izquierda de la CARA SUPERIOR.
#   2. Detecta los fondos planos (cajeras, rebajes, escalones) y su profundidad EXACTA.
#   3. Vacía cada cajera / rebaje (zigzag + pasada de pared) bajando por escalones
#      hasta el fondo justo, con islas respetadas y entrada en rampa.
#   4. Agujeros y recortes pasantes: contorno por dentro (o taladrado si el agujero es
#      del tamaño de la fresa), arrancando desde la profundidad ya vaciada.
#   5. Contorno exterior al final, con pestañas en tramos rectos.
#   6. Escribe un .txt por pieza en CARPETA_SALIDA (por defecto el Escritorio), limpio:
#      arranca en S18000 M3, sin comentarios, sin T# M6, sin G28, termina en M5 / M30.
#
# Avisa: esquinas interiores vivas, zonas más angostas que la fresa, caras inclinadas
# o curvas (no 2,5D) y partes que solo se pueden hacer dando vuelta la placa.

import math
import os
import base64
import zlib
import struct
import bisect
import System
import System.Drawing
import Rhino
import Rhino.Geometry as rg
from Rhino.Geometry.Intersect import Intersection

# ---------------- CONFIGURACIÓN (perfil Taller 5) ----------------
CFG = globals().get("CFG", {}) or {}
DIAMETRO = float(CFG.get("diametro", 6.0))          # fresa plana Ø6
HUSILLO = int(CFG.get("husillo", 18000))             # S18000
AVANCE = float(CFG.get("avance", 2000.0))            # F2000 corte
AVANCE_BAJADA = float(CFG.get("avance_bajada", 2000.0))
PASO = float(CFG.get("paso", DIAMETRO * 0.5))        # paso vertical: 50 % del Ø
PASO_LATERAL = float(CFG.get("paso_lateral", DIAMETRO * 0.4))  # vaciado: 40 % del Ø
RAMPA_GRADOS = float(CFG.get("rampa_grados", 10.0))  # entrada en rampa
EXTRA = float(CFG.get("extra", 0.3))                 # pasante: espesor + 0,3
Z_SEGURO = float(CFG.get("z_seguro", 10.0))          # altura inicial / final
Z_LIBRE = float(CFG.get("z_libre", 2.0))             # traslados entre operaciones
PESTANA_LARGO = float(CFG.get("pestana_largo", 8.0))
PESTANA_ALTO = CFG.get("pestana_alto", None)         # None = ≈ 1/3 del espesor
PESTANAS_CANT = CFG.get("pestanas", None)            # None = según tamaño
NOMBRES = CFG.get("nombres", None)                   # nombres de objeto a procesar (None = todas)
CARPETA_SALIDA = CFG.get("carpeta", None) or System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
ESCRIBIR = bool(CFG.get("escribir", True))           # False = vista previa
DIBUJAR = bool(CFG.get("dibujar", True))             # trayectorias en la capa "Viruta"
DEVOLVER_CODIGO = bool(CFG.get("devolver_codigo", False))
MAPA = CFG.get("mapa_alturas", None)                 # paso de grilla (mm): escribe NOMBRE.mapa para verificar_gcode.py
TOL = 0.01
PLANO = rg.Plane.WorldXY

doc = __rhino_doc__
R = DIAMETRO / 2.0


# ---------------- utilidades ----------------
def fmt(v):
    s = "%.3f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def area(c):
    amp = rg.AreaMassProperties.Compute(c)
    return amp.Area if amp else 0.0


def contiene(c, p):
    return c.Contains(p, PLANO, 0.001) == rg.PointContainment.Inside


def centro(c):
    return c.GetBoundingBox(True).Center


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
    """Acuesta la pieza, X = lado corto, origen esquina inf. izq. de la cara superior. Devuelve la transformación."""
    total = rg.Transform.Identity
    bb = brep.GetBoundingBox(True)
    dims = [bb.Diagonal.X, bb.Diagonal.Y, bb.Diagonal.Z]
    menor = dims.index(min(dims))
    t = None
    if menor == 0:
        t = rg.Transform.Rotation(math.pi / 2, rg.Vector3d.YAxis, bb.Center)
    elif menor == 1:
        t = rg.Transform.Rotation(math.pi / 2, rg.Vector3d.XAxis, bb.Center)
    if t is not None:
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
    return brep, brep.GetBoundingBox(True), total


def seccion(brep, z):
    ok, cs, _ = Intersection.BrepPlane(brep, rg.Plane(rg.Point3d(0, 0, z), rg.Vector3d.ZAxis), TOL)
    cs = rg.Curve.JoinCurves(cs, TOL * 5) if cs else []
    cs = [c for c in cs if c.IsClosed]
    for c in cs:
        c.Transform(rg.Transform.Translation(0, 0, -z))
    return cs


def caras_material(curvas):
    """[(exterior, [huecos])] del material en una sección."""
    if not curvas:
        return []
    breps = rg.Brep.CreatePlanarBreps(curvas, TOL) or []
    out = []
    for b in breps:
        for f in b.Faces:
            ext, hs = None, []
            for lp in f.Loops:
                c = lp.To3dCurve()
                if lp.LoopType == rg.BrepLoopType.Outer:
                    ext = c
                elif lp.LoopType == rg.BrepLoopType.Inner:
                    hs.append(c)
            if ext is not None:
                out.append((ext, hs))
    return out


def offset_cerrada(c, dist, hacia_afuera):
    """Desfase de una curva cerrada, verificado: ningún punto queda a menos de `dist` de la original."""
    a0 = area(c)
    for signo in (1, -1):
        try:
            res = c.Offset(PLANO, signo * dist, TOL, rg.CurveOffsetCornerStyle.Round)
        except Exception:
            res = None
        if not res:
            continue
        uni = rg.Curve.JoinCurves(res, TOL * 5)
        if not uni or any(not u.IsClosed for u in uni):
            continue
        tot = sum(area(u) for u in uni)
        if hacia_afuera and tot <= a0:
            continue
        if not hacia_afuera and not (0 < tot < a0):
            continue
        if all(_offset_valido(u, c, dist, hacia_afuera) for u in uni):
            return list(uni)
    return []


def _offset_valido(u, c, dist, hacia_afuera):
    dom = u.Domain
    for i in range(40):
        p = u.PointAt(dom.ParameterAt(i / 40.0))
        ok, tc = c.ClosestPoint(p)
        if not ok or p.DistanceTo(c.PointAt(tc)) < dist - 0.02:
            return False
        if contiene(c, p) == hacia_afuera:
            return False
    return True


def a_polilinea(c):
    pc = c.ToPolyline(TOL, math.radians(3), 0, 0)
    ok, pl = pc.TryGetPolyline()
    return [rg.Point3d(p.X, p.Y, 0) for p in pl]


def densificar(pts, paso):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = a.DistanceTo(b)
        n = max(1, int(math.ceil(L / paso)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * (float(k) / n))
    return out


def simplificar(pts, cerrado):
    """Saca puntos intermedios alineados (desvío < 0,005 mm)."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b = out[-1], pts[i + 1]
        p = pts[i]
        ab = b - a
        L = ab.Length
        if L < 1e-9:
            continue
        d = abs((p.X - a.X) * ab.Y - (p.Y - a.Y) * ab.X) / L
        if d > 0.005:
            out.append(p)
    out.append(pts[-1])
    return out


def sentido_pts(pts, horario):
    a2 = sum(p.X * q.Y - q.X * p.Y for p, q in zip(pts, pts[1:] + pts[:1]))
    if (a2 < 0) != horario:
        pts = list(reversed(pts))
    return pts


def sentido(c, horario):
    es_h = c.ClosedCurveOrientation(rg.Vector3d.ZAxis) == rg.CurveOrientation.Clockwise
    if es_h != horario:
        c.Reverse()
    return c


def esquinas_vivas(c, es_exterior):
    """Esquinas interiores (cóncavas) del material, que la fresa deja redondeadas R."""
    cc = c.DuplicateCurve()
    antihorario = cc.ClosedCurveOrientation(rg.Vector3d.ZAxis) == rg.CurveOrientation.CounterClockwise
    if antihorario != es_exterior:
        cc.Reverse()
    pts = a_polilinea(cc)
    if pts[0].DistanceTo(pts[-1]) > 1e-6:
        pts.append(pts[0])
    n = len(pts) - 1
    res = []
    for i in range(n):
        p_prev = pts[i - 1] if i > 0 else pts[n - 1]
        p, p_next = pts[i], pts[i + 1]
        v1, v2 = p - p_prev, p_next - p
        if v1.Length < 1e-6 or v2.Length < 1e-6:
            continue
        if v1.X * v2.Y - v1.Y * v2.X < 0 and rg.Vector3d.VectorAngle(v1, v2) > math.radians(20):
            res.append(p)
    return res


def mismo_lazo(a, b):
    aa, ab = area(a), area(b)
    if aa <= 0 or abs(aa - ab) > 0.01 * aa + 0.05:
        return False
    return centro(a).DistanceTo(centro(b)) < 0.2


# ---------------- recorridos ----------------
class Camino(object):
    def __init__(self, pts, cerrado):
        if cerrado and pts[0].DistanceTo(pts[-1]) > 1e-6:
            pts = pts + [pts[0]]
        limpio = [pts[0]]
        for p in pts[1:]:
            if p.DistanceTo(limpio[-1]) > 1e-6:
                limpio.append(p)
        self.p = limpio
        self.cerrado = cerrado
        self.acum = [0.0]
        for i in range(len(self.p) - 1):
            self.acum.append(self.acum[-1] + self.p[i].DistanceTo(self.p[i + 1]))
        self.L = self.acum[-1]

    def punto(self, s):
        s = min(max(s, 0.0), self.L)
        i = bisect.bisect_right(self.acum, s) - 1
        i = min(max(i, 0), len(self.p) - 2)
        L = self.acum[i + 1] - self.acum[i]
        t = 0.0 if L < 1e-12 else (s - self.acum[i]) / L
        a, b = self.p[i], self.p[i + 1]
        return rg.Point3d(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t, 0)


class Emisor(object):
    """Escribe el código G y lleva la cuenta de largos y del dibujo."""

    def __init__(self):
        self.l = ["S%d M3" % HUSILLO, "G90 G17 G21"]
        self.x = self.y = 0.0
        self.z = None
        self.f = None
        self.nuevo_f = True
        self.corte = 0.0
        self.rapido = 0.0
        self.trazos = []
        self._tr = None

    def _r(self, v):
        return round(v, 3)

    def _fin_trazo(self):
        if self._tr and len(self._tr) > 1:
            self.trazos.append(self._tr)
        self._tr = None

    def g0z(self, z):
        z = self._r(z)
        if self.z is not None and abs(self.z - z) < 1e-9:
            return
        self.l.append("G0 Z%s" % fmt(z))
        if self.z is not None:
            self.rapido += abs(self.z - z)
        self.z = z
        self.nuevo_f = True
        self._fin_trazo()

    def g0xy(self, x, y):
        x, y = self._r(x), self._r(y)
        if abs(self.x - x) < 1e-9 and abs(self.y - y) < 1e-9:
            return
        self.l.append("G0 X%s Y%s" % (fmt(x), fmt(y)))
        self.rapido += math.hypot(x - self.x, y - self.y)
        self.x, self.y = x, y
        self.nuevo_f = True
        self._fin_trazo()

    def g1(self, x, y, z, f=None):
        x, y, z = self._r(x), self._r(y), self._r(z)
        z0 = self.z if self.z is not None else z
        dx, dy, dz = x - self.x, y - self.y, z - z0
        if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
            return
        partes = ["G1"]
        if abs(dx) > 1e-9:
            partes.append("X" + fmt(x))
        if abs(dy) > 1e-9:
            partes.append("Y" + fmt(y))
        if abs(dz) > 1e-9:
            partes.append("Z" + fmt(z))
        f = f or AVANCE
        if self.nuevo_f or f != self.f:
            partes.append("F" + fmt(f))
            self.f = f
            self.nuevo_f = False
        self.l.append(" ".join(partes))
        self.corte += math.sqrt(dx * dx + dy * dy + dz * dz)
        if self._tr is None:
            self._tr = [rg.Point3d(self.x, self.y, z0)]
        self._tr.append(rg.Point3d(x, y, z))
        self.x, self.y, self.z = x, y, z

    def ir_a(self, x, y, z_libre_hasta):
        """Traslado seguro a (x, y) y bajada hasta z_libre_hasta (profundidad ya vaciada)."""
        if self.z is None or self.z < Z_LIBRE:
            self.g0z(Z_LIBRE)
        self.g0xy(x, y)
        if self.z > Z_LIBRE:
            self.g0z(Z_LIBRE)
        if z_libre_hasta < self.z - 1e-9:
            self.g1(x, y, z_libre_hasta, AVANCE_BAJADA)

    def terminar(self):
        self.g0z(Z_SEGURO)
        self.l += ["M5", "M30"]
        self._fin_trazo()


def largo_rampa(dz):
    return dz / math.tan(math.radians(RAMPA_GRADOS)) if dz > 1e-6 else 0.0


def recorrer_cerrado(em, cam, s0, z_ini, z_fin, z_pest=None, tabs=None):
    """Desde la posición s0 (ya a z_ini): rampa hasta z_fin y una vuelta completa a z_fin.
    Las pestañas (intervalos de recorrido) quedan a z_pest. Devuelve la posición final."""
    L = cam.L
    dz = z_ini - z_fin
    Lr = largo_rampa(dz)
    total = Lr + L
    tabs = tabs or []

    def zf(d):
        return z_fin if Lr <= 0 else z_ini - dz * min(1.0, max(0.0, d) / Lr)

    def en_tab(s):
        s %= L
        return any(a < s < b for a, b in tabs)

    def zc(d):
        z = zf(d)
        if z_pest is not None and z < z_pest and en_tab(s0 + d):
            return z_pest
        return z

    bps = list(cam.acum)
    bordes = sorted(set([x % L for iv in tabs for x in iv]))
    ds = set([total])
    if Lr > 0:
        ds.add(Lr)
    vueltas = int(total // L) + 2
    for k in range(-1, vueltas + 1):
        for b in bps + bordes:
            d = k * L + b - s0
            if 1e-7 < d < total - 1e-7:
                ds.add(round(d, 7))
    for d in sorted(ds):
        s = (s0 + d) % L
        p = cam.punto(s)
        if any(abs(s - b) < 1e-5 or abs(s - b - L) < 1e-5 or abs(s - b + L) < 1e-5 for b in bordes):
            em.g1(p.X, p.Y, zc(d - 1e-4))
            em.g1(p.X, p.Y, zc(d + 1e-4))
        else:
            em.g1(p.X, p.Y, zc(d))
    return (s0 + total) % L


def recorrer_abierto(em, cam, z_ini, z_fin):
    """Desde el inicio (ya a z_ini): rampa ida y vuelta hasta z_fin, vuelve al inicio y corta hasta el final."""
    L = cam.L
    dz = z_ini - z_fin
    p0 = cam.p[0]
    if L < 1.0 or dz <= 1e-6:
        if dz > 1e-6:
            em.g1(p0.X, p0.Y, z_fin, AVANCE_BAJADA)
        for p in cam.p[1:]:
            em.g1(p.X, p.Y, z_fin)
        return
    Lr = largo_rampa(dz)
    ds = set([Lr])
    k = 0
    while 2 * k * L < Lr:
        for a in cam.acum:
            for d in (2 * k * L + a, 2 * k * L + 2 * L - a):
                if 1e-7 < d < Lr:
                    ds.add(d)
        k += 1

    def pos(d):
        m = d % (2 * L)
        return m if m <= L else 2 * L - m

    for d in sorted(ds):
        p = cam.punto(pos(d))
        em.g1(p.X, p.Y, z_ini - dz * min(1.0, d / Lr))
    s_fin = pos(Lr)
    # volver al inicio a z_fin y cortar todo
    for i in range(len(cam.acum) - 1, -1, -1):
        if cam.acum[i] < s_fin - 1e-7:
            em.g1(cam.p[i].X, cam.p[i].Y, z_fin)
    for p in cam.p[1:]:
        em.g1(p.X, p.Y, z_fin)


def escalones(desde, hasta):
    """Profundidades (negativas) parejas de a lo sumo PASO, de `desde` a `hasta` (mm, positivos)."""
    if hasta <= desde + 1e-6:
        return []
    n = int(math.ceil((hasta - desde) / PASO - 1e-9))
    return [-(desde + (hasta - desde) * k / n) for k in range(1, n + 1)]


# ---------------- análisis de la pieza ----------------
def punto_en_cara(f):
    """Un punto que esté de verdad sobre la cara (no en una zona recortada)."""
    du, dv = f.Domain(0), f.Domain(1)
    for n in (1, 3, 7, 15):
        for i in range(n):
            for j in range(n):
                u = du.ParameterAt((i + 0.5) / n)
                v = dv.ParameterAt((j + 0.5) / n)
                if f.IsPointOnFace(u, v) == rg.PointFaceRelation.Interior:
                    return f.PointAt(u, v), f.NormalAt(u, v)
    return None, None


def analizar_caras(brep, espesor, avisos):
    pisos = set()
    incl = False
    for f in brep.Faces:
        p, n = punto_en_cara(f)
        if p is None:
            continue
        ok, pl = f.TryGetPlane(0.01)
        if ok and abs(abs(pl.Normal.Z) - 1) < 1e-3:
            z = pl.Origin.Z
            if -espesor + 0.05 < z < -0.05:
                abajo = brep.IsPointInside(rg.Point3d(p.X, p.Y, z - 0.05), 0.001, False)
                arriba = brep.IsPointInside(rg.Point3d(p.X, p.Y, z + 0.05), 0.001, False)
                if abajo and not arriba:
                    pisos.add(round(-z, 2))
                elif arriba and not abajo:
                    avisos.append("Hay una cara mirando hacia abajo a %s mm: esa parte solo se puede mecanizar dando vuelta la placa (no está en este archivo)." % fmt(-z))
        elif abs(n.Z) > 0.02:
            incl = True
    if incl:
        avisos.append("Hay caras inclinadas o curvas (no verticales ni planas horizontales): Viruta mecaniza en 2,5D (paredes verticales y fondos planos), esas caras quedan escalonadas o sin hacer.")
    return sorted(pisos)


class Nivel(object):
    """Zona a vaciar a una profundidad: dentro del contorno y fuera del material (todo desfasado R)."""

    def __init__(self, brep, z, contorno_in, pasantes, avisos, angostos):
        self.contorno_in = contorno_in
        self.comps = []
        self.igualados = set()
        self.huecos_material = []
        self.exteriores_material = []
        for ext, hs in caras_material(seccion(brep, z)):
            self.exteriores_material.append(ext)
            O = offset_cerrada(ext, R, True)
            if not O:
                avisos.append("No se pudo desfasar el borde del material a %s mm; revisá la pieza." % fmt(-z))
                continue
            H = []
            for h in hs:
                idx = next((i for i, ph in enumerate(pasantes) if mismo_lazo(h, ph)), None)
                if idx is not None:
                    self.igualados.add(idx)
                    continue
                self.huecos_material.append(h)
                hi = offset_cerrada(h, R, False)
                if not hi:
                    c, bb = centro(h), h.GetBoundingBox(True)
                    clave = (round(c.X), round(c.Y))
                    if clave not in angostos:
                        angostos.add(clave)
                        avisos.append("Cajera/ranura en X%s Y%s (%s × %s mm) más angosta que la fresa Ø%s: no se puede vaciar." % (
                            fmt(c.X), fmt(c.Y), fmt(bb.Diagonal.X), fmt(bb.Diagonal.Y), fmt(DIAMETRO)))
                    continue
                H += hi
            self.comps.append((O, H))
        self.curvas = [(c, "contorno", "C") for c in contorno_in]
        for i, (O, H) in enumerate(self.comps):
            self.curvas += [(o, i, "O") for o in O] + [(h, i, "H") for h in H]

    def permitido(self, p, ignorar=None):
        if ignorar != "contorno" and not any(contiene(c, p) for c in self.contorno_in):
            return False
        for i, (O, H) in enumerate(self.comps):
            if i == ignorar:
                continue
            if any(contiene(o, p) for o in O) and not any(contiene(h, p) for h in H):
                return False
        return True

    def barridos(self):
        """Segmentos de vaciado en zigzag (paralelos a Y)."""
        bb = rg.BoundingBox.Empty
        for c in self.contorno_in:
            bb.Union(c.GetBoundingBox(True))
        segs = []
        x = bb.Min.X + 0.05
        while x < bb.Max.X:
            linea = rg.LineCurve(rg.Point3d(x, bb.Min.Y - 5, 0), rg.Point3d(x, bb.Max.Y + 5, 0))
            ys = []
            for c, _, _ in self.curvas:
                for e in Intersection.CurveCurve(linea, c, 0.001, 0.001) or []:
                    ys.append(e.PointA.Y)
                    if e.IsOverlap:
                        ys.append(e.PointA2.Y)
            ys = sorted(set(round(y, 5) for y in ys))
            tramos = []
            for a, b in zip(ys, ys[1:]):
                if b - a < 0.05:
                    continue
                if self.permitido(rg.Point3d(x, (a + b) / 2, 0)):
                    if tramos and abs(tramos[-1][1] - a) < 1e-4:
                        tramos[-1][1] = b
                    else:
                        tramos.append([a, b])
            for a, b in tramos:
                if b - a > 0.1:  # puntas apenas adentro, para poder enlazar sin subir
                    segs.append((rg.Point3d(x, a + 0.02, 0), rg.Point3d(x, b - 0.02, 0)))
            x += PASO_LATERAL
        return segs

    def paredes(self):
        """Tramos de borde de la zona a vaciar (pasada de terminación de paredes).
        Recorre cada borde cada 0,25 mm y se queda con los tramos que son borde de verdad.
        Devuelve [(puntos, cerrado, tipo)] con tipo O (isla), H (cajera) o C (rebaje abierto)."""
        res = []
        for c, cid, tipo in self.curvas:
            pts = densificar(a_polilinea(c), 0.25)
            if pts[0].DistanceTo(pts[-1]) > 1e-6:
                pts.append(pts[0])
            base = pts[:-1]
            marca = [self.permitido(p, ignorar=cid) for p in base]
            if all(marca):
                res.append((simplificar(base + [base[0]], True), True, tipo))
                continue
            if not any(marca):
                continue
            k = marca.index(False)
            base, marca = base[k:] + base[:k], marca[k:] + marca[:k]
            tramo = []
            for p, m in zip(base + [base[0]], marca + [marca[0]]):
                if m:
                    tramo.append(p)
                else:
                    if len(tramo) >= 2:
                        res.append((simplificar(tramo, False), False, tipo))
                    tramo = []
            if len(tramo) >= 2:
                res.append((simplificar(tramo, False), False, tipo))
        return res

    def enlace_ok(self, a, b):
        L = a.DistanceTo(b)
        if L > 3 * PASO_LATERAL:
            return False
        n = max(2, int(L / 0.25))
        for i in range(1, n):
            if not self.permitido(a + (b - a) * (float(i) / n)):
                return False
        return True


def vaciar_nivel(em, nivel, zs, z_arriba):
    """Vacía la zona del nivel bajando por los escalones zs desde z_arriba (ya vaciado)."""
    segs = nivel.barridos()
    paredes = nivel.paredes()
    if not segs and not paredes:
        return False
    z_prev = z_arriba
    for z in zs:
        # zigzag: vecino más cercano, enlazando sin subir cuando se puede
        quedan = list(segs)
        actual = None
        while quedan:
            ref = actual if actual is not None else rg.Point3d(em.x, em.y, 0)
            mejor, inv, dmin = None, False, 1e18
            for sg in quedan:
                for invertido, extremo in ((False, sg[0]), (True, sg[1])):
                    d = ref.DistanceTo(extremo)
                    if d < dmin:
                        mejor, inv, dmin = sg, invertido, d
            quedan.remove(mejor)
            a, b = (mejor[1], mejor[0]) if inv else mejor
            if actual is not None and abs(em.z - z) < 1e-6 and nivel.enlace_ok(actual, a):
                em.g1(a.X, a.Y, z)
                em.g1(b.X, b.Y, z)
            else:
                em.ir_a(a.X, a.Y, z_prev)
                recorrer_abierto(em, Camino([a, b], False), z_prev, z)
            actual = b
        # paredes (concordante con M3: islas en sentido horario, cajeras antihorario)
        for pts, cerrado, tipo in paredes:
            if cerrado:
                pts = sentido_pts(pts, horario=(tipo == "O"))
                cam = Camino(pts, True)
                em.ir_a(cam.p[0].X, cam.p[0].Y, z_prev)
                recorrer_cerrado(em, cam, 0.0, z_prev, z)
            else:
                cam = Camino(pts, False)
                em.ir_a(cam.p[0].X, cam.p[0].Y, z_prev)
                recorrer_abierto(em, cam, z_prev, z)
        z_prev = z
    return True


# ---------------- pestañas ----------------
def tramos_rectos(pts):
    tramos, s, ini, prev = [], 0.0, 0.0, None
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
    if n <= 0:
        return [], total, True
    if not utiles:
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
        k = min(k, max(1, int((b2 - a2) // (hueco + DIAMETRO)) + 1))
        for j in range(k):
            centros.append(a2 + (b2 - a2) * (j + 0.5) / k if k > 1 else (a2 + b2) / 2)
    centros.sort()
    return [(cc - hueco / 2, cc + hueco / 2) for cc in centros], total, True


# ---------------- mapa de alturas (para verificar) ----------------
def mapa_alturas(brep, paso):
    mp = rg.MeshingParameters()
    mp.Tolerance = 0.002          # malla fina: los círculos no quedan "cortados" por cuerdas
    mp.RelativeTolerance = 0.0
    mp.MinimumEdgeLength = 0.0001
    mp.RefineGrid = True
    mp.SimplePlanes = False
    mallas = rg.Mesh.CreateFromBrep(brep, mp)
    malla = rg.Mesh()
    for m in mallas:
        malla.Append(m)
    bb = brep.GetBoundingBox(True)
    x0, y0 = bb.Min.X - 8 + paso * 0.37, bb.Min.Y - 8 + paso * 0.37  # celdas que no caen justo sobre las paredes
    nx = int(math.ceil((bb.Diagonal.X + 16) / paso)) + 1
    ny = int(math.ceil((bb.Diagonal.Y + 16) / paso)) + 1
    vals = []
    for j in range(ny):
        y = y0 + j * paso
        for i in range(nx):
            x = x0 + i * paso
            t = Intersection.MeshRay(malla, rg.Ray3d(rg.Point3d(x, y, 5), -rg.Vector3d.ZAxis))
            vals.append(-32000 if t < 0 else int(round((5 - t) * 100)))
    datos = base64.b64encode(zlib.compress(struct.pack("<%dh" % len(vals), *vals), 9)).decode("ascii")
    return "MAPA %s %s %s %d %d %s" % (fmt(x0), fmt(y0), fmt(paso), nx, ny, datos)


# ---------------- pieza ----------------
def procesar(nombre, brep, idx):
    avisos = []
    brep, bb, xf = orientar(brep)
    ok_inv, xf_inv = xf.TryGetInverse()
    espesor = bb.Diagonal.Z
    ancho, largo_p = bb.Diagonal.X, bb.Diagonal.Y
    prof = espesor + EXTRA
    alto_pest = float(PESTANA_ALTO) if PESTANA_ALTO is not None else max(1.0, round(espesor / 3.0 * 2) / 2.0)
    z_pest = -prof + alto_pest

    pisos = analizar_caras(brep, espesor, avisos)

    # contorno y pasantes: sección cerca del fondo
    caras_fondo = caras_material(seccion(brep, -espesor + 0.02))
    if not caras_fondo:
        return None, ["No se pudo leer el contorno de la pieza."], None, None
    caras_fondo.sort(key=lambda fh: area(fh[0]), reverse=True)
    if len(caras_fondo) > 1:
        avisos.append("La pieza tiene %d partes separadas abajo: se toma la más grande como contorno." % len(caras_fondo))
    contorno, pasantes = caras_fondo[0]
    # límite para el centro de la fresa al vaciar: hasta un radio por fuera del contorno
    # (en los rebajes abiertos al borde la fresa sale por fuera; donde hay material, el
    # material desfasado ya lo impide)
    contorno_in = offset_cerrada(contorno, R, True) or [contorno]

    em = Emisor()
    em.g0z(Z_SEGURO)

    # 1) cajeras, rebajes y escalones, del menos al más profundo
    angostos = set()
    inicio_pasante = [0.0] * len(pasantes)
    hechos_pisos = []
    vivas = []
    z_arriba = 0.0
    for f in pisos:
        nivel = Nivel(brep, -f + 0.02, contorno_in, pasantes, avisos, angostos)
        for i in range(len(pasantes)):
            if i not in nivel.igualados:
                inicio_pasante[i] = f
        for h in nivel.huecos_material:
            vivas += esquinas_vivas(h, False)
        for ext in nivel.exteriores_material:
            vivas += esquinas_vivas(ext, True)
        if vaciar_nivel(em, nivel, escalones(z_arriba, f), -z_arriba):
            hechos_pisos.append(f)
        z_arriba = f

    # 2) agujeros y recortes pasantes
    hechos_pas, taladros = 0, 0
    for i, h in enumerate(pasantes):
        vivas += esquinas_vivas(h, False)
        d = offset_cerrada(h, R, False)
        desde = inicio_pasante[i]
        if not d:
            ok_c, circ = h.TryGetCircle(0.02)
            c = centro(h)
            if ok_c and DIAMETRO - 0.01 <= 2 * circ.Radius <= DIAMETRO + 0.4:
                em.ir_a(c.X, c.Y, -desde)
                zs = escalones(desde, prof)
                for k, z in enumerate(zs):  # picoteo: baja un escalón, sale a sacar viruta
                    em.g1(c.X, c.Y, z, AVANCE_BAJADA)
                    em.g0z(Z_LIBRE)
                    if k < len(zs) - 1:
                        em.g0z(z + 0.5)
                taladros += 1
            else:
                bbh = h.GetBoundingBox(True)
                avisos.append("Agujero/recorte pasante en X%s Y%s (%s × %s mm) más chico que la fresa Ø%s: no se puede cortar, se salteó." % (
                    fmt(c.X), fmt(c.Y), fmt(bbh.Diagonal.X), fmt(bbh.Diagonal.Y), fmt(DIAMETRO)))
            continue
        for dd in d:
            cc = sentido(dd, horario=False)
            cam = Camino(a_polilinea(cc), True)
            em.ir_a(cam.p[0].X, cam.p[0].Y, -desde)
            s = 0.0
            z_prev = -desde
            for z in escalones(desde, prof):
                s = recorrer_cerrado(em, cam, s, z_prev, z)
                z_prev = z
        hechos_pas += 1

    # 3) contorno exterior con pestañas
    vivas += esquinas_vivas(contorno, True)
    d = offset_cerrada(contorno, R, True)
    if not d:
        return None, avisos + ["No se pudo desfasar el contorno exterior."], None, None
    d = sentido(max(d, key=area), horario=True)
    pts = a_polilinea(d)
    if pts[0].DistanceTo(pts[-1]) > 1e-6:
        pts.append(pts[0])
    tramos, perim = tramos_rectos(pts)
    mejor = max(tramos, key=lambda t: t[1] - t[0])
    s, idx_ini = 0.0, 0
    for i in range(len(pts) - 1):
        if abs(s - mejor[0]) < 1e-6:
            idx_ini = i
            break
        s += pts[i].DistanceTo(pts[i + 1])
    base = pts[:-1]
    base = base[idx_ini:] + base[:idx_ini]
    pts = base + [base[0]]
    n = cant_pestanas(max(ancho, largo_p), perim)
    intervalos, perim, en_rectas = ubicar_pestanas(pts, n)
    cam = Camino(pts, True)
    em.ir_a(cam.p[0].X, cam.p[0].Y, 0.0)
    s, z_prev = 0.0, 0.0
    for z in escalones(0.0, prof):
        s = recorrer_cerrado(em, cam, s, z_prev, z, z_pest, intervalos)
        z_prev = z
    em.terminar()

    # esquinas vivas (sin repetir)
    unicas, vistas = [], set()
    for p in vivas:
        k = (round(p.X, 1), round(p.Y, 1))
        if k not in vistas:
            vistas.add(k)
            unicas.append(p)
    if unicas:
        ej = ", ".join("X%s Y%s" % (fmt(p.X), fmt(p.Y)) for p in unicas[:8])
        avisos.append("%d esquinas interiores vivas (%s%s): la fresa Ø%s las deja redondeadas R%s. Si son encastres, agregá descargas (dogbones) en Rhino antes de cortar." % (
            len(unicas), ej, "…" if len(unicas) > 8 else "", fmt(DIAMETRO), fmt(R)))

    pos = []
    for a, b in intervalos:
        p = cam.punto(((a + b) / 2) % cam.L)
        pos.append((p.X, p.Y))

    nombre_arch = (nombre or "pieza_%d" % idx).strip().replace(" ", "_")
    nombre_arch = "".join(ch for ch in nombre_arch if ch.isalnum() or ch in "_-.")
    ruta = os.path.join(CARPETA_SALIDA, nombre_arch + ".txt")
    if ESCRIBIR:
        with open(ruta, "w", newline="\r\n") as fh:
            fh.write("\n".join(em.l) + "\n")

    if DIBUJAR and ok_inv:
        at = Rhino.DocObjects.ObjectAttributes()
        at.LayerIndex = obtener_capa("Viruta")
        at.Name = "viruta_" + nombre_arch
        for tr in em.trazos:
            pl = rg.PolylineCurve(tr)
            pl.Transform(xf_inv)
            doc.Objects.AddCurve(pl, at)
        for x, y in pos:
            pt = rg.Point3d(x, y, 0)
            pt.Transform(xf_inv)
            doc.Objects.AddTextDot("P", pt, at)
        doc.Views.Redraw()

    minutos = (em.corte / AVANCE + em.rapido / 3000.0) * 1.1
    resumen = [
        ("archivo", ruta if ESCRIBIR else "(vista previa: no se escribió)"),
        ("pieza_mm", "%s (X) x %s (Y) x %s (espesor)" % (fmt(ancho), fmt(largo_p), fmt(espesor))),
        ("cajeras_rebajes_mm", ", ".join(fmt(f) for f in hechos_pisos) or "no hay"),
        ("pasante_mm", fmt(prof)),
        ("agujeros_pasantes", "%d por contorno, %d taladrados" % (hechos_pas, taladros)),
        ("pestanas", "%d de %s x %s mm (%s)" % (len(intervalos), fmt(PESTANA_LARGO), fmt(alto_pest), "en tramos rectos" if en_rectas else "pieza curva: repartidas parejo")),
        ("pestanas_xy", ", ".join("X%s Y%s" % (fmt(x), fmt(y)) for x, y in pos)),
        ("lineas", len(em.l)),
        ("tiempo_min", round(minutos, 1)),
    ]
    mapa = None
    if MAPA:
        mapa = os.path.join(CARPETA_SALIDA, nombre_arch + ".mapa")
        with open(mapa, "w") as fh:
            fh.write(mapa_alturas(brep, float(MAPA)) + "\n")
        resumen.append(("mapa_alturas", mapa))
    return resumen, avisos, ("\n".join(em.l) if DEVOLVER_CODIGO else None), mapa


def main():
    if DIBUJAR:
        limpiar_dibujos()
    piezas = obtener_piezas()
    if not piezas:
        print("No encontré piezas sólidas (polisuperficies cerradas) visibles en el documento.")
        return
    for i, (nombre, b) in enumerate(piezas, 1):
        res, avisos, codigo, mapa = procesar(nombre, b, i)
        print("=== %s ===" % (nombre or "pieza_%d" % i))
        for k, v in (res or []):
            print("%s: %s" % (k, v))
        for a in avisos:
            print("AVISO: " + a)
        if codigo:
            print("---CODIGO---")
            print(codigo)
            print("---FIN---")


main()
