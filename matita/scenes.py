# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scene demo per provare l'add-on: architettura, meccanica, natura morta.

Ogni demo viene costruita in una scena nuova (la scena corrente non viene
toccata), interamente via bmesh: nessun operatore, nessun file esterno.
"""

import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from . import core, presets

SMOOTH_ANGLE = math.radians(30)


# ---------------------------------------------------------------------------
# costruzione mesh
# ---------------------------------------------------------------------------
def _spline(points, steps):
    """Catmull-Rom sul profilo (r, z). Un punto (r, z, "c") è uno spigolo vivo."""
    runs, run = [], []
    for p in points:
        run.append((p[0], p[1]))
        if len(p) > 2 and len(run) > 1:
            runs.append(run)
            run = [(p[0], p[1])]
    if len(run) > 1:
        runs.append(run)
    out = [runs[0][0]]
    for run in runs:
        if len(run) == 2 or steps < 2:
            out.extend(run[1:])
            continue
        ext = [run[0]] + run + [run[-1]]
        for i in range(1, len(ext) - 2):
            p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
            for k in range(1, steps + 1):
                t = k / steps
                out.append(tuple(
                    0.5 * ((2 * p1[a]) + (-p0[a] + p2[a]) * t
                           + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t * t
                           + (-p0[a] + 3 * p1[a] - 3 * p2[a] + p3[a]) * t ** 3)
                    for a in (0, 1)))
    return [(max(r, 0.0), z) for r, z in out]


class Builder:
    """Crea oggetti mesh in una collection. Angoli in gradi, quote in metri."""

    def __init__(self, collection):
        self.col = collection

    def _finish(self, name, bm, loc, rot, smooth):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if smooth:
            for f in bm.faces:
                f.smooth = True
            for e in bm.edges:
                if len(e.link_faces) == 2:
                    e.smooth = e.calc_face_angle(0.0) < SMOOTH_ANGLE
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = Euler([math.radians(a) for a in rot])
        self.col.objects.link(ob)
        return ob

    def box(self, name, size, loc=(0, 0, 0), rot=(0, 0, 0), offset=(0, 0, 0)):
        """Parallelepipedo centrato in `offset` (coordinate locali)."""
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.transform(bm, verts=bm.verts,
                            matrix=Matrix.Translation(offset) @ Matrix.Diagonal((*size, 1.0)))
        return self._finish(name, bm, loc, rot, False)

    def block(self, name, x0, x1, y0, y1, z0, z1):
        """Parallelepipedo dato per estremi."""
        return self.box(name, (x1 - x0, y1 - y0, z1 - z0),
                        ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))

    def cyl(self, name, r, h, loc=(0, 0, 0), rot=(0, 0, 0), segs=32, r2=None):
        """Cilindro/cono con la base nell'origine locale, asse +Z."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r,
                              radius2=r if r2 is None else r2, depth=h,
                              matrix=Matrix.Translation((0, 0, h / 2)))
        return self._finish(name, bm, loc, rot, True)

    def sphere(self, name, r, loc=(0, 0, 0), scale=(1, 1, 1), subdiv=3):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r,
                                   matrix=Matrix.Diagonal((*scale, 1.0)))
        return self._finish(name, bm, loc, (0, 0, 0), True)

    def lathe(self, name, profile, loc=(0, 0, 0), rot=(0, 0, 0), segs=48,
              closed=False, steps=0):
        """Solido di rivoluzione attorno a Z dal profilo [(r, z), ...].

        steps > 0 ammorbidisce il profilo; closed chiude l'ultimo punto sul
        primo (anelli, cerchioni); r = 0 genera un polo.
        """
        pts = _spline(profile, steps) if steps else [(p[0], p[1]) for p in profile]
        bm = bmesh.new()
        rings = []
        for r, z in pts:
            if r < 1e-7:
                rings.append([bm.verts.new((0, 0, z))])
            else:
                rings.append([bm.verts.new((r * math.cos(2 * math.pi * j / segs),
                                            r * math.sin(2 * math.pi * j / segs), z))
                              for j in range(segs)])
        pairs = list(zip(rings, rings[1:]))
        if closed:
            pairs.append((rings[-1], rings[0]))
        for a, b in pairs:
            if len(a) == 1 and len(b) == 1:
                continue
            for j in range(segs):
                k = (j + 1) % segs
                if len(a) == 1:
                    bm.faces.new((a[0], b[k], b[j]))
                elif len(b) == 1:
                    bm.faces.new((a[j], a[k], b[0]))
                else:
                    bm.faces.new((a[j], a[k], b[k], b[j]))
        return self._finish(name, bm, loc, rot, True)

    def ring(self, name, r_in, r_out, length, loc=(0, 0, 0), rot=(0, 0, 0), segs=48):
        """Anello a sezione rettangolare centrato sull'origine locale (asse Z)."""
        h = length / 2
        return self.lathe(name, [(r_in, -h), (r_out, -h), (r_out, h), (r_in, h)],
                          loc, rot, segs, closed=True)

    def gear(self, name, teeth, module, width, bore, loc=(0, 0, 0), rot=(0, 0, 0), phase=0.0):
        """Ruota dentata a denti dritti nel piano XY locale, asse Z."""
        pitch = 2 * math.pi / teeth
        r_tip = module * (teeth / 2 + 1.0)
        r_root = module * (teeth / 2 - 1.25)
        outline = []
        for i in range(teeth):
            a = phase + i * pitch
            outline += [(r_root, a - 0.27 * pitch), (r_tip, a - 0.12 * pitch),
                        (r_tip, a + 0.12 * pitch), (r_root, a + 0.27 * pitch)]
        bm = bmesh.new()
        loops = {}
        for z in (-width / 2, width / 2):
            loops[z, "out"] = [bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, a in outline]
            loops[z, "in"] = [bm.verts.new((bore * math.cos(a), bore * math.sin(a), z)) for _, a in outline]
        lo, hi = -width / 2, width / 2
        n = len(outline)
        for j in range(n):
            k = (j + 1) % n
            bm.faces.new((loops[lo, "out"][j], loops[lo, "out"][k], loops[hi, "out"][k], loops[hi, "out"][j]))
            bm.faces.new((loops[lo, "in"][j], loops[lo, "in"][k], loops[hi, "in"][k], loops[hi, "in"][j]))
            for z in (lo, hi):
                bm.faces.new((loops[z, "out"][j], loops[z, "out"][k], loops[z, "in"][k], loops[z, "in"][j]))
        return self._finish(name, bm, loc, rot, True)


# ---------------------------------------------------------------------------
# 1. architettura: villa moderna su podio
# ---------------------------------------------------------------------------
def _tree(b, name, x, y, s=1.0):
    b.cyl(f"{name}_Tronco", 0.24 * s, 3.4 * s, (x, y, 0), segs=12, r2=0.14 * s)
    for i, (dx, dy, dz, r) in enumerate(((0, 0, 4.6, 2.2), (1.1, -0.7, 5.7, 1.6),
                                         (-1.2, 0.6, 5.3, 1.5), (0.3, 1.0, 6.3, 1.2))):
        b.sphere(f"{name}_Chioma{i}", r * s, (x + dx * s, y + dy * s, dz * s),
                 scale=(1.0, 1.0, 0.85), subdiv=3)


def build_architecture(b):
    # terreno (basamento da plastico) e podio
    b.block("Basamento", -15, 15, -11, 11, -0.5, 0)
    b.block("Podio", -9, 8, -4, 6, 0, 0.6)
    for i in range(3):
        b.block(f"Gradino{i}", -2, 2, -4 - 0.4 * (3 - i), -4 - 0.4 * (2 - i), 0, 0.15 * (i + 1))
    for i, y in enumerate((-6.9, -8.4, -9.9)):
        b.block(f"Lastra{i}", -1.1, 1.1, y, y + 1.2, 0, 0.05)

    # piano terra: padiglione vetrato (z 0.6 -> 3.6)
    z0, z1 = 0.6, 3.6
    b.block("PT_MuroRetro", -7, 3, 4.75, 5, z0, z1)
    b.block("PT_MuroSx", -7, -6.75, -1, 4.75, z0, z1)
    b.block("PT_MuroDx", 2.75, 3, 2, 4.75, z0, z1)
    b.block("PT_Architrave", -6.75, 3, -1, -0.8, 3.3, z1)
    b.block("PT_ArchitraveDx", 2.8, 3, -0.8, 2, 3.3, z1)
    for i in range(9):
        x = -6.75 + 9.5 * i / 8
        b.block(f"PT_Montante{i}", x - 0.04, x + 0.04, -0.96, -0.84, z0, 3.3)
    for i in range(1, 3):
        y = -0.9 + 2.9 * i / 3
        b.block(f"PT_MontanteDx{i}", 2.84, 2.96, y - 0.04, y + 0.04, z0, 3.3)
    b.block("PT_Traverso", -6.75, 2.9, -0.93, -0.87, 2.7, 2.76)
    b.block("PT_Nucleo", -2.6, -0.6, 2.2, 4.75, z0, z1)
    b.block("PT_Isola", -5.6, -3.6, 0.6, 1.5, z0, 1.5)

    # solaio e volume superiore a sbalzo (z 3.95 -> 6.9)
    b.block("Solaio", -7.4, 9, -4, 5.4, 3.6, 3.95)
    u0, u1 = 3.95, 6.9
    b.block("P1_MuroRetro", -3, 9, 1.75, 2, u0, u1)
    b.block("P1_MuroSx", -3, -2.75, -4, 1.75, u0, u1)
    b.block("P1_MuroDx", 8.75, 9, -4, 1.75, u0, u1)
    b.block("P1_Parapetto", -2.75, 8.75, -4, -3.75, u0, 4.85)
    b.block("P1_Veletta", -2.75, 8.75, -4, -3.75, 6.3, u1)
    for i in range(1, 10):
        x = -2.75 + 11.5 * i / 10
        b.block(f"P1_Montante{i}", x - 0.035, x + 0.035, -3.94, -3.82, 4.85, 6.3)
    b.block("P1_Tramezzo", 3, 3.2, -3.75, 1.75, u0, u1)
    b.block("Tetto", -3.5, 9.5, -4.5, 2.5, u1, 7.15)
    b.block("Tetto_Volume", 4.6, 6.4, -0.8, 0.9, 7.15, 8.1)
    b.block("Camino", -2.3, -1.6, 0.6, 1.3, 7.15, 9.0)

    # pilotis sotto lo sbalzo
    for i, (x, y, base) in enumerate(((8.4, -3.4, 0.0), (8.4, 1.4, 0.0), (5.2, -3.4, 0.6))):
        b.cyl(f"Pilotis{i}", 0.16, 3.6 - base, (x, y, base), segs=24)

    # ringhiera della terrazza (fronte e lato sinistro)
    posts = [(-7.3 + 4.2 * i / 3, -3.9) for i in range(4)] + [(-7.3, -3.9 + 9.2 * i / 6) for i in range(1, 7)]
    for i, (x, y) in enumerate(posts):
        b.block(f"Ringhiera_Paletto{i}", x - 0.025, x + 0.025, y - 0.025, y + 0.025, u0, 4.95)
    for j, z in enumerate((4.45, 4.95)):
        b.block(f"Ringhiera_FronteCorr{j}", -7.33, -3.0, -3.93, -3.87, z, z + 0.05)
        b.block(f"Ringhiera_LatoCorr{j}", -7.33, -7.27, -3.93, 5.33, z, z + 0.05)

    # vasca d'acqua, muro di cinta, panca
    b.block("Vasca_Acqua", 3.25, 11.75, -9.25, -6.25, 0, 0.06)
    for name, ext in (("F", (3, 12, -9.5, -9.25)), ("R", (3, 12, -6.25, -6)),
                      ("S", (3, 3.25, -9.25, -6.25)), ("D", (11.75, 12, -9.25, -6.25))):
        b.block(f"Vasca_Bordo{name}", *ext, 0, 0.22)
    b.block("Muro_Cinta", -13.6, -13.3, -9.5, 8.5, 0, 1.1)
    b.block("Panca", -12.6, -10.4, -7.2, -6.6, 0.35, 0.45)
    for i, x in enumerate((-12.4, -10.6)):
        b.block(f"Panca_Piede{i}", x - 0.08, x + 0.08, -7.15, -6.65, 0, 0.35)

    _tree(b, "Albero1", -11.0, 3.5)
    _tree(b, "Albero2", 12.0, 7.0, 1.15)
    _tree(b, "Albero3", -10.8, -3.2, 0.7)


# ---------------------------------------------------------------------------
# 2. meccanica: rinvio a ingranaggi su supporti
# ---------------------------------------------------------------------------
AXIS_Y = (-90, 0, 0)  # ruota l'asse locale +Z sull'asse +Y del mondo


def _shaft(b, name, x, z, y0, y1, r=0.022):
    c, n = 0.003, y1 - y0
    b.lathe(name, [(0, 0), (r - c, 0), (r, c), (r, n - c), (r - c, n), (0, n)],
            (x, y0, z), AXIS_Y, segs=32)


def _pillow_block(b, name, x, y, z):
    """Supporto ritto: piede imbullonato, corpo, sede cuscinetto, ingrassatore."""
    b.block(f"{name}_Piede", x - 0.078, x + 0.078, y - 0.03, y + 0.03, 0.03, 0.055)
    b.block(f"{name}_Corpo", x - 0.042, x + 0.042, y - 0.026, y + 0.026, 0.055, z)
    b.ring(f"{name}_Sede", 0.022, 0.056, 0.07, (x, y, z), AXIS_Y)
    b.ring(f"{name}_Coperchio", 0.022, 0.04, 0.084, (x, y, z), AXIS_Y)
    b.cyl(f"{name}_Ingrassatore", 0.007, 0.018, (x, y, z + 0.054), segs=12)
    for i, dx in enumerate((-0.06, 0.06)):
        b.cyl(f"{name}_Bullone{i}", 0.012, 0.011, (x + dx, y, 0.055), (0, 0, 15), segs=6)


def build_mechanical(b):
    module, z = 0.0125, 0.22          # modulo dei denti, quota degli assi
    teeth_a, teeth_b = 24, 12
    xa = -0.14
    xb = xa + module * (teeth_a + teeth_b) / 2   # interasse = somma dei raggi primitivi

    b.block("Banco", -0.85, 0.85, -0.62, 0.62, -0.06, 0)
    b.block("Piastra", -0.55, 0.55, -0.36, 0.36, 0, 0.03)
    for i, (x, y) in enumerate(((-0.5, -0.31), (0.5, -0.31), (-0.5, 0.31), (0.5, 0.31))):
        b.cyl(f"Piastra_Rondella{i}", 0.03, 0.004, (x, y, 0.03), segs=24)
        b.cyl(f"Piastra_Bullone{i}", 0.02, 0.016, (x, y, 0.034), (0, 0, 10 * i), segs=6)

    _shaft(b, "AlberoA", xa, z, -0.43, 0.34)
    _shaft(b, "AlberoB", xb, z, -0.34, 0.45)
    for name, x in (("A", xa), ("B", xb)):
        for side, y in (("Ant", -0.25), ("Post", 0.25)):
            _pillow_block(b, f"Supporto{name}_{side}", x, y, z)
            b.ring(f"Collare{name}_{side}", 0.022, 0.034, 0.018, (x, y * 0.72, z), AXIS_Y)

    # ruote dentate ingranate: un vano della B davanti a un dente della A
    b.gear("RuotaA", teeth_a, module, 0.05, 0.022, (xa, 0, z), AXIS_Y)
    b.gear("RuotaB", teeth_b, module, 0.05, 0.022, (xb, 0, z), AXIS_Y,
           phase=math.pi + math.pi / teeth_b)
    b.ring("RuotaA_Mozzo", 0.022, 0.05, 0.085, (xa, 0, z), AXIS_Y)
    b.ring("RuotaB_Mozzo", 0.022, 0.04, 0.085, (xb, 0, z), AXIS_Y)
    for i in range(6):   # fori di alleggerimento: borchie anulari sul disco della ruota grande
        a = math.radians(60 * i + 30)
        b.ring(f"RuotaA_Borchia{i}", 0.014, 0.02, 0.054,
               (xa + 0.092 * math.cos(a), 0, z + 0.092 * math.sin(a)), AXIS_Y, segs=24)

    # puleggia a gola sull'estremità anteriore dell'albero A
    yp = -0.385
    b.lathe("Puleggia_Corona", [(0.108, -0.026), (0.132, -0.026), (0.132, -0.013), (0.119, 0.0),
                                (0.132, 0.013), (0.132, 0.026), (0.108, 0.026)],
            (xa, yp, z), AXIS_Y, segs=64, closed=True)
    b.ring("Puleggia_Mozzo", 0.022, 0.042, 0.064, (xa, yp, z), AXIS_Y)
    for i in range(5):
        b.box(f"Puleggia_Razza{i}", (0.072, 0.014, 0.02), (xa, yp, z), (0, 72 * i + 18, 0),
              offset=(0.075, 0, 0))

    # flangia di accoppiamento sull'estremità posteriore dell'albero B
    yf = 0.405
    b.ring("Flangia_Disco", 0.022, 0.072, 0.02, (xb, yf, z), AXIS_Y)
    b.ring("Flangia_Mozzo", 0.022, 0.04, 0.06, (xb, yf, z), AXIS_Y)
    for i in range(6):
        a = math.radians(60 * i)
        b.cyl(f"Flangia_Bullone{i}", 0.009, 0.034,
              (xb + 0.054 * math.cos(a), yf - 0.017, z + 0.054 * math.sin(a)), AXIS_Y, segs=6)
    b.block("AlberoB_Linguetta", xb - 0.004, xb + 0.004, -0.335, -0.285, z + 0.019, z + 0.027)

    # pezzi sciolti sul banco: ruota di ricambio, dadi, spina
    b.gear("Ricambio_Ruota", 14, module, 0.03, 0.02, (0.69, -0.4, 0.015), phase=0.2)
    b.ring("Ricambio_Mozzo", 0.02, 0.036, 0.05, (0.69, -0.4, 0.025))
    for i, (x, y, rz) in enumerate(((0.66, -0.2, 0), (0.71, -0.14, 20), (0.64, -0.12, 40))):
        b.ring(f"Dado{i}", 0.011, 0.021, 0.016, (x, y, 0.008), (0, 0, rz), segs=6)
    b.cyl("Spina", 0.008, 0.14, (0.62, 0.22, 0.008), (90, 0, 25), segs=16)


# ---------------------------------------------------------------------------
# 3. natura morta: tavolo con vaso, bottiglia, ciotola di frutta, libri
# ---------------------------------------------------------------------------
APPLE = [(0, 0.008), (0.012, 0.002), (0.03, 0.007), (0.041, 0.03), (0.04, 0.052),
         (0.028, 0.07), (0.013, 0.075), (0, 0.066)]
PEAR = [(0, 0.004), (0.02, 0.002), (0.04, 0.02), (0.046, 0.046), (0.038, 0.076),
        (0.024, 0.1), (0.017, 0.118), (0.008, 0.128), (0, 0.13)]


def _fruit(b, name, profile, loc, rot=(0, 0, 0), stem=0.068):
    b.lathe(name, profile, loc, rot, segs=32, steps=4)
    top = Vector(loc) + Euler([math.radians(a) for a in rot]).to_matrix() @ Vector((0, 0, stem))
    b.cyl(f"{name}_Picciolo", 0.0016, 0.022, top, (rot[0] + 12, rot[1], rot[2]), segs=6)


def _book(b, name, size, loc, rz):
    w, d, h = size
    c = 0.004  # spessore copertina
    b.box(f"{name}_CopertinaInf", (w, d, c), loc, (0, 0, rz), offset=(0, 0, c / 2))
    b.box(f"{name}_Pagine", (w - 0.012, d - 0.016, h - 2 * c), loc, (0, 0, rz),
          offset=(-0.004, 0, h / 2))
    b.box(f"{name}_CopertinaSup", (w, d, c), loc, (0, 0, rz), offset=(0, 0, h - c / 2))
    b.box(f"{name}_Dorso", (c, d, h), loc, (0, 0, rz), offset=(-w / 2 + c / 2, 0, h / 2))


def build_still_life(b):
    # tavolo
    b.block("Tavolo_Piano", -0.72, 0.72, -0.46, 0.46, -0.04, 0)
    b.block("Tavolo_Fascia", -0.66, 0.66, -0.4, 0.4, -0.14, -0.04)
    for i, (x, y) in enumerate(((-0.62, -0.36), (0.62, -0.36), (-0.62, 0.36), (0.62, 0.36))):
        b.block(f"Tavolo_Gamba{i}", x - 0.035, x + 0.035, y - 0.035, y + 0.035, -0.76, -0.14)

    b.lathe("Vaso", [(0, 0), (0.056, 0, "c"), (0.06, 0.012), (0.078, 0.07), (0.108, 0.15),
                     (0.118, 0.225), (0.108, 0.3), (0.08, 0.37), (0.05, 0.425), (0.043, 0.465),
                     (0.05, 0.5), (0.064, 0.522, "c"), (0.056, 0.522, "c"), (0.039, 0.465),
                     (0.045, 0.41), (0.072, 0.34), (0, 0.31)],
            (-0.2, 0.12, 0), segs=64, steps=5)
    b.lathe("Bottiglia", [(0, 0), (0.037, 0, "c"), (0.0385, 0.012), (0.0385, 0.1), (0.0385, 0.19),
                          (0.034, 0.225), (0.02, 0.262), (0.0148, 0.29), (0.014, 0.325, "c"),
                          (0.0165, 0.325, "c"), (0.0165, 0.34, "c"), (0.011, 0.34, "c"), (0, 0.337)],
            (0.03, 0.24, 0), segs=48, steps=4)
    bowl = (0.24, -0.04)
    b.lathe("Ciotola", [(0, 0), (0.05, 0, "c"), (0.056, 0.013, "c"), (0.092, 0.032), (0.136, 0.07),
                        (0.156, 0.112, "c"), (0.149, 0.112, "c"), (0.129, 0.071), (0.086, 0.036),
                        (0, 0.026)],
            (*bowl, 0), segs=64, steps=5)
    for i, (dx, dy, dz, rot) in enumerate(((-0.046, -0.022, 0.03, (10, -14, 0)),
                                           (0.047, 0.012, 0.03, (-12, 8, 40)),
                                           (-0.004, 0.052, 0.03, (16, 6, 90)),
                                           (0.0, 0.006, 0.085, (-6, 10, 20)))):
        _fruit(b, f"Mela{i}", APPLE, (bowl[0] + dx, bowl[1] + dy, dz), rot)
    _fruit(b, "Mela_Tavolo", APPLE, (0.1, -0.29, 0), (0, 0, 30))
    _fruit(b, "Pera", PEAR, (-0.02, -0.2, 0), (0, 0, 0), stem=0.128)

    b.lathe("Calice", [(0, 0), (0.04, 0, "c"), (0.04, 0.004, "c"), (0.012, 0.012), (0.007, 0.04),
                       (0.007, 0.085), (0.02, 0.1), (0.04, 0.13), (0.045, 0.17), (0.042, 0.2, "c"),
                       (0.039, 0.2, "c"), (0.041, 0.17), (0.036, 0.135), (0.015, 0.112), (0, 0.108)],
            (0.47, 0.2, 0), segs=48, steps=4)

    _book(b, "Libro1", (0.25, 0.18, 0.036), (-0.45, -0.2, 0), 18)
    _book(b, "Libro2", (0.21, 0.15, 0.028), (-0.455, -0.195, 0.036), -9)

    b.lathe("Candeliere", [(0, 0), (0.05, 0, "c"), (0.05, 0.006, "c"), (0.02, 0.02), (0.012, 0.05),
                           (0.019, 0.08), (0.012, 0.11), (0.03, 0.13, "c"), (0.03, 0.137, "c"),
                           (0.013, 0.137, "c"), (0.013, 0.118, "c"), (0, 0.118)],
            (-0.5, 0.22, 0), segs=48, steps=4)
    b.cyl("Candela", 0.0115, 0.17, (-0.5, 0.22, 0.118), segs=24)
    b.cyl("Candela_Stoppino", 0.0012, 0.012, (-0.5, 0.22, 0.288), segs=6)


# ---------------------------------------------------------------------------
# registro delle demo
# ---------------------------------------------------------------------------
# camera: (posizione, punto guardato, focale mm); sun: direzione in cui viaggia la luce
DEMOS = {
    "ARCHITECTURE": dict(
        label="Architettura — Villa moderna", icon="HOME",
        description="Villa su podio con volume a sbalzo, pilotis, vetrate, vasca e alberi",
        build=build_architecture, preset="ARCH_SKETCH",
        camera=((-25.0, -29.5, 9.0), (0.3, -1.5, 2.6), 35.0), sun=(-0.42, 0.62, -0.66),
        settings=dict(constr_length=0.35),
    ),
    "MECHANICAL": dict(
        label="Meccanica — Rinvio a ingranaggi", icon="SETTINGS",
        description="Coppia di ruote dentate su alberi e supporti, puleggia, flangia imbullonata",
        build=build_mechanical, preset="TECH_PEN",
        camera=((1.36, -1.68, 1.02), (0.1, -0.1, 0.07), 50.0), sun=(-0.5, 0.52, -0.69),
        settings=dict(hidden_enable=True),
    ),
    "STILL_LIFE": dict(
        label="Natura morta — Tavolo da disegno", icon="MESH_UVSPHERE",
        description="Vaso, bottiglia, ciotola di frutta, calice, libri e candeliere: superfici curve e ombre morbide",
        build=build_still_life, preset="PENCIL",
        camera=((0.38, -1.95, 0.86), (-0.02, -0.02, 0.17), 50.0), sun=(0.55, 0.42, -0.72),
        settings=dict(), sun_angle=math.radians(6),
    ),
}

ENUM_ITEMS = [(key, d["label"], d["description"]) for key, d in DEMOS.items()]


def scene_name(key):
    return "Matita Demo - " + DEMOS[key]["label"].split(" — ")[0]


def _discard_scene(scene):
    """Elimina una scena demo precedente con tutti i suoi dati."""
    core.remove(scene)
    objects = list(scene.objects)
    datas = {o.data for o in objects if o.data is not None}
    collections = list(scene.collection.children_recursive)
    bpy.data.batch_remove(objects)
    bpy.data.batch_remove([d for d in datas if d.users == 0])
    bpy.data.batch_remove([c for c in collections if not c.all_objects])
    bpy.data.scenes.remove(scene)


def create(context, key):
    """Costruisce la demo in una scena nuova, la attiva e applica Matita."""
    demo = DEMOS[key]
    name = scene_name(key)
    old = bpy.data.scenes.get(name)
    if old is not None:
        old.name = name + " (precedente)"   # libera il nome; viene eliminata a fine costruzione

    scene = bpy.data.scenes.new(name)
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    col = bpy.data.collections.new(f"Demo [{name}]")
    scene.collection.children.link(col)
    demo["build"](Builder(col))

    loc, target, lens = demo["camera"]
    cam_data = bpy.data.cameras.new(f"Camera [{name}]")
    cam_data.lens = lens
    dist = (Vector(loc) - Vector(target)).length
    cam_data.clip_start = dist * 0.02
    cam_data.clip_end = dist * 20
    cam = bpy.data.objects.new(f"Camera [{name}]", cam_data)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(cam)
    scene.camera = cam

    if context.window is not None:
        context.window.scene = scene
    if old is not None:
        _discard_scene(old)

    # le matrici mondo servono per misurare la scena prima del primo disegno
    scene.view_layers[0].update()
    core.setup(scene)
    presets.apply(scene, demo["preset"])
    p = core.settings(scene)
    core._suspend = True
    try:
        for k, v in demo["settings"].items():
            setattr(p, k, v)
    finally:
        core._suspend = False
    # la luce è un normale sole di Blender: la demo lo orienta e ne fissa la morbidezza
    sun = scene.sketch_render.sun_object
    if sun is not None:
        sun.rotation_euler = Vector(demo["sun"]).to_track_quat("-Z", "Y").to_euler()
        sun.data.angle = demo.get("sun_angle", math.radians(2))
    core.calibrate_exposure(scene)
    core.sync(scene, refresh_metrics=True)
    return scene
