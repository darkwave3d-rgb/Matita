# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Genera le miniature dei menu visivi di punte, matite e retini.

Uso, dalla cartella del progetto:
    blender --background --factory-startup --python tools/make_tool_previews.py

- matita/tips/T035.png ...  tratto campione di ogni punta, in proporzione
- matita/tips/P_HB.png ...  segno di matita su carta con grana
- matita/tones/BRICK.png ... ritaglio del retino reso con lo shader dell'add-on
"""

import math
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matita  # noqa: E402

SIZE = 128
PAPER = np.array([0.965, 0.955, 0.93])


def _to_srgb(c):
    c = max(c, 0.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _save(rgb, path):
    """rgb: array (SIZE, SIZE, 3) già in valori di visualizzazione (sRGB)."""
    img = bpy.data.images.new("tmp_preview", SIZE, SIZE, alpha=True)
    rgba = np.ones((SIZE, SIZE, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)
    img.pixels.foreach_set(rgba[::-1].ravel())     # Blender parte dal basso
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _blur(a, passes):
    """Sfocatura a scatola ripetuta (quasi gaussiana)."""
    for _ in range(passes):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    return a


def _stroke_distance(cap=14):
    """Distanza di ogni pixel dal segmento orizzontale centrale (estremi arrotondati)."""
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) + 0.5
    cx = np.clip(x, cap, SIZE - cap)
    return np.hypot(x - cx, y - SIZE / 2)


def pen_icon(mm, path):
    w = min(max(mm * 24.0, 1.1), 56.0)               # 2 mm = 48 px, 0,05 mm ~ 1 px
    cov = np.clip(w / 2 - _stroke_distance() + 0.5, 0.0, 1.0)
    ink = np.array([0.06, 0.06, 0.07])
    rgb = PAPER * (1 - cov[..., None]) + ink * cov[..., None]
    _save(rgb, path)


def pencil_icon(grade, path, tips):
    mm, gray, alpha, tooth = tips.pencil(grade)
    rng = np.random.default_rng(7)
    grain = _blur(rng.random((SIZE, SIZE)), 1)
    grain = (grain - grain.min()) / (grain.max() - grain.min())
    # grana a due scale: fine più nuvolature morbide
    coarse = _blur(rng.random((SIZE, SIZE)), 6)
    coarse = (coarse - coarse.min()) / (coarse.max() - coarse.min())
    paper_peaks = np.clip((0.6 * grain + 0.4 * coarse - 0.45) * 4.0, 0.0, 1.0)
    w = mm * 40.0
    edge = (rng.random(SIZE) - 0.5) * 2.0 * (1.0 + tooth * 3.0)   # bordo irregolare
    d = _stroke_distance(cap=10) + edge[None, :] * 0.5
    cov = np.clip(w / 2 - d + 0.5, 0.0, 1.0)
    cov *= alpha * (1.0 - tooth + tooth * paper_peaks)
    g = _to_srgb(gray)
    ink = np.array([g, g, g * 1.02])
    paper = PAPER - 0.03 * grain[..., None]
    rgb = paper * (1 - cov[..., None]) + ink * cov[..., None]
    _save(rgb, path)


def tone_icons(core, tones):
    """Retini resi con lo shader vero, in campitura uniforme su un piano."""
    scene = bpy.data.scenes.new("TonePreviews")
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    me = bpy.data.meshes.new("plane")
    me.from_pydata([(-50, -50, 0), (50, -50, 0), (50, 50, 0), (-50, 50, 0)], [], [(0, 1, 2, 3)])
    plane = bpy.data.objects.new("plane", me)
    scene.collection.objects.link(plane)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 10
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, 0, 10)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.view_layers[0].update()
    core.setup(scene)
    p = core.settings(scene)
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
    r.use_border = r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = 0.4, 0.4 + SIZE / 1920
    r.border_min_y, r.border_max_y = 0.4, 0.4 + SIZE / 1080
    r.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 16
    core._suspend = True
    try:
        p.paper_type = "SMOOTH"
        p.paper_color = (0.93, 0.915, 0.87)
        p.paper_grain = p.paper_fibers = 0.0
        p.line_enable = p.constr_enable = p.hidden_enable = False
        p.hatch_enable = p.shadow_enable = p.wash_enable = p.stipple_enable = False
        p.tone_enable = True
        p.tone_mode = "FLAT"
        p.tone_density = 70.0
        p.tone_angle = 0.0
        p.ink_color = (0.03, 0.03, 0.035)
    finally:
        core._suspend = False
    os.makedirs(tones.PREVIEW_DIR, exist_ok=True)
    for ident, _label, _desc, _num in tones.PATTERNS:
        core._suspend = True
        try:
            p.tone_pattern = ident
            p.tone_size = 0.72
            p.tone_angle = math.radians(45) if ident in ("DOTS", "LINES", "EARTH") else 0.0
        finally:
            core._suspend = False
        core.sync(scene)
        r.filepath = os.path.join(tones.PREVIEW_DIR, ident + ".png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        print("retino:", r.filepath)


def main():
    matita.register()
    from matita import core, tips, tones
    os.makedirs(tips.PREVIEW_DIR, exist_ok=True)
    for mm in tips.ALL_PEN_MM:
        pen_icon(mm, os.path.join(tips.PREVIEW_DIR, tips.pen_id(mm) + ".png"))
    for g in tips.PENCIL_GRADES:
        pencil_icon(g, os.path.join(tips.PREVIEW_DIR, "P_" + g + ".png"), tips)
    print("punte e matite:", len(tips.ALL_PEN_MM) + len(tips.PENCIL_GRADES))
    tone_icons(core, tones)


main()
