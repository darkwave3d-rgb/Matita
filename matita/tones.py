# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Retini: i motivi più usati nel disegno di architettura e nella rappresentazione.

Un retino si può usare in due modi:
  TONE  come un retino tipografico: compare nelle zone in ombra e si infittisce
        con il buio (è il comportamento classico del "Retino")
  FLAT  campitura uniforme del materiale, come nelle sezioni e nelle tavole:
        lo stesso motivo su tutta la superficie, indipendente dalla luce

Il retino generale vale per tutta la scena; ogni oggetto può sceglierne uno
proprio (muri a mattoni, solai in calcestruzzo, terreno...) oppure nessuno.
L'oggetto salva solo un numero (Object.sketch_tone_id) che lo shader legge:
per questo i numeri non vanno mai cambiati né riusati.

I nodi di ogni motivo stanno in nodes.py (_tone_pattern); il materiale contiene
solo i motivi effettivamente in uso.
"""

import os

# (identificatore, nome, descrizione, numero)
PATTERNS = (
    ("DOTS", "Punti", "Retino a punti, quello classico del fumetto e della grafica", 1),
    ("LINES", "Linee", "Righe parallele: sezioni generiche, vetro, superfici lisce", 2),
    ("GRID", "Griglia", "Quadrettato (o losanghe ruotando l'angolo): pavimenti, piastrelle, rivestimenti", 3),
    ("BRICK", "Mattoni", "Muratura in mattoni a giunti sfalsati", 4),
    ("CONCRETE", "Calcestruzzo", "Calcestruzzo: punti e inerti sparsi", 5),
    ("SAND", "Sabbia / intonaco", "Puntinato fine e casuale: sabbia, intonaco, massetti", 6),
    ("GRAVEL", "Ghiaia", "Ciottoli arrotondati: ghiaia, vespai, drenaggi", 7),
    ("STONE", "Pietra", "Muratura in pietra irregolare (opus incertum)", 8),
    ("INSULATION", "Isolante", "Isolante termico: la classica linea ondulata", 9),
    ("WOOD", "Legno", "Venature del legno", 10),
    ("EARTH", "Terreno", "Terreno naturale: tratti obliqui spezzati e punti", 11),
)
IDS = {ident: num for ident, _l, _d, num in PATTERNS}
BY_NUM = {num: ident for ident, _l, _d, num in PATTERNS}
# valori speciali per l'oggetto
OBJ_SCENE = 0     # usa il retino generale
OBJ_NONE = 99     # nessun retino su questo oggetto

PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "tones")
_previews = None
_items = []
_obj_items = []


def _icon(key):
    if _previews is not None and key in _previews:
        return _previews[key].icon_id
    return 0


def enum_items(self, context):
    if not _items:
        for ident, label, desc, num in PATTERNS:
            _items.append((ident, label, desc, _icon(ident), num))
    return _items


def object_items(self, context):
    if not _obj_items:
        _obj_items.append(("SCENE", "Come la scena", "Usa il retino generale della scena", "WORLD", OBJ_SCENE))
        _obj_items.append(("NONE", "Nessuno", "Nessun retino su questo oggetto", "X", OBJ_NONE))
        for ident, label, desc, num in PATTERNS:
            _obj_items.append((ident, label, desc, _icon(ident), num))
    return _obj_items


def used_in(scene):
    """Motivi scelti dagli oggetti della scena (oltre al generale), ordinati."""
    found = set()
    any_none = False
    for o in scene.objects:
        num = getattr(o, "sketch_tone_id", 0)
        if num == OBJ_NONE:
            any_none = True
        elif num in BY_NUM:
            found.add(BY_NUM[num])
    return sorted(found), any_none


def register():
    global _previews
    import bpy.utils.previews
    _previews = bpy.utils.previews.new()
    if os.path.isdir(PREVIEW_DIR):
        for fn in os.listdir(PREVIEW_DIR):
            if fn.endswith(".png"):
                _previews.load(fn[:-4], os.path.join(PREVIEW_DIR, fn), "IMAGE")
    _items.clear()
    _obj_items.clear()


def unregister():
    global _previews
    import bpy.utils.previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _items.clear()
    _obj_items.clear()
