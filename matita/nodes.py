# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Costruzione dei node tree: materiale di superficie "schizzo" e world carta.

Tutti i parametri regolabili sono nodi Value/RGB con nome che inizia per "SK_":
la funzione sync() in core.py li aggiorna senza ricostruire il grafo.
"""

import math

SURFACE_MAT = "Matita_Surface"
WORLD_NAME = "Matita_Paper"

# Il materiale contiene solo i nodi delle tecniche attive: una tecnica spenta
# non costa nulla alla GPU. La "firma" salvata sul materiale dice a core.sync()
# quando il grafo va ricostruito (cambio di tecniche o aggiornamento add-on).
FEATURES_KEY = "sk_features"
GRAPH_VERSION = 5
# chiavi che descrivono la carta: le uniche da cui dipende il World
PAPER_KEYS = ("grain", "fibers", "pattern", "age")
# tpat  motivo del retino generale         tobj  motivi scelti dagli oggetti ("A+B", "+NONE")
# tflat retino come campitura uniforme     hl    lumeggiature
# neg   tratteggio in negativo (xilografia)
# objcol colore per oggetto                objwash l'acquerello usa il colore dell'oggetto
ALL_FEATURES = {"hatch": 4, "hstyle": "CROSS", "follow": False, "tone": True, "stipple": True,
                "shadow": True, "wash": True, "tooth": False,
                "grain": True, "fibers": True, "pattern": "NONE", "age": True,
                "tpat": "DOTS", "tobj": "", "tflat": False, "hl": False, "neg": False,
                "objcol": False, "objwash": False}
# nomi delle proprietà dell'oggetto lette dallo shader (vedi props.py)
OBJ_TONE_ATTR = "sketch_tone_id"
OBJ_COLOR_ATTR = "sketch_color"
# passo di quantizzazione dell'angolo quando il tratteggio segue le superfici
FOLLOW_STEP = math.radians(30)
TAU = 2 * math.pi
# stile "Circolare": celle per passo di linea (ogni cerchio è largo ~3 linee)
CIRCLE_CELLS = 0.22
# Disporre i nodi in colonne serve solo a chi apre lo Shader Editor e costa un
# terzo del tempo di costruzione del grafo: attivarlo per ispezionare il materiale.
LAYOUT_NODES = False


def _sig(f, keys):
    return "v{} ".format(GRAPH_VERSION) + " ".join(
        "{}={}".format(k, int(f[k]) if isinstance(f[k], bool) else f[k]) for k in keys)


def features_signature(f):
    return _sig(f, sorted(ALL_FEATURES))


def world_signature(f):
    """Il World dipende solo dalla carta."""
    return _sig(f, PAPER_KEYS)


def _node_tree(idb):
    if idb.node_tree is None:      # < 5.0: i nodi vanno attivati esplicitamente
        idb.use_nodes = True
    return idb.node_tree

class NodeBuilder:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    # -- primitive ---------------------------------------------------------
    def new(self, bl_type, **props):
        nd = self.nodes.new(bl_type)
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def feed(self, socket, value):
        # ogni scrittura fa aggiornare l'albero a Blender: si scrive solo se serve
        if isinstance(value, (int, float)):
            if socket.default_value != value:
                socket.default_value = value
        elif isinstance(value, tuple):
            socket.default_value = value
        else:
            self.links.new(value, socket)

    def value(self, name, default):
        nd = self.nodes.new("ShaderNodeValue")
        nd.name = nd.label = name
        nd.outputs[0].default_value = default
        return nd.outputs[0]

    def rgb(self, name, default):
        nd = self.nodes.new("ShaderNodeRGB")
        nd.name = nd.label = name
        nd.outputs[0].default_value = default
        return nd.outputs[0]

    def math(self, op, a, b=0.0, clamp=False):
        nd = self.nodes.new("ShaderNodeMath")
        if op != "ADD":
            nd.operation = op
        if clamp:
            nd.use_clamp = True
        self.feed(nd.inputs[0], a)
        self.feed(nd.inputs[1], b)
        return nd.outputs[0]

    def add(self, a, b): return self.math("ADD", a, b)
    def sub(self, a, b): return self.math("SUBTRACT", a, b)
    def mul(self, a, b): return self.math("MULTIPLY", a, b)
    def div(self, a, b): return self.math("DIVIDE", a, b)
    def max(self, a, b): return self.math("MAXIMUM", a, b)
    def clamp(self, a): return self.math("ADD", a, 0.0, clamp=True)

    def combine(self, x, y, z=0.0):
        nd = self.new("ShaderNodeCombineXYZ")
        self.feed(nd.inputs[0], x)
        self.feed(nd.inputs[1], y)
        self.feed(nd.inputs[2], z)
        return nd.outputs[0]

    def scale_vec(self, vec, s):
        nd = self.new("ShaderNodeVectorMath", operation="SCALE")
        self.feed(nd.inputs[0], vec)
        self.feed(nd.inputs["Scale"], s)
        return nd.outputs[0]

    def mix_rgb(self, fac, a, b, blend="MIX"):
        nd = self.new("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self.feed(nd.inputs[0], fac)
        self.feed(nd.inputs[6], a)
        self.feed(nd.inputs[7], b)
        return nd.outputs[2]

    def equal(self, a, value):
        """1 se a vale `value` (numeri interi), altrimenti 0."""
        nd = self.new("ShaderNodeMath", operation="COMPARE")
        self.feed(nd.inputs[0], a)
        nd.inputs[1].default_value = float(value)
        nd.inputs[2].default_value = 0.5
        return nd.outputs[0]

    def object_attr(self, name):
        nd = self.new("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name)
        return nd

    def voronoi(self, vec, feature="F1", randomness=1.0):
        nd = self.new("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature=feature)
        nd.inputs["Randomness"].default_value = randomness
        nd.inputs["Scale"].default_value = 1.0
        self.links.new(vec, nd.inputs["Vector"])
        return nd

    def separate_rgb(self, col):
        nd = self.new("ShaderNodeSeparateColor")
        self.feed(nd.inputs[0], col)
        return nd.outputs

    def noise(self, vec, detail=2.0, roughness=0.5, scale=None):
        """Rumore. Attenzione: il nodo moltiplica il vettore per la propria scala
        (5 di default); passare scale=1 quando il vettore è già nella scala voluta."""
        nd = self.new("ShaderNodeTexNoise")
        nd.inputs["Detail"].default_value = detail
        nd.inputs["Roughness"].default_value = roughness
        if scale is not None:
            nd.inputs["Scale"].default_value = scale
        self.links.new(vec, nd.inputs["Vector"])
        return nd

    # anti-aliasing lineare: copertura = clamp((r - d)/aa + 0.5)
    def coverage(self, radius, dist, aa):
        return self.clamp(self.add(self.div(self.sub(radius, dist), aa), 0.5))

    # -- layout automatico (per chi apre lo Shader Editor) -----------------
    def layout(self):
        # un solo passaggio sui collegamenti: chiedere "socket.links" a ogni
        # socket fa scorrere a Blender l'intero albero ogni volta (da solo
        # costava più di metà del tempo di costruzione del grafo)
        preds = {}
        for lk in self.links:
            preds.setdefault(lk.to_node.as_pointer(), []).append(lk.from_node)
        depth = {}

        def d(node):
            key = node.as_pointer()
            if key in depth:
                return depth[key]
            depth[key] = 0          # il grafo è aciclico; protegge comunque da ricorsioni
            best = 0
            for src in preds.get(key, ()):
                best = max(best, d(src) + 1)
            depth[key] = best
            return best

        rows = {}
        for nd in self.nodes:
            c = d(nd)
            r = rows.get(c, 0)
            rows[c] = r + 1
            nd.location = (c * 220, -r * 170)


# ---------------------------------------------------------------------------
def screen_coords(nb):
    """Coordinate schermo in unità di "altezza schermo" (x corretto per aspect).

    Restituisce (px, py) puri e (pxs, pys) traslati dal seed, per variare
    grana e tremolii senza cambiare la struttura del disegno.
    """
    tc = nb.new("ShaderNodeTexCoord")
    sep = nb.new("ShaderNodeSeparateXYZ")
    nb.links.new(tc.outputs["Window"], sep.inputs[0])
    aspect = nb.value("SK_aspect", 16 / 9)
    px = nb.mul(sep.outputs[0], aspect)
    py = sep.outputs[1]
    seed = nb.value("SK_seed", 0.0)
    return px, py, nb.add(px, nb.mul(seed, 17.31)), nb.add(py, nb.mul(seed, 9.17))


# ---------------------------------------------------------------------------
# carta
# ---------------------------------------------------------------------------
def _rotated(nb, px, py, angle):
    """Coordinate ruotate di un angolo costante: (lungo, attraverso)."""
    c, s = math.cos(angle), math.sin(angle)
    return nb.add(nb.mul(px, c), nb.mul(py, s)), nb.sub(nb.mul(py, c), nb.mul(px, s))


def _paper_pattern(nb, kind, px, py, p0):
    """Trama della carta in 0..1 (1 = più scuro). La scala è regolabile."""
    ps = nb.value("SK_pattern_scale", 1.0)
    if kind == "LAID":
        # vergatura: righe fitte orizzontali + filoni verticali radi
        ribs = nb.add(0.5, nb.mul(nb.math("SINE", nb.mul(py, nb.mul(ps, 1500.0))), 0.5))
        x = nb.math("FRACT", nb.mul(px, nb.mul(ps, 7.0)))
        chain = nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(x, 0.5)), 90.0)))
        return nb.add(nb.mul(ribs, 0.6), nb.mul(chain, 0.35))
    if kind == "BUMPS":
        # rilievo a luce radente: differenza tra due campioni vicini dello stesso rumore
        vec = nb.scale_vec(p0, nb.mul(ps, 380.0))
        n1 = nb.noise(vec, detail=2.0)
        shifted = nb.new("ShaderNodeVectorMath", operation="ADD")
        nb.links.new(vec, shifted.inputs[0])
        shifted.inputs[1].default_value = (0.35, 0.35, 0.0)
        n2 = nb.noise(shifted.outputs[0], detail=2.0)
        return nb.clamp(nb.add(nb.mul(nb.sub(n1.outputs["Fac"], n2.outputs["Fac"]), 2.2), 0.5))
    if kind == "HONEYCOMB":
        vor = nb.new("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="DISTANCE_TO_EDGE")
        vor.inputs["Randomness"].default_value = 0.3
        nb.links.new(nb.scale_vec(p0, nb.mul(ps, 150.0)), vor.inputs["Vector"])
        return nb.sub(1.0, nb.clamp(nb.mul(vor.outputs["Distance"], 3.5)))
    if kind == "CANVAS":
        f = nb.mul(ps, TAU * 190.0)
        weave = nb.mul(nb.math("SINE", nb.mul(px, f)), nb.math("SINE", nb.mul(py, f)))
        return nb.add(0.5, nb.mul(weave, 0.5))
    if kind == "STREAKS":
        # pennellate orizzontali del fondo steso a mano
        vec = nb.combine(nb.mul(px, nb.mul(ps, 5.0)), nb.mul(py, nb.mul(ps, 300.0)))
        return nb.noise(vec, detail=3.0, roughness=0.6).outputs["Fac"]
    if kind == "MOTTLE":
        n = nb.noise(nb.scale_vec(p0, nb.mul(ps, 6.0)), detail=6.0, roughness=0.7)
        return nb.clamp(nb.mul(nb.sub(n.outputs["Fac"], 0.4), 2.5))
    return None


def paper_color(nb, px, py, f, tooth=False):
    """Colore della carta. Restituisce (colore, grana fine) – la grana serve
    anche ai mezzi secchi, che si depositano solo sui rilievi della carta.

    Vengono creati solo i nodi delle caratteristiche attive.
    """
    p0 = nb.combine(px, py)
    paper = nb.rgb("SK_paper", (0.96, 0.94, 0.89, 1.0))
    dark = []   # contributi di scurimento, ognuno con la propria intensità

    grain_fac = None
    if f["grain"] or tooth:
        # "Finezza grana" = granuli per altezza immagine
        grain_fac = nb.noise(nb.scale_vec(p0, nb.value("SK_grain_scale", 750.0)),
                             detail=2.0, roughness=0.6, scale=1.0).outputs["Fac"]
    if f["grain"]:
        dark.append(nb.mul(nb.value("SK_grain", 0.06), grain_fac))

    if f["fibers"]:
        # fibre: rumore molto allungato in due direzioni, di cui restano solo i filamenti
        strands = None
        for angle in (0.35, -1.1):
            along, across = _rotated(nb, px, py, angle)
            n = nb.noise(nb.combine(nb.mul(along, 14.0), nb.mul(across, 420.0)), detail=1.0)
            strand = nb.clamp(nb.mul(nb.sub(n.outputs["Fac"], 0.62), 7.0))
            strands = strand if strands is None else nb.max(strands, strand)
        cloud = nb.noise(nb.scale_vec(p0, 14.0), detail=4.0, roughness=0.6).outputs["Fac"]
        fib = nb.add(nb.mul(strands, 0.7), nb.mul(cloud, 0.3))
        dark.append(nb.mul(nb.value("SK_fibers", 0.08), fib))

    if f["pattern"] != "NONE":
        pat = _paper_pattern(nb, f["pattern"], px, py, p0)
        if pat is not None:
            dark.append(nb.mul(nb.value("SK_pattern", 0.1), pat))

    if dark:
        total = dark[0]
        for d in dark[1:]:
            total = nb.add(total, d)
        paper = nb.scale_vec(paper, nb.sub(1.0, total))

    if f["age"]:
        # invecchiamento: macchie ampie e irregolari che virano verso l'ocra/bruno
        age_n = nb.noise(nb.scale_vec(p0, 1.6), detail=7.0, roughness=0.68)
        blot = nb.clamp(nb.mul(nb.sub(age_n.outputs["Fac"], 0.45), 2.2))
        aged = nb.new("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        nb.feed(aged.inputs[0], nb.mul(blot, nb.value("SK_paper_age", 0.0)))
        nb.feed(aged.inputs[6], paper)
        aged.inputs[7].default_value = (0.82, 0.66, 0.42, 1.0)
        paper = aged.outputs[2]
    return paper, grain_fac


# ---------------------------------------------------------------------------
# tratteggio
# ---------------------------------------------------------------------------
def _tone_ramp(nb, T, start):
    """0 sotto la soglia, 1 nel buio pieno."""
    return nb.clamp(nb.div(nb.sub(T, start), nb.max(nb.sub(1.0, start), 0.001)))


def _hatch(nb, f, pxs, pys, p0s, T):
    """Tratteggio a livelli. Ogni linea ha un indice: tremolio, peso e
    interruzioni sono campionati per-linea, così ogni tratto è indipendente.

    Stili (hstyle):
      CROSS     livelli incrociati ad angoli diversi
      PARALLEL  una sola direzione: nelle ombre si aggiungono linee intermedie
      WAVY      linee ondulate            ZIGZAG  linee a zig-zag
      SCRIBBLE  linee che vagano (scarabocchio)
      WEAVE     gruppi di tratti alternati a 90° (intreccio)
      CIRCLES   piccoli cerchi sovrapposti (circulism)
    """
    style = f["hstyle"]
    hd = nb.value("SK_hatch_density", 300.0)
    hw = nb.value("SK_hatch_weight", 0.5)
    haa = nb.value("SK_hatch_aa", 0.3)
    hwob = nb.value("SK_hatch_wobble", 0.15)
    hwsc = nb.value("SK_hatch_wobble_scale", 25.0)
    hbrk = nb.value("SK_hatch_breaks", 0.3)
    hbsc = nb.value("SK_hatch_break_scale", 6.0)
    shape = nb.value("SK_hatch_shape", 0.5) if style in ("WAVY", "ZIGZAG", "SCRIBBLE") else None

    follow = None
    if f["follow"]:
        # direzione della normale sullo schermo, a passi: ogni piano riceve un
        # proprio angolo di tratteggio. Ridotta modulo 180° perché un
        # tratteggio ruotato di mezzo giro è lo stesso tratteggio.
        geo = nb.new("ShaderNodeNewGeometry")
        vt = nb.new("ShaderNodeVectorTransform", vector_type="NORMAL",
                    convert_from="WORLD", convert_to="CAMERA")
        nb.links.new(geo.outputs["Normal"], vt.inputs[0])
        sepn = nb.new("ShaderNodeSeparateXYZ")
        nb.links.new(vt.outputs[0], sepn.inputs[0])
        phi = nb.math("ARCTAN2", sepn.outputs[1], sepn.outputs[0])
        steps = nb.math("ROUND", nb.div(phi, FOLLOW_STEP))
        follow = nb.math("FLOORED_MODULO", nb.mul(steps, FOLLOW_STEP), math.pi)

    if style == "SCRIBBLE":
        # deforma il foglio con un rumore ampio: le linee diventano percorsi che vagano
        warp = nb.noise(nb.scale_vec(p0s, nb.mul(hd, 0.035)), detail=1.0)
        r, g, _b = nb.separate_rgb(warp.outputs["Color"])[:3]
        amp = nb.div(nb.mul(shape, 16.0), hd)
        pxs = nb.add(pxs, nb.mul(nb.sub(r, 0.5), amp))
        pys = nb.add(pys, nb.mul(nb.sub(g, 0.5), amp))

    hatch = None
    for i in range(int(f["hatch"])):
        a = nb.value(f"SK_hatch_a{i}", math.radians(45 + 90 * i))
        if follow is not None:
            a = nb.add(a, follow)
        t = nb.value(f"SK_hatch_t{i}", 0.2 + 0.2 * i)
        k = _tone_ramp(nb, T, t)

        if style == "CIRCLES":
            vor = nb.new("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="F1")
            vor.inputs["Randomness"].default_value = 1.0
            vor.inputs["Scale"].default_value = 1.0
            vec = nb.new("ShaderNodeVectorMath", operation="ADD")
            nb.links.new(nb.scale_vec(p0s, nb.mul(hd, CIRCLE_CELLS)), vec.inputs[0])
            vec.inputs[1].default_value = (13.7 * i, 7.3 * i, 0.0)
            nb.links.new(vec.outputs[0], vor.inputs["Vector"])
            lid_k = nb.add(nb.mul(nb.separate_rgb(vor.outputs["Color"])[0], 997.0), 13.7 * i)
            # distanza dall'anello, in passi di linea (una cella = 1/CIRCLE_CELLS passi)
            dist = nb.mul(nb.math("ABSOLUTE", nb.sub(vor.outputs["Distance"], 0.36)), 1.0 / CIRCLE_CELLS)
            wn = nb.noise(nb.combine(lid_k, 0.0), detail=0.0)
            bn_vec = nb.combine(nb.add(lid_k, 50.0), 0.0)
        else:
            ca, sa = nb.math("COSINE", a), nb.math("SINE", a)
            ux = nb.add(nb.mul(pxs, ca), nb.mul(pys, sa))   # perpendicolare alle linee
            v = nb.sub(nb.mul(pys, ca), nb.mul(pxs, sa))    # lungo le linee
            u0 = nb.mul(ux, hd)
            if style == "PARALLEL" and i > 0:
                # stesse linee, raddoppiate: le nuove cadono a metà tra le precedenti
                u0 = nb.add(nb.mul(u0, float(2 ** (i - 1))), 0.5)
            elif style == "WAVY":
                wave = nb.math("SINE", nb.mul(v, nb.mul(hd, 0.5)))
                u0 = nb.add(u0, nb.mul(wave, nb.mul(shape, 1.5)))
            elif style == "ZIGZAG":
                tri = nb.math("PINGPONG", nb.mul(v, nb.mul(hd, 0.25)), 1.0)
                u0 = nb.add(u0, nb.mul(nb.sub(tri, 0.5), nb.mul(shape, 4.0)))
            elif style == "WEAVE":
                # scacchiera di celle da 5 linee: in una cella sì e una no i tratti girano di 90°
                vd = nb.mul(v, hd)
                cell = nb.add(nb.math("FLOOR", nb.div(u0, 5.0)), nb.math("FLOOR", nb.div(vd, 5.0)))
                turn = nb.math("FLOORED_MODULO", cell, 2.0)
                keep_dir = nb.sub(1.0, turn)
                u0, v = (nb.add(nb.mul(u0, keep_dir), nb.mul(vd, turn)),
                         nb.add(nb.mul(v, keep_dir), nb.mul(ux, turn)))
            lid_k = nb.add(nb.mul(nb.math("FLOOR", u0), 5.31), 13.7 * i)
            # tremolio per-linea
            wn = nb.noise(nb.combine(lid_k, nb.mul(v, hwsc)), detail=1.0)
            u = nb.add(u0, nb.mul(nb.sub(wn.outputs["Fac"], 0.5), nb.mul(hwob, 2.0)))
            dist = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", u), 0.5))
            bn_vec = nb.combine(nb.add(lid_k, 50.0), nb.mul(v, hbsc))

        # spessore: cresce col tono e varia leggermente da linea a linea
        lw = nb.add(0.75, nb.mul(wn.outputs["Fac"], 0.5))
        w = nb.mul(nb.mul(nb.math("SQRT", k), nb.mul(hw, 0.5)), lw)
        ink = nb.mul(nb.coverage(w, dist, haa), nb.math("GREATER_THAN", k, 0.0))
        # interruzioni: tratti di lunghezza finita, con inizio/fine sfalsati
        bn = nb.noise(bn_vec, detail=0.0)
        keep = nb.clamp(nb.div(nb.sub(bn.outputs["Fac"], nb.mul(hbrk, 0.55)), 0.02))
        ink = nb.mul(ink, keep)
        hatch = ink if hatch is None else nb.max(hatch, ink)
    return nb.mul(hatch, nb.value("SK_hatch_strength", 1.0))


# ---------------------------------------------------------------------------
# retini (vedi tones.py)
# ---------------------------------------------------------------------------
def _dist_to_int(nb, x):
    """Distanza dall'intero più vicino (0 sulle righe di giunto, 0.5 a metà cella)."""
    return nb.sub(0.5, nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", x), 0.5)))


def _tone_pattern(nb, kind, qx, qy, r, aa, flat=False):
    """Copertura 0..1 di un motivo. qx, qy sono in celle (1 cella = 1/densità
    dell'altezza immagine); r è lo "spessore" 0..1 del segno; aa l'antialias
    espresso in celle. In campitura (flat) punti e righe usano segni sottili,
    come i retini da tavola; a tono crescono fino a coprire il buio."""
    q = nb.combine(qx, qy)
    if kind == "LINES":
        d = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", qy), 0.5))
        return nb.coverage(nb.mul(r, 0.2 if flat else 0.5), d, aa)
    if kind == "GRID":
        d = nb.math("MINIMUM", _dist_to_int(nb, qx), _dist_to_int(nb, qy))
        return nb.coverage(nb.mul(r, 0.12 if flat else 0.25), d, aa)
    if kind == "BRICK":
        # corsi alti una cella, mattoni lunghi due, giunti verticali sfalsati
        row = nb.math("FLOOR", qy)
        shift = nb.mul(nb.math("FLOORED_MODULO", row, 2.0), 0.5)
        jx = nb.mul(_dist_to_int(nb, nb.add(nb.mul(qx, 0.5), shift)), 2.0)
        d = nb.math("MINIMUM", jx, _dist_to_int(nb, qy))
        return nb.coverage(nb.mul(r, 0.15), d, aa)
    if kind == "SAND":
        vor = nb.voronoi(nb.scale_vec(q, 1.6))
        present = nb.math("LESS_THAN", nb.separate_rgb(vor.outputs["Color"])[0], 0.7)
        return nb.mul(nb.coverage(nb.mul(r, 0.22), nb.mul(vor.outputs["Distance"], 1.6), aa), present)
    if kind == "CONCRETE":
        # punti di varia grandezza più inerti (anellini irregolari)
        dots = nb.voronoi(nb.scale_vec(q, 1.1))
        rnd = nb.separate_rgb(dots.outputs["Color"])
        dp = nb.math("LESS_THAN", rnd[0], 0.8)
        size = nb.mul(r, nb.add(0.12, nb.mul(rnd[1], 0.22)))
        fine = nb.mul(nb.coverage(size, nb.mul(dots.outputs["Distance"], 1.1), aa), dp)
        agg = nb.voronoi(nb.scale_vec(q, 0.35), randomness=0.8)
        ap = nb.math("LESS_THAN", nb.separate_rgb(agg.outputs["Color"])[1], 0.6)
        ring = nb.math("ABSOLUTE", nb.sub(agg.outputs["Distance"], 0.28))
        stones = nb.mul(nb.coverage(nb.mul(r, 0.04), ring, nb.mul(aa, 0.35)), ap)
        return nb.max(fine, stones)
    if kind == "GRAVEL":
        vor = nb.voronoi(nb.scale_vec(q, 0.45), randomness=0.7)
        ring = nb.math("ABSOLUTE", nb.sub(vor.outputs["Distance"], 0.36))
        return nb.coverage(nb.mul(r, 0.05), ring, nb.mul(aa, 0.45))
    if kind == "STONE":
        f1 = nb.voronoi(nb.scale_vec(q, 0.3), "F1", 0.85)
        f2 = nb.voronoi(nb.scale_vec(q, 0.3), "F2", 0.85)
        edge = nb.sub(f2.outputs["Distance"], f1.outputs["Distance"])
        return nb.coverage(nb.mul(r, 0.06), edge, nb.mul(aa, 0.3))
    if kind == "INSULATION":
        wave = nb.mul(nb.math("SINE", nb.mul(qx, math.pi * 0.8)), 0.4)
        d = nb.mul(nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.add(nb.mul(qy, 0.5), wave)), 0.5)), 2.0)
        return nb.coverage(nb.mul(r, 0.15), d, aa)
    if kind == "WOOD":
        # venature: righe quasi parallele, piegate lentamente da un rumore
        n = nb.noise(nb.combine(nb.mul(qx, 0.04), nb.mul(qy, 0.12)), detail=2.0, scale=1.0)
        u = nb.add(nb.mul(qy, 0.6), nb.mul(n.outputs["Fac"], 1.6))
        d = nb.mul(nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", u), 0.5)), 1.0 / 0.6)
        return nb.coverage(nb.mul(r, 0.12), d, aa)
    if kind == "EARTH":
        u = nb.mul(nb.add(qx, qy), 0.7)
        along = nb.mul(nb.sub(qx, qy), 0.7)
        d = nb.mul(nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", u), 0.5)), 1.0 / 0.7)
        dash = nb.math("LESS_THAN", nb.math("FRACT", nb.add(nb.mul(along, 0.5),
                                                          nb.mul(nb.math("FLOOR", u), 0.37))), 0.45)
        lines = nb.mul(nb.coverage(nb.mul(r, 0.12), d, aa), dash)
        vor = nb.voronoi(nb.scale_vec(q, 0.9))
        dp = nb.math("LESS_THAN", nb.separate_rgb(vor.outputs["Color"])[0], 0.25)
        dots = nb.mul(nb.coverage(nb.mul(r, 0.1), nb.mul(vor.outputs["Distance"], 0.9), aa), dp)
        return nb.max(lines, dots)
    # DOTS (predefinito)
    fx = nb.sub(nb.math("FRACT", qx), 0.5)
    fy = nb.sub(nb.math("FRACT", qy), 0.5)
    dd = nb.math("SQRT", nb.add(nb.mul(fx, fx), nb.mul(fy, fy)))
    return nb.coverage(nb.mul(r, 0.35) if flat else r, dd, aa)


def _tone(nb, f, px, py, T):
    from . import tones
    td = nb.value("SK_tone_density", 70.0)
    ta = nb.value("SK_tone_angle", math.radians(45))
    c, s = nb.math("COSINE", ta), nb.math("SINE", ta)
    qx = nb.mul(nb.add(nb.mul(px, c), nb.mul(py, s)), td)
    qy = nb.mul(nb.sub(nb.mul(py, c), nb.mul(px, s)), td)
    size = nb.value("SK_tone_size", 0.72)
    aa = nb.value("SK_tone_aa", 0.07)
    k = _tone_ramp(nb, T, nb.value("SK_tone_start", 0.15))
    if f["tflat"]:
        r, present = size, None          # campitura uniforme del materiale
    else:
        r, present = nb.mul(nb.math("SQRT", k), size), nb.math("GREATER_THAN", k, 0.0)

    main = f["tpat"]
    per_object = [x for x in f["tobj"].split("+") if x and x != "NONE"]
    flat = bool(f["tflat"])
    if not f["tobj"]:
        tone = _tone_pattern(nb, main, qx, qy, r, aa, flat)
    else:
        # ogni oggetto sceglie il suo motivo: 0 = come la scena, 99 = nessuno
        tid = nb.object_attr(OBJ_TONE_ATTR).outputs["Fac"]
        tone = None
        for kind in [main] + [x for x in per_object if x != main]:
            mask = nb.equal(tid, tones.IDS.get(kind, 1))
            if kind == main:
                mask = nb.max(mask, nb.equal(tid, tones.OBJ_SCENE))
            cov = nb.mul(_tone_pattern(nb, kind, qx, qy, r, aa, flat), mask)
            tone = cov if tone is None else nb.max(tone, cov)
    if present is not None:
        tone = nb.mul(tone, present)
    return nb.mul(tone, nb.value("SK_tone_strength", 1.0))


def _object_color(nb):
    """Colore dell'oggetto (Object.sketch_color); se non impostato, il colore predefinito."""
    attr = nb.object_attr(OBJ_COLOR_ATTR)
    return nb.mix_rgb(attr.outputs["Alpha"], nb.rgb("SK_obj_default", (0.8, 0.8, 0.8, 1.0)),
                      attr.outputs["Color"])


# ---------------------------------------------------------------------------
# materiale di superficie
# ---------------------------------------------------------------------------
def build_surface_material(mat, features=None):
    f = dict(ALL_FEATURES, **(features or {}))
    tree = _node_tree(mat)
    tree.nodes.clear()
    nb = NodeBuilder(tree)

    px, py, pxs, pys = screen_coords(nb)
    p0s = nb.combine(pxs, pys)

    # --- luminosità dalla luce reale (ombre portate incluse) --------------
    diff = nb.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = nb.new("ShaderNodeShaderToRGB")
    nb.links.new(diff.outputs[0], s2r.inputs[0])
    bw = nb.new("ShaderNodeRGBToBW")
    nb.links.new(s2r.outputs["Color"], bw.inputs[0])
    lit = nb.math("MULTIPLY", bw.outputs[0], nb.value("SK_exposure", 1.0), clamp=True)
    L = nb.math("POWER", lit, nb.value("SK_gamma", 1.0))
    T = nb.sub(1.0, L)  # "tono": 0 = luce piena, 1 = buio

    inks = []  # contributi di inchiostro delle tecniche attive

    if f["hatch"]:
        if f["neg"]:
            # xilografia: il nero pieno è la regola, le luci sono linee scavate
            # nel legno, tanto più larghe quanto più la zona è chiara
            inks.append(nb.clamp(nb.sub(1.0, _hatch(nb, f, pxs, pys, p0s, nb.sub(1.0, T)))))
        else:
            inks.append(_hatch(nb, f, pxs, pys, p0s, T))

    # --- RETINO (motivi di tones.py) -------------------------------------
    if f["tone"]:
        inks.append(_tone(nb, f, px, py, T))

    # --- PUNTINATO (stippling casuale) ------------------------------------
    if f["stipple"]:
        sd = nb.value("SK_stipple_density", 160.0)
        vor = nb.new("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="F1")
        vor.inputs["Randomness"].default_value = 1.0
        nb.links.new(nb.scale_vec(p0s, sd), vor.inputs["Vector"])
        rnd = nb.separate_rgb(vor.outputs["Color"])[0]
        k = _tone_ramp(nb, T, nb.value("SK_stipple_start", 0.05))
        present = nb.math("LESS_THAN", rnd, nb.math("POWER", k, 0.75))
        sr = nb.mul(nb.value("SK_stipple_size", 0.28), nb.add(0.6, nb.mul(k, 0.4)))
        stip = nb.mul(nb.coverage(sr, vor.outputs["Distance"], nb.value("SK_stipple_aa", 0.15)), present)
        inks.append(nb.mul(stip, nb.value("SK_stipple_strength", 1.0)))

    # --- OMBRE: campitura netta oppure sfumato ----------------------------
    if f["shadow"]:
        # sfumatura 0 = bordo netto; 1 = passaggio graduale dalla luce all'ombra
        width = nb.add(0.03, nb.mul(nb.value("SK_shadow_soft", 0.0), 0.7))
        sh = nb.clamp(nb.div(nb.sub(nb.value("SK_shadow_threshold", 0.6), L), width))
        inks.append(nb.mul(sh, nb.value("SK_shadow_strength", 0.3)))

    # --- composizione -----------------------------------------------------
    use_tooth = bool(f["tooth"]) and (bool(inks) or bool(f["hl"]))
    base, grain_fac = paper_color(nb, pxs, pys, f, tooth=use_tooth)
    peaks = None
    if use_tooth:
        # rilievi della carta: i mezzi secchi si depositano solo lì
        peaks = nb.clamp(nb.mul(nb.sub(grain_fac, 0.45), 5.0))

    # --- COLORE PER OGGETTO: tinta piatta presa dal materiale originale -----
    obj_col = None
    if f["objcol"] or f["objwash"]:
        obj_col = _object_color(nb)
    if f["objcol"]:
        tinted = nb.mix_rgb(1.0, base, obj_col, blend="MULTIPLY")
        base = nb.mix_rgb(nb.value("SK_obj_strength", 0.85), base, tinted)

    # --- ACQUERELLO / campitura colorata con bordi irregolari --------------
    if f["wash"]:
        wash_n = nb.noise(nb.scale_vec(p0s, nb.value("SK_wash_scale", 3.0)), detail=5.0, roughness=0.65)
        wth = nb.value("SK_wash_threshold", 0.3)
        wirr = nb.value("SK_wash_irregularity", 0.35)
        edge = nb.add(wth, nb.mul(nb.sub(wash_n.outputs["Fac"], 0.5), wirr))
        inside = nb.sub(T, edge)                     # > 0 dentro la campitura
        wash = nb.clamp(nb.div(inside, 0.05))
        # variazione interna del pigmento
        wash = nb.mul(wash, nb.add(0.75, nb.mul(wash_n.outputs["Fac"], 0.5)))
        # il pigmento si accumula lungo il bordo e sfuma verso l'interno
        rim = nb.clamp(nb.sub(1.0, nb.div(inside, 0.12)))
        wash = nb.mul(wash, nb.add(1.0, nb.mul(rim, nb.value("SK_wash_edge", 0.35))))
        wash = nb.clamp(nb.mul(wash, nb.value("SK_wash_strength", 0.6)))
        if f["objwash"]:
            # velatura del colore dell'oggetto, più scura della sua tinta piatta
            wash_col = nb.scale_vec(obj_col, 0.62)
        else:
            wash_col = nb.rgb("SK_wash_color", (0.45, 0.55, 0.7, 1.0))
        base = nb.mix_rgb(wash, base, wash_col)

    col = base
    tooth = nb.value("SK_tooth", 0.5) if use_tooth else None
    if inks:
        ink = inks[0]
        for other in inks[1:]:
            ink = nb.max(ink, other)
        ink = nb.clamp(ink)
        if use_tooth:
            # mezzi secchi (matita, gessetto, carboncino): il pigmento resta sui
            # rilievi della carta e lascia scoperti gli avvallamenti
            ink = nb.mul(ink, nb.add(nb.sub(1.0, tooth), nb.mul(tooth, peaks)))
        col = nb.mix_rgb(ink, base, nb.rgb("SK_ink", (0.08, 0.08, 0.1, 1.0)))

    # --- LUMEGGIATURE: gessetto chiaro sulle parti in luce ----------------
    if f["hl"]:
        width = nb.add(0.03, nb.mul(nb.value("SK_hl_soft", 0.3), 0.5))
        hl = nb.clamp(nb.div(nb.sub(L, nb.value("SK_hl_threshold", 0.75)), width))
        if use_tooth:
            hl = nb.mul(hl, nb.add(nb.sub(1.0, tooth), nb.mul(tooth, peaks)))
        hl = nb.mul(hl, nb.value("SK_hl_strength", 0.8))
        col = nb.mix_rgb(hl, col, nb.rgb("SK_hl_color", (1.0, 1.0, 1.0, 1.0)))

    emit = nb.new("ShaderNodeEmission")
    nb.links.new(col, emit.inputs["Color"])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.links.new(emit.outputs[0], out.inputs["Surface"])
    if LAYOUT_NODES:
        nb.layout()
    mat[FEATURES_KEY] = features_signature(f)
    return mat


def build_world(world, features=None):
    f = dict(ALL_FEATURES, **(features or {}))
    tree = _node_tree(world)
    tree.nodes.clear()
    nb = NodeBuilder(tree)

    _, _, pxs, pys = screen_coords(nb)
    paper, _grain = paper_color(nb, pxs, pys, f)

    bg_paper = nb.new("ShaderNodeBackground")
    nb.links.new(paper, bg_paper.inputs["Color"])
    bg_amb = nb.new("ShaderNodeBackground")
    bg_amb.inputs["Color"].default_value = (1, 1, 1, 1)
    nb.links.new(nb.value("SK_ambient", 0.25), bg_amb.inputs["Strength"])

    lp = nb.new("ShaderNodeLightPath")
    mix = nb.new("ShaderNodeMixShader")
    nb.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nb.links.new(bg_amb.outputs[0], mix.inputs[1])
    nb.links.new(bg_paper.outputs[0], mix.inputs[2])
    out = nb.new("ShaderNodeOutputWorld")
    nb.links.new(mix.outputs[0], out.inputs["Surface"])
    if LAYOUT_NODES:
        nb.layout()
    world[FEATURES_KEY] = world_signature(f)
    return world