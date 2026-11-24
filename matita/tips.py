# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Strumenti da disegno: punte delle penne e gradazioni delle matite.

Lo spessore di una penna è in millimetri di carta. Per sapere quanti pixel
sono, serve sapere su che foglio "stampiamo" l'immagine: il formato decide
quanti millimetri misura il lato lungo del render. Il formato non dipende dalla
scala del modello né dall'inquadratura: traduce solo mm di carta in pixel.

Le miniature dei menu visivi stanno in tips/ (vedi tools/make_tip_previews.py).
"""

import os

# --- penne ------------------------------------------------------------------
# serie ISO 128 delle penne tecniche a china e punte dei fineliner
ISO_PEN_MM = (0.13, 0.18, 0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0)
FINELINER_MM = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8)
ALL_PEN_MM = tuple(sorted(set(ISO_PEN_MM) | set(FINELINER_MM)))


def pen_id(mm):
    """Identificatore stabile di una punta: 0.35 -> "T035"."""
    return "T%03d" % round(mm * 100)


def pen_mm(ident):
    try:
        return int(ident[1:]) / 100.0
    except (ValueError, TypeError, IndexError):
        return 0.35


def pen_label(mm):
    return ("%g" % mm).replace(".", ",")


# --- matite -------------------------------------------------------------------
# dalla più dura alla più morbida. Per ogni gradazione:
#   mm     larghezza del segno (mina di matita in legno, temperata)
#   gray   colore lineare della grafite: le dure sono grigio chiaro, le morbide quasi nere
#   alpha  opacità del segno
#   tooth  quanto il segno si aggrappa alla grana della carta
PENCIL_GRADES = ("9H", "8H", "7H", "6H", "5H", "4H", "3H", "2H", "H", "F", "HB",
                 "B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B")


def pencil(grade):
    """(mm, grigio, opacità, presa della grana) di una gradazione."""
    try:
        i = PENCIL_GRADES.index(grade)
    except ValueError:
        i = PENCIL_GRADES.index("HB")
    d = i / (len(PENCIL_GRADES) - 1)          # 0 = 9H, 1 = 9B
    mm = 0.22 + 0.68 * d
    gray = 0.40 * (1.0 - d) ** 1.6 + 0.018
    alpha = 0.55 + 0.45 * d ** 0.7
    tooth = 0.18 + 0.47 * d
    return mm, gray, alpha, tooth


def apply_grade(settings, grade):
    """Sceglie la gradazione: colore della grafite, opacità e grana del segno.
    Restano poi regolabili a mano."""
    _mm, gray, alpha, tooth = pencil(grade)
    settings.ink_color = (gray, gray, gray * 1.04)
    settings.line_opacity = alpha
    settings.ink_tooth = tooth


# --- formato del foglio -----------------------------------------------------
# lato lungo in mm (serie A). AUTO = l'immagine stampata a 300 dpi.
SHEETS = (("AUTO", "Automatico (300 dpi)", 0.0), ("A5", "A5", 210.0), ("A4", "A4", 297.0),
          ("A3", "A3", 420.0), ("A2", "A2", 594.0), ("A1", "A1", 841.0), ("A0", "A0", 1189.0))
AUTO_DPI = 300.0


def px_per_mm(scene, sheet):
    """Pixel per millimetro di carta, alla risoluzione piena del render."""
    long_mm = dict((k, mm) for k, _l, mm in SHEETS).get(sheet, 420.0)
    if long_mm <= 0.0:
        return AUTO_DPI / 25.4
    r = scene.render
    return max(r.resolution_x, r.resolution_y, 1) / long_mm


def tip_mm(p):
    """Spessore in mm dello strumento scelto (None per lo strumento libero)."""
    if p.tool_type in ("TECH_PEN", "FINELINER"):
        return pen_mm(p.tool_tip)
    if p.tool_type == "PENCIL":
        return pencil(p.pencil_grade)[0]
    return None


def line_px(scene, p):
    """Spessore della linea principale in pixel."""
    mm = tip_mm(p)
    if mm is None:
        return p.line_thickness
    return mm * px_per_mm(scene, p.sheet_format)


def uses_pen_set(p):
    """Penne: ogni tipo di linea ha la sua punta (gerarchia del disegno tecnico)."""
    return p.tool_type in ("TECH_PEN", "FINELINER")


def ratios(p):
    """(profili, costruzione, nascoste) come multipli della linea principale."""
    if uses_pen_set(p):
        main = max(pen_mm(p.tool_tip), 1e-3)
        return (pen_mm(p.pen_profile) / main, pen_mm(p.pen_constr) / main,
                pen_mm(p.pen_hidden) / main)
    return p.profile_factor, p.constr_thickness, p.hidden_thickness


# --- menu visivi ----------------------------------------------------------------
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "tips")
_previews = None
_pen_items = []
_pencil_items = []


def _icon(key):
    if _previews is not None and key in _previews:
        return _previews[key].icon_id
    return 0


def pen_items(self, context):
    if not _pen_items:
        for mm in ALL_PEN_MM:
            series = []
            if mm in ISO_PEN_MM:
                series.append("penna tecnica ISO")
            if mm in FINELINER_MM:
                series.append("fineliner")
            _pen_items.append((pen_id(mm), pen_label(mm), "%s mm (%s)" % (pen_label(mm), ", ".join(series)),
                               _icon(pen_id(mm)), round(mm * 100)))
    return _pen_items


def pencil_items(self, context):
    if not _pencil_items:
        for i, g in enumerate(PENCIL_GRADES):
            kind = "dura" if "H" in g else ("morbida" if "B" in g and g != "HB" else "media")
            _pencil_items.append((g, g, "Matita %s (%s)" % (g, kind), _icon("P_" + g), i))
    return _pencil_items


def register():
    global _previews
    import bpy.utils.previews
    _previews = bpy.utils.previews.new()
    if os.path.isdir(PREVIEW_DIR):
        for fn in os.listdir(PREVIEW_DIR):
            if fn.endswith(".png"):
                _previews.load(fn[:-4], os.path.join(PREVIEW_DIR, fn), "IMAGE")
    _pen_items.clear()
    _pencil_items.clear()


def unregister():
    global _previews
    import bpy.utils.previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _pen_items.clear()
    _pencil_items.clear()
