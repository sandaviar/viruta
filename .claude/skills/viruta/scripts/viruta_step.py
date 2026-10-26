#!/usr/bin/env python3
# Viruta — Copyright (c) 2026 María Sol Segovia Sánchez. PolyForm Strict 1.0.0 (ver LICENSE.md).
"""Viruta universal: STEP o IGES (de cualquier programa) -> código G para router CNC.

Sirve para piezas modeladas en SolidWorks, Fusion, Rhino, Inventor, Onshape, FreeCAD,
Solid Edge, CATIA o lo que sea, mientras se puedan exportar a STEP (o IGES). Mecanizado 2,5D
desde arriba (paredes verticales y fondos planos) con las profundidades EXACTAS del modelo:

  - lee cada cuerpo/pieza del archivo con su nombre (cuerpo de Rhino/Fusion, pieza de
    SolidWorks/Inventor, componentes de un ensamble) y junta las copias iguales en un solo
    archivo con su cantidad (las piezas espejadas quedan aparte);
  - acomoda cada pieza: elige la cara de arriba (la que se puede mecanizar), X = lado
    corto, origen y cero de Z según el perfil de la máquina;
  - cajeras, rebajes abiertos al borde, escalones, islas (zigzag + pasada de pared,
    entrada en rampa);
  - agujeros y recortes pasantes (contorno, o taladrado si son del tamaño de la fresa);
  - contorno exterior al final con pestañas en tramos rectos (o donde se pidan);
  - descargas (dogbones) automáticas en las esquinas interiores, si se piden;
  - varias herramientas: la 2.ª (más chica) hace solo lo que la 1.ª no pudo;
  - un archivo por pieza y por herramienta, ya limpio para el pendrive;
  - mapa de alturas del modelo (independiente de las trayectorias), vista previa PNG,
    lista de cortes CSV y verificación por simulación (verificar_gcode.py).

Requiere: pip install cadquery-ocp shapely numpy scipy matplotlib

Uso:
  python viruta_step.py PIEZA.step [OTRA.step ...] [--perfil taller5] [--salida CARPETA]
         [--diametro 6 | --herramientas 6,3] [--loc 19] [--paso-pct 0.5]
         [--pestanas 4] [--pestana-largo 8] [--pestana-alto 3] [--pestanas-en "X,Y;X,Y"]
         [--descargas] [--piezas "Pata,Asiento"] [--separar-iguales]
         [--formato mach3|grbl|linuxcnc] [--origen esquina|centro] [--z0 arriba|mesa]
         [--x-largo] [--extension .txt] [--husillo 18000] [--avance 2000] [--avance-bajada 2000]
         [--extra 0.3] [--cara-arriba auto|+Z|-Z|+X|-X|+Y|-Y] [--config maquina.json]
         [--vista-previa] [--verificar] [--no-escribir]
"""
import argparse
import bisect
import base64
import csv
import json
import math
import os
import re
import struct
import sys
import zlib

import numpy as np
import shapely
from shapely.geometry import (GeometryCollection, LineString, MultiLineString, MultiPolygon,
                              Point, Polygon)
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_TangentialDeflection
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_SurfaceOfExtrusion
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

# ---------------------------------------------------------------- perfiles
PERFILES = {
    "taller5": {  # Router del Taller 5 de UNAHUR (DDCS V4.1, post Mach3)
        "nombre": "Taller 5 UNAHUR (DDCS V4.1 / Mach3)",
        "formato": "mach3", "husillo": 18000, "avance": 2000, "avance_bajada": 2000,
        "origen": "esquina", "z0": "arriba", "x_lado_corto": True,
        "extra": 0.3, "z_seguro": 10.0, "z_libre": 2.0, "extension": ".txt",
        "herramientas": [{"diametro": 6.0, "loc": 19.0, "nombre": "6MM CRB 2FL 19 LOC"}],
    },
}

DEF = {
    "formato": "mach3", "husillo": 18000, "avance": 2000.0, "avance_bajada": 2000.0,
    "paso_pct": 0.5, "paso_lateral_pct": 0.4, "rampa_grados": 10.0, "extra": 0.3,
    "z_seguro": 10.0, "z_libre": 2.0, "pestanas": None, "pestana_largo": 8.0,
    "pestana_alto": None, "origen": "esquina", "z0": "arriba", "x_lado_corto": True,
    "extension": ".txt", "cara_arriba": "auto", "herramientas": [{"diametro": 6.0}],
    "rapido": 3000.0,
}

TOL = 0.005
QS = 24  # segmentos por cuarto de círculo en los desfases


def fmt(v):
    s = "%.3f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------- STEP y geometría OCC
_GENERICOS = re.compile(
    r"^(|open[\s_]cascade.*|untitled|unnamed|sin[\s_]t[ií]tulo|sin[\s_]nombre|document|documento|body|cuerpo|solid|s[oó]lido|brep|part|pieza|parte|component|componente|"
    r"(saliente|cortar|cut|boss|extru\w*|revol\w*|redondeo|fillet|chafl[aá]n|chamfer|simetr[ií]a|mirror|matriz|pattern|"
    r"vaciado|shell|combinar|combine|mover|move|copiar|copy|importar|imported|import|sweep|barrer|loft|recubrir|"
    r"split|dividir|body|cuerpo|solid|s[oó]lido)[\s_\-\w]*?)([\s_\-:]*(\d+|\(\d+\)|<\d+>))*$", re.I)


def _nombre_util(n):
    n = (n or "").strip()
    if not n or _GENERICOS.match(n):
        return ""
    return n


def leer_step(path):
    """Lee los sólidos del STEP con su nombre: el del cuerpo (Rhino, Fusion) o el de la pieza/componente
    (SolidWorks, Inventor, ensambles). Devuelve [(nombre_o_vacío, sólido), ...] en coordenadas del modelo.
    También acepta IGES (.igs/.iges): si viene en superficies, las cose para armar el sólido."""
    if path.lower().endswith((".igs", ".iges")):
        return _leer_iges(path)
    try:
        return _leer_step_xcaf(path)
    except Exception:  # pragma: no cover  (si falla XCAF, lectura simple)
        pass
    r = STEPControl_Reader()
    if int(r.ReadFile(path)) != 1:  # IFSelect_RetDone
        raise SystemExit("No se pudo leer el STEP: %s" % path)
    r.TransferRoots()
    res = []
    ex = TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    while ex.More():
        res.append(("", TopoDS.Solid(ex.Current())))
        ex.Next()
    return res


def _leer_iges(path):
    from OCP.IGESControl import IGESControl_Reader
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.TopAbs import TopAbs_SHELL
    r = IGESControl_Reader()
    if int(r.ReadFile(path)) != 1:
        raise SystemExit("No se pudo leer el IGES: %s" % path)
    r.TransferRoots()
    forma = r.OneShape()
    sols = []
    ex = TopExp_Explorer(forma, TopAbs_SOLID)
    while ex.More():
        sols.append(("", TopoDS.Solid(ex.Current())))
        ex.Next()
    if sols:
        return sols
    cos = BRepBuilderAPI_Sewing(0.01)
    cos.Add(forma)
    cos.Perform()
    ex = TopExp_Explorer(cos.SewedShape(), TopAbs_SHELL)
    while ex.More():
        ms = BRepBuilderAPI_MakeSolid(TopoDS.Shell(ex.Current()))
        if ms.IsDone():
            s = ms.Solid()
            if volumen(s) < 0:
                s.Reverse()
            sols.append(("", s))
        ex.Next()
    return sols


def _leer_step_xcaf(path):
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_Label
    from OCP.TDataStd import TDataStd_Name
    from OCP.collections import Sequence_TDF_Label

    def nombre(l):
        a = TDataStd_Name()
        if not l.IsNull() and l.FindAttribute(TDataStd_Name.GetID_s(), a):
            return a.Get().ToExtString()
        return ""

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    if int(r.ReadFile(path)) != 1:
        raise SystemExit("No se pudo leer el STEP: %s" % path)
    if not r.Transfer(doc):
        raise RuntimeError("XCAF")
    tr = r.Reader().WS().TransferReader()
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    libres = Sequence_TDF_Label()
    st.GetFreeShapes(libres)
    res = []

    def nombre_solido(s, l):
        sub = TDF_Label()
        n = _nombre_util(nombre(sub)) if st.FindSubShape(l, s, sub) else ""
        if not n:
            try:
                e = tr.EntityFromShapeResult(s, 1)
                if e is not None and e.Name() is not None:
                    n = _nombre_util(e.Name().ToCString())
            except Exception:
                n = ""
        return n

    def rec(l, loc, nom_padre):
        if st.IsAssembly_s(l):
            cs = Sequence_TDF_Label()
            st.GetComponents_s(l, cs)
            for i in range(1, cs.Length() + 1):
                c = cs.Value(i)
                ref = TDF_Label()
                st.GetReferredShape_s(c, ref)
                n = _nombre_util(nombre(ref)) or _nombre_util(nombre(c)) or nom_padre
                rec(ref, loc.Multiplied(st.GetLocation_s(c)), n)
            return
        forma = st.GetShape_s(l)
        n_l = _nombre_util(nombre(l)) or nom_padre
        ex = TopExp_Explorer(forma, TopAbs_SOLID)
        sols = []
        while ex.More():
            sols.append(TopoDS.Solid(ex.Current()))
            ex.Next()
        for s in sols:
            n = nombre_solido(s, l) if len(sols) > 1 or not n_l else ""
            s2 = s.Moved(loc) if not loc.IsIdentity() else s
            res.append((n or n_l, TopoDS.Solid(s2)))

    for i in range(1, libres.Length() + 1):
        rec(libres.Value(i), TopLoc_Location(), "")
    if not res:
        raise RuntimeError("sin sólidos")
    return res


def huella(s):
    """Datos para reconocer piezas iguales (misma forma, en cualquier posición)."""
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(s, p)
    q = GProp_GProps()
    BRepGProp.SurfaceProperties_s(s, q)
    m = p.MatrixOfInertia()
    ii = np.linalg.eigvalsh(np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]))
    return (p.Mass(), q.Mass(), tuple(ii))


def misma_huella(a, b, tol=1e-3):
    va, aa, ia = a
    vb, ab, ib = b
    if abs(va - vb) > tol * max(1.0, va) or abs(aa - ab) > tol * max(1.0, aa):
        return False
    return all(abs(x - y) <= tol * max(1.0, abs(x)) for x, y in zip(ia, ib))


def descargas(forma, R, espesor, angulo_min=45.0):
    """Agrega descargas (dogbones) en las esquinas interiores vivas verticales de la pieza ya acostada:
    un cilindro de radio R centrado sobre la bisectriz, hacia el lado vacío, que pasa por la esquina.
    Devuelve (forma_nueva, [(x, y), ...])."""
    try:
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    except ImportError:
        from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.TopExp import TopExp
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.gp import gp_Ax2

    mapa = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(forma, TopAbs_EDGE, TopAbs_FACE, mapa)
    clas = BRepClass3d_SolidClassifier(forma)
    cos_max = math.cos(math.radians(angulo_min))
    hechos, cil = [], []
    for i in range(1, mapa.Extent() + 1):
        e = TopoDS.Edge(mapa.FindKey(i))
        cu = BRepAdaptor_Curve(e)
        if cu.GetType() != GeomAbs_Line:
            continue
        if abs(cu.Line().Direction().Z()) < 0.999:
            continue
        fs = [TopoDS.Face(f) for f in mapa.FindFromIndex(i)]
        if len(fs) != 2 or fs[0].IsSame(fs[1]):
            continue
        n1, _ = normal_plana(fs[0])
        n2, _ = normal_plana(fs[1])
        if n1 is None or n2 is None or abs(n1[2]) > 1e-3 or abs(n2[2]) > 1e-3:
            continue
        if float(np.dot(n1, n2)) > cos_max:
            continue  # esquina abierta: la fresa deja casi nada
        a, b = cu.Value(cu.FirstParameter()), cu.Value(cu.LastParameter())
        za, zb = sorted((a.Z(), b.Z()))
        if zb - za < 0.05:
            continue
        P = np.array([a.X(), a.Y(), (za + zb) / 2])

        def adentro(v):
            q = P + v * 0.05
            clas.Perform(gp_Pnt(*q), 1e-6)
            return clas.State() == TopAbs_IN

        if not (adentro(n1 - n2) and adentro(n2 - n1)):
            continue  # esquina convexa del material (la fresa la hace bien)
        bis = n1 + n2
        bis[2] = 0.0
        if np.linalg.norm(bis) < 1e-9:
            continue
        bis /= np.linalg.norm(bis)
        c = P[:2] + bis[:2] * R
        if any(math.dist(c, h) < 1e-3 for h in hechos):
            continue
        hechos.append((float(c[0]), float(c[1])))
        z0 = za - 1.0 if za <= -espesor + 0.01 else za
        cil.append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(c[0], c[1], z0), gp_Dir(0, 0, 1)), R, 1.0 - z0).Shape())
    for cy in cil:
        forma = BRepAlgoAPI_Cut(forma, cy).Shape()
    sol = []
    ex = TopExp_Explorer(forma, TopAbs_SOLID)
    while ex.More():
        sol.append(TopoDS.Solid(ex.Current()))
        ex.Next()
    if len(sol) == 1:
        forma = sol[0]
    esquinas = [(round(x - 0.0, 3), round(y, 3)) for x, y in hechos]
    return forma, esquinas


def transformar(forma, trsf):
    return BRepBuilderAPI_Transform(forma, trsf, True).Shape()


def caja(forma):
    b = Bnd_Box()
    BRepBndLib.Add_s(forma, b, False)
    a, c = b.CornerMin(), b.CornerMax()
    return (a.X(), a.Y(), a.Z(), c.X(), c.Y(), c.Z())


def volumen(forma):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(forma, p)
    return p.Mass()


def caras(forma):
    ex = TopExp_Explorer(forma, TopAbs_FACE)
    while ex.More():
        yield TopoDS.Face(ex.Current())
        ex.Next()


def area_cara(f):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, p)
    return p.Mass()


def normal_plana(f):
    s = BRepAdaptor_Surface(f)
    if s.GetType() != GeomAbs_Plane:
        return None, None
    pl = s.Plane()
    d = pl.Axis().Direction()
    n = np.array([d.X(), d.Y(), d.Z()])
    if f.Orientation() == TopAbs_REVERSED:
        n = -n
    loc = pl.Location()
    return n, np.array([loc.X(), loc.Y(), loc.Z()])


def rotacion_a_z(n):
    """Transformación que lleva el vector n a +Z."""
    n = n / np.linalg.norm(n)
    t = gp_Trsf()
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(n, z))
    if c > 1 - 1e-9:
        return t
    if c < -1 + 1e-9:
        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.pi)
        return t
    eje = np.cross(n, z)
    eje /= np.linalg.norm(eje)
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*eje)), math.acos(c))
    return t


def seccion(forma, z):
    """Material de la pieza en el plano Z = z, como (Multi)Polygon de shapely."""
    sec = BRepAlgoAPI_Section(forma, gp_Pln(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1)), False)
    sec.Approximation(True)
    sec.Build()
    lineas = []
    ex = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge(ex.Current())
        ad = BRepAdaptor_Curve(e)
        td = GCPnts_TangentialDeflection(ad, 0.02, 0.003)
        pts = []
        for i in range(1, td.NbPoints() + 1):
            p = td.Value(i)
            pts.append((round(p.X(), 6), round(p.Y(), 6)))
        if len(pts) >= 2:
            lineas.append(LineString(pts))
        ex.Next()
    if not lineas:
        return Polygon()
    red = unary_union(lineas)
    cls = BRepClass3d_SolidClassifier(forma)
    mat = []
    for pg in polygonize(red):
        if pg.area < 1e-6:
            continue
        rp = pg.representative_point()
        cls.Perform(gp_Pnt(rp.x, rp.y, z), 1e-6)
        if cls.State() == TopAbs_IN:
            mat.append(pg)
    return unary_union(mat).buffer(0) if mat else Polygon()


def analizar_caras(forma, espesor):
    """Fondos (profundidades, mm positivos), caras hacia abajo y caras no 2,5D."""
    pisos, abajo, incl = set(), set(), False
    for f in caras(forma):
        s = BRepAdaptor_Surface(f)
        tipo = s.GetType()
        if tipo == GeomAbs_Plane:
            n, p0 = normal_plana(f)
            if abs(abs(n[2]) - 1) < 1e-4:
                z = p0[2]
                if -espesor + 0.02 < z < -0.02:
                    (pisos if n[2] > 0 else abajo).add(round(-z, 3))
            elif abs(n[2]) > 1e-3:
                incl = True
        elif tipo == GeomAbs_Cylinder:
            d = s.Cylinder().Axis().Direction()
            if abs(abs(d.Z()) - 1) > 1e-4:
                incl = True
        elif tipo == GeomAbs_SurfaceOfExtrusion:
            d = s.Direction()
            if abs(abs(d.Z()) - 1) > 1e-4:
                incl = True
        else:
            incl = True
    return sorted(pisos), sorted(abajo), incl


# ---------------------------------------------------------------- orientación
def orientar(solido, cfg, avisos):
    """Deja la pieza con la cara de arriba en Z = 0, abajo-izquierda en (0, 0)."""
    # candidatos: normal de la cara plana más grande (y su opuesta), o lo que pida la persona
    pedidas = {"+Z": (0, 0, 1), "-Z": (0, 0, -1), "+X": (1, 0, 0), "-X": (-1, 0, 0),
               "+Y": (0, 1, 0), "-Y": (0, -1, 0)}
    ca = cfg.get("cara_arriba", "auto")
    if ca in pedidas:
        candidatos = [np.array(pedidas[ca], dtype=float)]
    else:
        mejor, amax = None, -1
        for f in caras(solido):
            n, _ = normal_plana(f)
            if n is None:
                continue
            a = area_cara(f)
            if a > amax + 1e-6:
                mejor, amax = n, a
        if mejor is None:
            mejor = np.array([0.0, 0.0, 1.0])
        # que el candidato "positivo" mire hacia +Z del modelo si se puede
        if mejor[2] < -1e-6 or (abs(mejor[2]) < 1e-6 and (mejor[1] < 0 or mejor[0] < 0)):
            mejor = -mejor
        candidatos = [mejor, -mejor]
    elegido = None
    for n in candidatos:
        t = rotacion_a_z(n)
        f2 = transformar(solido, t)
        x0, y0, z0, x1, y1, z1 = caja(f2)
        tz = gp_Trsf()
        tz.SetTranslation(gp_Vec(0, 0, -z1))
        f2 = transformar(f2, tz)
        esp = z1 - z0
        pisos, abajo, incl = analizar_caras(f2, esp)
        puntaje = (len(abajo), -len(pisos))
        if elegido is None or puntaje < elegido[0]:
            elegido = (puntaje, f2, esp, pisos, abajo, incl, t)
    _, forma, espesor, pisos, abajo, incl, t_rot = elegido
    # giro en el plano: lados del rectángulo mínimo alineados con X/Y, X = lado corto
    fondo = seccion(forma, -espesor + 0.02)
    if fondo.is_empty:
        fondo = seccion(forma, -espesor / 2)
    rect = fondo.minimum_rotated_rectangle if not fondo.is_empty else None
    ang = 0.0
    if rect is not None and rect.geom_type == "Polygon":
        c = list(rect.exterior.coords)
        e1 = np.subtract(c[1], c[0])
        e2 = np.subtract(c[2], c[1])
        largo = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
        ang_largo = math.atan2(largo[1], largo[0])
        objetivo = math.pi / 2 if cfg.get("x_lado_corto", True) else 0.0
        # girar lo mínimo: sumar o restar 180° deja el lado largo igual de alineado
        ang = math.atan2(math.sin(objetivo - ang_largo), math.cos(objetivo - ang_largo))
        if ang > math.pi / 2 + 1e-9:
            ang -= math.pi
        elif ang < -math.pi / 2 - 1e-9:
            ang += math.pi
        if abs(ang) < 1e-9:
            ang = 0.0
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), ang)
    forma = transformar(forma, tr)
    x0, y0, z0, x1, y1, z1 = caja(forma)
    tt = gp_Trsf()
    tt.SetTranslation(gp_Vec(-x0, -y0, -z1))
    forma = transformar(forma, tt)
    if abajo:
        avisos.append("Hay caras que miran hacia abajo a %s mm: esa parte solo se puede hacer dando vuelta la placa (no está en este archivo)." %
                      ", ".join(fmt(a) for a in abajo))
    if incl:
        avisos.append("Hay caras inclinadas o curvas (no verticales ni fondos planos): Viruta trabaja en 2,5D; esas caras quedan escalonadas o sin hacer.")
    return forma, espesor, pisos


# ---------------------------------------------------------------- utilidades 2D
def poligonos(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [p for p in g.geoms if p.geom_type == "Polygon" and not p.is_empty]
    return []


def anillo_pts(anillo, horario):
    simp = anillo.simplify(0.004, preserve_topology=True)
    pts = list((simp if len(simp.coords) >= 4 else anillo).coords)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    a2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))
    if (a2 < 0) != horario:
        pts = pts[::-1]
    return pts


def esquinas_vivas(pg, r=None):
    """Esquinas cóncavas del material (interiores), que la fresa deja redondeadas.
    Con r, descarta las que dejan un resto despreciable (por ejemplo, las que ya tienen descarga)."""
    res = []
    pg = shapely.geometry.polygon.orient(pg, 1.0)  # exterior antihorario, huecos horario
    for anillo in [pg.exterior] + list(pg.interiors):
        pts = list(anillo.coords)[:-1]
        n = len(pts)
        for i in range(n):
            a, b, c = np.array(pts[i - 1]), np.array(pts[i]), np.array(pts[(i + 1) % n])
            v1, v2 = b - a, c - b
            if np.linalg.norm(v1) < 1e-6 or np.linalg.norm(v2) < 1e-6:
                continue
            cruz = v1[0] * v2[1] - v1[1] * v2[0]
            ang = math.degrees(math.acos(max(-1, min(1, np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))))))
            if cruz < 0 and ang > 20:
                res.append((float(b[0]), float(b[1])))
    if r and res:
        ok = []
        for x, y in res:
            pt = Point(x, y)
            vacio = pt.buffer(2.5 * r + 1.0, quad_segs=8).difference(pg)
            abierto = vacio.buffer(-r + 0.01, quad_segs=QS).buffer(r - 0.01, quad_segs=QS)
            if vacio.difference(abierto).intersection(pt.buffer(1.0, quad_segs=8)).area > 0.05:
                ok.append((x, y))
        res = ok
    return res


def hecho_antes(v, f, hechos):
    return any(abs(zf - f) < 1e-6 and mismo_hueco(v, z) for z, zf in hechos)


def mismo_hueco(a, b):
    if a.area <= 0:
        return False
    return a.symmetric_difference(b).area < 0.01 * a.area + 0.05


# ---------------------------------------------------------------- emisor de código G
class Camino(object):
    def __init__(self, pts, cerrado):
        pts = [tuple(p) for p in pts]
        if cerrado and pts[0] != pts[-1]:
            pts.append(pts[0])
        limpio = [pts[0]]
        for p in pts[1:]:
            if math.dist(p, limpio[-1]) > 1e-6:
                limpio.append(p)
        self.p = limpio
        self.acum = [0.0]
        for a, b in zip(self.p, self.p[1:]):
            self.acum.append(self.acum[-1] + math.dist(a, b))
        self.L = self.acum[-1]

    def punto(self, s):
        s = min(max(s, 0.0), self.L)
        i = min(max(bisect.bisect_right(self.acum, s) - 1, 0), len(self.p) - 2)
        L = self.acum[i + 1] - self.acum[i]
        t = 0.0 if L < 1e-12 else (s - self.acum[i]) / L
        a, b = self.p[i], self.p[i + 1]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class Emisor(object):
    def __init__(self, cfg, herr):
        self.cfg = cfg
        self.av, self.avb = float(cfg["avance"]), float(cfg["avance_bajada"])
        self.l = []
        self.x = self.y = 0.0
        self.z = None
        self.f = None
        self.nuevo_f = True
        self.corte = self.rapido = 0.0
        self.trazos = []
        self._tr = None

    def _fin(self):
        if self._tr and len(self._tr) > 1:
            self.trazos.append(self._tr)
        self._tr = None

    def g0z(self, z):
        z = round(z, 3)
        if self.z is not None and abs(self.z - z) < 1e-9:
            return
        self.l.append(("G0", None, None, z, None))
        if self.z is not None:
            self.rapido += abs(self.z - z)
        self.z = z
        self.nuevo_f = True
        self._fin()

    def g0xy(self, x, y):
        x, y = round(x, 3), round(y, 3)
        if abs(self.x - x) < 1e-9 and abs(self.y - y) < 1e-9:
            return
        self.l.append(("G0", x, y, None, None))
        self.rapido += math.hypot(x - self.x, y - self.y)
        self.x, self.y = x, y
        self.nuevo_f = True
        self._fin()

    def g1(self, x, y, z, f=None):
        x, y, z = round(x, 3), round(y, 3), round(z, 3)
        z0 = self.z if self.z is not None else z
        dx, dy, dz = x - self.x, y - self.y, z - z0
        if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
            return
        f = f or self.av
        ff = None
        if self.nuevo_f or f != self.f:
            ff, self.f, self.nuevo_f = f, f, False
        self.l.append(("G1", x if abs(dx) > 1e-9 else None, y if abs(dy) > 1e-9 else None,
                       z if abs(dz) > 1e-9 else None, ff))
        self.corte += math.sqrt(dx * dx + dy * dy + dz * dz)
        if self._tr is None:
            self._tr = [(self.x, self.y, z0)]
        self._tr.append((x, y, z))
        self.x, self.y, self.z = x, y, z

    def ir_a(self, x, y, z_hasta):
        zl = self.cfg["z_libre"]
        if self.z is None or self.z < zl:
            self.g0z(zl)
        self.g0xy(x, y)
        if self.z > zl:
            self.g0z(zl)
        if z_hasta < self.z - 1e-9:
            self.g1(x, y, z_hasta, self.avb)

    def texto(self, dz=0.0, dx=0.0, dy=0.0):
        """Código G final según el formato. dz/dx/dy: corrimiento de origen."""
        cfg = self.cfg
        fmtm = cfg["formato"]
        S = int(cfg["husillo"])
        out = []
        if fmtm == "grbl":
            out += ["G21 G90 G17", "M3 S%d" % S]
        elif fmtm == "linuxcnc":
            out += ["G21 G90 G17 G94", "M3 S%d" % S]
        else:  # mach3 / DDCS: la primera línea tiene que ser la del husillo (limpieza de la cátedra)
            out += ["S%d M3" % S, "G90 G17 G21"]
        for g, x, y, z, f in self.l:
            partes = [g]
            if x is not None:
                partes.append("X" + fmt(x + dx))
            if y is not None:
                partes.append("Y" + fmt(y + dy))
            if z is not None:
                partes.append("Z" + fmt(z + dz))
            if f is not None:
                partes.append("F" + fmt(f))
            out.append(" ".join(partes))
        out.append("G0 Z%s" % fmt(cfg["z_seguro"] + dz))
        out += ["M5", "M30"]
        return out


def largo_rampa(dz, cfg):
    return dz / math.tan(math.radians(cfg["rampa_grados"])) if dz > 1e-6 else 0.0


def recorrer_cerrado(em, cam, s0, z_ini, z_fin, cfg, z_pest=None, tabs=None):
    L = cam.L
    dz = z_ini - z_fin
    Lr = largo_rampa(dz, cfg)
    total = Lr + L
    tabs = tabs or []

    def zf(d):
        return z_fin if Lr <= 0 else z_ini - dz * min(1.0, max(0.0, d) / Lr)

    def zc(d):
        z = zf(d)
        s = (s0 + d) % L
        if z_pest is not None and z < z_pest and any(a < s < b for a, b in tabs):
            return z_pest
        return z

    bordes = sorted(set(x % L for iv in tabs for x in iv))
    ds = set([total] + ([Lr] if Lr > 0 else []))
    for k in range(-1, int(total // L) + 3):
        for b in list(cam.acum) + bordes:
            d = k * L + b - s0
            if 1e-7 < d < total - 1e-7:
                ds.add(round(d, 7))
    for d in sorted(ds):
        s = (s0 + d) % L
        x, y = cam.punto(s)
        if any(abs(s - b) < 1e-5 or abs(abs(s - b) - L) < 1e-5 for b in bordes):
            em.g1(x, y, zc(d - 1e-4))
            em.g1(x, y, zc(d + 1e-4))
        else:
            em.g1(x, y, zc(d))
    return (s0 + total) % L


def recorrer_abierto(em, cam, z_ini, z_fin, cfg):
    L = cam.L
    dz = z_ini - z_fin
    if L < 1.0 or dz <= 1e-6:
        if dz > 1e-6:
            em.g1(cam.p[0][0], cam.p[0][1], z_fin, em.avb)
        for p in cam.p[1:]:
            em.g1(p[0], p[1], z_fin)
        return
    Lr = largo_rampa(dz, cfg)
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
        x, y = cam.punto(pos(d))
        em.g1(x, y, z_ini - dz * min(1.0, d / Lr))
    s_fin = pos(Lr)
    for i in range(len(cam.acum) - 1, -1, -1):
        if cam.acum[i] < s_fin - 1e-7:
            em.g1(cam.p[i][0], cam.p[i][1], z_fin)
    for p in cam.p[1:]:
        em.g1(p[0], p[1], z_fin)


def escalones(desde, hasta, paso):
    if hasta <= desde + 1e-6:
        return []
    n = int(math.ceil((hasta - desde) / paso - 1e-9))
    return [-(desde + (hasta - desde) * k / n) for k in range(1, n + 1)]


# ---------------------------------------------------------------- pestañas
def tramos_rectos(pts):
    tramos, s, ini, prev = [], 0.0, 0.0, None
    for a, b in zip(pts, pts[1:]):
        v = np.subtract(b, a)
        L = float(np.linalg.norm(v))
        if L < 1e-9:
            continue
        v = v / L
        if prev is not None and math.degrees(math.acos(max(-1, min(1, float(np.dot(prev, v)))))) > 1.0:
            tramos.append((ini, s))
            ini = s
        prev = v
        s += L
    tramos.append((ini, s))
    return tramos, s


def cant_pestanas(cfg, lado_mayor, perimetro):
    if cfg.get("pestanas") is not None:
        return int(cfg["pestanas"])
    if lado_mayor < 80:
        return 2
    if lado_mayor <= 300:
        return 4
    if lado_mayor <= 600:
        return 6
    return max(8, int(math.ceil(perimetro / 200.0)))


def ubicar_pestanas(pts, n, D, largo):
    hueco = largo + D
    margen = D
    tramos, total = tramos_rectos(pts)
    if n <= 0:
        return [], True
    utiles = [(a, b) for a, b in tramos if (b - a) >= hueco + 2 * margen]
    if not utiles:
        return [((k + 0.5) * total / n - hueco / 2, (k + 0.5) * total / n + hueco / 2) for k in range(n)], False
    largos = [b - a for a, b in utiles]
    tot = sum(largos)
    cuotas = [n * L / tot for L in largos]
    asign = [int(math.floor(q)) for q in cuotas]
    orden = sorted(range(len(utiles)), key=lambda i: (cuotas[i] - asign[i], largos[i]), reverse=True)
    for i in orden[:n - sum(asign)]:
        asign[i] += 1
    centros = []
    for (a, b), k in zip(utiles, asign):
        if k == 0:
            continue
        a2, b2 = a + margen + hueco / 2, b - margen - hueco / 2
        k = min(k, max(1, int((b2 - a2) // (hueco + D)) + 1))
        for j in range(k):
            centros.append(a2 + (b2 - a2) * (j + 0.5) / k if k > 1 else (a2 + b2) / 2)
    centros.sort()
    return [(c - hueco / 2, c + hueco / 2) for c in centros], True


# ---------------------------------------------------------------- vaciado de una zona
def zigzag(A, paso_lat):
    """Segmentos paralelos a Y dentro de la zona A (centro de la fresa)."""
    segs = []
    if A.is_empty:
        return segs
    x0, y0, x1, y1 = A.bounds
    x = x0 + 0.05
    while x < x1:
        inter = A.intersection(LineString([(x, y0 - 5), (x, y1 + 5)]))
        geoms = getattr(inter, "geoms", [inter])
        for g in geoms:
            if g.geom_type == "LineString" and g.length > 0.1:
                (ax, ay), (bx, by) = g.coords[0], g.coords[-1]
                if ay > by:
                    ay, by = by, ay
                segs.append(((x, ay + 0.02), (x, by - 0.02)))
        x += paso_lat
    return segs


def vaciar(em, A, zs, z_arriba, cfg, D):
    """Vacía la zona A (centro de la fresa) bajando por zs desde z_arriba."""
    if A.is_empty:
        return False
    paso_lat = D * cfg["paso_lateral_pct"]
    segs = zigzag(A, paso_lat)
    paredes = []
    for pg in poligonos(A):
        paredes.append(anillo_pts(pg.exterior, horario=False))       # borde de cajera: antihorario
        for it in pg.interiors:
            paredes.append(anillo_pts(it, horario=True))              # isla: horario
    Ap = prep(A.buffer(1e-3))
    z_prev = z_arriba
    for z in zs:
        quedan = list(segs)
        actual = None
        while quedan:
            ref = actual if actual is not None else (em.x, em.y)
            mejor, inv, dmin = None, False, 1e18
            for sg in quedan:
                for invertido, ext in ((False, sg[0]), (True, sg[1])):
                    d = math.dist(ref, ext)
                    if d < dmin:
                        mejor, inv, dmin = sg, invertido, d
            quedan.remove(mejor)
            a, b = (mejor[1], mejor[0]) if inv else mejor
            if (actual is not None and abs(em.z - z) < 1e-6 and math.dist(actual, a) <= 3 * paso_lat
                    and Ap.contains(LineString([actual, a]))):
                em.g1(a[0], a[1], z)
                em.g1(b[0], b[1], z)
            else:
                em.ir_a(a[0], a[1], z_prev)
                recorrer_abierto(em, Camino([a, b], False), z_prev, z, cfg)
            actual = b
        for pts in paredes:
            cam = Camino(pts, True)
            em.ir_a(cam.p[0][0], cam.p[0][1], z_prev)
            recorrer_cerrado(em, cam, 0.0, z_prev, z, cfg)
        z_prev = z
    return True


# ---------------------------------------------------------------- mapa de alturas (independiente)
def mapa_alturas(forma, paso=0.5, margen=8.0):
    BRepMesh_IncrementalMesh(forma, 0.01, False, 0.1, True)
    x0b, y0b, z0b, x1b, y1b, z1b = caja(forma)
    x0 = x0b - margen + paso * 0.37
    y0 = y0b - margen + paso * 0.37
    nx = int(math.ceil((x1b - x0b + 2 * margen) / paso)) + 1
    ny = int(math.ceil((y1b - y0b + 2 * margen) / paso)) + 1
    Z = np.full((ny, nx), -np.inf)
    gx = x0 + np.arange(nx) * paso
    gy = y0 + np.arange(ny) * paso
    for f in caras(forma):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        tf = loc.Transformation()
        nodos = []
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(tf)
            nodos.append((p.X(), p.Y(), p.Z()))
        nodos = np.array(nodos)
        for i in range(1, tri.NbTriangles() + 1):
            t = tri.Triangle(i)
            a, b, c = nodos[t.Value(1) - 1], nodos[t.Value(2) - 1], nodos[t.Value(3) - 1]
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-12:
                continue  # triángulo vertical (pared)
            i0 = max(int(math.floor((min(a[0], b[0], c[0]) - x0) / paso)), 0)
            i1 = min(int(math.ceil((max(a[0], b[0], c[0]) - x0) / paso)), nx - 1)
            j0 = max(int(math.floor((min(a[1], b[1], c[1]) - y0) / paso)), 0)
            j1 = min(int(math.ceil((max(a[1], b[1], c[1]) - y0) / paso)), ny - 1)
            if i1 < i0 or j1 < j0:
                continue
            X, Y = np.meshgrid(gx[i0:i1 + 1], gy[j0:j1 + 1])
            l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / det
            l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / det
            l3 = 1 - l1 - l2
            dentro = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
            zz = l1 * a[2] + l2 * b[2] + l3 * c[2]
            sub = Z[j0:j1 + 1, i0:i1 + 1]
            sub[dentro] = np.maximum(sub[dentro], zz[dentro])
    vals = np.where(np.isfinite(Z), np.round(Z * 100), -32000).astype("<i2")
    datos = base64.b64encode(zlib.compress(vals.tobytes(), 9)).decode("ascii")
    return "MAPA %s %s %s %d %d %s" % (fmt(x0), fmt(y0), fmt(paso), nx, ny, datos), (x0, y0, paso, np.where(np.isfinite(Z), Z, np.nan))


# ---------------------------------------------------------------- una pieza, una herramienta
def mecanizar(forma, espesor, pisos, cfg, herr, previas, avisos, notas, desp=(0.0, 0.0)):
    """Devuelve (Emisor, info). `previas`: estado de lo que hicieron las herramientas anteriores."""
    D = float(herr["diametro"])
    r = D / 2
    paso = D * cfg["paso_pct"]
    ox, oy = desp

    def X(v):
        return fmt(v + ox)

    def Y(v):
        return fmt(v + oy)
    prof = espesor + cfg["extra"]
    principal = previas is None
    em = Emisor(dict(cfg, paso=paso), herr)
    em.g0z(cfg["z_seguro"])
    info = {"pisos": [], "pasantes": 0, "taladros": 0, "pestanas": [], "angostos": []}
    estado = {"pisos_hechos": set(), "huecos_hechos": set(), "zonas_hechas": []}

    fondo = seccion(forma, -espesor + 0.02)
    pgs = sorted(poligonos(fondo), key=lambda p: p.area, reverse=True)
    if not pgs:
        raise SystemExit("No se pudo leer el contorno de la pieza.")
    if len(pgs) > 1 and principal:
        avisos.append("La pieza tiene %d partes separadas abajo: se toma la más grande como contorno." % len(pgs))
    contorno = Polygon(pgs[0].exterior)
    pasantes = [Polygon(h) for h in pgs[0].interiors]
    limite = contorno.buffer(r, quad_segs=QS)

    # 1) cajeras, rebajes y escalones
    # los restos en esquinas (radio de la fresa) tienen un círculo inscripto de ≈ 0,17·r;
    # lo que sobrevive a una apertura de 0,25·Ø es una zona angosta de verdad
    apertura = max(0.6, 0.25 * D)
    angostos = {}
    inicio_pas = [0.0] * len(pasantes)
    z_arriba = 0.0
    hechos_prev = previas["zonas"] if previas else []
    vivas = []
    for f in pisos:
        mat = seccion(forma, -f + 0.02)
        vacios = poligonos(contorno.difference(mat))
        igualados = []
        mat2 = [mat]
        for v in vacios:
            idx = next((i for i, h in enumerate(pasantes) if mismo_hueco(v, h)), None)
            if idx is not None:
                igualados.append(idx)
                mat2.append(v)
            else:
                # lo que ya vació una herramienta anterior cuenta como material para esta
                if hecho_antes(v, f, hechos_prev):
                    mat2.append(v)
        for i in range(len(pasantes)):
            if i not in igualados:
                inicio_pas[i] = f
        M = unary_union(mat2)
        A = limite.difference(M.buffer(r, quad_segs=QS))
        A = unary_union([p for p in poligonos(A) if p.area > 1e-4])
        # zonas que esta fresa no alcanza
        alcanzado = A.buffer(r - 0.01, quad_segs=QS) if not A.is_empty else Polygon()
        for v in vacios:
            if any(mismo_hueco(v, pasantes[i]) for i in igualados):
                continue
            if hecho_antes(v, f, hechos_prev):
                continue
            resto = v.difference(alcanzado)
            grande = resto.buffer(-apertura).buffer(apertura)
            if not grande.is_empty and grande.area > 1.0:
                c = grande.centroid
                b = grande.bounds
                info["angostos"].append({"zona": v, "piso": f})
                clave = (round(c.x), round(c.y))
                angostos.setdefault(clave, {"b": b, "c": c, "pisos": []})["pisos"].append(f)
            else:
                estado["zonas_hechas"].append((v, f))
        if principal:
            for pg in poligonos(mat):
                vivas += esquinas_vivas(pg, r)
        if not A.is_empty and vaciar(em, A, escalones(z_arriba, f, paso), -z_arriba, cfg, D):
            info["pisos"].append(f)
        z_arriba = f

    for z_ in angostos.values():
        c, b = z_["c"], z_["b"]
        avisos.append("Zona a %s mm de profundidad cerca de X%s Y%s (%s × %s mm) más angosta que la fresa Ø%s: queda sin vaciar%s." % (
            " y ".join(fmt(f) for f in z_["pisos"]), X(c.x), Y(c.y), fmt(b[2] - b[0]), fmt(b[3] - b[1]), fmt(D),
            (" (la completa la fresa siguiente, en su propio archivo)" if D > min(float(h["diametro"]) for h in cfg["herramientas"]) + 1e-9
             else " (hace falta una fresa más chica en otro archivo, ej. --herramientas %s,3)" % fmt(D))))

    # 2) agujeros y recortes pasantes
    hechos_pas_prev = previas["pasantes"] if previas else set()
    for i, h in enumerate(pasantes):
        if i in hechos_pas_prev:
            continue
        if principal:
            vivas += esquinas_vivas(Polygon(h.buffer(3 * D + 2).exterior, [h.exterior]), r)
        path = h.buffer(-r, quad_segs=QS)
        desde = inicio_pas[i]
        c = h.centroid
        if path.is_empty or path.area < 1e-4:
            x0, y0, x1, y1 = h.bounds
            d_eq = 2 * math.sqrt(h.area / math.pi)
            redondo = abs((x1 - x0) - (y1 - y0)) < 0.05 and abs(d_eq - (x1 - x0)) < 0.05
            if redondo and D - 0.01 <= d_eq <= D + 0.4:
                em.ir_a(c.x, c.y, -desde)
                zs = escalones(desde, prof, paso)
                for k, z in enumerate(zs):
                    em.g1(c.x, c.y, z, em.avb)
                    em.g0z(cfg["z_libre"])
                    if k < len(zs) - 1:
                        em.g0z(z + 0.5)
                info["taladros"] += 1
                estado["huecos_hechos"].add(i)
            else:
                avisos.append("Agujero/recorte pasante cerca de X%s Y%s (%s × %s mm) más chico que la fresa Ø%s: no se puede cortar%s." % (
                    X(c.x), Y(c.y), fmt(x1 - x0), fmt(y1 - y0), fmt(D),
                    " con esta fresa (lo corta la siguiente, en su propio archivo)" if D > min(float(h["diametro"]) for h in cfg["herramientas"]) + 1e-9
                    else " (hace falta una fresa más chica)"))
            continue
        resto = h.difference(path.buffer(r - 0.01, quad_segs=QS)).buffer(-apertura).buffer(apertura)
        if not resto.is_empty and resto.area > 1.0:
            avisos.append("Parte del recorte pasante cerca de X%s Y%s es más angosta que la fresa Ø%s: queda sin cortar." % (X(c.x), Y(c.y), fmt(D)))
        for pg in poligonos(path):
            cam = Camino(anillo_pts(pg.exterior, horario=False), True)
            em.ir_a(cam.p[0][0], cam.p[0][1], -desde)
            s, z_prev = 0.0, -desde
            for z in escalones(desde, prof, paso):
                s = recorrer_cerrado(em, cam, s, z_prev, z, cfg)
                z_prev = z
        info["pasantes"] += 1
        estado["huecos_hechos"].add(i)
    if previas:
        estado["huecos_hechos"] |= previas["pasantes"]

    # 3) contorno exterior con pestañas (solo la herramienta principal)
    if principal:
        vivas += esquinas_vivas(contorno, r)
        ext = limite.exterior
        pts = anillo_pts(ext, horario=True)
        tramos, perim = tramos_rectos(pts)
        mejor = max(tramos, key=lambda t: t[1] - t[0])
        s, idx = 0.0, 0
        for i in range(len(pts) - 1):
            if abs(s - mejor[0]) < 1e-6:
                idx = i
                break
            s += math.dist(pts[i], pts[i + 1])
        base = pts[:-1]
        base = base[idx:] + base[:idx]
        pts = base + [base[0]]
        x0, y0, x1, y1 = contorno.bounds
        n = cant_pestanas(cfg, max(x1 - x0, y1 - y0), perim)
        largo_p = float(cfg["pestana_largo"])
        alto_p = float(cfg["pestana_alto"]) if cfg.get("pestana_alto") is not None else max(1.0, round(espesor / 3.0 * 2) / 2.0)
        tabs, en_rectas = ubicar_pestanas(pts, n, D, largo_p)
        if cfg.get("_pestanas_en_int"):
            linea = LineString(pts)
            hueco = largo_p + D
            tabs = sorted((linea.project(Point(px, py)) - hueco / 2, linea.project(Point(px, py)) + hueco / 2)
                          for px, py in cfg["_pestanas_en_int"])
            tabs = [(max(a_, 0.0), min(b_, linea.length)) for a_, b_ in tabs]
            en_rectas = True
        cam = Camino(pts, True)
        z_pest = -prof + alto_p
        em.ir_a(cam.p[0][0], cam.p[0][1], 0.0)
        s, z_prev = 0.0, 0.0
        for z in escalones(0.0, prof, paso):
            s = recorrer_cerrado(em, cam, s, z_prev, z, cfg, z_pest if tabs else None, tabs)
            z_prev = z
        info["pestanas"] = [cam.punto(((a + b) / 2) % cam.L) for a, b in tabs]
        info["pestana_medida"] = (largo_p, alto_p, en_rectas)
        # esquinas vivas sin repetir
        unicas, vistas = [], set()
        for p in vivas:
            k = (round(p[0], 1), round(p[1], 1))
            if k not in vistas:
                vistas.add(k)
                unicas.append(p)
        if unicas:
            avisos.append("%d esquinas interiores vivas (%s%s): la fresa Ø%s las deja redondeadas R%s. Si son encastres, agregá descargas (dogbones) en el modelo o pedí que Viruta las agregue (--descargas)." % (
                len(unicas), ", ".join("X%s Y%s" % (X(x), Y(y)) for x, y in unicas[:8]), "…" if len(unicas) > 8 else "", fmt(D), fmt(r)))
    loc = herr.get("loc")
    if loc and prof > float(loc) + 1e-6:
        avisos.append("La fresa Ø%s tiene %s mm de largo de corte y el corte pasante pide %s mm: no alcanza." % (fmt(D), fmt(loc), fmt(prof)))
    if previas:
        estado["zonas_hechas"] += previas["zonas"]
    em._fin()
    return em, info, {"zonas": estado["zonas_hechas"], "pasantes": estado["huecos_hechos"]}, contorno


# ---------------------------------------------------------------- vista previa
def vista_previa(path, nombre, contorno, mapa, trazos_por_herr, info, cfg, espesor, origen_txt):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x0, y0, paso, Z = mapa
    ny, nx = Z.shape
    w = (nx * paso)
    h = (ny * paso)
    fig_w = 7.5
    fig, ax = plt.subplots(figsize=(fig_w, max(4.0, fig_w * h / w)), dpi=130)
    prof = np.where(np.isnan(Z), np.nan, -Z)
    im = ax.imshow(prof, origin="lower", extent=(x0, x0 + nx * paso, y0, y0 + ny * paso),
                   cmap="Blues", vmin=-0.35 * max(espesor, 1), vmax=max(espesor, 1), alpha=0.9)
    cx, cy = contorno.exterior.xy
    ax.plot(cx, cy, color="#495057", lw=0.8)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("profundidad desde la cara de arriba (mm)")
    colores = ["#d9480f", "#7048e8", "#2b8a3e"]
    for k, (D, trazos) in enumerate(trazos_por_herr):
        for tr in trazos:
            xs = [p[0] for p in tr]
            ys = [p[1] for p in tr]
            ax.plot(xs, ys, color=colores[k % 3], lw=0.35, alpha=0.8)
        ax.plot([], [], color=colores[k % 3], lw=1.5, label="trayectoria fresa Ø%s" % fmt(D))
    for x, y in info.get("pestanas", []):
        ax.plot(x, y, "s", ms=7, mfc="#ffd43b", mec="#000", mew=0.8)
        ax.annotate("P", (x, y), ha="center", va="center", fontsize=6, fontweight="bold")
    ax.plot([], [], "s", ms=7, mfc="#ffd43b", mec="#000", label="pestaña")
    b = contorno.bounds
    L = min(b[2] - b[0], b[3] - b[1]) * 0.25 + 5
    ax.annotate("", xy=(L, 0), xytext=(0, 0), arrowprops=dict(arrowstyle="->", color="red", lw=1.5))
    ax.annotate("", xy=(0, L), xytext=(0, 0), arrowprops=dict(arrowstyle="->", color="green", lw=1.5))
    ax.text(L, -3, "X", color="red", fontsize=9, va="top")
    ax.text(-3, L, "Y", color="green", fontsize=9, ha="right")
    ax.plot(0, 0, "o", color="black", ms=4)
    ax.set_aspect("equal")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title("%s — %s × %s × %s mm\n%s" % (nombre, fmt(b[2] - b[0]), fmt(b[3] - b[1]), fmt(espesor), origen_txt), fontsize=9)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.85)
    ax.grid(True, lw=0.2, alpha=0.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- principal
def cargar_cfg(a):
    cfg = dict(DEF)
    if a.perfil and a.perfil != "ninguno":
        if a.perfil not in PERFILES:
            raise SystemExit("Perfil desconocido: %s (hay: %s)" % (a.perfil, ", ".join(PERFILES)))
        cfg.update({k: v for k, v in PERFILES[a.perfil].items() if k != "nombre"})
        cfg["perfil_nombre"] = PERFILES[a.perfil]["nombre"]
    if a.config:
        with open(a.config, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    for k in ("husillo", "avance", "avance_bajada", "extra", "z_seguro", "z_libre", "pestanas", "pestana_largo",
              "pestana_alto", "formato", "origen", "z0", "extension", "rampa_grados", "cara_arriba",
              "pestanas_en"):
        v = getattr(a, k, None)
        if v is not None:
            cfg[k] = v
    if a.x_largo:
        cfg["x_lado_corto"] = False
    base_h = cfg["herramientas"][0] if cfg["herramientas"] else {"diametro": 6.0}
    if a.herramientas:
        ds = [float(d) for d in a.herramientas.split(",")]
    elif a.diametro:
        ds = [a.diametro]
    else:
        ds = None
    if ds:
        cfg["herramientas"] = [dict(base_h) if abs(float(base_h["diametro"]) - d) < 1e-9 else {"diametro": d} for d in ds]
    if a.loc:
        cfg["herramientas"][0]["loc"] = a.loc
    if a.paso_pct:
        cfg["paso_pct"] = a.paso_pct
    cfg["herramientas"] = sorted(cfg["herramientas"], key=lambda h: -float(h["diametro"]))
    return cfg


def _limpiar_nombre(n):
    n = "".join(ch if (ch.isalnum() or ch in "_-.") else "_" for ch in n.strip())
    n = re.sub(r"_+", "_", n).strip("_.")
    return n or "pieza"


def _raiz(n):
    """'Pata (2)', 'Pata:3', 'Pata_4', 'Pata<1>' -> 'pata' (copias de la misma pieza)."""
    return re.sub(r"([\s_\-:.]*(\(\d+\)|<\d+>|\d+))+$", "", n.strip()).lower()


def _mapa_igual(m1, m2, tol=0.06):
    """Mismo mapa de alturas (o girado 180°), con tolerancia en los bordes de la grilla."""
    a, b = m1[3], m2[3]
    for bb in (b, b[::-1, ::-1]):
        if a.shape != bb.shape:
            continue
        na, nb = np.isnan(a), np.isnan(bb)
        if (na != nb).mean() > 0.02:
            continue
        comun = ~na & ~nb
        if not comun.any():
            continue
        dif = np.abs(a[comun] - bb[comun])
        if (dif > tol).mean() <= 0.02:
            return True
    return False


def juntar_piezas(a, cfg):
    """Lee todos los STEP, acuesta cada pieza y junta las copias iguales (misma forma y mismo nombre base)
    en un solo archivo con su cantidad."""
    filtro = [_raiz(x) for x in a.piezas.split(",")] if a.piezas else None
    crudas = []
    for path in a.step:
        sols = leer_step(path)
        base = a.nombre if (a.nombre and len(a.step) == 1) else os.path.splitext(os.path.basename(path))[0]
        if not sols:
            print("AVISO: %s no tiene sólidos cerrados (exportá sólidos, no superficies)." % path)
        for n, s in sols:
            crudas.append((n or base, s))
    if filtro:
        crudas = [(n, s) for n, s in crudas if _raiz(n) in filtro or n.lower() in filtro]
        if not crudas:
            raise SystemExit("Ninguna pieza se llama %s." % a.piezas)
    grupos = []
    for n, s in crudas:
        h = huella(s)
        av = []
        forma, espesor, pisos = orientar(s, cfg, av)
        mapa = mapa_alturas(forma, 1.0)[1]
        for g in grupos:
            if (not a.separar_iguales and _raiz(g["nombre_orig"]) == _raiz(n) and misma_huella(g["huella"], h)
                    and _mapa_igual(g["mapa"], mapa)):
                g["cantidad"] += 1
                break
        else:
            grupos.append({"nombre_orig": n, "huella": h, "mapa": mapa, "forma": forma, "espesor": espesor,
                           "pisos": pisos, "avisos": av, "notas": [], "cantidad": 1})
    # nombres de archivo únicos
    usados = {}
    for g in grupos:
        base = _limpiar_nombre(g["nombre_orig"] if g["cantidad"] == 1 else re.sub(r"([\s_\-:.]*(\(\d+\)|<\d+>|\d+))+$", "", g["nombre_orig"]) or g["nombre_orig"])
        k = base.lower()
        usados[k] = usados.get(k, 0) + 1
        g["nombre"] = base if usados[k] == 1 else "%s_%d" % (base, usados[k])
    # descargas (dogbones)
    if a.descargas:
        D = float(cfg["herramientas"][0]["diametro"])
        R = D / 2.0 + float(a.descargas_extra)
        for g in grupos:
            f2, hechas = descargas(g["forma"], R, g["espesor"])
            if hechas:
                g["forma"] = f2
                g["descargas"] = (R, hechas)
    return grupos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="+", help="uno o más archivos STEP")
    ap.add_argument("--perfil", default="taller5", help="perfil de máquina (taller5), o 'ninguno' para armarlo con --config y opciones")
    ap.add_argument("--config", help="JSON con valores del perfil (otra máquina)")
    ap.add_argument("--salida", default=".", help="carpeta de salida")
    ap.add_argument("--nombre", help="nombre base de los archivos (por defecto, el del STEP)")
    ap.add_argument("--diametro", type=float)
    ap.add_argument("--loc", type=float, help="largo de corte de la fresa principal (mm)")
    ap.add_argument("--herramientas", help="diámetros separados por coma, ej. 6,3")
    ap.add_argument("--paso-pct", dest="paso_pct", type=float, help="paso vertical como fracción del Ø (0,5)")
    ap.add_argument("--husillo", type=int)
    ap.add_argument("--avance", type=float)
    ap.add_argument("--avance-bajada", dest="avance_bajada", type=float)
    ap.add_argument("--extra", type=float, help="profundidad extra en pasantes (0,3)")
    ap.add_argument("--z-seguro", dest="z_seguro", type=float)
    ap.add_argument("--z-libre", dest="z_libre", type=float)
    ap.add_argument("--pestanas", type=int, help="cantidad (0 = sin pestañas)")
    ap.add_argument("--pestana-largo", dest="pestana_largo", type=float)
    ap.add_argument("--pestana-alto", dest="pestana_alto", type=float)
    ap.add_argument("--pestanas-en", dest="pestanas_en",
                    help="dónde poner las pestañas, en coordenadas del código: 'X,Y;X,Y;...' (se llevan al contorno)")
    ap.add_argument("--descargas", action="store_true", help="agregar descargas (dogbones) en las esquinas interiores vivas")
    ap.add_argument("--descargas-extra", dest="descargas_extra", type=float, default=0.2,
                    help="radio de la descarga = radio de la fresa + esto (0,2 mm)")
    ap.add_argument("--piezas", help="procesar solo estas piezas (nombres separados por coma)")
    ap.add_argument("--separar-iguales", dest="separar_iguales", action="store_true",
                    help="un archivo por cada copia aunque sean iguales")
    ap.add_argument("--rampa-grados", dest="rampa_grados", type=float)
    ap.add_argument("--formato", choices=["mach3", "grbl", "linuxcnc"])
    ap.add_argument("--origen", choices=["esquina", "centro"])
    ap.add_argument("--z0", choices=["arriba", "mesa"])
    ap.add_argument("--x-largo", dest="x_largo", action="store_true", help="X = lado largo (por defecto X = lado corto)")
    ap.add_argument("--extension")
    ap.add_argument("--cara-arriba", dest="cara_arriba", choices=["auto", "+Z", "-Z", "+X", "-X", "+Y", "-Y"])
    ap.add_argument("--mapa", type=float, default=0.5, help="paso del mapa de alturas (0 = no)")
    ap.add_argument("--vista-previa", dest="vista", action="store_true")
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--no-escribir", dest="no_escribir", action="store_true", help="solo informe y vista previa")
    a = ap.parse_args()
    cfg = cargar_cfg(a)
    os.makedirs(a.salida, exist_ok=True)

    piezas = juntar_piezas(a, cfg)

    filas_csv = []
    resumen_global = []
    for pz in piezas:
        nombre, forma, espesor, pisos, cant = pz["nombre"], pz["forma"], pz["espesor"], pz["pisos"], pz["cantidad"]
        avisos, notas = list(pz["avisos"]), list(pz["notas"])
        x0, y0, z0, x1, y1, z1 = caja(forma)
        ancho, largo = x1 - x0, y1 - y0
        prof = espesor + cfg["extra"]
        dx = dy = 0.0
        if cfg["origen"] == "centro":
            dx, dy = -ancho / 2, -largo / 2
        dz = espesor if cfg["z0"] == "mesa" else 0.0
        origen_txt = "Origen: %s, Z0 %s" % ("centro de la pieza" if cfg["origen"] == "centro" else "esquina inferior izquierda",
                                          "sobre la mesa (cara de abajo)" if cfg["z0"] == "mesa" else "en la cara de ARRIBA de la placa")
        if pz.get("descargas"):
            R_, hechas = pz["descargas"]
            notas.append("Descargas (dogbones) R%s agregadas en %d esquinas interiores: %s." % (
                fmt(R_), len(hechas), ", ".join("X%s Y%s" % (fmt(x + dx), fmt(y + dy)) for x, y in hechas[:10]) + ("…" if len(hechas) > 10 else "")))
        if cfg.get("pestanas_en"):
            cfg["_pestanas_en_int"] = [(float(p.split(",")[0]) - dx, float(p.split(",")[1]) - dy)
                                       for p in str(cfg["pestanas_en"]).replace(" ", "").split(";") if p]
        previas = None
        archivos, trazos_h = [], []
        info0 = None
        contorno = None
        multi = len(cfg["herramientas"]) > 1
        for k, herr in enumerate(cfg["herramientas"]):
            D = float(herr["diametro"])
            em, info, previas_n, cont = mecanizar(forma, espesor, pisos, cfg, herr, previas, avisos, notas, (dx, dy))
            if k == 0:
                info0, contorno = info, cont
            hizo_algo = any(l[0] == "G1" for l in em.l)
            if k > 0 and not hizo_algo:
                notas.append("La fresa Ø%s no tiene nada para hacer (todo lo hizo la anterior)." % fmt(D))
                previas = previas_n
                continue
            sufijo = ("_T%s" % fmt(D).replace(".", "-")) if multi else ""
            ruta = os.path.join(a.salida, nombre + sufijo + cfg["extension"])
            texto = em.texto(dz=dz, dx=dx, dy=dy)
            if not a.no_escribir:
                with open(ruta, "w", newline="\r\n", encoding="ascii") as fh:
                    fh.write("\n".join(texto) + "\n")
            minutos = (em.corte / float(cfg["avance"]) + em.rapido / float(cfg["rapido"])) * 1.1
            archivos.append({"archivo": ruta, "diametro": D, "lineas": len(texto), "tiempo_min": round(minutos, 1),
                             "dx": dx, "dy": dy, "dz": dz})
            trazos_h.append((D, [[(x, y) for x, y, z in tr] for tr in em.trazos]))
            filas_csv.append({"pieza": nombre, "medidas_mm": "%s x %s x %s" % (fmt(ancho), fmt(largo), fmt(espesor)),
                              "cantidad": cant, "herramienta": "Ø%s %s" % (fmt(D), herr.get("nombre", "plana")),
                              "rpm": int(cfg["husillo"]), "avance_mm_min": fmt(cfg["avance"]),
                              "tiempo_estimado_min": round(minutos, 1), "archivo": os.path.basename(ruta)})
            previas = previas_n

        mapa_txt, mapa = (None, None)
        if a.mapa and a.mapa > 0:
            mapa_txt, mapa = mapa_alturas(forma, a.mapa)
            ruta_mapa = os.path.join(a.salida, nombre + ".mapa")
            with open(ruta_mapa, "w") as fh:
                fh.write(mapa_txt + "\n")
        if a.vista and mapa is not None:
            vista_previa(os.path.join(a.salida, nombre + "_vista.png"), nombre, contorno, mapa, trazos_h, info0, cfg, espesor, origen_txt)

        print("=== %s ===" % nombre)
        print("pieza: %s (X) x %s (Y) x %s (espesor) mm" % (fmt(ancho), fmt(largo), fmt(espesor)))
        if cant > 1:
            print("cantidad: %d piezas iguales -> el mismo archivo se corta %d veces" % (cant, cant))
        print("perfil: %s | formato %s | %s" % (cfg.get("perfil_nombre", "personalizado"), cfg["formato"], origen_txt))
        print("cajeras/rebajes (mm): %s" % (", ".join(fmt(p) for p in info0["pisos"]) or "no hay"))
        print("pasante: %s mm | agujeros por contorno: %d | taladrados: %d" % (fmt(prof), info0["pasantes"], info0["taladros"]))
        lp, hp, rect = info0.get("pestana_medida", (0, 0, True))
        print("pestañas: %d de %s x %s mm (%s): %s" % (len(info0["pestanas"]), fmt(lp), fmt(hp), "en tramos rectos" if rect else "pieza curva: repartidas parejo",
                                                       ", ".join("X%s Y%s" % (fmt(x + dx), fmt(y + dy)) for x, y in info0["pestanas"])))
        for ar in archivos:
            print("archivo: %s (fresa Ø%s, %d líneas, ≈ %s min)" % (ar["archivo"] if not a.no_escribir else "(vista previa)", fmt(ar["diametro"]), ar["lineas"], ar["tiempo_min"]))
        for n_ in notas:
            print("NOTA: " + n_)
        vistos = set()
        for av in avisos:
            if av not in vistos:
                vistos.add(av)
                print("AVISO: " + av)
        if a.verificar and mapa_txt and not a.no_escribir:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import verificar_gcode as vg
            pares = [(ar["archivo"], ar["diametro"]) for ar in archivos]
            ok = vg.verificar(pares, os.path.join(a.salida, nombre + ".mapa"), espesor, desplazamiento=(dx, dy, dz))
            resumen_global.append((nombre, ok))
        print()

    if filas_csv and not a.no_escribir:
        ruta_csv = os.path.join(a.salida, "lista_de_cortes.csv")
        with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas_csv[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(filas_csv)
        print("lista de cortes: %s" % ruta_csv)
    if resumen_global:
        print("VERIFICACIÓN: " + ", ".join("%s %s" % (n, "OK" if ok else "CON ERRORES") for n, ok in resumen_global))


if __name__ == "__main__":
    main()
