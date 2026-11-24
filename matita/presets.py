# SPDX-FileCopyrightText: 2026 Matita contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preset di stile.

- Preset integrati: partono dai valori BASE e sovrascrivono solo ciò che cambia.
- Preset utente: file JSON nella cartella utente dell'estensione (sopravvivono
  agli aggiornamenti dell'add-on). Identificatore enum: "USER:<nome>".
"""

import json
import math
import os
import re
import time
import zlib

from . import papers

USER_PREFIX = "USER:"

# Categorie del menu Stile: (chiave, titolo, icona)
CATEGORIES = (
    ("TECH", "Tecnico", "MESH_GRID"),
    ("ART", "Artistico", "BRUSH_DATA"),
    ("DESIGN", "Design", "MOD_SMOOTH"),
    ("VIP", "VIP", "SOLO_ON"),
)

# (identificatore, nome, descrizione, categoria, numero)
# Il numero è quello salvato nei .blend: non va mai cambiato né riusato.
STYLES = (
    ("TECH_PEN", "Penna tecnica", "Tratto pulito a china, tratteggio parallelo regolare a 45°", "TECH", 1),
    ("BLUEPRINT", "Blueprint", "Linee bianche su carta cianografica", "TECH", 6),
    ("STRUCTURE", "Struttura (tutti i bordi)", "Ogni spigolo della geometria, nascosti a trattini, linee più sottili e chiare in lontananza", "TECH", 10),
    ("ARCH_SKETCH", "Schizzo architettonico", "Linee estese, ripassi, tratteggio incrociato, linee guida", "ART", 0),
    ("PENCIL", "Matita", "Grafite morbida su carta da schizzo: tratti ripassati, sfumato, grana visibile", "ART", 2),
    ("STIPPLE", "Puntinato", "Ombreggiatura a punti, stile illustrazione scientifica", "ART", 3),
    ("SCREENTONE", "Retino", "Retino a punti e ombre piene, stile fumetto/manga", "ART", 4),
    ("WATERCOLOR", "Concept acquerello", "Linee libere con campiture ad acquerello", "ART", 5),
    ("MARKER", "Pennarello", "Tratto grosso e ombre a pennarello grigio", "ART", 7),
    ("DESIGN_FURNITURE", "Arredo e prodotto", "Fineliner e pennarelli grigi su carta bianca: silhouette marcate, linee guida, campiture a marker", "DESIGN", 12),
    ("DESIGN_AUTO", "Automotive", "Schizzo di carrozzeria: profili pesanti e slanciati, linee che sfuggono oltre gli spigoli, tratteggio veloce e marker freddi", "DESIGN", 13),
    ("DESIGN_FASHION", "Moda", "Figurino: linea elegante a pressione variabile, acquerello colorato steso a larghe macchie, niente tratteggio", "DESIGN", 14),
    ("LEONARDO", "Leonardo", "Penna e inchiostro bruno su carta antica: tratteggio parallelo da mancino, pentimenti, lievi acquerellature", "VIP", 8),
    ("MICHELANGELO", "Michelangelo", "Sanguigna su carta vergata: contorni ripassati, tratteggio incrociato che segue i volumi, sfumato", "VIP", 9),
    ("PIRANESI", "Piranesi", "Acquaforte: fitto tratteggio incrociato a losanghe che segue i volumi, neri profondi, lontananze schiarite", "VIP", 11),
    ("PATENT", "Disegno da brevetto", "China nera su bianco: tratteggio parallelo sulle superfici, puntinato sulle curve, nessuna campitura", "TECH", 15),
    ("CHALKBOARD", "Lavagna", "Gesso bianco su lavagna verde scuro: linee e lumeggiature che prendono la grana", "TECH", 16),
    ("CHARCOAL", "Carboncino", "Neri pieni e sfumati, segno grosso e irregolare che si aggrappa alla carta", "ART", 17),
    ("INK_WASH", "Inchiostro diluito", "Sumi-e: poche linee a pressione variabile e velature grigie su carta washi", "ART", 18),
    ("LIGNE_CLAIRE", "Linea chiara", "Fumetto franco-belga: linea uniforme e pulita, colori piatti per oggetto, ombre nette", "ART", 19),
    ("URBAN", "Urban sketching", "Fineliner libero e acquerello steso con i colori degli oggetti", "ART", 20),
    ("TROIS_CRAYONS", "Tre matite", "Sanguigna, pietra nera e gessetto bianco su carta tinta", "ART", 21),
    ("WOODCUT", "Xilografia", "Incisione su legno: masse nere con le luci scavate in linee bianche", "ART", 22),
    ("WHITE_MODEL", "Plastico bianco", "Modello bianco da concorso: linee sottili grigie e ombre morbide", "DESIGN", 23),
    ("INTERIOR", "Interior", "Fineliner e pennarelli dai colori caldi degli oggetti, per arredi e ambienti", "DESIGN", 24),
    ("DURER", "Dürer", "Incisione a bulino: tratteggio finissimo che avvolge le forme, puntini nei passaggi di luce", "VIP", 25),
    ("REMBRANDT", "Rembrandt", "Penna e inchiostro bruno con velature dense e chiaroscuro profondo", "VIP", 26),
    ("CANALETTO", "Canaletto", "Veduta a penna con acquerello grigio-azzurro, linee nitide e prospettiche", "VIP", 27),
    ("HOKUSAI", "Hokusai", "Stampa giapponese: contorni netti, campiture piatte di colore, blu di Prussia", "VIP", 28),
)
# numeri dei titoli di categoria nel menu (non sono stili selezionabili)
_HEADING_BASE = 900

# elenco semplice (identificatore, nome, descrizione) nell'ordine del menu
ENUM_ITEMS = [(ident, label, desc) for ident, label, desc, _c, _n in STYLES]
DEFAULT_STYLE = "ARCH_SKETCH"

BASE = dict(
    # carta: il tipo porta con sé colore, grana, fibre e trama (vedi papers.py);
    # i valori qui sotto sono quelli della carta da disegno
    paper_type=papers.DEFAULT, **papers.defaults(papers.DEFAULT),
    ink_color=(0.08, 0.08, 0.10), ink_tooth=0.0,
    # esposizione e luci non fanno parte dello stile: dipendono dalla scena
    gamma=1.0, ambient=0.3,
    # strumento: prima il tipo, poi le punte (l'ordine delle voci conta)
    tool_type="FREE", tool_tip="T035", pencil_grade="HB", sheet_format="A3",
    pen_profile="T050", pen_hidden="T025", pen_constr="T018",
    line_enable=True, use_line_color=False, line_thickness=1.6, line_opacity=1.0,
    profile_factor=1.8, crease_angle=math.radians(140), split_angle=math.radians(165),
    line_intersections=True, all_edges=False, depth_thin=0.0, depth_fade=0.0,
    # punto di partenza da disegno tecnico: gli stili artistici li alzano
    overshoot=0.01, overshoot_random=0.5,
    multi_strokes=1, multi_distance=2.5, tremor=0.12, tremor_scale=0.12,
    tremor_thickness=0.4, line_smooth=0.15, boil=False, boil_step=3,
    line_color=(0.08, 0.08, 0.10),
    constr_enable=True, constr_length=0.6, constr_opacity=0.25, constr_thickness=0.4,
    hidden_enable=False, hidden_dash=12.0, hidden_gap=7.0, hidden_opacity=1.0, hidden_thickness=0.9,
    hidden_levels=1,
    hatch_enable=True, hatch_style="CROSS", hatch_shape=0.5, hatch_cross=math.radians(90),
    hatch_follow=False,
    hatch_strength=1.0, hatch_layers=2, hatch_density=300.0,
    hatch_angle=math.radians(45), hatch_weight=0.5, hatch_start=0.25,
    hatch_wobble=0.15, hatch_wobble_scale=25.0, hatch_breaks=0.3, hatch_break_scale=6.0,
    hatch_use_tip=False, hatch_tip="T018", hatch_negative=False,
    tone_enable=False, tone_pattern="DOTS", tone_mode="TONE",
    tone_strength=1.0, tone_density=70.0, tone_angle=math.radians(45),
    tone_size=0.72, tone_start=0.15,
    highlight_enable=False, highlight_color=(1.0, 1.0, 1.0), highlight_strength=0.8,
    highlight_threshold=0.75, highlight_soft=0.3,
    objcolor_enable=False, objcolor_strength=0.85, objcolor_default=(0.8, 0.8, 0.8),
    wash_use_object=False,
    stipple_enable=False, stipple_strength=1.0, stipple_density=160.0, stipple_size=0.28,
    stipple_start=0.05,
    shadow_enable=True, shadow_strength=0.3, shadow_threshold=0.6, shadow_soft=0.0,
    wash_enable=False, wash_strength=0.6, wash_color=(0.45, 0.55, 0.70),
    wash_threshold=0.3, wash_irregularity=0.35, wash_scale=3.0, wash_edge=0.35,
)

# Ogni preset parte da BASE, poi dalla carta indicata in paper_type, e infine
# sovrascrive solo ciò che elenca.
# Pennini tipici delle tavole tecniche (penna tecnica ISO)
_ISO_SET = dict(tool_type="TECH_PEN", tool_tip="T035", pen_profile="T050",
                pen_hidden="T025", pen_constr="T018")

PRESETS = {
    "ARCH_SKETCH": dict(overshoot=0.06, tremor=0.4, tremor_scale=0.3),
    "TECH_PEN": dict(
        _ISO_SET, paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0,
        multi_strokes=0, tremor_thickness=0.0, line_smooth=0.0, constr_enable=False,
        hatch_style="PARALLEL", hatch_layers=2, hatch_density=320.0, hatch_weight=0.36,
        hatch_use_tip=True, hatch_tip="T018",
        hatch_wobble=0.0, hatch_breaks=0.0, hatch_start=0.3, shadow_enable=False, profile_factor=2.2,
    ),
    "PENCIL": dict(
        paper_type="SKETCH", ink_color=(0.12, 0.12, 0.135), ink_tooth=0.45, ambient=0.2,
        tool_type="PENCIL", pencil_grade="2B",
        line_opacity=0.85, line_thickness=1.4, multi_strokes=2, multi_distance=3.5,
        tremor=0.9, tremor_scale=0.3, tremor_thickness=0.7, overshoot=0.12, constr_opacity=0.18,
        hatch_layers=3, hatch_density=340.0, hatch_weight=0.45, hatch_wobble=0.3,
        hatch_wobble_scale=40.0, hatch_breaks=0.45, hatch_break_scale=10.0, hatch_strength=0.9,
        shadow_strength=0.5, shadow_soft=0.8,
    ),
    "STIPPLE": dict(
        paper_type="SMOOTH", multi_strokes=0, tremor=0.15,
        constr_enable=False, hatch_enable=False, stipple_enable=True, shadow_enable=False,
        line_thickness=1.2, profile_factor=2.0,
    ),
    "SCREENTONE": dict(
        paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0, ink_color=(0.02, 0.02, 0.02),
        overshoot=0.02, multi_strokes=0, tremor=0.1, constr_enable=False,
        line_thickness=2.4, profile_factor=2.5,
        hatch_enable=False, tone_enable=True, shadow_strength=1.0, shadow_threshold=0.6,
    ),
    "WATERCOLOR": dict(
        paper_type="WC_COLD", ink_color=(0.18, 0.16, 0.15),
        line_thickness=1.2, overshoot=0.15, multi_strokes=1, tremor=0.8, tremor_scale=0.3,
        hatch_enable=False, shadow_enable=False,
        wash_enable=True, wash_strength=0.7, wash_threshold=0.2,
        wash_color=(0.42, 0.55, 0.72), constr_opacity=0.15,
    ),
    "BLUEPRINT": dict(
        paper_type="SMOOTH", paper_color=(0.06, 0.22, 0.48), paper_grain=0.08, paper_fibers=0.1,
        ink_color=(0.92, 0.95, 1.0), **_ISO_SET,
        multi_strokes=0, tremor_thickness=0.1,
        constr_opacity=0.35, hatch_style="PARALLEL", hatch_layers=1, hatch_weight=0.3,
        hatch_strength=0.6, hatch_wobble=0.0, hatch_breaks=0.0, shadow_enable=False,
    ),
    "MARKER": dict(
        paper_type="SMOOTH", line_thickness=3.5,
        profile_factor=1.5, overshoot=0.05, multi_strokes=0, tremor=0.3, tremor_scale=0.25,
        tremor_thickness=0.15, constr_enable=False, hatch_enable=False,
        wash_enable=True, wash_color=(0.62, 0.62, 0.64), wash_strength=0.9,
        wash_threshold=0.25, wash_irregularity=0.1, wash_scale=8.0,
        shadow_enable=True, shadow_strength=0.55, shadow_threshold=0.6,
    ),
    # Lettura della geometria: tutti i bordi visibili a tratto pieno, quelli
    # nascosti a trattini, peso della linea che cala con la distanza.
    "STRUCTURE": dict(
        paper_type="SMOOTH", paper_color=(0.985, 0.985, 0.98), paper_grain=0.0,
        ink_color=(0.05, 0.07, 0.12), **_ISO_SET,
        line_thickness=1.9, profile_factor=1.8, all_edges=True,
        depth_thin=0.5, depth_fade=0.35,
        multi_strokes=0, tremor_thickness=0.0, line_smooth=0.0,
        constr_enable=False, hidden_enable=True, hidden_levels=2, hidden_opacity=0.9,
        hidden_thickness=0.75, hatch_enable=False, shadow_enable=True, shadow_strength=0.12,
    ),
    # Leonardo, studi a penna (codici e fogli di Windsor):
    # - inchiostro ferrogallico, oggi bruno caldo, su carta fatta a mano ingiallita;
    # - tratteggio PARALLELO da mancino: linee diritte che scendono da sinistra in
    #   alto a destra in basso ("\\" = hatch_angle 45° nel nostro sistema), tutte
    #   nella stessa direzione qualunque sia la forma; il tono nasce dall'infittirsi
    #   delle linee, non dall'incrocio;
    # - contorno sottile a penna d'oca con pressione variabile, ripassato cercando
    #   la forma (pentimenti); linee geometriche di costruzione appena accennate;
    # - nelle ombre più fonde una lieve acquerellatura di inchiostro diluito.
    "LEONARDO": dict(
        paper_type="ANTIQUE", ink_color=(0.075, 0.03, 0.011), ambient=0.2,
        line_thickness=1.3, profile_factor=1.5, line_opacity=0.95,
        overshoot=0.03, overshoot_random=0.7,
        multi_strokes=2, multi_distance=2.2,
        tremor=0.35, tremor_scale=0.5, tremor_thickness=0.7, line_smooth=0.1,
        constr_enable=True, constr_length=0.3, constr_opacity=0.12, constr_thickness=0.35,
        hatch_enable=True, hatch_style="PARALLEL", hatch_follow=False, hatch_layers=3,
        hatch_density=300.0, hatch_angle=math.radians(45), hatch_weight=0.5, hatch_start=0.16,
        hatch_strength=0.95, hatch_wobble=0.2, hatch_wobble_scale=14.0,
        hatch_breaks=0.22, hatch_break_scale=7.0,
        shadow_enable=False,
        wash_enable=True, wash_strength=0.28, wash_color=(0.35, 0.195, 0.09),
        wash_threshold=0.5, wash_irregularity=0.4, wash_scale=4.0, wash_edge=0.2,
    ),
    # Michelangelo, studi di figura a sanguigna (studi per la Sistina):
    # - gessetto rosso su carta vergata chiara: il segno prende la grana della carta;
    # - contorni energici, ripassati più volte, più pesanti dei tratti interni;
    # - modellato "da scultore": tratteggio incrociato a tratti brevi che gira
    #   seguendo i volumi, come i colpi di gradina sul marmo;
    # - passaggi di tono fusi a sfumato nelle ombre.
    "MICHELANGELO": dict(
        paper_type="LAID", paper_color=(0.86, 0.80, 0.68), paper_pattern=0.07,
        ink_color=(0.30, 0.055, 0.02), ink_tooth=0.4, ambient=0.12, gamma=1.15,
        line_thickness=2.0, profile_factor=1.9, line_opacity=0.85,
        overshoot=0.02, overshoot_random=0.5,
        multi_strokes=2, multi_distance=3.0,
        tremor=0.6, tremor_scale=0.4, tremor_thickness=0.8, line_smooth=0.2,
        constr_enable=False,
        hatch_enable=True, hatch_style="CROSS", hatch_cross=math.radians(50), hatch_follow=True,
        hatch_layers=3,
        hatch_density=300.0, hatch_angle=math.radians(35), hatch_weight=0.62, hatch_start=0.12,
        hatch_strength=0.95, hatch_wobble=0.3, hatch_wobble_scale=28.0,
        hatch_breaks=0.4, hatch_break_scale=8.0,
        shadow_enable=True, shadow_strength=0.6, shadow_threshold=0.68, shadow_soft=0.8,
        wash_enable=False,
    ),
    # Piranesi, acqueforti (Carceri d'invenzione, Vedute di Roma):
    # - inchiostro calcografico nero caldo su carta vergata avorio;
    # - linee incise: tratto controllato, senza tremolio della mano né ripassi;
    # - modellato a tratteggio incrociato fittissimo, a losanghe (incrocio
    #   stretto), che segue i piani; fino a quattro passate nelle ombre;
    # - chiaroscuro teatrale: neri profondi accanto a luci piene;
    # - prospettiva aerea: in lontananza le linee si fanno più sottili e chiare.
    "PIRANESI": dict(
        paper_type="LAID", paper_color=(0.89, 0.85, 0.75), paper_pattern=0.05,
        ink_color=(0.035, 0.03, 0.028), ambient=0.08, gamma=1.6,
        line_thickness=1.5, profile_factor=2.2, line_opacity=1.0,
        overshoot=0.0, multi_strokes=0,
        tremor=0.12, tremor_scale=0.5, tremor_thickness=0.35, line_smooth=0.05,
        constr_enable=False,
        depth_thin=0.3, depth_fade=0.4,
        hatch_enable=True, hatch_style="CROSS", hatch_cross=math.radians(40), hatch_follow=True,
        hatch_layers=4, hatch_density=340.0, hatch_angle=math.radians(20),
        hatch_weight=0.62, hatch_start=0.08, hatch_strength=1.0,
        hatch_wobble=0.06, hatch_wobble_scale=12.0, hatch_breaks=0.12, hatch_break_scale=4.0,
        shadow_enable=True, shadow_strength=0.92, shadow_threshold=0.68, shadow_soft=0.35,
        wash_enable=False,
    ),
    # Design di arredo e prodotto: fineliner nero e pennarelli grigi su carta
    # bianca liscia. Silhouette marcata per staccare l'oggetto dal foglio,
    # linee guida lunghe e leggere, ombre a campiture piatte di marker con
    # l'accumulo di colore sul bordo della passata.
    "DESIGN_FURNITURE": dict(
        paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0,
        ink_color=(0.09, 0.09, 0.11),
        tool_type="FINELINER", tool_tip="T030", pen_profile="T080", pen_hidden="T020", pen_constr="T010",
        line_thickness=1.8, profile_factor=2.6, overshoot=0.18, overshoot_random=0.6,
        multi_strokes=1, multi_distance=2.0,
        tremor=0.2, tremor_scale=0.25, tremor_thickness=0.3, line_smooth=0.25,
        constr_enable=True, constr_length=0.9, constr_opacity=0.2, constr_thickness=0.35,
        hatch_enable=False,
        wash_enable=True, wash_color=(0.55, 0.56, 0.58), wash_strength=0.8,
        wash_threshold=0.15, wash_irregularity=0.12, wash_scale=6.0, wash_edge=0.5,
        shadow_enable=True, shadow_strength=0.5, shadow_threshold=0.42, shadow_soft=0.0,
    ),
    # Car design: profili pesanti e tesi, linee che sfuggono ben oltre gli
    # spigoli (il gesto veloce del designer), linee di costruzione lunghe,
    # tratteggio parallelo a tratti brevi e rapidi, marker grigio-freddi.
    "DESIGN_AUTO": dict(
        paper_type="SMOOTH", paper_color=(0.97, 0.97, 0.98), paper_grain=0.0,
        ink_color=(0.04, 0.04, 0.06), gamma=1.1,
        tool_type="FINELINER", tool_tip="T040", pen_profile="T080", pen_hidden="T020", pen_constr="T010",
        line_thickness=2.0, profile_factor=3.0, overshoot=0.22, overshoot_random=0.4,
        multi_strokes=1, multi_distance=1.6,
        tremor=0.08, tremor_scale=0.2, tremor_thickness=0.25, line_smooth=0.35,
        constr_enable=True, constr_length=1.0, constr_opacity=0.22, constr_thickness=0.3,
        depth_thin=0.3,
        hatch_enable=True, hatch_style="PARALLEL", hatch_layers=2, hatch_density=140.0,
        hatch_angle=math.radians(30), hatch_weight=0.6, hatch_start=0.45, hatch_strength=0.7,
        hatch_wobble=0.05, hatch_breaks=0.5, hatch_break_scale=3.0,
        wash_enable=True, wash_color=(0.40, 0.43, 0.48), wash_strength=0.9,
        wash_threshold=0.2, wash_irregularity=0.08, wash_scale=10.0, wash_edge=0.3,
        shadow_enable=True, shadow_strength=0.65, shadow_threshold=0.35, shadow_soft=0.0,
    ),
    # Figurino di moda: linea sottile ed elegante con forte variazione di
    # pressione, poche linee ma sicure, colore ad acquerello steso a macchie
    # larghe e libere, nessun tratteggio.
    "DESIGN_FASHION": dict(
        paper_type="WC_HOT", ink_color=(0.12, 0.10, 0.10),
        tool_type="FINELINER", tool_tip="T010", pen_profile="T030", pen_hidden="T010", pen_constr="T005",
        line_thickness=1.3, profile_factor=2.4, overshoot=0.1, overshoot_random=0.6,
        multi_strokes=0, tremor=0.4, tremor_scale=0.25, tremor_thickness=0.9, line_smooth=0.3,
        constr_enable=False,
        hatch_enable=False, shadow_enable=False,
        wash_enable=True, wash_color=(0.70, 0.35, 0.40), wash_strength=0.7,
        wash_threshold=0.18, wash_irregularity=0.45, wash_scale=2.5, wash_edge=0.45,
    ),

    # ----------------------------------------------------------------- tecnici
    # Disegno da brevetto: china nera su bianco, nessuna campitura; superfici
    # piane a tratteggio parallelo, curve rese a puntini.
    "PATENT": dict(
        _ISO_SET, tool_tip="T025", pen_hidden="T018", pen_constr="T013",
        paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0,
        ink_color=(0.01, 0.01, 0.01), multi_strokes=0, tremor_thickness=0.0, line_smooth=0.0,
        constr_enable=False, shadow_enable=False,
        hatch_enable=True, hatch_style="PARALLEL", hatch_layers=2, hatch_density=220.0,
        hatch_angle=math.radians(45), hatch_start=0.3, hatch_strength=1.0,
        hatch_wobble=0.0, hatch_breaks=0.0, hatch_use_tip=True, hatch_tip="T018",
        stipple_enable=True, stipple_density=200.0, stipple_size=0.22, stipple_start=0.15,
        stipple_strength=0.8,
    ),
    # Lavagna: gesso bianco su ardesia verde. Il gesso va dove c'è luce: niente
    # tratteggio scuro, solo linee e lumeggiature che prendono la grana.
    "CHALKBOARD": dict(
        paper_type="SMOOTH", paper_color=(0.035, 0.075, 0.055), paper_grain=0.12, paper_fibers=0.08,
        ink_color=(0.92, 0.92, 0.88), ink_tooth=0.6,
        line_thickness=2.2, profile_factor=1.6, line_opacity=0.9,
        overshoot=0.05, tremor=0.3, tremor_scale=0.3, tremor_thickness=0.5, multi_strokes=1,
        constr_enable=True, constr_opacity=0.2,
        hatch_enable=False, shadow_enable=False,
        highlight_enable=True, highlight_color=(0.9, 0.9, 0.86), highlight_strength=0.55,
        highlight_threshold=0.68, highlight_soft=0.4,
    ),

    # --------------------------------------------------------------- artistici
    "CHARCOAL": dict(
        paper_type="SKETCH", ink_color=(0.03, 0.03, 0.035), ink_tooth=0.7, gamma=1.2,
        line_thickness=3.0, profile_factor=1.6, line_opacity=0.9,
        overshoot=0.1, multi_strokes=2, multi_distance=3.5,
        tremor=0.8, tremor_scale=0.3, tremor_thickness=0.8, line_smooth=0.2,
        constr_enable=True, constr_opacity=0.15,
        hatch_enable=True, hatch_style="CROSS", hatch_layers=2, hatch_density=140.0,
        hatch_weight=0.7, hatch_start=0.25, hatch_strength=0.9, hatch_wobble=0.4,
        hatch_breaks=0.5, hatch_break_scale=8.0,
        shadow_enable=True, shadow_strength=0.85, shadow_threshold=0.5, shadow_soft=0.9,
    ),
    "INK_WASH": dict(
        paper_type="WASHI", ink_color=(0.02, 0.02, 0.025),
        line_thickness=1.6, profile_factor=2.4, overshoot=0.04, multi_strokes=0,
        tremor=0.5, tremor_scale=0.25, tremor_thickness=0.9, line_smooth=0.3,
        constr_enable=False, hatch_enable=False, shadow_enable=False,
        wash_enable=True, wash_color=(0.18, 0.18, 0.2), wash_strength=0.75, wash_threshold=0.25,
        wash_irregularity=0.7, wash_scale=2.0, wash_edge=0.6,
    ),
    # Linea chiara: tratto uniforme (stessa punta per tutto), colori piatti
    # presi dagli oggetti, ombra netta appena accennata.
    "LIGNE_CLAIRE": dict(
        paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0,
        ink_color=(0.02, 0.02, 0.02),
        tool_type="FINELINER", tool_tip="T040", pen_profile="T040", pen_hidden="T020", pen_constr="T010",
        multi_strokes=0, tremor=0.05, tremor_thickness=0.0, line_smooth=0.4,
        constr_enable=False, hatch_enable=False, wash_enable=False,
        objcolor_enable=True, objcolor_strength=0.9,
        shadow_enable=True, shadow_strength=0.18, shadow_threshold=0.35, shadow_soft=0.0,
    ),
    "URBAN": dict(
        paper_type="WC_COLD", ink_color=(0.06, 0.06, 0.07),
        tool_type="FINELINER", tool_tip="T030", pen_profile="T050", pen_hidden="T020", pen_constr="T010",
        overshoot=0.12, overshoot_random=0.6, multi_strokes=1, multi_distance=2.0,
        tremor=0.45, tremor_scale=0.3, tremor_thickness=0.5,
        constr_enable=True, constr_length=0.6, constr_opacity=0.18,
        hatch_enable=True, hatch_style="PARALLEL", hatch_layers=1, hatch_density=150.0,
        hatch_weight=0.45, hatch_start=0.5, hatch_strength=0.6, hatch_wobble=0.25, hatch_breaks=0.5,
        shadow_enable=False,
        wash_enable=True, wash_use_object=True, wash_strength=0.7, wash_threshold=0.12,
        wash_irregularity=0.55, wash_scale=2.5, wash_edge=0.4,
    ),
    # Tre matite: contorni a sanguigna, ombre a pietra nera, luci a gessetto
    # bianco, su carta tinta color nocciola.
    "TROIS_CRAYONS": dict(
        paper_type="LAID", paper_color=(0.52, 0.42, 0.30), paper_pattern=0.06,
        ink_color=(0.03, 0.025, 0.025), ink_tooth=0.55, ambient=0.15,
        use_line_color=True, line_color=(0.32, 0.06, 0.025),
        line_thickness=1.8, profile_factor=1.8, multi_strokes=2, multi_distance=2.5,
        tremor=0.5, tremor_scale=0.35, tremor_thickness=0.7, overshoot=0.04,
        constr_enable=False,
        hatch_enable=True, hatch_style="CROSS", hatch_follow=True, hatch_layers=2,
        hatch_density=260.0, hatch_weight=0.55, hatch_start=0.35, hatch_strength=0.85,
        hatch_wobble=0.25, hatch_breaks=0.35,
        shadow_enable=True, shadow_strength=0.4, shadow_threshold=0.35, shadow_soft=0.8,
        highlight_enable=True, highlight_color=(0.97, 0.95, 0.9), highlight_strength=0.85,
        highlight_threshold=0.62, highlight_soft=0.45,
    ),
    # Xilografia: il nero è il fondo, le luci sono linee scavate che seguono
    # i volumi e si allargano verso la luce piena.
    "WOODCUT": dict(
        paper_type="SMOOTH", paper_color=(0.94, 0.91, 0.84), paper_grain=0.04,
        ink_color=(0.02, 0.02, 0.02), gamma=1.2,
        line_thickness=3.0, profile_factor=1.5, overshoot=0.0, multi_strokes=0,
        tremor=0.25, tremor_scale=0.2, tremor_thickness=0.5, line_smooth=0.3,
        constr_enable=False, shadow_enable=False,
        hatch_enable=True, hatch_negative=True, hatch_style="PARALLEL", hatch_follow=True,
        hatch_layers=2, hatch_density=110.0, hatch_weight=0.85, hatch_start=0.45,
        hatch_strength=1.0, hatch_wobble=0.12, hatch_breaks=0.0,
    ),

    # ------------------------------------------------------------------ design
    "WHITE_MODEL": dict(
        paper_type="SMOOTH", paper_color=(0.97, 0.97, 0.96), paper_grain=0.0,
        ink_color=(0.16, 0.16, 0.18), gamma=1.3,
        tool_type="TECH_PEN", tool_tip="T025", pen_profile="T050", pen_hidden="T018", pen_constr="T013",
        line_opacity=0.85, overshoot=0.0, tremor=0.0, tremor_thickness=0.0, multi_strokes=0,
        line_smooth=0.0, constr_enable=False, hatch_enable=False,
        shadow_enable=True, shadow_strength=0.35, shadow_threshold=0.8, shadow_soft=0.9,
    ),
    "INTERIOR": dict(
        paper_type="SMOOTH", paper_color=(1.0, 1.0, 1.0), paper_grain=0.0,
        ink_color=(0.08, 0.07, 0.07),
        tool_type="FINELINER", tool_tip="T030", pen_profile="T050", pen_hidden="T020", pen_constr="T010",
        overshoot=0.1, tremor=0.25, tremor_scale=0.25, multi_strokes=1,
        constr_enable=True, constr_length=0.6, constr_opacity=0.15,
        hatch_enable=False,
        objcolor_default=(0.85, 0.75, 0.62),
        wash_enable=True, wash_use_object=True, wash_strength=0.8, wash_threshold=0.12,
        wash_irregularity=0.12, wash_scale=7.0, wash_edge=0.5,
        shadow_enable=True, shadow_strength=0.4, shadow_threshold=0.3, shadow_soft=0.0,
    ),

    # --------------------------------------------------------------------- VIP
    # Dürer, incisioni a bulino: linee finissime e controllate che avvolgono le
    # forme, incrocio nelle ombre, puntini nei passaggi verso la luce.
    "DURER": dict(
        paper_type="LAID", paper_color=(0.92, 0.89, 0.80), paper_pattern=0.04,
        ink_color=(0.03, 0.03, 0.03), gamma=1.3, depth_fade=0.2,
        line_thickness=1.3, profile_factor=1.8, overshoot=0.0, multi_strokes=0,
        tremor=0.06, tremor_scale=0.4, tremor_thickness=0.3,
        constr_enable=False, shadow_enable=False,
        hatch_enable=True, hatch_style="CROSS", hatch_cross=math.radians(70), hatch_follow=True,
        hatch_layers=4, hatch_density=420.0, hatch_angle=math.radians(30), hatch_weight=0.5,
        hatch_start=0.12, hatch_strength=1.0, hatch_wobble=0.03, hatch_breaks=0.05, hatch_break_scale=3.0,
        stipple_enable=True, stipple_density=380.0, stipple_size=0.15, stipple_start=0.05,
        stipple_strength=0.6,
    ),
    # Rembrandt, disegni a penna: tratto bruno rapido e spezzato, velature
    # dense di inchiostro diluito, chiaroscuro profondo.
    "REMBRANDT": dict(
        paper_type="SKETCH", paper_color=(0.90, 0.85, 0.74),
        ink_color=(0.12, 0.07, 0.035), gamma=1.3, ambient=0.12,
        line_thickness=2.0, profile_factor=2.2, overshoot=0.06, multi_strokes=1,
        tremor=0.7, tremor_scale=0.3, tremor_thickness=0.9,
        constr_enable=False,
        hatch_enable=True, hatch_style="PARALLEL", hatch_layers=2, hatch_density=160.0,
        hatch_angle=math.radians(60), hatch_weight=0.55, hatch_start=0.4, hatch_strength=0.8,
        hatch_wobble=0.35, hatch_breaks=0.45,
        wash_enable=True, wash_color=(0.36, 0.22, 0.11), wash_strength=0.85, wash_threshold=0.35,
        wash_irregularity=0.5, wash_scale=3.0, wash_edge=0.5,
        shadow_enable=True, shadow_strength=0.55, shadow_threshold=0.25, shadow_soft=0.6,
    ),
    # Canaletto, vedute a penna: linee nitide tirate col righello, guide
    # prospettiche appena visibili, acquerello grigio-azzurro, lontananze chiare.
    "CANALETTO": dict(
        paper_type="DRAWING", paper_color=(0.94, 0.92, 0.86),
        ink_color=(0.07, 0.065, 0.06), depth_fade=0.3,
        line_thickness=1.3, profile_factor=1.8, overshoot=0.02, multi_strokes=0,
        tremor=0.15, tremor_scale=0.2,
        constr_enable=True, constr_length=0.4, constr_opacity=0.12,
        hatch_enable=True, hatch_style="PARALLEL", hatch_layers=1, hatch_density=200.0,
        hatch_weight=0.4, hatch_start=0.45, hatch_strength=0.6, hatch_breaks=0.2,
        wash_enable=True, wash_color=(0.42, 0.47, 0.52), wash_strength=0.6, wash_threshold=0.25,
        wash_irregularity=0.25, wash_scale=4.0, wash_edge=0.35,
        shadow_enable=False,
    ),
    # Hokusai, silografia policroma: contorni netti indaco, campiture piatte
    # di colore (blu di Prussia per ciò che non ha un colore proprio).
    "HOKUSAI": dict(
        paper_type="WASHI", paper_color=(0.93, 0.89, 0.79), paper_fibers=0.25,
        ink_color=(0.05, 0.06, 0.10),
        line_thickness=1.8, profile_factor=1.6, overshoot=0.0, multi_strokes=0,
        tremor=0.15, tremor_scale=0.2, tremor_thickness=0.5, line_smooth=0.3,
        constr_enable=False, hatch_enable=False, wash_enable=False,
        objcolor_enable=True, objcolor_strength=0.75, objcolor_default=(0.35, 0.48, 0.62),
        shadow_enable=True, shadow_strength=0.25, shadow_threshold=0.35, shadow_soft=0.0,
    ),
}

# ---------------------------------------------------------------------------
# preset utente
# ---------------------------------------------------------------------------
_user_dir = None
_listing = {"stamp": None, "checked": 0.0, "items": []}  # cache dell'elenco preset utente


def user_dir():
    global _user_dir
    if _user_dir is None or not os.path.isdir(_user_dir):
        import bpy
        try:
            _user_dir = bpy.utils.extension_path_user(__package__, path="presets", create=True)
        except Exception:
            # add-on caricato fuori dal sistema delle estensioni
            _user_dir = bpy.utils.user_resource("CONFIG", path="matita/presets", create=True)
    return _user_dir


def _invalidate():
    _listing["stamp"] = None


def _filename(name):
    """Percorso libero per un nuovo preset (nomi diversi non si sovrascrivono mai)."""
    safe = re.sub(r"[^\w\-. ]", "_", name).strip() or "preset"
    path = os.path.join(user_dir(), safe + ".json")
    i = 2
    while os.path.exists(path):
        path = os.path.join(user_dir(), f"{safe}_{i}.json")
        i += 1
    return path


def list_user():
    """[(nome, percorso)] ordinati per nome.

    L'enum dei preset viene valutato a ogni ridisegno dell'interfaccia: la
    cartella viene riletta solo quando cambia (data di modifica), non ogni volta.
    """
    now = time.monotonic()
    if _listing["stamp"] is not None and now - _listing["checked"] < 2.0:
        return _listing["items"]     # il disco viene interrogato al massimo ogni 2 secondi
    _listing["checked"] = now
    d = user_dir()
    try:
        stamp = os.stat(d).st_mtime_ns
    except OSError:
        return []
    if stamp == _listing["stamp"]:
        return _listing["items"]
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as f:
                name = json.load(f).get("name") or fn[:-5]
        except (OSError, ValueError, AttributeError):
            continue
        out.append((str(name), path))
    out.sort(key=lambda x: x[0].lower())
    _listing["stamp"] = stamp
    _listing["items"] = out
    return out


def refresh_user():
    """Rilegge la cartella (dopo aver copiato o modificato file a mano)."""
    _invalidate()
    return list_user()


def user_exists(name):
    return any(n == name for n, _ in list_user())


FILE_VERSION = 2


def _legacy_values(stored):
    """Valori per le voci che un preset salvato con una versione vecchia non ha.

    Senza questo le voci mancanti prenderebbero i valori di base di oggi e il
    preset cambierebbe aspetto: per esempio comparirebbero fibre nella carta o
    il bordo scuro nell'acquerello, che quando è stato salvato non esistevano.
    """
    grain = float(stored.get("paper_grain", 0.0) or 0.0)
    legacy = {
        "paper_type": papers.DEFAULT, "paper_grain_scale": 750.0,
        # la vecchia "grana" comprendeva anche le nuvolature dell'impasto
        "paper_fibers": min(grain * 0.5, 1.0),
        "paper_pattern": 0.0, "paper_pattern_scale": 1.0, "ink_tooth": 0.0,
        "hatch_style": "CROSS", "hatch_shape": 0.5, "hatch_cross": math.radians(90),
        "hatch_follow": False, "shadow_soft": 0.0, "wash_edge": 0.0,
        "all_edges": False, "depth_thin": 0.0, "depth_fade": 0.0,
        "hidden_enable": False, "hidden_levels": 1,
    }
    return {k: v for k, v in legacy.items() if k not in stored}


def load_user(name):
    """Valori di un preset utente, completati per i file di versioni precedenti.
    None se il file non esiste o non è leggibile."""
    for n, path in list_user():
        if n == name:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                stored = data.get("values", {})
                if not isinstance(stored, dict):
                    raise ValueError("'values' non è un dizionario")
            except (OSError, ValueError, AttributeError) as ex:
                print(f"Matita: preset '{name}' non leggibile: {ex}")
                return None
            if int(data.get("version", 1) or 1) < FILE_VERSION:
                stored = dict(_legacy_values(stored), **stored)
            return stored
    return None


def save_user(scene, name):
    from . import core
    s = core.settings(scene)
    values = {}
    for k in BASE:
        v = getattr(s, k)
        values[k] = list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v
    data = {"name": name, "version": FILE_VERSION, "values": values}
    # se esiste già un preset con lo stesso nome, sovrascrive quel file
    path = next((p for n, p in list_user() if n == name), None) or _filename(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _invalidate()
    return path


def delete_user(name):
    for n, path in list(list_user()):
        if n == name:
            os.remove(path)
    _invalidate()


# ---------------------------------------------------------------------------
# enum dinamico (built-in + utente)
# ---------------------------------------------------------------------------
# Blender richiede che le stringhe dell'enum restino referenziate: la lista
# viene ricostruita solo quando cambia l'elenco dei preset utente.
_enum = {"source": None, "items": []}


def enum_items(self, context):
    try:
        users = list_user()
    except OSError:
        users = []
    if _enum["source"] is not users:
        # un identificatore vuoto è un titolo: Blender apre una colonna del menu
        items = []
        for k, (cat, title, icon) in enumerate(CATEGORIES):
            items.append(("", title, "", icon, _HEADING_BASE + k))
            items += [(ident, label, desc, "", num)
                      for ident, label, desc, c, num in STYLES if c == cat]
        if users:
            items.append(("", "Personali", "", "USER", _HEADING_BASE + len(CATEGORIES)))
        for name, _ in users:
            # numero stabile derivato dal nome: l'indice salvato nel .blend non
            # cambia quando si aggiungono/rimuovono altri preset
            num = 1000 + zlib.crc32(name.encode("utf-8")) % 1_000_000_000
            items.append((USER_PREFIX + name, name, "Preset utente", "USER", num))
        _enum["source"] = users
        _enum["items"] = items
    return _enum["items"]


def apply(scene, key):
    from . import core
    s = scene.sketch_render
    values = dict(BASE)
    if key.startswith(USER_PREFIX):
        stored = load_user(key[len(USER_PREFIX):])
        if stored is None:
            print(f"Matita: preset '{key[len(USER_PREFIX):]}' non trovato")
            return False
        values.update({k: v for k, v in stored.items() if k in BASE})
    else:
        preset = PRESETS.get(key, {})
        # prima la carta dello stile, poi ciò che lo stile cambia rispetto ad essa
        values.update(papers.defaults(preset.get("paper_type", BASE["paper_type"])))
        values.update(preset)
    p = core.settings(scene)
    core._suspend = True
    try:
        s.preset = key
        for k, v in values.items():
            try:
                setattr(p, k, v)
            except (TypeError, ValueError):
                pass  # valore non valido in un JSON modificato a mano
    finally:
        core._suspend = False
    if s.is_setup and (p.objcolor_enable or p.wash_use_object):
        core.fill_object_colors(scene, only_missing=True)
    core.sync(scene)
    if s.is_setup and s.lines_frozen:
        # le linee congelate sono tratti fissi: vanno ricalcolate con il nuovo stile
        core.refreeze_later(scene)
    core.redraw_views()
    return True
