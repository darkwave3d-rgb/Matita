# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Genera le anteprime delle carte (matita/papers/<TIPO>.png).

Uso, dalla cartella del progetto:
    blender --background --factory-startup --python tools/make_paper_previews.py

Ogni anteprima è un ritaglio a grandezza reale di un foglio 1920x1080 reso con
lo shader dell'add-on; grana, fibre e trama sono accentuate perché si leggano
anche in un'icona.
"""

import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matita  # noqa: E402

SIZE = 160          # lato dell'anteprima in pixel
BOOST = {"paper_grain": 2.5, "paper_fibers": 2.0, "paper_pattern": 2.5}


def main():
    matita.register()
    from matita import core, papers

    scene = bpy.data.scenes.new("PaperPreviews")
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    core.setup(scene)
    p = core.settings(scene)
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
    r.use_border = r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = 0.4, 0.4 + SIZE / 1920
    r.border_min_y, r.border_max_y = 0.4, 0.4 + SIZE / 1080
    r.image_settings.file_format = "PNG"
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16
    os.makedirs(papers.PREVIEW_DIR, exist_ok=True)

    for key in papers.TYPES:
        core._suspend = True
        try:
            p.paper_type = key
            papers.apply_type(p, key)
            for name, factor in BOOST.items():
                setattr(p, name, min(getattr(p, name) * factor, 0.6))
            p.line_enable = p.constr_enable = p.hidden_enable = False
        finally:
            core._suspend = False
        core.sync(scene)
        r.filepath = os.path.join(papers.PREVIEW_DIR, key + ".png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        print("anteprima:", r.filepath)


main()
