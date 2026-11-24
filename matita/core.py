# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Setup della scena, sincronizzazione parametri -> modificatori/nodi, rimozione.

Prestazioni
-----------
* Le impostazioni regolabili vivono sul World della carta, non sulla Scena:
  modificare una proprietà Python di una Scena la marca come "da ricalcolare"
  e il Line Art (che dipende dalla scena) rigenera tutte le linee. Dal World lo
  stesso slider costa ~0.3 ms invece di un ricalcolo completo.
* Un solo oggetto Grease Pencil: il primo Line Art calcola la scena; profili,
  linee di costruzione e linee nascoste riusano la sua cache (``use_cache``).
* ``sync()`` scrive un valore solo se è davvero cambiato: toccare una proprietà
  di un modificatore fa ricalcolare il Line Art anche se il valore è identico.
* Le metriche camera/scena (pixel -> unità mondo, profondità) sono in cache:
  vengono ricalcolate da setup/Aggiorna e automaticamente prima di ogni render.
* Il materiale contiene solo i nodi delle tecniche attive (vedi nodes.py).

Illuminazione
-------------
Le luci sono della scena: intensità, colore, morbidezza e direzione si regolano
in Blender e l'add-on non le riscrive mai. L'add-on converte la luce in toni
tramite "Esposizione", che si può calibrare sulla scena con un pulsante.
"""

import math
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector

from . import nodes, papers, tips, tones

COLLECTION = "Matita"
# collezioni create dalle versioni di prova: si riconoscono e si rinominano
OLD_COLLECTIONS = ("Sketch Studio", "Sketch Render")
INK_OBJ = "Sketch_Ink"
SUN_OBJ = "Sketch_Sun"
CAM_OBJ = "Sketch_Camera"
INK_MAT = "SketchRender_InkLine"
CONSTR_MAT = "SketchRender_ConstrLine"
HIDDEN_MAT = "SketchRender_HiddenLine"
LAYER_INK = "Lines"
LAYER_CONSTR = "Construction"
LAYER_HIDDEN = "Hidden"
DEPTH_GROUP = "SK_Depth"
OWNED = "sketch_render_owned"  # custom property sugli oggetti creati dall'add-on

# proprietà di stato: restano sulla Scena e non vengono copiate nel World
STATE_KEYS = frozenset((
    "is_setup", "migrated", "preset", "lines_frozen", "ink_object", "construction_object", "sun_object",
    "surface_material", "paper_world", "orig_world", "orig_override",
    "orig_view_transform", "orig_look", "orig_engine"))

# ampiezza del tremolio: tremor=1.0 -> circa TREMOR_PX pixel (alla risoluzione piena)
TREMOR_PX = 20.0
# "tutti i bordi": appena sotto 180° per non disegnare le diagonali delle facce piane
ALL_EDGES_ANGLE = math.radians(179.5)
# luce laterale predefinita rispetto alla camera (da sinistra, dall'alto)
DEFAULT_AZIMUTH = math.radians(-60)
DEFAULT_ELEVATION = math.radians(42)
# livello di una superficie bianca rivolta alla luce che corrisponde a esposizione 1
# (= sole di intensità 3 più luce ambiente 0.3)
WHITE_TARGET = 3.0 / math.pi + 0.3

LUMA = (0.2126, 0.7152, 0.0722)

# parti di sync(): uno slider di superficie non tocca le linee e viceversa
SURFACE = 1
LINES = 2
ALL = SURFACE | LINES

# oltre questa soglia di poligoni la prima attivazione sceglie le linee veloci
FAST_LINES_POLYGONS = 400_000
# variazione minima della scala camera che fa riallineare gli spessori da soli
METRICS_TOLERANCE = 0.03
# ricongelamento automatico: attesa dopo l'ultima modifica prima di ricalcolare
AUTO_FREEZE_DELAY = 0.6
# operatori modali durante i quali non si ricalcola: trascinamenti e navigazione
# della vista (con "Blocca camera alla vista" ruotare o spostare la vista
# muove la camera, quindi le linee vanno ricalcolate, ma solo a gesto finito)
_MODAL_PREFIXES = ("TRANSFORM_OT", "VIEW3D_OT")

_suspend = False
_freezing = False    # vero mentre freeze_lines lavora: i suoi aggiornamenti non contano
_auto_pending = set()  # scene (per nome) da ricongelare appena l'utente si ferma
_view_keys = {}      # scene.session_uid -> impronta di camera e risoluzione
_pending = set()     # scene (per nome) in attesa di riallineamento
_metrics = {}  # scene.session_uid -> (unità mondo per pixel, distanza camera, vicino, lontano, centro)


# ---------------------------------------------------------------------------
# impostazioni
# ---------------------------------------------------------------------------
def settings(scene):
    """Gruppo delle impostazioni regolabili: sul World della carta dopo il setup."""
    s = scene.sketch_render
    world = s.paper_world
    if world is not None and world.sketch_render.migrated:
        return world.sketch_render
    return s


def scenes_of(idb):
    """Scene governate da un gruppo di impostazioni (il suo proprietario è Scena o World)."""
    if isinstance(idb, bpy.types.Scene):
        return (idb,)
    return [sc for sc in bpy.data.scenes if sc.sketch_render.paper_world == idb]


def _migrate(scene):
    """Copia le impostazioni dalla Scena al World (file creati con versioni <= 0.5)."""
    global _suspend
    s = scene.sketch_render
    world = s.paper_world
    if world is None or world.sketch_render.migrated:
        return
    dst = world.sketch_render
    prev, _suspend = _suspend, True
    try:
        for prop in s.bl_rna.properties:
            key = prop.identifier
            if key in STATE_KEYS or key == "rna_type" or prop.is_readonly:
                continue
            setattr(dst, key, getattr(s, key))
        dst.migrated = True
    finally:
        _suspend = prev


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _n(base, scene):
    """Nome per-scena: ogni scena ha i propri oggetti/materiali/world."""
    return f"{base} [{scene.name}]"


def _view_layer(scene):
    vl = bpy.context.view_layer
    if vl is not None and vl.id_data == scene:
        return vl
    return scene.view_layers[0]


def _differs(a, b):
    if isinstance(b, float):
        return abs(a - b) > 1e-6 * max(1.0, abs(b))
    if isinstance(b, (tuple, list)):
        return len(a) != len(b) or any(_differs(x, y) for x, y in zip(a, b))
    return a != b


def _set(owner, **values):
    """Assegna solo ciò che cambia (evita ricalcoli e aggiornamenti inutili)."""
    for attr, value in values.items():
        if _differs(getattr(owner, attr), value):
            setattr(owner, attr, value)


def _eevee_engine():
    ids = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    # 4.2-4.4: BLENDER_EEVEE_NEXT, dalla 5.0 di nuovo BLENDER_EEVEE
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"


def _gp_datablocks():
    return getattr(bpy.data, "grease_pencils_v3", None) or bpy.data.grease_pencils


def _collection(scene):
    name = _n(COLLECTION, scene)
    col = bpy.data.collections.get(name)
    if col is None:
        old = next((c for c in (bpy.data.collections.get(_n(b, scene)) for b in OLD_COLLECTIONS)
                    if c is not None), None)
        if old is not None:
            old.name = name      # file di una versione precedente: si rinomina la collezione
            col = old
        else:
            col = bpy.data.collections.new(name)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def _gp_material(name):
    mat = bpy.data.materials.get(name)
    if mat is not None and mat.grease_pencil is None:
        mat = None
    if mat is None:
        mat = bpy.data.materials.new(name)
        bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.show_fill = False
    return mat


def _line_object(scene, obj, mats):
    """Oggetto Grease Pencil unico con i layer Lines, Construction e Hidden."""
    if obj is not None and (obj.type != "GREASEPENCIL" or scene not in obj.users_scene):
        obj = None
    if obj is None:
        gp = _gp_datablocks().new(_n(INK_OBJ, scene))
        obj = bpy.data.objects.new(_n(INK_OBJ, scene), gp)
        _collection(scene).objects.link(obj)
    gp = obj.data
    # il fotogramma chiave deve precedere qualsiasi frame renderizzato
    first = min(scene.frame_start, scene.frame_current, 0)
    for lname in (LAYER_INK, LAYER_CONSTR, LAYER_HIDDEN):
        layer = gp.layers.get(lname) or gp.layers.new(lname)
        if not len(layer.frames):
            layer.frames.new(first)
    for i, mat in enumerate(mats):
        if i < len(gp.materials):
            if gp.materials[i] != mat:
                gp.materials[i] = mat
        else:
            gp.materials.append(mat)
    obj[OWNED] = True
    obj.hide_select = True
    # Line Art ha già rimosso le linee nascoste: disegnare "in front" evita che
    # estensioni e tremolii vengano coperti dalle superfici (z-fighting).
    obj.show_in_front = True
    return obj


def _scene_bounds(scene):
    """(centro, diagonale) del volume occupato dalle mesh visibili."""
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for o in scene.objects:
        if o.type != "MESH" or not o.visible_get():
            continue
        mw = o.matrix_world
        for c in o.bound_box:
            p = mw @ Vector(c)
            for i in range(3):
                if p[i] < lo[i]:
                    lo[i] = p[i]
                if p[i] > hi[i]:
                    hi[i] = p[i]
    if lo[0] == math.inf:
        return Vector((0, 0, 0)), 5.0
    lo, hi = Vector(lo), Vector(hi)
    return (lo + hi) / 2, max((hi - lo).length, 0.01)


def _camera_metrics(scene):
    """(unità mondo per pixel al centro scena, distanza camera-centro, vicino, lontano, centro).

    Calcolato sulla risoluzione al 100%: un'anteprima al 50% resta identica
    al render finale, solo più piccola. Vicino/lontano delimitano la scena
    lungo la profondità (per l'attenuazione delle linee con la distanza).
    """
    cam = scene.camera
    r = scene.render
    res_x = max(r.resolution_x, 1.0)
    res_y = max(r.resolution_y, 1.0)
    center, size = _scene_bounds(scene)
    if cam is None or cam.type != "CAMERA":
        return size / res_x, size, size * 0.5, size * 1.5, center
    dist = max((cam.matrix_world.translation - center).length, 0.001)
    near, far = max(dist - size / 2, 0.0), dist + size / 2
    cd = cam.data
    fit_horizontal = cd.sensor_fit == "HORIZONTAL" or (cd.sensor_fit == "AUTO" and res_x >= res_y)
    res = res_x if fit_horizontal else res_y
    if cd.type == "ORTHO":
        return cd.ortho_scale / res, dist, near, far, center
    sensor = cd.sensor_width if cd.sensor_fit != "VERTICAL" else cd.sensor_height
    return dist * sensor / cd.lens / res, dist, near, far, center


def metrics(scene, refresh=False):
    key = scene.session_uid
    if refresh or key not in _metrics:
        _metrics[key] = _camera_metrics(scene)
    return _metrics[key]


def _look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------------------
# luci: la scena comanda, l'add-on legge
# ---------------------------------------------------------------------------
def scene_lights(scene):
    return [o for o in scene.objects if o.type == "LIGHT"]


def _camera_heading(scene):
    """Direzione di vista della camera proiettata sul piano orizzontale."""
    cam = scene.camera
    if cam is None:
        return Vector((0.0, 1.0, 0.0))
    rot = cam.matrix_world.to_3x3()
    v = rot @ Vector((0.0, 0.0, -1.0))
    if v.xy.length < 1e-3:          # camera a piombo: usa il suo "alto"
        v = rot @ Vector((0.0, 1.0, 0.0))
    return Vector((v.x, v.y, 0.0)).normalized()


def sun_rotation(scene, azimuth, elevation):
    """Rotazione di una luce data la direzione rispetto alla camera.

    azimuth 0 = luce alle spalle della camera (frontale, piatta: tutte le facce
    visibili sono illuminate e le ombre restano nascoste dietro gli oggetti);
    negativo = da sinistra, positivo = da destra. elevation = altezza sull'orizzonte.
    """
    h = Matrix.Rotation(azimuth, 3, "Z") @ _camera_heading(scene)
    d = Vector((h.x * math.cos(elevation), h.y * math.cos(elevation), -math.sin(elevation)))
    return d.to_track_quat("-Z", "Y").to_euler()


def light_angles(scene, obj):
    """(azimuth, elevation) attuali di una luce rispetto alla camera."""
    d = (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    f = _camera_heading(scene)
    azimuth = math.atan2(f.x * d.y - f.y * d.x, f.x * d.x + f.y * d.y)
    return azimuth, math.asin(max(-1.0, min(1.0, -d.z)))


def light_level(obj, center):
    """Luminosità che la luce produce su una superficie bianca rivolta verso di essa.

    Formule misurate su EEVEE: sole E/π; punto e spot P/(4π²d²); area P·cos/(π²d²).
    """
    if obj.hide_render:
        return 0.0
    d = obj.data
    power = d.energy * sum(c * w for c, w in zip(d.color, LUMA)) * getattr(d, "diffuse_factor", 1.0)
    if d.type == "SUN":
        return power / math.pi
    mw = obj.matrix_world
    v = center - mw.translation
    dist2 = max(v.length_squared, 1e-8)
    if d.type == "POINT":
        return power / (4 * math.pi ** 2 * dist2)
    cos = (mw.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized().dot(v.normalized())
    if d.type == "SPOT":
        return power / (4 * math.pi ** 2 * dist2) if cos >= math.cos(d.spot_size / 2) else 0.0
    return power * max(cos, 0.0) / (math.pi ** 2 * dist2)   # AREA


def white_level(scene, lights=None):
    """Livello stimato di una superficie bianca in piena luce al centro della scena."""
    center = metrics(scene)[4]
    if lights is None:
        lights = scene_lights(scene)
    levels = sorted((light_level(o, center) for o in lights), reverse=True)
    key = levels[0] if levels else 0.0
    # la luce principale conta per intero, le altre arrivano da direzioni diverse
    return key + 0.5 * sum(levels[1:]) + settings(scene).ambient


def suggested_exposure(scene, lights=None):
    level = white_level(scene, lights)
    return min(max(WHITE_TARGET / level, 0.001), 1000.0) if level > 1e-9 else 1.0


def calibrate_exposure(scene):
    """Porta l'esposizione al valore che bilancia le luci attuali della scena."""
    metrics(scene, refresh=True)
    settings(scene).exposure = suggested_exposure(scene)


def key_light(scene):
    """La luce più influente al centro della scena."""
    lights = scene_lights(scene)
    if not lights:
        return None
    center = metrics(scene)[4]
    return max(lights, key=lambda o: light_level(o, center))


def add_sun(scene):
    """Sole laterale rispetto alla camera. Da qui in poi lo si regola in Blender."""
    sun_data = bpy.data.lights.new(_n(SUN_OBJ, scene), "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new(_n(SUN_OBJ, scene), sun_data)
    sun[OWNED] = True
    _collection(scene).objects.link(sun)
    sun.rotation_euler = sun_rotation(scene, DEFAULT_AZIMUTH, DEFAULT_ELEVATION)
    scene.sketch_render.sun_object = sun
    return sun


def _is_own_sun(obj):
    return obj is not None and obj.type == "LIGHT" and (
        obj.get(OWNED) or obj.name.startswith(SUN_OBJ))


def _features(p):
    """Tecniche attive: determinano quali nodi vengono costruiti nel materiale."""
    return {
        "hatch": p.hatch_layers if p.hatch_enable else 0,
        "hstyle": p.hatch_style if p.hatch_enable else "CROSS",
        "follow": p.hatch_enable and p.hatch_follow,
        "tone": p.tone_enable,
        "stipple": p.stipple_enable,
        "shadow": p.shadow_enable,
        "wash": p.wash_enable,
        "tooth": p.ink_tooth > 0.0,
        "grain": p.paper_grain > 0.0,
        "fibers": p.paper_fibers > 0.0,
        "pattern": papers.pattern(p.paper_type) if p.paper_pattern > 0.0 else "NONE",
        "age": p.paper_age > 0.0,
        "tpat": (p.tone_pattern or "DOTS") if p.tone_enable else "DOTS",
        "tobj": p.tone_objects if p.tone_enable else "",
        "tflat": p.tone_enable and p.tone_mode == "FLAT",
        "hl": p.highlight_enable,
        "neg": p.hatch_enable and p.hatch_negative,
        "objcol": p.objcolor_enable,
        "objwash": p.wash_enable and p.wash_use_object,
    }


# ---------------------------------------------------------------------------
# proprietà per oggetto: retino e colore
# ---------------------------------------------------------------------------
def refresh_object_tones(scene):
    """Aggiorna l'elenco dei motivi scelti dagli oggetti: il materiale contiene
    solo i motivi in uso, quindi un motivo nuovo fa ricostruire il grafo."""
    used, any_none = tones.used_in(scene)
    value = "+".join(used) + ("+NONE" if any_none else "")
    p = settings(scene)
    if p.tone_objects != value:
        global _suspend
        prev, _suspend = _suspend, True
        try:
            p.tone_objects = value
        finally:
            _suspend = prev
        sync(scene, parts=SURFACE)


def material_color(obj):
    """Colore del materiale originale di un oggetto (base del Principled o colore viewport)."""
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        if mat.node_tree is not None:
            for nd in mat.node_tree.nodes:
                if nd.type == "BSDF_PRINCIPLED":
                    inp = nd.inputs.get("Base Color")
                    if inp is not None and not inp.is_linked:
                        c = inp.default_value
                        return (c[0], c[1], c[2], 1.0)
        c = mat.diffuse_color
        return (c[0], c[1], c[2], 1.0)
    return None


def fill_object_colors(scene, only_missing=True):
    """Copia nel "Colore Sketch" di ogni oggetto il colore del suo materiale."""
    n = 0
    for obj in scene.objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        if only_missing and obj.sketch_color[3] > 0.0:
            continue
        col = material_color(obj)
        if col is not None:
            obj.sketch_color = col
            n += 1
    return n


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------
def setup(scene):
    s = scene.sketch_render
    vl = _view_layer(scene)

    # memorizza lo stato originale per poterlo ripristinare
    if not s.is_setup:
        s.orig_world = scene.world
        s.orig_view_transform = scene.view_settings.view_transform
        s.orig_look = scene.view_settings.look
        s.orig_override = vl.material_override
        s.orig_engine = scene.render.engine

    center, size = _scene_bounds(scene)
    if any(bpy.data.collections.get(_n(b, scene)) is not None for b in OLD_COLLECTIONS):
        _collection(scene)    # file di una versione precedente: rinomina la collezione

    # camera
    if scene.camera is None:
        cam_data = bpy.data.cameras.new(_n(CAM_OBJ, scene))
        cam = bpy.data.objects.new(_n(CAM_OBJ, scene), cam_data)
        _collection(scene).objects.link(cam)
        cam.location = center + Vector((1.0, -1.3, 0.75)).normalized() * size * 1.6
        _look_at(cam, center)
        scene.camera = cam
        _view_layer(scene).update()   # la matrice della camera serve subito per luce e metriche

    # carta: il World ospita anche le impostazioni regolabili
    world = s.paper_world or bpy.data.worlds.new(_n(nodes.WORLD_NAME, scene))
    s.paper_world = world
    _migrate(scene)
    p = settings(scene)
    used, any_none = tones.used_in(scene)
    p.tone_objects = "+".join(used) + ("+NONE" if any_none else "")
    if p.objcolor_enable or p.wash_use_object:
        fill_object_colors(scene, only_missing=True)
    feats = _features(p)
    nodes.build_world(world, feats)
    scene.world = world

    # materiale di superficie (riusa il datablock già collegato alla scena)
    mat = s.surface_material or bpy.data.materials.new(_n(nodes.SURFACE_MAT, scene))
    nodes.build_surface_material(mat, feats)
    vl.material_override = mat
    s.surface_material = mat

    # luce: solo se la scena non ne ha nessuna viene creato un sole
    metrics(scene, refresh=True)
    lights = scene_lights(scene)
    if not lights:
        add_sun(scene)
    elif s.sun_object is None or scene not in s.sun_object.users_scene:
        s.sun_object = key_light(scene)

    # linee
    if s.lines_frozen and s.ink_object is not None:
        # Aggiorna ricostruisce la pila: i tratti fissi vanno tolti
        s.lines_frozen = False
        for layer in s.ink_object.data.layers:
            layer.hide = False
            for frame in layer.frames:
                if len(frame.drawing.strokes):
                    frame.drawing.remove_strokes()
    mats = tuple(_gp_material(_n(base, scene)) for base in (INK_MAT, CONSTR_MAT, HIDDEN_MAT))
    ink = _line_object(scene, s.ink_object, mats)
    _build_line_stack(ink, *mats)
    s.ink_object = ink
    # versioni <= 0.3 usavano un secondo oggetto per le linee di costruzione
    old = s.construction_object
    if old is not None:
        s.construction_object = None
        _remove_object(old)

    # render
    scene.render.engine = _eevee_engine()
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.film_transparent = False

    s.is_setup = True
    sync(scene, refresh_metrics=True)
    if p.auto_freeze:
        freeze_lines(scene)


def _lineart(obj, name, layer, mat, cache):
    la = obj.modifiers.new(name, "LINEART")
    la.source_type = "SCENE"
    la.target_layer = layer
    la.target_material = mat
    la.use_cache = cache
    la.use_material = False
    return la


def _build_line_stack(obj, ink_mat, con_mat, hid_mat):
    """LineArt -> profili -> costruzione -> nascoste -> stile -> profondità.

    I modificatori di stile sono filtrati per materiale, così linee, linee di
    costruzione e linee nascoste convivono nello stesso oggetto con parametri
    indipendenti. L'attenuazione con la distanza agisce su tutte.
    """
    obj.modifiers.clear()
    la = _lineart(obj, "LineArt", LAYER_INK, ink_mat, cache=False)
    la.use_contour = la.use_crease = la.use_edge_mark = la.use_loose = True
    la.use_intersection = True

    prof = _lineart(obj, "LineArt_Profile", LAYER_INK, ink_mat, cache=True)
    prof.use_contour = True
    prof.use_crease = prof.use_intersection = prof.use_edge_mark = prof.use_loose = False

    con = _lineart(obj, "LineArt_Constr", LAYER_CONSTR, con_mat, cache=True)
    con.use_contour = con.use_crease = con.use_edge_mark = con.use_loose = True
    con.use_intersection = False

    # spigoli coperti da altre superfici (livelli di occlusione >= 1), poi
    # ricampionati a passo costante e spezzati in trattini
    hid = _lineart(obj, "LineArt_Hidden", LAYER_HIDDEN, hid_mat, cache=True)
    hid.use_contour = hid.use_crease = hid.use_edge_mark = True
    hid.use_loose = hid.use_intersection = False
    hid.level_start = 1
    resample = obj.modifiers.new("Hidden_Resample", "GREASE_PENCIL_SIMPLIFY")
    resample.mode = "SAMPLE"
    resample.material_filter = hid_mat
    dash = obj.modifiers.new("Hidden_Dash", "GREASE_PENCIL_DASH")
    dash.material_filter = hid_mat
    if not len(dash.segments):
        dash.segments.new(name="Tratto")

    for name, mtype, mat in (
            ("Overshoot", "GREASE_PENCIL_LENGTH", ink_mat),
            ("Overshoot_C", "GREASE_PENCIL_LENGTH", con_mat),
            ("MultiStroke", "GREASE_PENCIL_MULTIPLY", ink_mat),
            ("Tremor", "GREASE_PENCIL_NOISE", ink_mat),
            ("Tremor_C", "GREASE_PENCIL_NOISE", con_mat),
            ("Smooth", "GREASE_PENCIL_SMOOTH", ink_mat)):
        mod = obj.modifiers.new(name, mtype)
        mod.material_filter = mat
        if mtype == "GREASE_PENCIL_LENGTH":
            mod.use_curvature = False
            mod.mode = "RELATIVE"

    # profondità: peso 0 vicino alla camera, 1 in fondo alla scena; spessore e
    # opacità vengono ridotti in proporzione al peso
    # (i nomi del gruppo di pesi vengono assegnati da sync() quando il gruppo
    # esiste: Blender scarta il nome di un gruppo che non c'è ancora)
    obj.modifiers.new("Depth_Weight", "GREASE_PENCIL_VERTEX_WEIGHT_PROXIMITY")
    thick = obj.modifiers.new("Depth_Thick", "GREASE_PENCIL_THICKNESS")
    thick.use_weight_factor = False   # il gruppo fa da influenza: 0 vicino = spessore intatto
    thick.use_uniform_thickness = False
    fade = obj.modifiers.new("Depth_Fade", "GREASE_PENCIL_OPACITY")
    fade.color_mode = "STROKE"


# ---------------------------------------------------------------------------
# sync: proprietà -> scena
# ---------------------------------------------------------------------------
def _set_node(tree, name, value):
    nd = tree.nodes.get(name)
    if nd is None:
        return
    out = nd.outputs[0]
    if nd.type == "RGB":
        value = (value[0], value[1], value[2], 1.0)
        if _differs(tuple(out.default_value), value):
            out.default_value = value
    elif _differs(out.default_value, float(value)):
        out.default_value = value


def sync(scene, refresh_metrics=False, parts=ALL):
    if _suspend:
        return
    s = scene.sketch_render
    if not s.is_setup:
        return
    p = settings(scene)
    if parts & SURFACE:
        _sync_surface(scene, s, p)
    if parts & LINES:
        _sync_lines(scene, s, p, refresh_metrics)


def _sync_surface(scene, s, p):
    r = scene.render
    res_y = max(r.resolution_y * r.resolution_percentage / 100.0, 1.0)
    aspect = (r.resolution_x * r.pixel_aspect_x) / max(r.resolution_y * r.pixel_aspect_y, 1)
    feats = _features(p)
    signature = nodes.features_signature(feats)
    # la carta è identica nel materiale e nel World
    paper = {
        "SK_paper": p.paper_color, "SK_grain": p.paper_grain,
        "SK_grain_scale": p.paper_grain_scale, "SK_fibers": p.paper_fibers,
        "SK_pattern": p.paper_pattern, "SK_pattern_scale": p.paper_pattern_scale,
        "SK_paper_age": p.paper_age,
    }

    # --- materiale superficie -------------------------------------------
    mat = s.surface_material
    if mat:
        if mat.get(nodes.FEATURES_KEY) != signature:
            nodes.build_surface_material(mat, feats)
        t = mat.node_tree
        n = max(p.hatch_layers, 1)
        # il tratteggio parallelo non incrocia: tutti i livelli hanno lo stesso angolo
        cross = p.hatch_cross
        offsets = (0.0,) * 4 if p.hatch_style == "PARALLEL" else (0.0, cross, cross / 2, -cross / 2)
        hatch_weight = p.hatch_weight
        if p.hatch_use_tip:
            # punta in mm -> larghezza in passi di linea (il passo è altezza/densità)
            tip_px = tips.pen_mm(p.hatch_tip) * tips.px_per_mm(scene, p.sheet_format)
            hatch_weight = min(max(tip_px * p.hatch_density / max(r.resolution_y, 1), 0.02), 1.0)
        values = {
            "SK_aspect": aspect, "SK_seed": float(p.seed),
            "SK_exposure": p.exposure, "SK_gamma": p.gamma / 2.2,  # toni percettivi
            "SK_ink": p.ink_color, "SK_tooth": p.ink_tooth,
            "SK_hatch_shape": p.hatch_shape, "SK_shadow_soft": p.shadow_soft,
            # lumeggiature e colore per oggetto
            "SK_hl_color": p.highlight_color, "SK_hl_strength": p.highlight_strength,
            "SK_hl_threshold": p.highlight_threshold, "SK_hl_soft": p.highlight_soft,
            "SK_obj_strength": p.objcolor_strength, "SK_obj_default": p.objcolor_default,
            # tratteggio
            "SK_hatch_strength": p.hatch_strength, "SK_hatch_density": p.hatch_density,
            "SK_hatch_weight": hatch_weight, "SK_hatch_aa": p.hatch_density / res_y * 1.2,
            "SK_hatch_wobble": p.hatch_wobble, "SK_hatch_wobble_scale": p.hatch_wobble_scale,
            "SK_hatch_breaks": p.hatch_breaks, "SK_hatch_break_scale": p.hatch_break_scale,
            # retino
            "SK_tone_strength": p.tone_strength, "SK_tone_density": p.tone_density,
            "SK_tone_angle": p.tone_angle, "SK_tone_start": p.tone_start,
            "SK_tone_size": p.tone_size, "SK_tone_aa": p.tone_density / res_y * 1.2,
            # puntinato
            "SK_stipple_strength": p.stipple_strength, "SK_stipple_density": p.stipple_density,
            "SK_stipple_size": p.stipple_size, "SK_stipple_start": p.stipple_start,
            "SK_stipple_aa": p.stipple_density / res_y * 1.2,
            # ombre
            "SK_shadow_strength": p.shadow_strength, "SK_shadow_threshold": p.shadow_threshold,
            # acquerello
            "SK_wash_strength": p.wash_strength, "SK_wash_color": p.wash_color,
            "SK_wash_threshold": p.wash_threshold, "SK_wash_irregularity": p.wash_irregularity,
            "SK_wash_scale": p.wash_scale, "SK_wash_edge": p.wash_edge,
        }
        for i in range(4):
            values[f"SK_hatch_a{i}"] = p.hatch_angle + offsets[i]
            values[f"SK_hatch_t{i}"] = p.hatch_start + i * (1.0 - p.hatch_start) / n * 0.85
        values.update(paper)
        for name, value in values.items():
            _set_node(t, name, value)  # i nodi delle tecniche spente non esistono: ignorati

    # --- world ----------------------------------------------------------
    world = s.paper_world
    if world:
        if world.get(nodes.FEATURES_KEY) != nodes.world_signature(feats):
            nodes.build_world(world, feats)
        t = world.node_tree
        _set_node(t, "SK_aspect", aspect)
        _set_node(t, "SK_seed", float(p.seed))
        _set_node(t, "SK_ambient", p.ambient)
        for name, value in paper.items():
            _set_node(t, name, value)


def _sync_lines(scene, s, p, refresh_metrics):
    wpp, cam_dist, near, far, _center = metrics(scene, refresh_metrics)
    depth_off = cam_dist * 0.01
    # spessore dallo strumento: pixel (libero) o millimetri di carta (penne, matite)
    radius = tips.line_px(scene, p) * 0.5 * wpp
    profile_k, constr_k, hidden_k = tips.ratios(p)

    ink = s.ink_object
    if ink:
        c = p.line_color if p.use_line_color else p.ink_color
        color = (c[0], c[1], c[2], 1.0)
        for m in ink.data.materials:
            if m and m.grease_pencil:
                _set(m.grease_pencil, color=color)

        hidden = not (p.line_enable or p.constr_enable or p.hidden_enable)
        _set(ink, hide_render=hidden, hide_viewport=hidden or not p.viewport_lines)
        # "tutti i bordi": ogni spigolo non piatto, anche dentro le superfici smussate
        crease = ALL_EDGES_ANGLE if p.all_edges else p.crease_angle
        # linee veloci: il calcolo delle intersezioni tra oggetti è di gran lunga
        # la parte più costosa del Line Art (circa 7 volte il resto su 2 milioni
        # di triangoli); scartare le facce posteriori toglie un altro 25%
        fast = p.line_perf == "FAST"
        live = not s.lines_frozen
        for lname, on in ((LAYER_INK, p.line_enable), (LAYER_CONSTR, p.constr_enable),
                          (LAYER_HIDDEN, p.hidden_enable)):
            layer = ink.data.layers.get(lname)
            if layer is not None:
                _set(layer, hide=not (live or on))
        m = ink.modifiers
        la = m.get("LineArt")
        if la:
            _set(la, show_viewport=p.line_enable and live, show_render=p.line_enable and live,
                 stroke_depth_offset=depth_off, radius=radius, opacity=p.line_opacity,
                 crease_threshold=crease, use_crease_on_smooth=p.all_edges,
                 split_angle=p.split_angle,
                 use_intersection=p.line_intersections and not fast,
                 use_back_face_culling=fast)
        prof = m.get("LineArt_Profile")
        if prof:
            on = p.line_enable and profile_k > 1.001 and live
            _set(prof, show_viewport=on, show_render=on, use_cache=True,
                 stroke_depth_offset=depth_off * 1.05, radius=radius * profile_k,
                 opacity=p.line_opacity, split_angle=p.split_angle, use_back_face_culling=fast)
        con = m.get("LineArt_Constr")
        if con:
            # senza il Line Art principale non c'è cache da riusare
            _set(con, show_viewport=p.constr_enable and live, show_render=p.constr_enable and live,
                 use_cache=p.line_enable,
                 stroke_depth_offset=depth_off, radius=radius * constr_k,
                 opacity=p.constr_opacity, crease_threshold=crease,
                 use_crease_on_smooth=p.all_edges,
                 split_angle=max(p.split_angle, math.radians(60)), use_back_face_culling=fast)

        hid = m.get("LineArt_Hidden")
        if hid:
            # il passo di ricampionamento divide esattamente tratto e vuoto
            unit_px = max(min(p.hidden_dash, p.hidden_gap) / 3.0, 1.0)
            _set(hid, show_viewport=p.hidden_enable and live, show_render=p.hidden_enable and live,
                 use_cache=p.line_enable, stroke_depth_offset=depth_off,
                 radius=radius * hidden_k, opacity=p.hidden_opacity,
                 crease_threshold=crease, use_crease_on_smooth=p.all_edges,
                 split_angle=p.split_angle,
                 use_back_face_culling=False,
                 use_multiple_levels=p.hidden_levels > 1, level_start=1,
                 level_end=max(p.hidden_levels, 1))
            rs = m.get("Hidden_Resample")
            if rs:
                _set(rs, show_viewport=p.hidden_enable, show_render=p.hidden_enable,
                     length=unit_px * wpp)
            dm = m.get("Hidden_Dash")
            if dm:
                _set(dm, show_viewport=p.hidden_enable, show_render=p.hidden_enable)
                if len(dm.segments):
                    # n punti coprono n-1 passi; g punti saltati lasciano g+1 passi vuoti
                    _set(dm.segments[0], dash=max(round(p.hidden_dash / unit_px), 1) + 1,
                         gap=max(round(p.hidden_gap / unit_px) - 1, 1))

        _sync_overshoot(m.get("Overshoot"), p.line_enable, p.overshoot, p.overshoot_random, p.seed)
        _sync_overshoot(m.get("Overshoot_C"), p.constr_enable, p.constr_length, 0.6, p.seed + 7)
        mul = m.get("MultiStroke")
        if mul:
            on = p.line_enable and p.multi_strokes > 0
            _set(mul, show_viewport=on, show_render=on, duplicates=p.multi_strokes,
                 distance=p.multi_distance * wpp, offset=0.0)
        tremor = p.tremor * wpp * TREMOR_PX
        _sync_noise(m.get("Tremor"), p.line_enable, tremor, p.tremor_scale,
                    p.tremor_thickness, p.seed, p.boil, p.boil_step)
        _sync_noise(m.get("Tremor_C"), p.constr_enable, tremor * 0.4, p.tremor_scale,
                    0.3, p.seed + 3, p.boil, p.boil_step)
        sm = m.get("Smooth")
        if sm:
            on = p.line_enable and p.line_smooth > 0
            _set(sm, show_viewport=on, show_render=on, factor=p.line_smooth, step=2)

        # attenuazione con la distanza (si somma all'assottigliamento prospettico)
        depth_on = (p.depth_thin > 0.0 or p.depth_fade > 0.0) and scene.camera is not None
        # il gruppo di pesi esiste solo quando serve: su un oggetto Line Art un
        # gruppo di vertici inutilizzato fa perdere a Blender un po' di memoria a ogni render
        group = ink.vertex_groups.get(DEPTH_GROUP)
        if depth_on and group is None:
            ink.vertex_groups.new(name=DEPTH_GROUP)
        elif not depth_on and group is not None:
            ink.vertex_groups.remove(group)
        dw = m.get("Depth_Weight")
        if dw:
            _set(dw, show_viewport=depth_on, show_render=depth_on)
            if depth_on:
                _set(dw, target_vertex_group=DEPTH_GROUP, object=scene.camera,
                     distance_start=near, distance_end=max(far, near + 1e-4))
        dt = m.get("Depth_Thick")
        if dt:
            on = depth_on and p.depth_thin > 0.0
            _set(dt, show_viewport=on, show_render=on, thickness_factor=1.0 - p.depth_thin)
            if on:
                _set(dt, vertex_group_name=DEPTH_GROUP)
        df = m.get("Depth_Fade")
        if df:
            on = depth_on and p.depth_fade > 0.0
            _set(df, show_viewport=on, show_render=on, color_factor=1.0 - p.depth_fade)
            if on:
                _set(df, vertex_group_name=DEPTH_GROUP)


def _sync_overshoot(mod, enabled, amount, rnd, seed):
    if mod is None:
        return
    on = enabled and amount > 0.0
    _set(mod, show_viewport=on, show_render=on, start_factor=amount, end_factor=amount,
         use_random=rnd > 0.0, random_start_factor=rnd * amount * 2,
         random_end_factor=rnd * amount * 2, seed=seed)


def _sync_noise(mod, enabled, amount, scale, thick, seed, boil, step):
    if mod is None:
        return
    on = enabled and (amount > 0.0 or thick > 0.0)
    _set(mod, show_viewport=on, show_render=on, factor=amount, noise_scale=scale,
         factor_thickness=thick, factor_strength=thick * 0.5, seed=seed,
         use_random=boil, step=step)


# ---------------------------------------------------------------------------
# aggiornamento dell'interfaccia e riallineamento automatico
# ---------------------------------------------------------------------------
def redraw_views():
    """Ridisegna subito le viste 3D: senza, alcune modifiche compaiono solo al
    primo movimento del mouse sulla vista."""
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "PROPERTIES"}:
                area.tag_redraw()


def scene_polygons(scene):
    """Poligoni delle mesh visibili (prima dei modificatori): stima del peso per il Line Art."""
    return sum(len(o.data.polygons) for o in scene.objects
               if o.type == "MESH" and o.visible_get())


def _view_key(scene):
    cam = scene.camera
    r = scene.render
    key = [r.resolution_x, r.resolution_y]
    if cam is not None and cam.type == "CAMERA":
        key += [round(v, 4) for row in cam.matrix_world for v in row]
        key += [round(cam.data.lens, 3), round(cam.data.ortho_scale, 4), cam.data.type]
    return tuple(key)


def _realign_pending():
    """Timer: riallinea gli spessori quando la camera si è fermata."""
    global _pending
    names, _pending = _pending, set()
    for name in names:
        scene = bpy.data.scenes.get(name)
        if scene is None or not scene.sketch_render.is_setup:
            continue
        key = scene.session_uid
        old = _metrics.get(key)
        new = _camera_metrics(scene)
        # si interviene solo se la scala è cambiata in modo visibile: riscrivere
        # i modificatori fa ricalcolare le linee
        if old is None or abs(new[0] - old[0]) > METRICS_TOLERANCE * max(old[0], 1e-12):
            _metrics[key] = new
            try:
                sync(scene, parts=LINES)
            except Exception as ex:
                print("Matita:", ex)
    return None


def _changes_lines(depsgraph, ink):
    """Vero se l'aggiornamento cambia ciò che il Line Art vede.

    Selezionare un oggetto segnala solo la Scena (e l'oggetto delle linee):
    non conta. Contano gli oggetti spostati o modificati (camera compresa) e
    le collezioni la cui geometria cambia (oggetti nascosti o mostrati).
    Le luci non cambiano le linee.
    """
    for u in depsgraph.updates:
        idb = u.id
        if isinstance(idb, bpy.types.Object):
            if idb.type == "LIGHT" or (ink is not None and idb.original == ink):
                continue
            if u.is_updated_transform or u.is_updated_geometry:
                return True
        elif isinstance(idb, bpy.types.Collection) and u.is_updated_geometry:
            return True
    return False


@persistent
def _on_depsgraph_update(scene, depsgraph=None):
    """Camera o risoluzione cambiate: gli spessori in pixel vanno riallineati.
    Il lavoro è rimandato a un timer, così durante lo spostamento non si fa nulla.

    Con "Ricongela da sole" le linee restano congelate e vengono ricalcolate
    solo quando cambia qualcosa che il Line Art vede, dopo una breve pausa."""
    try:
        s = scene.sketch_render
        if not s.is_setup or _suspend or _freezing:
            return
        if settings(scene).auto_freeze:
            if depsgraph is not None and _changes_lines(depsgraph, s.ink_object):
                schedule_refreeze(scene)
            return
        if s.lines_frozen:
            return
        uid = scene.session_uid
        key = _view_key(scene)
        if _view_keys.get(uid) == key:
            return
        first = uid not in _view_keys
        _view_keys[uid] = key
        if first:
            return
        _pending.add(scene.name)
        if bpy.app.timers.is_registered(_realign_pending):
            bpy.app.timers.unregister(_realign_pending)
        bpy.app.timers.register(_realign_pending, first_interval=0.4)
    except Exception as ex:
        print("Matita:", ex)


# ---------------------------------------------------------------------------
# linee congelate: calcolate una volta e conservate, per scene molto pesanti
# ---------------------------------------------------------------------------
_ATTR_FIELD = {"FLOAT_VECTOR": "vector", "FLOAT_COLOR": "color", "BYTE_COLOR": "color",
               "FLOAT2": "vector", "QUATERNION": "value"}
_ATTR_WIDTH = {"FLOAT_VECTOR": 3, "FLOAT_COLOR": 4, "BYTE_COLOR": 4, "FLOAT2": 2, "QUATERNION": 4}


def _copy_drawing(src, dst):
    """Copia i tratti di un disegno Grease Pencil valutato in uno originale."""
    dst.remove_strokes()
    n = len(src.strokes)
    if not n:
        return 0
    offsets = [0] * (n + 1)
    src.curve_offsets.foreach_get("value", offsets)
    dst.add_strokes([offsets[i + 1] - offsets[i] for i in range(n)])
    for attr in src.attributes:
        if attr.is_internal or attr.data_type == "STRING" or not len(attr.data):
            continue
        field = _ATTR_FIELD.get(attr.data_type, "value")
        target = dst.attributes.get(attr.name)
        if target is None or target.data_type != attr.data_type or target.domain != attr.domain:
            if target is not None:
                dst.attributes.remove(target)
            target = dst.attributes.new(attr.name, attr.data_type, attr.domain)
        buf = [0] * (len(attr.data) * _ATTR_WIDTH.get(attr.data_type, 1))
        attr.data.foreach_get(field, buf)
        if len(target.data) == len(attr.data):
            target.data.foreach_set(field, buf)
    return n


def freeze_lines(scene):
    """Conserva le linee calcolate in questo momento come tratti fissi.

    Il Line Art viene valutato una volta (con la cache condivisa, quindi al
    costo di un normale aggiornamento) e il risultato copiato nei layer; poi i
    Line Art restano spenti. Finché sono congelate le linee non vengono più
    ricalcolate: la vista resta fluida anche con milioni di poligoni. Estensioni,
    ripassi, tremolio e trattini continuano ad agire sui tratti conservati.
    Vanno ricongelate dopo aver mosso la camera o modificato il modello.
    """
    global _freezing
    if scene.sketch_render.ink_object is None:
        return False
    prev, _freezing = _freezing, True
    try:
        return _freeze_lines(scene)
    finally:
        _freezing = prev


def _freeze_lines(scene):
    s = scene.sketch_render
    ink = s.ink_object
    _auto_pending.discard(scene.name)
    if s.lines_frozen:
        unfreeze_lines(scene)
    sync(scene, refresh_metrics=True, parts=LINES)
    # si valutano solo i Line Art: lo stile resta "vivo" sopra i tratti conservati
    style = [m for m in ink.modifiers if m.type != "LINEART" and m.show_viewport]
    hidden = ink.hide_viewport
    total = 0
    try:
        for m in style:
            m.show_viewport = False
        ink.hide_viewport = False
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        evaluated = ink.evaluated_get(depsgraph).data
        for layer in ink.data.layers:
            src_layer = evaluated.layers.get(layer.name)
            frame = layer.current_frame()
            src_frame = src_layer.current_frame() if src_layer is not None else None
            if frame is None or src_frame is None:
                continue
            total += _copy_drawing(src_frame.drawing, frame.drawing)
    finally:
        for m in style:
            m.show_viewport = True
        ink.hide_viewport = hidden
    s.lines_frozen = total > 0
    sync(scene, parts=LINES)      # spegne i Line Art e allinea la visibilità dei layer
    ink.data.update_tag()
    # valuta subito le modifiche appena fatte (visibilità, modificatori):
    # altrimenti arriverebbero al prossimo aggiornamento e sembrerebbero
    # modifiche dell'utente, facendo ripartire il ricongelamento automatico
    bpy.context.evaluated_depsgraph_get().update()
    return s.lines_frozen


# ---------------------------------------------------------------------------
# ricongelamento automatico
# ---------------------------------------------------------------------------
def _transforming():
    """Vero durante un trascinamento o la navigazione in volo: si aspetta la fine."""
    wm = bpy.context.window_manager
    if wm is None:
        return False
    for window in wm.windows:
        for op in getattr(window, "modal_operators", ()):
            if op.bl_idname.startswith(_MODAL_PREFIXES):
                return True
    return False


def _auto_freeze_timer():
    if _transforming():
        return 0.3    # l'utente sta ancora trascinando: si riprova tra poco
    global _auto_pending
    names, _auto_pending = _auto_pending, set()
    for name in names:
        scene = bpy.data.scenes.get(name)
        if scene is None or not scene.sketch_render.is_setup or not settings(scene).auto_freeze:
            continue
        try:
            freeze_lines(scene)
        except Exception as ex:
            print("Matita:", ex)
    redraw_views()
    return None


def schedule_refreeze(scene, delay=AUTO_FREEZE_DELAY):
    """Ricongela le linee quando l'utente si ferma.

    Ogni nuova modifica sposta in avanti l'attesa: durante un trascinamento le
    linee si ricalcolano una volta sola, alla fine. Senza interfaccia (i timer
    non girano) il ricalcolo avviene prima del render.
    """
    _auto_pending.add(scene.name)
    if bpy.app.background:
        return
    if bpy.app.timers.is_registered(_auto_freeze_timer):
        bpy.app.timers.unregister(_auto_freeze_timer)
    bpy.app.timers.register(_auto_freeze_timer, first_interval=delay)


def auto_freeze_pending(scene):
    return scene.name in _auto_pending


_refreeze = set()


def _refreeze_pending():
    global _refreeze
    names, _refreeze = _refreeze, set()
    for name in names:
        scene = bpy.data.scenes.get(name)
        if scene is not None and scene.sketch_render.is_setup and scene.sketch_render.lines_frozen:
            try:
                freeze_lines(scene)
            except Exception as ex:
                print("Matita:", ex)
    redraw_views()
    return None


def refreeze_later(scene):
    """Ricongela le linee appena possibile. Non lo si fa subito perché questa
    funzione viene chiamata mentre Blender sta aggiornando una proprietà, e lì
    non si possono eseguire operatori. In background (senza interfaccia) i
    timer non girano: si ricongela direttamente."""
    if bpy.app.background:
        freeze_lines(scene)
        return
    _refreeze.add(scene.name)
    if not bpy.app.timers.is_registered(_refreeze_pending):
        bpy.app.timers.register(_refreeze_pending, first_interval=0.05)


def unfreeze_lines(scene):
    """Toglie i tratti conservati e riaccende il calcolo in tempo reale."""
    s = scene.sketch_render
    ink = s.ink_object
    s.lines_frozen = False
    if ink is None:
        return
    for layer in ink.data.layers:
        layer.hide = False
        for frame in layer.frames:
            if len(frame.drawing.strokes):
                frame.drawing.remove_strokes()
    ink.data.update_tag()
    sync(scene, parts=LINES)

@persistent
def _on_render_pre(scene, *_):
    """Prima del render riallinea spessori e antialias a camera/risoluzione correnti."""
    try:
        if scene.sketch_render.is_setup:
            if bpy.app.background and scene.name in _auto_pending:
                freeze_lines(scene)   # senza interfaccia il timer non è mai partito
            sync(scene, refresh_metrics=True)
    except Exception as ex:  # un handler non deve mai bloccare il render
        print("Matita:", ex)


@persistent
def _on_load_post(*_):
    """File salvati con versioni precedenti: sposta le impostazioni sul World."""
    _metrics.clear()
    _view_keys.clear()
    _pending.clear()
    _auto_pending.clear()
    for scene in bpy.data.scenes:
        try:
            if scene.sketch_render.is_setup:
                _migrate(scene)
        except Exception as ex:
            print("Matita:", ex)


# ---------------------------------------------------------------------------
# rimozione
# ---------------------------------------------------------------------------
def _remove_object(obj):
    data = obj.data
    mats = list(data.materials) if hasattr(data, "materials") else []
    bpy.data.objects.remove(obj)
    ids = [m for m in mats if m and m.users == 0]
    if data and data.users == 0:
        ids.append(data)
    if ids:
        bpy.data.batch_remove(ids)


def remove(scene):
    global _suspend
    s = scene.sketch_render
    if not s.is_setup:
        return
    # le impostazioni tornano sulla Scena: riattivando l'add-on si ritrovano
    p = settings(scene)
    if p != s:
        prev, _suspend = _suspend, True
        try:
            for prop in s.bl_rna.properties:
                key = prop.identifier
                if key not in STATE_KEYS and key != "rna_type" and not prop.is_readonly:
                    setattr(s, key, getattr(p, key))
        finally:
            _suspend = prev
    _view_layer(scene).material_override = s.orig_override
    scene.world = s.orig_world
    for owner, attr, value in ((scene.render, "engine", s.orig_engine),
                               (scene.view_settings, "view_transform", s.orig_view_transform or "AgX"),
                               (scene.view_settings, "look", s.orig_look or "None")):
        if value:
            try:
                setattr(owner, attr, value)
            except TypeError:
                pass  # motore/trasformazione non più disponibili
    objs = [s.ink_object, s.construction_object]
    if _is_own_sun(s.sun_object):  # solo la luce creata da noi
        objs.append(s.sun_object)
    s.ink_object = s.construction_object = s.sun_object = None
    for obj in objs:
        if obj is not None:
            _remove_object(obj)
    mat, world = s.surface_material, s.paper_world
    s.surface_material = None
    s.paper_world = None
    ids = [idb for idb in (mat, world) if idb and idb.users == 0]
    if ids:
        bpy.data.batch_remove(ids)
    for base in (COLLECTION,) + OLD_COLLECTIONS:
        col = bpy.data.collections.get(_n(base, scene))
        if col and len(col.all_objects) == 0:
            bpy.data.collections.remove(col)
    _metrics.pop(scene.session_uid, None)
    s.is_setup = False


def register():
    if _on_render_pre not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(_on_render_pre)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_render_pre in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(_on_render_pre)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if bpy.app.timers.is_registered(_realign_pending):
        bpy.app.timers.unregister(_realign_pending)
    if bpy.app.timers.is_registered(_refreeze_pending):
        bpy.app.timers.unregister(_refreeze_pending)
    if bpy.app.timers.is_registered(_auto_freeze_timer):
        bpy.app.timers.unregister(_auto_freeze_timer)
    _refreeze.clear()
    _auto_pending.clear()
    _view_keys.clear()
    _pending.clear()
    _metrics.clear()
