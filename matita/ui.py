# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import os

import bpy

from . import core, presets, scenes, tips

PRODUCT = "Matita"


def _read_version():
    """Versione leggibile dal manifest: "1.0.0-beta" -> "1.0 beta"."""
    try:
        import tomllib
        with open(os.path.join(os.path.dirname(__file__), "blender_manifest.toml"), "rb") as f:
            version = str(tomllib.load(f).get("version", ""))
    except Exception:
        return ""
    number, _, tag = version.partition("-")
    parts = number.split(".")
    while len(parts) > 2 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts) + (" " + tag if tag else "")


VERSION = _read_version()


class SKETCH_OT_setup(bpy.types.Operator):
    bl_idname = "matita.setup"
    bl_label = "Attiva Matita"
    bl_description = "Crea linee Line Art, materiale schizzo, carta e luce nella scena"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        first = not scene.sketch_render.is_setup
        core.setup(scene)
        presets.apply(scene, scene.sketch_render.preset)
        if first:
            # prima attivazione: l'esposizione parte bilanciata sulle luci della scena
            core.calibrate_exposure(scene)
            # scene pesanti: si parte con il calcolo veloce delle linee
            polygons = core.scene_polygons(scene)
            if polygons > core.FAST_LINES_POLYGONS:
                core.settings(scene).line_perf = "FAST"
                self.report({"INFO"}, f"Scena pesante ({polygons:,} poligoni): linee in modalità Veloce")
        return {"FINISHED"}


class SKETCH_OT_freeze_lines(bpy.types.Operator):
    bl_idname = "matita.freeze_lines"
    bl_label = "Congela linee"
    bl_description = ("Calcola le linee una volta e le conserva: la vista resta fluida anche con "
                      "milioni di poligoni. Ripeti dopo aver mosso la camera o modificato il modello")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            ok = core.freeze_lines(context.scene)
        except RuntimeError as ex:
            self.report({"ERROR"}, f"Impossibile congelare le linee: {ex}")
            return {"CANCELLED"}
        if not ok:
            self.report({"WARNING"}, "Nessuna linea da congelare")
            return {"CANCELLED"}
        self.report({"INFO"}, "Linee congelate")
        return {"FINISHED"}


class SKETCH_OT_unfreeze_lines(bpy.types.Operator):
    bl_idname = "matita.unfreeze_lines"
    bl_label = "Scongela"
    bl_description = "Torna alle linee calcolate in tempo reale"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        p = core.settings(context.scene)
        if p.auto_freeze:
            core._suspend = True     # tornare al calcolo continuo spegne anche l'automatico
            try:
                p.auto_freeze = False
            finally:
                core._suspend = False
        core.unfreeze_lines(context.scene)
        core.sync(context.scene, refresh_metrics=True)
        return {"FINISHED"}


class SKETCH_OT_calibrate(bpy.types.Operator):
    bl_idname = "matita.calibrate_exposure"
    bl_label = "Calibra esposizione"
    bl_description = ("Imposta l'esposizione in base alle luci presenti nella scena, senza "
                      "modificarle: una superficie in piena luce resta bianca come la carta")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        core.calibrate_exposure(context.scene)
        self.report({"INFO"}, f"Esposizione: {core.settings(context.scene).exposure:.3g}")
        return {"FINISHED"}


class SKETCH_OT_add_sun(bpy.types.Operator):
    bl_idname = "matita.add_sun"
    bl_label = "Aggiungi sole"
    bl_description = "Aggiunge un sole laterale rispetto alla camera; poi lo si regola in Blender"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        core.add_sun(context.scene)
        return {"FINISHED"}


class SKETCH_OT_orient_light(bpy.types.Operator):
    bl_idname = "matita.orient_light"
    bl_label = "Orienta rispetto alla camera"
    bl_description = ("Ruota una volta la luce principale rispetto all'inquadratura. "
                      "Intensità e altre proprietà della luce non vengono toccate")
    bl_options = {"REGISTER", "UNDO"}

    azimuth: bpy.props.FloatProperty(
        name="Direzione", subtype="ANGLE", default=core.DEFAULT_AZIMUTH,
        min=-3.14159265, max=3.14159265,
        description="0° = luce alle spalle della camera (piatta, senza ombre visibili); "
                    "negativo = da sinistra, positivo = da destra; ±180° = controluce")
    elevation: bpy.props.FloatProperty(
        name="Altezza", subtype="ANGLE", default=core.DEFAULT_ELEVATION,
        min=0.035, max=1.5707963,
        description="Altezza sull'orizzonte: bassa = ombre lunghe")

    @classmethod
    def poll(cls, context):
        return context.scene.sketch_render.sun_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        light = scene.sketch_render.sun_object
        light.rotation_mode = "XYZ"
        light.rotation_euler = core.sun_rotation(scene, self.azimuth, self.elevation)
        return {"FINISHED"}


class SKETCH_OT_demo_scene(bpy.types.Operator):
    bl_idname = "matita.demo_scene"
    bl_label = "Crea scena demo"
    bl_description = ("Costruisce una scena di prova in una scena nuova (quella corrente non viene "
                      "modificata) e vi applica Matita con uno stile adatto")
    bl_options = {"REGISTER", "UNDO"}

    demo: bpy.props.EnumProperty(name="Scena", items=scenes.ENUM_ITEMS)

    @classmethod
    def description(cls, context, properties):
        return scenes.DEMOS[properties.demo]["description"]

    def execute(self, context):
        scene = scenes.create(context, self.demo)
        self.report({"INFO"}, f"Scena '{scene.name}' pronta: premi Render o cambia stile")
        return {"FINISHED"}


class SKETCH_MT_demo_scenes(bpy.types.Menu):
    bl_idname = "SKETCH_MT_demo_scenes"
    bl_label = "Scene demo"

    def draw(self, context):
        for key, demo in scenes.DEMOS.items():
            self.layout.operator("matita.demo_scene", text=demo["label"],
                                 icon=demo["icon"]).demo = key


class SKETCH_OT_remove(bpy.types.Operator):
    bl_idname = "matita.remove"
    bl_label = "Rimuovi Matita"
    bl_description = "Rimuove gli oggetti creati e ripristina world, materiali e color management"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        core.remove(context.scene)
        return {"FINISHED"}


class SKETCH_OT_preset_save(bpy.types.Operator):
    bl_idname = "matita.preset_save"
    bl_label = "Salva preset"
    bl_description = "Salva le impostazioni correnti come preset personale"

    name: bpy.props.StringProperty(name="Nome", default="Mio stile")

    def invoke(self, context, event):
        cur = context.scene.sketch_render.preset
        if cur.startswith(presets.USER_PREFIX):
            self.name = cur[len(presets.USER_PREFIX):]
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "name")
        if presets.user_exists(self.name.strip()):
            col.label(text="Esiste già: verrà sovrascritto", icon="ERROR")

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({"ERROR"}, "Inserisci un nome")
            return {"CANCELLED"}
        overwrite = presets.user_exists(name)
        presets.save_user(context.scene, name)
        core._suspend = True
        try:
            context.scene.sketch_render.preset = presets.USER_PREFIX + name
        finally:
            core._suspend = False
        self.report({"INFO"}, f"Preset '{name}' {'aggiornato' if overwrite else 'salvato'}")
        return {"FINISHED"}


class SKETCH_OT_preset_delete(bpy.types.Operator):
    bl_idname = "matita.preset_delete"
    bl_label = "Elimina preset"
    bl_description = "Elimina il preset personale selezionato"

    @classmethod
    def poll(cls, context):
        return context.scene.sketch_render.preset.startswith(presets.USER_PREFIX)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Elimina preset",
            message=f"Eliminare '{context.scene.sketch_render.preset[len(presets.USER_PREFIX):]}'?",
            confirm_text="Elimina")

    def execute(self, context):
        s = context.scene.sketch_render
        name = s.preset[len(presets.USER_PREFIX):]
        presets.delete_user(name)
        core._suspend = True
        try:
            s.preset = presets.DEFAULT_STYLE  # torna allo stile base senza cambiare i parametri
        finally:
            core._suspend = False
        self.report({"INFO"}, f"Preset '{name}' eliminato")
        return {"FINISHED"}


class SKETCH_OT_preset_folder(bpy.types.Operator):
    bl_idname = "matita.preset_folder"
    bl_label = "Apri cartella preset"
    bl_description = "Apre la cartella dei preset personali (file .json, condivisibili)"

    def execute(self, context):
        presets.refresh_user()  # al ritorno l'elenco riflette i file copiati a mano
        bpy.ops.wm.path_open(filepath=presets.user_dir())
        return {"FINISHED"}


class SKETCH_OT_tone_to_selected(bpy.types.Operator):
    bl_idname = "matita.tone_to_selected"
    bl_label = "Applica ai selezionati"
    bl_description = "Dà a tutti gli oggetti selezionati il retino dell'oggetto attivo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        value = context.object.sketch_tone_id
        n = 0
        for obj in context.selected_objects:
            if obj.sketch_tone_id != value:
                obj.sketch_tone_id = value
                n += 1
        core.refresh_object_tones(context.scene)
        core.redraw_views()
        self.report({"INFO"}, f"Retino applicato a {n} oggetti")
        return {"FINISHED"}


class SKETCH_OT_object_colors(bpy.types.Operator):
    bl_idname = "matita.object_colors"
    bl_label = "Colori dai materiali"
    bl_description = ("Copia in ogni oggetto il colore del suo materiale originale "
                      "(sovrascrive i colori Matita già impostati)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = core.fill_object_colors(context.scene, only_missing=False)
        core.redraw_views()
        self.report({"INFO"}, f"Colore preso dal materiale per {n} oggetti")
        return {"FINISHED"}


class SKETCH_OT_refresh(bpy.types.Operator):
    bl_idname = "matita.refresh"
    bl_label = "Aggiorna"
    bl_description = ("Ricostruisce materiale e carta e riapplica i parametri "
                      "(dopo aver spostato la camera, cambiato risoluzione o aggiornato l'add-on)")

    def execute(self, context):
        presets.refresh_user()
        core.setup(context.scene)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# pannelli: "s" è lo stato sulla Scena, "p" le impostazioni regolabili (World)
#
# Ogni gruppo di comandi sta in un riquadro con titolo; dentro, ogni voce ha la
# propria riga con etichetta a sinistra e campo a destra.
# ---------------------------------------------------------------------------
def _group(layout, title=None, icon="NONE", active=True):
    """Riquadro con titolo; restituisce la colonna in cui mettere le voci."""
    box = layout.box()
    if title:
        box.label(text=title, icon=icon)
    col = box.column()
    col.use_property_split = True
    col.use_property_decorate = False
    col.active = active
    return col


def _fields(col, owner, names):
    for name in names:
        col.prop(owner, name)


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PRODUCT

    @classmethod
    def poll(cls, context):
        return context.scene.sketch_render.is_setup


class SKETCH_PT_main(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PRODUCT
    bl_label = f"{PRODUCT} V{VERSION}" if VERSION else PRODUCT

    def draw(self, context):
        scene = context.scene
        s = scene.sketch_render
        layout = self.layout

        box = layout.box()
        box.label(text="Stile", icon="BRUSH_DATA")
        row = box.row(align=True)
        row.prop(s, "preset", text="")
        row.operator("matita.preset_save", text="", icon="ADD")
        row.operator("matita.preset_delete", text="", icon="REMOVE")
        row.operator("matita.preset_folder", text="", icon="FILE_FOLDER")
        if not s.is_setup:
            col = box.column()
            col.scale_y = 1.4
            col.operator("matita.setup", icon="GREASEPENCIL")
            layout.menu("SKETCH_MT_demo_scenes", icon="SCENE_DATA")
            return

        p = core.settings(scene)
        col = _group(layout, "Colori", "COLOR")
        col.prop(p, "paper_color", text="Carta")
        col.prop(p, "ink_color", text="Inchiostro")
        col.prop(p, "seed")

        # render e prestazioni insieme: sono le regolazioni che si toccano
        # insieme quando la scena è pesante
        col = _group(layout, "Render e prestazioni", "RENDER_STILL")
        if hasattr(scene.eevee, "taa_render_samples"):
            col.prop(scene.eevee, "taa_render_samples", text="Campioni render")
        col.prop(p, "line_perf")
        col.prop(p, "viewport_lines")
        col.prop(p, "auto_freeze")
        row = col.row(align=True)
        if p.auto_freeze:
            row.operator("matita.freeze_lines", text="Ricalcola ora", icon="FILE_REFRESH")
            if core.auto_freeze_pending(scene):
                col.label(text="Aggiornamento appena ti fermi…", icon="SORTTIME")
            else:
                col.label(text="Si aggiornano da sole quando ti fermi", icon="CHECKMARK")
        elif s.lines_frozen:
            row.operator("matita.freeze_lines", text="Ricalcola", icon="FILE_REFRESH")
            row.operator("matita.unfreeze_lines", icon="UNLOCKED")
            col.label(text="Linee congelate: non si aggiornano da sole", icon="LOCKED")
        else:
            row.operator("matita.freeze_lines", icon="LOCKED")
            sp = context.space_data
            if (p.viewport_lines and getattr(sp, "type", "") == "VIEW_3D" and sp.lock_camera
                    and sp.region_3d is not None and sp.region_3d.view_perspective == "CAMERA"):
                # navigare in camera la sposta: ogni passo ricalcola tutte le linee
                box = col.box()
                box.label(text="Camera bloccata alla vista:", icon="INFO")
                box.label(text="ogni movimento ricalcola le linee.")
                box.prop(p, "auto_freeze", text="Attiva Ricongela da sole")
        row = col.row()
        row.scale_y = 1.3
        row.operator("render.render", text="Render", icon="RENDER_STILL")

        row = layout.row(align=True)
        row.operator("matita.refresh", icon="FILE_REFRESH")
        row.operator("matita.remove", icon="X", text="Rimuovi")
        layout.menu("SKETCH_MT_demo_scenes", icon="SCENE_DATA")


class SKETCH_PT_paper(_Base, bpy.types.Panel):
    """Menu visivo delle carte: ogni icona mostra la grana; sotto, le caratteristiche regolabili."""
    bl_label = "Carta"
    bl_parent_id = "SKETCH_PT_main"
    bl_order = 0
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        p = core.settings(context.scene)
        layout = self.layout
        box = layout.box()
        box.label(text="Tipo di carta", icon="IMAGE_DATA")
        box.template_icon_view(p, "paper_type", show_labels=True, scale=6.0, scale_popup=5.0)
        box.prop(p, "paper_type", text="")

        col = _group(layout, "Superficie", "TEXTURE")
        col.prop(p, "paper_color", text="Colore")
        col.prop(p, "paper_grain")
        sub = col.column()
        sub.active = p.paper_grain > 0.0 or p.ink_tooth > 0.0
        sub.prop(p, "paper_grain_scale")
        col.prop(p, "paper_fibers")
        col.prop(p, "paper_age")

        col = _group(layout, "Trama", "MOD_LATTICE")
        col.prop(p, "paper_pattern")
        sub = col.column()
        sub.active = p.paper_pattern > 0.0
        sub.prop(p, "paper_pattern_scale")

        col = _group(layout, "Mezzo", "GREASEPENCIL")
        col.prop(p, "ink_tooth")


def _draw_tool(layout, scene, p, on):
    """Strumento da disegno: menu visivo delle punte (penne) o delle gradazioni (matite)."""
    box = layout.box()
    box.active = on
    box.label(text="Strumento", icon="TOOL_SETTINGS")
    box.row().prop(p, "tool_type", expand=True)
    if p.tool_type == "FREE":
        return
    if p.tool_type == "PENCIL":
        box.template_icon_view(p, "pencil_grade", show_labels=True, scale=5.0, scale_popup=4.0)
        box.prop(p, "pencil_grade", text="")
    else:
        box.template_icon_view(p, "tool_tip", show_labels=True, scale=5.0, scale_popup=4.0)
        box.prop(p, "tool_tip", text="Spigoli")
    col = box.column()
    col.use_property_split = True
    col.use_property_decorate = False
    col.prop(p, "sheet_format")
    mm = tips.tip_mm(p)
    col.label(text="%s mm = %.1f px sul render" % (tips.pen_label(round(mm, 2)), tips.line_px(scene, p)),
              icon="INFO")
    if tips.uses_pen_set(p):
        sub = box.column(align=True)
        sub.use_property_split = True
        sub.use_property_decorate = False
        sub.label(text="Gerarchia dei tratti")
        sub.prop(p, "pen_profile")
        sub.prop(p, "pen_hidden")
        sub.prop(p, "pen_constr")


class SKETCH_PT_lines(_Base, bpy.types.Panel):
    bl_label = "Linee"
    bl_parent_id = "SKETCH_PT_main"
    bl_order = 1

    def draw_header(self, context):
        self.layout.prop(core.settings(context.scene), "line_enable", text="")

    def draw(self, context):
        scene = context.scene
        p = core.settings(scene)
        layout = self.layout
        on = p.line_enable

        _draw_tool(layout, scene, p, on)

        col = _group(layout, "Tratto", "LINE_DATA", on)
        if p.tool_type == "FREE":
            _fields(col, p, ("line_thickness", "profile_factor"))
        elif p.tool_type == "PENCIL":
            col.prop(p, "profile_factor")
        col.prop(p, "line_opacity")
        col.prop(p, "use_line_color")
        sub = col.column()
        sub.active = p.use_line_color
        sub.prop(p, "line_color")

        col = _group(layout, "Rilevamento", "EDGESEL", on)
        col.prop(p, "all_edges")
        sub = col.column()
        sub.active = not p.all_edges
        sub.prop(p, "crease_angle")
        col.prop(p, "split_angle")
        sub = col.column()
        sub.active = p.line_perf != "FAST"
        sub.prop(p, "line_intersections")

        col = _group(layout, "Profondità", "CON_CAMERASOLVER", on)
        _fields(col, p, ("depth_thin", "depth_fade"))

        col = _group(layout, "Mano libera", "GREASEPENCIL", on)
        _fields(col, p, ("overshoot", "overshoot_random", "multi_strokes"))
        sub = col.column()
        sub.active = p.multi_strokes > 0
        sub.prop(p, "multi_distance")
        _fields(col, p, ("tremor", "tremor_scale", "tremor_thickness", "line_smooth"))

        col = _group(layout, "Animazione", "TIME", on)
        col.prop(p, "boil")
        sub = col.column()
        sub.active = p.boil
        sub.prop(p, "boil_step")


def _technique_panel(cls_name, label, enable, groups, order, before=None, after=None, inactive=None):
    """Pannello di una tecnica: `groups` è una lista di (titolo, icona, voci).

    before/after(layout, context, p, on) disegnano parti speciali; inactive(p)
    restituisce le voci da mostrare spente (per esempio sostituite dalle punte).
    """
    def draw_header(self, context):
        self.layout.prop(core.settings(context.scene), enable, text="")

    def draw(self, context):
        p = core.settings(context.scene)
        on = getattr(p, enable)
        if before is not None:
            before(self.layout, context, p, on)
        off = inactive(p) if inactive is not None else ()
        for title, icon, names in groups:
            col = _group(self.layout, title, icon, on)
            for name in names:
                if name in off:
                    sub = col.column()
                    sub.active = False
                    sub.prop(p, name)
                else:
                    col.prop(p, name)
        if after is not None:
            after(self.layout, context, p, on)

    return type(cls_name, (_Base, bpy.types.Panel), dict(
        bl_label=label, bl_parent_id="SKETCH_PT_main", bl_order=order,
        bl_options={"DEFAULT_CLOSED"}, draw_header=draw_header, draw=draw))


def _pen_note(layout, p, prop, label):
    """Con le penne lo spessore di un tipo di linea è la sua punta."""
    if tips.uses_pen_set(p):
        col = _group(layout, "Punta", "LINE_DATA")
        col.prop(p, prop, text=label)


def _pens_replace(*names):
    return lambda p: names if tips.uses_pen_set(p) else ()


SKETCH_PT_construction = _technique_panel(
    "SKETCH_PT_construction", "Linee di costruzione", "constr_enable", [
        ("Tratto", "LINE_DATA", ("constr_length", "constr_opacity", "constr_thickness"))], 2,
    before=lambda layout, ctx, p, on: _pen_note(layout, p, "pen_constr", "Costruzione"),
    inactive=_pens_replace("constr_thickness"))
SKETCH_PT_hidden = _technique_panel("SKETCH_PT_hidden", "Linee nascoste", "hidden_enable", [
    ("Profondità", "XRAY", ("hidden_levels",)),
    ("Trattini", "LINE_DATA", ("hidden_dash", "hidden_gap", "hidden_opacity", "hidden_thickness"))], 3,
    before=lambda layout, ctx, p, on: _pen_note(layout, p, "pen_hidden", "Nascoste"),
    inactive=_pens_replace("hidden_thickness"))


def _hatch_tip(layout, context, p, on):
    col = _group(layout, "Punta", "LINE_DATA", on)
    col.prop(p, "hatch_use_tip")
    sub = col.column()
    sub.active = p.hatch_use_tip
    sub.prop(p, "hatch_tip")
    col.prop(p, "hatch_negative")


SKETCH_PT_hatch = _technique_panel("SKETCH_PT_hatch", "Tratteggio", "hatch_enable", [
    ("Stile", "BRUSH_DATA", ("hatch_style", "hatch_shape", "hatch_layers", "hatch_follow")),
    ("Trama", "MOD_LATTICE", ("hatch_density", "hatch_angle", "hatch_cross")),
    ("Tono", "IMAGE_ALPHA", ("hatch_strength", "hatch_weight", "hatch_start")),
    ("Mano libera", "GREASEPENCIL", ("hatch_wobble", "hatch_wobble_scale", "hatch_breaks",
                                     "hatch_break_scale"))], 4,
    after=_hatch_tip, inactive=lambda p: ("hatch_weight",) if p.hatch_use_tip else ())


def _tone_top(layout, context, p, on):
    box = layout.box()
    box.active = on
    box.label(text="Motivo", icon="TEXTURE")
    box.template_icon_view(p, "tone_pattern", show_labels=True, scale=5.0, scale_popup=4.0)
    box.prop(p, "tone_pattern", text="")
    row = box.row()
    row.prop(p, "tone_mode", expand=True)


def _tone_object(layout, context, p, on):
    obj = context.object
    col = _group(layout, "Retino dell'oggetto", "OBJECT_DATA", on)
    if obj is None:
        col.label(text="Nessun oggetto attivo")
        return
    col.label(text=obj.name, icon="OBJECT_DATA")
    col.prop(obj, "sketch_tone", text="Motivo")
    col.operator("matita.tone_to_selected", icon="RESTRICT_SELECT_OFF")


SKETCH_PT_tone = _technique_panel("SKETCH_PT_tone", "Retino", "tone_enable", [
    ("Disegno", "LIGHTPROBE_VOLUME", ("tone_density", "tone_angle", "tone_size")),
    ("Tono", "IMAGE_ALPHA", ("tone_strength", "tone_start"))], 5,
    before=_tone_top, after=_tone_object,
    inactive=lambda p: ("tone_start",) if p.tone_mode == "FLAT" else ())
SKETCH_PT_stipple = _technique_panel("SKETCH_PT_stipple", "Puntinato", "stipple_enable", [
    ("Punti", "LIGHTPROBE_VOLUME", ("stipple_density", "stipple_size")),
    ("Tono", "IMAGE_ALPHA", ("stipple_strength", "stipple_start"))], 6)
SKETCH_PT_shadow = _technique_panel("SKETCH_PT_shadow", "Campitura ombre", "shadow_enable", [
    ("Ombra", "MOD_MASK", ("shadow_strength", "shadow_threshold", "shadow_soft"))], 7)
SKETCH_PT_wash = _technique_panel("SKETCH_PT_wash", "Acquerello", "wash_enable", [
    ("Colore", "COLOR", ("wash_color", "wash_strength", "wash_threshold")),
    ("Bordi", "MOD_FLUID", ("wash_irregularity", "wash_scale", "wash_edge"))], 8,
    after=lambda layout, ctx, p, on: _group(layout, "Colore per oggetto", "OBJECT_DATA", on).prop(
        p, "wash_use_object"),
    inactive=lambda p: ("wash_color",) if p.wash_use_object else ())


def _objcolor_object(layout, context, p, on):
    obj = context.object
    col = _group(layout, "Oggetto attivo", "OBJECT_DATA", on)
    if obj is not None and hasattr(obj, "sketch_color"):
        col.label(text=obj.name, icon="OBJECT_DATA")
        col.prop(obj, "sketch_color", text="Colore")
    col.operator("matita.object_colors", icon="MATERIAL")


SKETCH_PT_objcolor = _technique_panel(
    "SKETCH_PT_objcolor", "Colore per oggetto", "objcolor_enable", [
        ("Tinta", "COLOR", ("objcolor_strength", "objcolor_default"))], 9,
    after=_objcolor_object)
SKETCH_PT_highlight = _technique_panel(
    "SKETCH_PT_highlight", "Lumeggiature", "highlight_enable", [
        ("Gessetto", "LIGHT_SUN", ("highlight_color", "highlight_strength", "highlight_threshold",
                                   "highlight_soft"))], 10)

LIGHT_ICONS = {"SUN": "LIGHT_SUN", "POINT": "LIGHT_POINT", "SPOT": "LIGHT_SPOT", "AREA": "LIGHT_AREA"}
MAX_LIGHT_ROWS = 8


class SKETCH_PT_light(_Base, bpy.types.Panel):
    """Le luci sono della scena: qui si leggono e si regolano le proprietà di Blender."""
    bl_label = "Luce e toni"
    bl_parent_id = "SKETCH_PT_main"
    bl_order = 11
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        scene = context.scene
        s = scene.sketch_render
        p = core.settings(scene)
        lights = core.scene_lights(scene)
        layout = self.layout

        # conversione luce -> toni (dell'add-on)
        col = _group(layout, "Toni", "IMAGE_ALPHA")
        row = col.row(align=True)
        row.prop(p, "exposure")
        row.operator("matita.calibrate_exposure", text="", icon="EYEDROPPER")
        suggested = core.suggested_exposure(scene, lights)
        ratio = p.exposure / suggested if suggested > 0 else 1.0
        if ratio > 1.6:
            col.label(text=f"Sovraesposto: consigliata {suggested:.3g}", icon="ERROR")
        elif ratio < 0.6:
            col.label(text=f"Sottoesposto: consigliata {suggested:.3g}", icon="ERROR")
        else:
            col.label(text=f"Bilanciato (consigliata {suggested:.3g})", icon="CHECKMARK")
        _fields(col, p, ("gamma", "ambient"))

        # luci della scena: proprietà di Blender, l'add-on non le riscrive
        if not lights:
            col = _group(layout, "Luci della scena", "OUTLINER_OB_LIGHT")
            col.label(text="Nessuna luce: solo luce ambiente")
            col.operator("matita.add_sun", icon="LIGHT_SUN")
            return
        for obj in lights[:MAX_LIGHT_ROWS]:
            data = obj.data
            box = layout.box()
            row = box.row(align=True)
            row.label(text=obj.name, icon=LIGHT_ICONS.get(data.type, "LIGHT"))
            if obj == s.sun_object:
                row.label(text="", icon="SOLO_ON")
            row.prop(obj, "hide_render", text="", emboss=False)
            sub = box.column()
            sub.use_property_split = True
            sub.use_property_decorate = False
            sub.active = not obj.hide_render
            sub.prop(data, "energy", text="Intensità")
            sub.prop(data, "angle" if data.type == "SUN" else "shadow_soft_size",
                     text="Morbidezza ombre")
            sub.prop(data, "use_shadow", text="Proietta ombre")
        if len(lights) > MAX_LIGHT_ROWS:
            layout.label(text=f"… e altre {len(lights) - MAX_LIGHT_ROWS} luci")

        col = _group(layout, "Direzione", "ORIENTATION_VIEW")
        col.prop(s, "sun_object")
        col.operator("matita.orient_light", icon="ORIENTATION_VIEW")


classes = (
    SKETCH_OT_setup, SKETCH_OT_remove, SKETCH_OT_refresh,
    SKETCH_OT_freeze_lines, SKETCH_OT_unfreeze_lines,
    SKETCH_OT_calibrate, SKETCH_OT_add_sun, SKETCH_OT_orient_light,
    SKETCH_OT_demo_scene, SKETCH_MT_demo_scenes,
    SKETCH_OT_preset_save, SKETCH_OT_preset_delete, SKETCH_OT_preset_folder,
    SKETCH_OT_tone_to_selected, SKETCH_OT_object_colors,
    SKETCH_PT_main, SKETCH_PT_paper, SKETCH_PT_lines, SKETCH_PT_construction, SKETCH_PT_hidden,
    SKETCH_PT_hatch, SKETCH_PT_tone, SKETCH_PT_stipple, SKETCH_PT_shadow, SKETCH_PT_wash,
    SKETCH_PT_objcolor, SKETCH_PT_highlight, SKETCH_PT_light,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)