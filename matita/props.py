# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import math
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty, StringProperty)

from . import core, papers, presets, tips, tones


def _upd(self, context):
    # id_data è il World (o la Scena, prima del setup) che possiede le
    # impostazioni: corretto anche da script o da un'altra finestra.
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        core.sync(scene)
    core.redraw_views()


def _upd_surface(self, context):
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        core.sync(scene, parts=core.SURFACE)
    core.redraw_views()


def _upd_lines(self, context):
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        core.sync(scene, parts=core.LINES)
    core.redraw_views()


def _upd_lines_baked(self, context):
    """Parametri del Line Art stesso: nei tratti congelati sono fissati al
    momento del calcolo, quindi con "Ricongela da sole" vanno ricalcolati."""
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        core.sync(scene, parts=core.LINES)
        if self.auto_freeze and scene.sketch_render.lines_frozen:
            core.schedule_refreeze(scene)
    core.redraw_views()


def _upd_tool(self, context):
    """Strumento, punte e formato del foglio: cambiano lo spessore delle linee
    (fissato nei tratti congelati) e quello del tratteggio a punta."""
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        core.sync(scene)
        if self.auto_freeze and scene.sketch_render.lines_frozen:
            core.schedule_refreeze(scene)
    core.redraw_views()


def _pencil_upd(self, context):
    """Scegliere la gradazione imposta colore, opacità e grana del segno."""
    if core._suspend:
        return
    core._suspend = True
    try:
        tips.apply_grade(self, self.pencil_grade)
    finally:
        core._suspend = False
    _upd_tool(self, context)


def _objcolor_upd(self, context):
    if core._suspend:
        return
    if self.objcolor_enable or self.wash_use_object:
        for scene in core.scenes_of(self.id_data):
            core.fill_object_colors(scene, only_missing=True)
    _upd_surface(self, context)


def _auto_freeze_upd(self, context):
    if core._suspend:
        return
    for scene in core.scenes_of(self.id_data):
        if not scene.sketch_render.is_setup:
            continue
        if self.auto_freeze:
            # dentro l'aggiornamento di una proprietà non si ricalcola: lo fa il timer
            if bpy.app.background:
                core.freeze_lines(scene)
            else:
                core.schedule_refreeze(scene, 0.05)
        elif scene.sketch_render.lines_frozen:
            core.unfreeze_lines(scene)
    core.redraw_views()


# proprietà che riguardano solo le linee (per prefisso) e quelle condivise
LINE_PREFIXES = ("line_", "profile_", "crease_", "split_", "overshoot", "multi_", "tremor",
                 "boil", "constr_", "hidden_", "depth_", "all_edges", "use_line_color",
                 "viewport_lines")
SHARED_PROPS = ("ink_color", "seed")
# proprietà delle linee che agiscono sui tratti già calcolati (modificatori di
# stile): restano vive anche sulle linee congelate e non chiedono un ricalcolo
LIVE_LINE_PROPS = frozenset((
    "line_color", "use_line_color", "viewport_lines",
    "overshoot", "overshoot_random", "multi_strokes", "multi_distance",
    "tremor", "tremor_scale", "tremor_thickness", "line_smooth", "boil", "boil_step",
    "depth_thin", "depth_fade", "constr_length", "hidden_dash", "hidden_gap"))


def _assign_updates(cls):
    """Ogni proprietà aggiorna solo la parte che la riguarda: linee o superfici."""
    for name, prop in cls.__annotations__.items():
        kw = getattr(prop, "keywords", None)
        if not kw or kw.get("update") is not _upd or name in SHARED_PROPS:
            continue
        if name.startswith(LINE_PREFIXES):
            kw["update"] = _upd_lines if name in LIVE_LINE_PROPS else _upd_lines_baked
        else:
            kw["update"] = _upd_surface


def _preset_upd(self, context):
    if core._suspend or not isinstance(self.id_data, bpy.types.Scene):
        return
    presets.apply(self.id_data, self.preset)


def _paper_upd(self, context):
    """Scegliere un tipo di carta ne carica le caratteristiche, poi regolabili a mano."""
    if core._suspend:
        return
    core._suspend = True
    try:
        papers.apply_type(self, self.paper_type)
    finally:
        core._suspend = False
    _upd_surface(self, context)


def _is_light(self, obj):
    return obj.type == "LIGHT"


HATCH_STYLES = [
    ("CROSS", "Incrociato", "Livelli di linee ad angoli diversi che si sovrappongono nelle ombre"),
    ("PARALLEL", "Parallelo", "Una sola direzione: nelle ombre le linee si infittiscono senza incrociarsi"),
    ("WAVY", "Ondulato", "Linee ondulate, morbide"),
    ("ZIGZAG", "Zig-zag", "Linee spezzate a zig-zag, tratto rapido"),
    ("SCRIBBLE", "Scarabocchio", "Linee che vagano liberamente, ombreggiatura a scarabocchio"),
    ("WEAVE", "Intreccio", "Gruppi di tratti brevi alternati a 90°, a canestro"),
    ("CIRCLES", "Circolare", "Piccoli cerchi sovrapposti (circulism), per toni morbidi"),
]


def F(name, default, lo, hi, desc="", soft=None, subtype="NONE", step=1):
    smin, smax = soft if soft else (lo, hi)
    return FloatProperty(name=name, description=desc, default=default, min=lo, max=hi,
                         soft_min=smin, soft_max=smax, subtype=subtype, update=_upd, step=step)


def ANG(name, default_deg, desc=""):
    return FloatProperty(name=name, description=desc, default=math.radians(default_deg),
                         subtype="ANGLE", update=_upd)


def COL(name, default, desc=""):
    return FloatVectorProperty(name=name, description=desc, default=default, size=3,
                               min=0.0, max=1.0, subtype="COLOR", update=_upd)


def B(name, default, desc=""):
    return BoolProperty(name=name, description=desc, default=default, update=_upd)


class SketchRenderSettings(bpy.types.PropertyGroup):
    # stato interno (sulla Scena; vedi core.STATE_KEYS)
    is_setup: BoolProperty(default=False)
    lines_frozen: BoolProperty(default=False)   # linee calcolate una volta e conservate
    migrated: BoolProperty(default=False)   # sul World: impostazioni già copiate dalla Scena
    ink_object: PointerProperty(type=bpy.types.Object)
    construction_object: PointerProperty(type=bpy.types.Object)
    sun_object: PointerProperty(
        type=bpy.types.Object, poll=_is_light, name="Luce principale",
        description="Luce usata da \"Orienta rispetto alla camera\". Intensità, colore e "
                    "morbidezza si regolano in Blender")
    surface_material: PointerProperty(type=bpy.types.Material)
    paper_world: PointerProperty(type=bpy.types.World)
    orig_world: PointerProperty(type=bpy.types.World)
    orig_override: PointerProperty(type=bpy.types.Material)
    orig_view_transform: StringProperty()
    orig_look: StringProperty()
    orig_engine: StringProperty()

    preset: EnumProperty(
        name="Stile",
        items=presets.enum_items,
        update=_preset_upd,
    )

    # --- generale ---------------------------------------------------------
    paper_color: COL("Carta", (0.96, 0.94, 0.89))
    ink_color: COL("Inchiostro", (0.08, 0.08, 0.10))
    paper_type: EnumProperty(
        name="Tipo di carta", items=papers.enum_items, update=_paper_upd,
        description="Carta su cui è eseguito il disegno. Sceglierla imposta colore, grana, "
                    "fibre e trama, che restano regolabili")
    paper_grain: F("Grana", 0.06, 0.0, 1.0, "Intensità della grana fine della carta")
    paper_grain_scale: F("Finezza grana", 750.0, 20.0, 8000.0,
                         "Granuli per altezza immagine: valori alti = grana più fine",
                         soft=(100.0, 1500.0))
    paper_fibers: F("Fibre", 0.08, 0.0, 1.0, "Filamenti e nuvolature dell'impasto della carta")
    paper_pattern: F("Trama", 0.0, 0.0, 1.0,
                     "Intensità della trama tipica della carta scelta: vergatura, rilievo, "
                     "alveoli, tela, pennellate del fondo")
    paper_pattern_scale: F("Scala trama", 1.0, 0.05, 20.0,
                           "Valori alti = trama più fitta", soft=(0.25, 4.0))
    ink_tooth: F("Presa della grana", 0.0, 0.0, 1.0,
                 "Mezzi secchi (matita, gessetto, carboncino): il segno resta sui rilievi della "
                 "carta e lascia scoperti gli avvallamenti. 0 = inchiostro pieno")
    paper_age: F("Invecchiamento carta", 0.0, 0.0, 1.0, "Macchie e ingiallimento irregolare della carta antica")
    seed: IntProperty(name="Seed", default=0, min=0, update=_upd,
                      description="Varia casualmente tremolii, estensioni e grana")
    viewport_lines: B("Linee nel viewport", True,
                      "Disattiva per lavorare veloce su scene pesanti: le linee non vengono "
                      "ricalcolate a ogni modifica ma compaiono comunque nel render")

    # --- luce ---------------------------------------------------------------
    exposure: F("Esposizione", 1.0, 0.0, 1000.0,
                "Converte la luce della scena in toni: più alta = disegno più chiaro. "
                "\"Calibra\" la imposta in base alle luci presenti", soft=(0.1, 3.0))
    gamma: F("Contrasto", 1.0, 0.1, 5.0, "Gamma dei toni: >1 più scuro, <1 più chiaro", soft=(0.3, 3.0))
    ambient: F("Luce ambiente", 0.3, 0.0, 2.0, "Luce diffusa del cielo (schiarisce le ombre)")

    # --- strumento -----------------------------------------------------------
    tool_type: EnumProperty(
        name="Strumento", default="FREE", update=_upd_tool,
        items=[("FREE", "Libero", "Spessore in pixel, regolato a mano", "SETTINGS", 0),
               ("TECH_PEN", "Penna tecnica", "Penna tecnica a china ricaricabile: tratto pieno, "
                                             "spessori ISO in millimetri", "LINE_DATA", 1),
               ("FINELINER", "Fineliner", "Pennarello a punta fine: spessori in millimetri",
                "GREASEPENCIL", 2),
               ("PENCIL", "Matita", "Matita in grafite: la gradazione decide spessore, "
                                    "scurezza e grana del segno", "OUTLINER_DATA_GP_LAYER", 3)],
        description="Strumento con cui sono tracciate le linee")
    tool_tip: EnumProperty(
        name="Punta", items=tips.pen_items, default=35, update=_upd_tool,
        description="Spessore della punta in millimetri di carta (linee degli spigoli)")
    pencil_grade: EnumProperty(
        name="Gradazione", items=tips.pencil_items, default=10, update=_pencil_upd,
        description="Gradazione della matita: H dure e chiare, B morbide e scure. Sceglierla "
                    "imposta colore, opacità e grana, che restano regolabili")
    sheet_format: EnumProperty(
        name="Formato foglio", default="A3", update=_upd_tool,
        items=[(k, label, ("L'immagine stampata a 300 dpi" if k == "AUTO" else
                           "Lato lungo del render = lato lungo di un foglio %s (%d mm)" % (k, mm)))
               for k, label, mm in tips.SHEETS],
        description="Su che foglio immaginare stampata l'immagine: traduce i millimetri delle "
                    "punte in pixel. Non dipende dalla scala del modello né dall'inquadratura")
    pen_profile: EnumProperty(name="Profili", items=tips.pen_items, default=50, update=_upd_tool,
                              description="Punta delle silhouette (contorni esterni)")
    pen_hidden: EnumProperty(name="Nascoste", items=tips.pen_items, default=25, update=_upd_tool,
                             description="Punta delle linee nascoste a trattini")
    pen_constr: EnumProperty(name="Costruzione", items=tips.pen_items, default=18, update=_upd_tool,
                             description="Punta delle linee di costruzione")

    # --- linee --------------------------------------------------------------
    line_enable: B("Linee", True)
    use_line_color: B("Colore linee separato", False)
    line_color: COL("Colore linee", (0.08, 0.08, 0.10))
    line_thickness: F("Spessore (px)", 1.6, 0.0, 50.0, "Larghezza del tratto in pixel, misurata al centro della scena", soft=(0.3, 8.0))
    line_opacity: F("Opacità", 1.0, 0.0, 1.0)
    profile_factor: F("Peso profili", 1.8, 1.0, 6.0, "Moltiplicatore di spessore per le silhouette (profili)")
    crease_angle: ANG("Angolo spigoli", 140.0, "Spigoli più acuti di questo angolo vengono disegnati")
    split_angle: ANG("Spezza agli angoli", 165.0,
                     "Spezza i tratti agli angoli più acuti di questo valore, così ogni spigolo si estende")
    line_intersections: B("Intersezioni", True, "Disegna le linee di intersezione tra oggetti")
    auto_freeze: BoolProperty(
        name="Ricongela da sole", default=False, update=_auto_freeze_upd,
        description="Le linee restano congelate mentre lavori (selezionare e girare la vista "
                    "non le ricalcola) e si aggiornano da sole quando sposti oggetti o camera, "
                    "appena ti fermi. Consigliato per le scene pesanti")
    line_perf: EnumProperty(
        name="Calcolo linee", update=_upd_lines_baked, default="FULL",
        items=[("FULL", "Completo", "Tutte le linee, comprese le intersezioni tra oggetti"),
               ("FAST", "Veloce", "Per scene pesanti: senza intersezioni tra oggetti e senza facce "
                                  "posteriori. Circa 10 volte più rapido su milioni di poligoni")],
        description="Quanto lavoro fa il Line Art a ogni aggiornamento")
    all_edges: B("Tutti i bordi", False,
                 "Disegna ogni spigolo della geometria, anche quelli quasi piatti e quelli "
                 "interni alle superfici smussate (ignora \"Angolo spigoli\")")
    depth_thin: F("Assottiglia con la distanza", 0.0, 0.0, 1.0,
                  "Riduce lo spessore delle linee lontane dalla camera, oltre al normale "
                  "effetto prospettico: 0 = nessuna riduzione, 1 = sul fondo spariscono")
    depth_fade: F("Schiarisci con la distanza", 0.0, 0.0, 1.0,
                  "Riduce l'opacità delle linee lontane dalla camera (prospettiva aerea)")
    overshoot: F("Estensione linee", 0.01, 0.0, 2.0, "Prolungamento oltre gli spigoli (frazione della lunghezza del tratto)", soft=(0.0, 0.5))
    overshoot_random: F("Casualità estensione", 0.5, 0.0, 1.0)
    multi_strokes: IntProperty(name="Tratti multipli", default=1, min=0, max=10, update=_upd,
                               description="Ripassi sovrapposti dello stesso tratto")
    multi_distance: F("Distanza ripassi (px)", 2.5, 0.0, 50.0, soft=(0.0, 10.0))
    tremor: F("Tremolio", 0.12, 0.0, 10.0, "Ampiezza del tremolio della mano", soft=(0.0, 3.0))
    tremor_scale: F("Frequenza tremolio", 0.12, 0.0, 1.0)
    tremor_thickness: F("Variazione spessore", 0.4, 0.0, 1.0, "Pressione irregolare lungo il tratto")
    line_smooth: F("Ammorbidisci", 0.15, 0.0, 1.0)
    boil: B("Animato (boil)", False, "Il tremolio cambia nel tempo, effetto disegno animato")
    boil_step: IntProperty(name="Ogni N frame", default=3, min=1, max=50, update=_upd)

    # --- linee di costruzione ----------------------------------------------
    constr_enable: B("Linee di costruzione", True)
    constr_length: F("Lunghezza", 0.6, 0.0, 5.0, "Prolungamento delle linee guida", soft=(0.0, 2.0))
    constr_opacity: F("Opacità", 0.25, 0.0, 1.0)
    constr_thickness: F("Spessore relativo", 0.4, 0.05, 2.0)

    # --- linee nascoste -----------------------------------------------------
    hidden_enable: B("Linee nascoste", False, "Disegna a trattini gli spigoli coperti da altre superfici")
    hidden_dash: F("Tratto (px)", 12.0, 1.0, 200.0, "Lunghezza di ogni trattino", soft=(2.0, 40.0))
    hidden_gap: F("Vuoto (px)", 7.0, 1.0, 200.0, "Spazio tra un trattino e il successivo", soft=(2.0, 40.0))
    hidden_opacity: F("Opacità", 1.0, 0.0, 1.0)
    hidden_thickness: F("Spessore relativo", 0.9, 0.05, 2.0)
    hidden_levels: IntProperty(
        name="Superfici attraversate", default=1, min=1, max=16, update=_upd,
        description="1 = solo gli spigoli coperti da una superficie; valori più alti "
                    "mostrano anche quelli più in profondità (vista a raggi X)")

    # --- tratteggio ---------------------------------------------------------
    hatch_enable: B("Tratteggio", True)
    hatch_strength: F("Intensità", 1.0, 0.0, 1.0)
    hatch_layers: IntProperty(name="Livelli", default=2, min=1, max=4, update=_upd,
                              description="Quante passate di tratteggio si sommano andando verso le ombre")
    hatch_style: EnumProperty(name="Stile", items=HATCH_STYLES, default="CROSS", update=_upd,
                              description="Tecnica di tratteggio")
    hatch_shape: F("Ampiezza motivo", 0.5, 0.0, 2.0,
                   "Ampiezza di onde, zig-zag e scarabocchi", soft=(0.0, 1.0))
    hatch_density: F("Densità", 300.0, 5.0, 3000.0, "Linee per altezza immagine", soft=(40.0, 800.0))
    hatch_angle: ANG("Angolo", 45.0)
    hatch_cross: FloatProperty(
        name="Angolo d'incrocio", subtype="ANGLE", default=math.radians(90),
        min=math.radians(5), max=math.radians(90), update=_upd,
        description="Angolo tra le passate del tratteggio incrociato: 90° = griglia, "
                    "valori minori = losanghe, come nell'incisione")
    hatch_follow: B("Segui le superfici", False,
                    "Ruota il tratteggio in base all'orientamento di ogni faccia, così piani "
                    "diversi si distinguono anche a parità di tono")
    hatch_weight: F("Peso", 0.5, 0.05, 1.0, "Spessore massimo delle linee di tratteggio")
    hatch_start: F("Soglia", 0.25, 0.0, 1.0, "Tono da cui inizia il tratteggio")
    hatch_wobble: F("Tremolio", 0.15, 0.0, 1.0, "Ondeggiamento di ogni singola linea", soft=(0.0, 0.4))
    hatch_wobble_scale: F("Frequenza tremolio", 25.0, 0.1, 200.0, soft=(2.0, 80.0))
    hatch_breaks: F("Interruzioni", 0.3, 0.0, 1.0, "Spezza le linee in tratti di lunghezza finita")
    hatch_break_scale: F("Lunghezza tratti", 6.0, 0.5, 100.0, "Valori alti = tratti più corti", soft=(1.0, 30.0))
    hatch_use_tip: BoolProperty(
        name="Punta per il tratteggio", default=False, update=_upd_tool,
        description="Il tratteggio usa una punta in millimetri (per esempio 0,18 con contorni "
                    "a 0,5) invece del Peso relativo alla densità")
    hatch_tip: EnumProperty(name="Punta tratteggio", items=tips.pen_items, default=18, update=_upd_tool,
                            description="Spessore delle linee di tratteggio in millimetri di carta")
    hatch_negative: B("In negativo (xilografia)", False,
                      "Il nero pieno diventa la regola e le luci sono linee bianche scavate, "
                      "come nell'incisione su legno o linoleum")

    # --- retino -------------------------------------------------------------
    tone_enable: B("Retino", False)
    tone_pattern: EnumProperty(
        name="Motivo", items=tones.enum_items, default=1, update=_upd_surface,
        description="Motivo del retino generale: punti, righe e le campiture d'architettura")
    tone_mode: EnumProperty(
        name="Modo", default="TONE", update=_upd_surface,
        items=[("TONE", "Tono", "Compare nelle ombre e si infittisce con il buio"),
               ("FLAT", "Campitura", "Motivo uniforme su tutta la superficie, come nelle sezioni")],
        description="Come si applica il retino")
    tone_objects: StringProperty()   # motivi scelti dagli oggetti, aggiornato da core
    tone_strength: F("Intensità", 1.0, 0.0, 1.0)
    tone_density: F("Densità", 70.0, 5.0, 1000.0, "Celle del motivo per altezza immagine", soft=(10.0, 300.0))
    tone_angle: ANG("Angolo", 45.0)
    tone_size: F("Spessore segno", 0.72, 0.05, 1.0, "Dimensione di punti e segni del motivo")
    tone_start: F("Soglia", 0.15, 0.0, 1.0)

    # --- lumeggiature -------------------------------------------------------
    highlight_enable: B("Lumeggiature", False,
                        "Gessetto chiaro sulle parti in luce, come negli studi su carta tinta")
    highlight_color: COL("Colore", (1.0, 1.0, 1.0))
    highlight_strength: F("Intensità", 0.8, 0.0, 1.0)
    highlight_threshold: F("Soglia", 0.75, 0.0, 1.0, "Sopra questa luminosità compare il gessetto")
    highlight_soft: F("Sfumatura", 0.3, 0.0, 1.0)

    # --- colore per oggetto ---------------------------------------------------
    objcolor_enable: BoolProperty(
        name="Colore per oggetto", default=False, update=_objcolor_upd,
        description="Ogni oggetto prende una tinta piatta, presa dal suo materiale originale "
                    "e modificabile (Proprietà oggetto)")
    objcolor_strength: F("Intensità", 0.85, 0.0, 1.0)
    objcolor_default: COL("Colore predefinito", (0.8, 0.8, 0.8),
                          "Tinta degli oggetti senza colore proprio")
    wash_use_object: BoolProperty(
        name="Colore dell'oggetto", default=False, update=_objcolor_upd,
        description="L'acquerello usa il colore di ogni oggetto invece di un colore unico")

    # --- puntinato ----------------------------------------------------------
    stipple_enable: B("Puntinato", False)
    stipple_strength: F("Intensità", 1.0, 0.0, 1.0)
    stipple_density: F("Densità", 160.0, 10.0, 2000.0, soft=(40.0, 600.0))
    stipple_size: F("Dimensione punti", 0.28, 0.02, 0.5)
    stipple_start: F("Soglia", 0.05, 0.0, 1.0)

    # --- ombre --------------------------------------------------------------
    shadow_enable: B("Campitura ombre", True)
    shadow_strength: F("Intensità", 0.3, 0.0, 1.0)
    shadow_threshold: F("Soglia", 0.6, 0.0, 1.0, "Sotto questa luminosità l'area viene campita")
    shadow_soft: F("Sfumatura", 0.0, 0.0, 1.0,
                   "0 = campitura dal bordo netto; 1 = sfumato, passaggio graduale dalla luce all'ombra")

    # --- acquerello / campitura colore -------------------------------------
    wash_enable: B("Acquerello", False)
    wash_strength: F("Intensità", 0.6, 0.0, 2.0)
    wash_color: COL("Colore", (0.45, 0.55, 0.70))
    wash_threshold: F("Soglia", 0.3, 0.0, 1.0)
    wash_irregularity: F("Irregolarità bordi", 0.35, 0.0, 2.0)
    wash_scale: F("Scala macchie", 3.0, 0.1, 50.0, soft=(0.5, 15.0))
    wash_edge: F("Bordo scuro", 0.35, 0.0, 2.0,
                 "Accumulo di pigmento sul bordo della campitura, come nell'acquerello vero")


_assign_updates(SketchRenderSettings)


# ---------------------------------------------------------------------------
# proprietà degli oggetti (lette dallo shader con un nodo Attribute)
# ---------------------------------------------------------------------------
def _get_obj_tone(self):
    return self.sketch_tone_id


def _set_obj_tone(self, value):
    self.sketch_tone_id = value
    for scene in self.users_scene:
        if scene.sketch_render.is_setup:
            core.refresh_object_tones(scene)
    core.redraw_views()


def register():
    bpy.utils.register_class(SketchRenderSettings)
    bpy.types.Scene.sketch_render = PointerProperty(type=SketchRenderSettings)
    # le impostazioni regolabili stanno sul World della carta (vedi core.settings)
    bpy.types.World.sketch_render = PointerProperty(type=SketchRenderSettings)
    bpy.types.Object.sketch_tone_id = IntProperty(default=0, options={"HIDDEN"})
    bpy.types.Object.sketch_tone = EnumProperty(
        name="Retino dell'oggetto", items=tones.object_items, get=_get_obj_tone, set=_set_obj_tone,
        description="Motivo del retino per questo oggetto: per esempio mattoni per i muri, "
                    "calcestruzzo per i solai")
    bpy.types.Object.sketch_color = FloatVectorProperty(
        name="Colore Sketch", size=4, subtype="COLOR", min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 0.0),
        description="Tinta dell'oggetto per \"Colore per oggetto\" (alfa 0 = colore predefinito)")


def unregister():
    for name in ("sketch_color", "sketch_tone", "sketch_tone_id"):
        if hasattr(bpy.types.Object, name):
            delattr(bpy.types.Object, name)
    del bpy.types.World.sketch_render
    del bpy.types.Scene.sketch_render
    bpy.utils.unregister_class(SketchRenderSettings)
