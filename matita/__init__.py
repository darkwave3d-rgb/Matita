# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Matita — rendering non fotorealistico in stile schizzo per Blender.

Le versioni di prova usavano un altro nome. I dati salvati nei .blend restano
sotto "sketch_render" (scene.sketch_render, world.sketch_render): così i file
creati con le versioni precedenti si aprono con le loro impostazioni.

Linee: Line Art + modificatori Grease Pencil (estensione, ripassi, tremolio).
Superfici: materiale EEVEE che converte la luce reale in tratteggio, retino,
puntinato, campiture d'ombra e acquerello, su carta con grana.
"""

if "bpy" in locals():
    import importlib
    from . import nodes, papers, tips, tones, core, presets, props, scenes, ui
    for m in (nodes, papers, tips, tones, core, presets, props, scenes, ui):
        importlib.reload(m)

import bpy  # noqa: E402
from . import core, papers, props, tips, tones, ui  # noqa: E402


def register():
    # le anteprime servono ai menu visivi di carte, punte e retini
    papers.register()
    tips.register()
    tones.register()
    props.register()
    ui.register()
    core.register()


def unregister():
    core.unregister()
    ui.unregister()
    props.unregister()
    tones.unregister()
    tips.unregister()
    papers.unregister()
