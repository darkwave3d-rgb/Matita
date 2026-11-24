# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tipi di carta delle belle arti.

Ogni tipo è un punto di partenza: sceglierlo imposta colore, grana, fibre e
trama, che restano poi regolabili uno per uno. La trama ("pattern") decide
quali nodi vengono costruiti nello shader (vedi nodes.paper_color).

I colori sono lineari (come li vuole Blender), non sRGB.
"""

import os

# parametri della carta impostati dalla scelta del tipo
PARAMS = ("paper_color", "paper_grain", "paper_grain_scale", "paper_fibers",
          "paper_pattern", "paper_pattern_scale", "paper_age")

# pattern: NONE, LAID (vergatura), BUMPS (rilievo), HONEYCOMB (alveoli),
#          CANVAS (tela), STREAKS (pennellate), MOTTLE (marezzatura)
TYPES = {
    "DRAWING": dict(
        label="Da disegno", desc="Carta da disegno a grana fine, per matita e penna",
        pattern="NONE", paper_color=(0.96, 0.94, 0.89), paper_grain=0.06, paper_grain_scale=750.0,
        paper_fibers=0.08, paper_pattern=0.0, paper_pattern_scale=1.0, paper_age=0.0),
    "SMOOTH": dict(
        label="Liscia (Bristol)", desc="Cartoncino satinato, superficie quasi priva di grana: china e pennarello",
        pattern="NONE", paper_color=(0.985, 0.98, 0.965), paper_grain=0.02, paper_grain_scale=1000.0,
        paper_fibers=0.0, paper_pattern=0.0, paper_pattern_scale=1.0, paper_age=0.0),
    "SKETCH": dict(
        label="Da schizzo", desc="Carta da schizzo a grana media, trattiene bene grafite e carboncino",
        pattern="NONE", paper_color=(0.95, 0.935, 0.90), paper_grain=0.11, paper_grain_scale=450.0,
        paper_fibers=0.12, paper_pattern=0.0, paper_pattern_scale=1.0, paper_age=0.0),
    "WC_HOT": dict(
        label="Acquerello satinata", desc="Carta da acquerello pressata a caldo (hot press): rilievo appena percettibile",
        pattern="BUMPS", paper_color=(0.975, 0.965, 0.94), paper_grain=0.03, paper_grain_scale=800.0,
        paper_fibers=0.04, paper_pattern=0.05, paper_pattern_scale=1.7, paper_age=0.0),
    "WC_COLD": dict(
        label="Acquerello grana fine", desc="Carta da acquerello pressata a freddo (cold press): rilievo fine e regolare",
        pattern="BUMPS", paper_color=(0.97, 0.955, 0.925), paper_grain=0.05, paper_grain_scale=600.0,
        paper_fibers=0.05, paper_pattern=0.12, paper_pattern_scale=1.0, paper_age=0.0),
    "WC_ROUGH": dict(
        label="Acquerello grana grossa", desc="Carta da acquerello torchon: rilievo marcato e irregolare",
        pattern="BUMPS", paper_color=(0.965, 0.95, 0.915), paper_grain=0.06, paper_grain_scale=450.0,
        paper_fibers=0.06, paper_pattern=0.2, paper_pattern_scale=0.5, paper_age=0.0),
    "LAID": dict(
        label="Vergata", desc="Carta vergata: sottili righe parallele e filoni, classica per carboncino e sanguigna",
        pattern="LAID", paper_color=(0.93, 0.90, 0.83), paper_grain=0.04, paper_grain_scale=750.0,
        paper_fibers=0.05, paper_pattern=0.10, paper_pattern_scale=1.0, paper_age=0.0),
    "PASTEL": dict(
        label="Pastello (alveolata)", desc="Carta colorata per pastello con trama a nido d'ape",
        pattern="HONEYCOMB", paper_color=(0.62, 0.56, 0.46), paper_grain=0.05, paper_grain_scale=650.0,
        paper_fibers=0.05, paper_pattern=0.13, paper_pattern_scale=1.0, paper_age=0.0),
    "CANVAS": dict(
        label="Telata", desc="Carta con impronta di tela, per tecniche a olio e acrilico",
        pattern="CANVAS", paper_color=(0.95, 0.94, 0.91), paper_grain=0.04, paper_grain_scale=650.0,
        paper_fibers=0.0, paper_pattern=0.12, paper_pattern_scale=1.0, paper_age=0.0),
    "WASHI": dict(
        label="Giapponese (washi)", desc="Carta giapponese sottile con lunghe fibre visibili",
        pattern="NONE", paper_color=(0.965, 0.95, 0.91), paper_grain=0.03, paper_grain_scale=900.0,
        paper_fibers=0.35, paper_pattern=0.0, paper_pattern_scale=1.0, paper_age=0.0),
    "KRAFT": dict(
        label="Kraft", desc="Carta da pacchi bruna e fibrosa, per studi a gessetto e lumeggiature",
        pattern="STREAKS", paper_color=(0.48, 0.31, 0.15), paper_grain=0.10, paper_grain_scale=550.0,
        paper_fibers=0.25, paper_pattern=0.08, paper_pattern_scale=1.0, paper_age=0.0),
    "PARCHMENT": dict(
        label="Pergamena", desc="Pergamena: superficie liscia e marezzata, toni caldi",
        pattern="MOTTLE", paper_color=(0.81, 0.72, 0.50), paper_grain=0.02, paper_grain_scale=950.0,
        paper_fibers=0.0, paper_pattern=0.14, paper_pattern_scale=1.0, paper_age=0.08),
    "PREPARED": dict(
        label="Preparata", desc="Carta con fondo tinto steso a pennello, come quelle rinascimentali per punta metallica e gessetti",
        pattern="STREAKS", paper_color=(0.67, 0.52, 0.30), paper_grain=0.05, paper_grain_scale=650.0,
        paper_fibers=0.06, paper_pattern=0.10, paper_pattern_scale=1.0, paper_age=0.10),
    "ANTIQUE": dict(
        label="Antica", desc="Carta vergata fatta a mano, ingiallita e macchiata dal tempo",
        pattern="LAID", paper_color=(0.74, 0.62, 0.40), paper_grain=0.08, paper_grain_scale=600.0,
        paper_fibers=0.15, paper_pattern=0.07, paper_pattern_scale=1.0, paper_age=0.25),
}

DEFAULT = "DRAWING"
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "papers")

_previews = None
_items = []   # Blender richiede che le stringhe dell'enum restino referenziate


def defaults(key):
    """Valori dei parametri carta per un tipo."""
    spec = TYPES.get(key) or TYPES[DEFAULT]
    return {k: spec[k] for k in PARAMS}


def pattern(key):
    return (TYPES.get(key) or TYPES[DEFAULT])["pattern"]


def apply_type(settings, key):
    for k, v in defaults(key).items():
        setattr(settings, k, v)


def enum_items(self, context):
    """Voci del menu visivo: l'icona è l'anteprima della grana di ogni carta."""
    if not _items:
        for i, (key, spec) in enumerate(TYPES.items()):
            icon = 0
            if _previews is not None and key in _previews:
                icon = _previews[key].icon_id
            _items.append((key, spec["label"], spec["desc"], icon, i))
    return _items


def register():
    global _previews
    import bpy.utils.previews
    _previews = bpy.utils.previews.new()
    for key in TYPES:
        path = os.path.join(PREVIEW_DIR, key + ".png")
        if os.path.isfile(path):
            _previews.load(key, path, "IMAGE")
    _items.clear()


def unregister():
    global _previews
    import bpy.utils.previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _items.clear()
