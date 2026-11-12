# -*- coding: utf-8 -*-
"""ShortPilot — synthèse musicale procédurale (aucun asset externe, 100% libre de droits).

Le choix « 🧠 Auto » ne se contente plus de la niche : `analyze_mood` écoute le script
(petits lexiques d'ambiance FR/EN + rythme !/?) et `explain_auto` combine ces signaux
avec la niche pour choisir l'ambiance — avec une raison lisible dans le journal.
"""
import os
import re
import unicodedata
import wave
import hashlib

import numpy as np

SR = 44100

PRESETS = {
    "energie": {"label": "🔥 Énergie", "bpm": 122, "chords": [[57, 60, 64], [53, 57, 60], [55, 59, 62], [52, 55, 59]],
                "style": "drive", "drums": True},
    "chill": {"label": "🌙 Chill / Lo-fi", "bpm": 78, "chords": [[57, 60, 64, 71], [53, 57, 60, 67], [55, 59, 62, 69], [52, 55, 59, 66]],
              "style": "pad", "drums": True},
    "drama": {"label": "🎬 Dramatique", "bpm": 64, "chords": [[50, 53, 57], [46, 50, 53], [48, 52, 55], [45, 48, 52]],
              "style": "pad", "drums": False},
    "happy": {"label": "☀️ Joyeux", "bpm": 112, "chords": [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]],
              "style": "pluck", "drums": True},
    "epique": {"label": "🎖️ Cinéma épique", "bpm": 88, "chords": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]],
               "style": "pad", "drums": True},
    "mystere": {"label": "🌫️ Suspense / Mystère", "bpm": 62, "chords": [[50, 53, 57], [46, 49, 53], [43, 46, 50], [45, 48, 52]],
                "style": "pad", "drums": False},
    "triste": {"label": "🌧️ Émotion / Piano", "bpm": 66, "chords": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [52, 55, 59]],
               "style": "pluck", "drums": False},
    "techno": {"label": "🛸 Techno / Futur", "bpm": 132, "chords": [[57, 60, 64], [57, 60, 64], [53, 57, 60], [55, 59, 62]],
               "style": "drive", "drums": True},
    "zen": {"label": "🍃 Zen / Ambiance", "bpm": 52, "chords": [[48, 52, 55, 59], [53, 57, 60, 64], [55, 59, 62, 64], [57, 60, 64, 67]],
            "style": "pad", "drums": False},
    "none": {"label": "🔇 Aucune", "bpm": 0, "chords": [], "style": "none", "drums": False},
}

# Niche du script → ambiance musicale automatique (choix « 🧠 Auto »)
NICHE_MUSIC = {
    "motivation": "epique",
    "faits": "happy",
    "psychologie": "mystere",
    "argent": "techno",
    "productivite": "energie",
    "sante": "zen",
    "tech": "techno",
    "histoire": "epique",
    "actu": "drama", "jour": "epique", "science": "techno", "mythes": "mystere",
    # Sujet libre is intentionally not pinned to chill: its actual subject
    # determines the soundtrack below.
    "sujet": None,
}

# Concrete subject has priority over the generic "sujet libre" category.  This
# is the main defence against every Wikipedia short becoming lo-fi at 78 BPM.
_SUBJECT_MOOD = (
    (("formule", "formula", "grand prix", "f1", "course", "rally", "avion", "pilot", "jet", "sport", "match"), "energie", "action / vitesse"),
    (("tokyo", "japon", "japan", "ramen", "sushi", "23 heures", "minuit"), "mystere", "documentaire nocturne"),
    (("pyramide", "egypte", "pharaon", "dynastie", "empire", "rome", "viking", "guerre", "bataille", "antique", "medieval"), "epique", "histoire / grandeur"),
    (("maya", "archeolog", "mystere", "secret", "dispar", "eclipse", "ombre", "enquete"), "mystere", "mystere / exploration"),
    (("nasa", "espace", "galaxie", "astronaute", "fusee", "mission spatiale", "lancement"), "epique", "exploration spatiale"),
    (("robot", "ia", "intelligence artificielle", "technologie"), "techno", "technologie / futur"),
    (("sante", "sommeil", "meditation", "respiration", "nature", "bien etre"), "zen", "calme / bien-etre"),
    (("musique", "art", "cinema", "voyage", "cuisine", "animal", "chat", "chien"), "happy", "decouverte / legerete"),
)

# ---- Analyse du ton du script (mode « 🧠 Auto ») -------------------------------
# Familles de mots FR + EN (déjà sans accents) caractéristiques d'une ambiance.
_LEX = {
    "sombre": """peur peurs angoisse angoisses danger dangers mort morts meurtre meurtres
        manipulation manipulé manipuler mensonge mensonges piège pièges secret secrets
        caché cachée cachent cachons obscur obscurité ombre ombres menace menaces
        cauchemar cauchemars toxique toxiques contrôle surveillance paranoïa paranoia
        mystère mystères inquiétant inquiétante obsession illusions illusion
        fear fears threat dark death murder dead secret secrets hidden lie lies
        trap manipulation nightmare nightmares anxiety anxious control toxic shadow
        shadows mystery mysterious unknown hidden danger dangerous""",
    "triste": """triste tristesse larme larmes pleure pleurer chagrin deuil perdu perdue
        rupture divorce abandon abandonné abandonnée mélancolie regret regrets
        déception déceptions échec échecs souffrance souffre souffrent seul seule
        nostalgie nostalgique vide manque
        sad sadness tears cry crying grief loss lost lonely loneliness heartbreak
        regret failure failures suffering suffering alone empty miss missing""",
    "victoire": """réussite réussir succès victoire victoires gagne gagner gagnant gagnants
        champion champions championne incroyable incroyables puissant puissante
        puissants discipline motivation ambition ambitions progrès progresser
        meilleur meilleure meilleurs exploits exploit dépassement
        win winner winners victory victories success successful amazing incredible
        powerful champion champions goal goals achieve achievement unstoppable
        stronger strong greatness grind hustle""",
    "epic": """guerre guerres empire empires roi rois reine reines château châteaux
        bataille batailles conquête conquérir conquérant légende légendes héros
        gladiateur gladiateurs viking vikings médiéval médiévale antique antiquité
        napoléon césar armée armées trône révolution civilisation civilisations
        siècles millénaire millénaires dynastie emblématique épique
        war wars empire empires king kings queen queens castle castles battle battles
        conquest conquer legend legends hero heroes army armies throne revolution
        ancient medieval rome roman vikings dynasty epic legendary centuries""",
    "tech": """technologie technologies robot robots algorithme algorithmes espace
        galaxie galaxies scientifique scientifiques donnée données internet
        écran écrans téléphone application applications numérique futur futuriste
        artificielle quantique nasa fusée fusées satellite satellites innovation
        innovations chimique physique laboratoire laboratoires molécule molécules
        technology technologies robot robots algorithm algorithms space universe
        galaxy galaxies science scientist scientists data internet screen screens
        digital future futuristic quantum computer computers satellite lab labs
        artificial neural innovation innovations""",
    "calme": """calme calmes respirer respiration sommeil dormir repos détente détendre
        méditation méditer méditez douceur sérénité équilibre silence paix paix
        lenteur ralentir souffle relaxation apaisant apaisante nature lent lente
        calm calmer breathe breathing sleep rest relax relaxation meditation
        meditate gentle serenity balance silence peace peaceful slow slowly
        mindfulness mindful soothing""",
    "fun": """drôle drôles insolite insolites bizarre bizarres étonnant étonnante
        amusant amusante surprenant surprenante improbable incroyable absurde
        étrange étranges curieux curieuse étonnantes surprenants fascinant
        funny weird strange amazing astonishing surprising fun crazy unbelievable
        bizarre odd curious fascinating incredible""",
}

# Famille → ambiances renforcées (+ poids par occurrence, plafonné)
_LEX_PRESETS = {
    "sombre": {"mystere": 2.0, "drama": 1.0},
    "triste": {"triste": 2.0, "drama": 1.0},
    "victoire": {"energie": 2.0, "epique": 1.0, "happy": 0.75},
    "epic": {"epique": 2.0, "drama": 0.5},
    "tech": {"techno": 2.0, "chill": 0.25},
    "calme": {"zen": 2.0, "chill": 0.5},
    "fun": {"happy": 2.0, "energie": 0.75},
}


def _norm(s):
    s = (s or "").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_LEX_SETS = {fam: {_norm(w) for w in words.split()} for fam, words in _LEX.items()}


def analyze_mood(text, lang="fr"):
    """Écoute le script. Retourne (scores_par_ambiance, mots_trouvés_par_famille)."""
    toks = [_norm(w) for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}", text or "")]
    hits = {}
    for fam, words in _LEX_SETS.items():
        h = {}
        for t in toks:
            base = t[:-1] if (t.endswith("s") and len(t) > 4 and t[:-1] in words) else t
            if base in words:
                h[base] = h.get(base, 0) + 1
        if h:
            hits[fam] = h
    scores = {}
    for fam, h in hits.items():
        # MOTS DISTINCTS (pas occurrences) : un mot répété dans tout l'article —
        # ex. « espace » dans « espace de travail » — ne signifie pas 3× plus d'ambiance.
        total = min(len(h), 4)  # plafond : 4 lexèmes distincts suffisent
        for pre, wgt in _LEX_PRESETS[fam].items():
            scores[pre] = scores.get(pre, 0.0) + wgt * total / 2.0
    # Rythme : « ! » denses → énergie ; « ? » denses → suspense
    nw = max(1, len(toks))
    if text.count("!") / nw * 100 >= 1.2:
        scores["energie"] = scores.get("energie", 0.0) + 1.0
    if text.count("?") / nw * 100 >= 1.0:
        scores["mystere"] = scores.get("mystere", 0.0) + 0.75
    return scores, hits


def _subject_direction(text):
    normalized = _norm(text)
    for terms, mood, label in _SUBJECT_MOOD:
        if any(re.search(r"\b" + re.escape(term) + (r"\b" if len(term) < 5 else ""), normalized)
               for term in terms):
            return mood, label
    return None, ""


def explain_auto(niche="", text="", lang="fr"):
    """(preset, raison lisible) : combine les signaux du script et la niche."""
    scores, hits = analyze_mood(text, lang)
    subject_mood, subject_reason = _subject_direction(text)
    base = NICHE_MUSIC.get(niche, "energie")
    if subject_mood:
        # Subject direction outranks a broad content bucket: Formula 1 must
        # not inherit a calm generic soundtrack merely because it is a topic.
        scores[subject_mood] = scores.get(subject_mood, 0.0) + 4.5
    elif base:
        scores[base] = scores.get(base, 0.0) + 2.5
    elif not scores:
        # Neutral free subjects still rotate rather than repeatedly falling
        # back to lo-fi.  The script text makes this choice reproducible.
        options = ("chill", "drama", "epique", "energie", "happy")
        base = options[sum(map(ord, _norm(text))) % len(options)]
        scores[base] = 1.0
    best = max(scores, key=lambda k: (scores[k], k == base))
    pts = []
    for fam, h in hits.items():
        for w, c in sorted(h.items(), key=lambda kv: (-kv[1], kv[0]))[:2]:
            pts.append(f"{w}×{c}" if c > 1 else w)
    reason = " ; ".join(pts[:3]) or "ton neutre"
    label = PRESETS.get(best, {}).get("label", best)
    direction = f" + direction sujet : {subject_reason}" if subject_reason else ""
    return best, f"{label} — signaux du script : {reason}{direction}"


def resolve_music(preset, niche="", text="", lang="fr"):
    """Traduit l'option « auto » en ambiance adaptée (script écouté + niche)."""
    if preset == "auto":
        return explain_auto(niche, text, lang)[0]
    return preset


def normalize_selection(value):
    if value in ("ace", "webauto"):
        return "instrumental"
    return value if value in ("instrumental", "auto", *PRESETS) else "instrumental"


def background_plan(selection, niche="", text="", lang="fr"):
    """Choose once: the returned plan is both logged and rendered unchanged."""
    selection = normalize_selection(selection)
    if selection == "none":
        return None
    automatic = selection in ("instrumental", "auto")
    preset = explain_auto(niche, text, lang)[0] if automatic else selection
    if automatic:
        mood, reason = detect_mood(text, preset)
    else:
        mood, reason = _LEGACY_MOOD[preset], "choix manuel"
    plan = score_plan(preset, text, mood=mood)
    plan["mood_reason"] = reason
    return plan


def instrumental_background(duration, preset="energie", path=None, *, text="", seed=None, scene_durations=None, plan=None):
    """Create the guaranteed no-vocals local background track.

    Unlike a generative audio model, this synth path has no lyric, voice or
    sample source at all.  It is the safe default for a narrated Short: the
    music follows the selected mood but can never compete with the voice-off.
    """
    if preset == "none":
        return synthesize(duration, preset, path)
    if plan is not None:
        return cinematic_background(duration, preset, path, text=text, seed=seed,
                                    scene_durations=scene_durations, plan=plan)
    if scene_durations is None:
        return cinematic_background(duration, preset, path, text=text, seed=seed)
    return cinematic_background(duration, preset, path, text=text, seed=seed, scene_durations=scene_durations)


# MUSIC_V3 : ambiance choisie d'apres le script, instrumentation et rythme propres a chaque ambiance.
_MODES = {
    "mineur": (0, 2, 3, 5, 7, 8, 10),
    "dorien": (0, 2, 3, 5, 7, 9, 10),
    "majeur": (0, 2, 4, 5, 7, 9, 11),
    "lydien": (0, 2, 4, 6, 7, 9, 11),
    "phrygien": (0, 1, 3, 5, 7, 8, 10),
}
# Progressions en degres de la gamme (0 = tonique) : l'harmonie suit le mode.
_DEGREE_PROGRESSIONS = (
    (0, 5, 3, 4), (0, 3, 5, 6), (0, 4, 5, 3), (5, 3, 0, 4),
    (0, 2, 5, 6), (0, 6, 5, 4), (3, 0, 4, 5), (0, 5, 2, 6),
)

# Vocabulaire par ambiance (mots complets ou debuts de mots >= 5 lettres, sans accents).
_MOOD_WORDS = {
    "epique": "guerre bataille armee soldat conquete empire victoire heros roi reine chevalier combat "
              "militaire siege revolte legion general napoleon cesar viking croisade royaume dynastie "
              "gladiateur spartiate samourai pirate legende epopee triomphe warrior battle army empire king",
    "tension": "catastrophe danger tempete volcan seisme tremblement virus pandemie accident peur "
               "dangereux explosion incendie naufrage crash menace attentat tsunami cyclone eruption "
               "epidemie famine massacre effondrement disaster fear threat",
    "mystere": "mystere secret disparition enigme inconnu enquete crime ombre fantome hante occulte "
               "complot conspiration assassin meurtre inexplique paranormal alien ovni piste suspect "
               "cache oublie interdit mystery secret unsolved haunted",
    "espace": "espace planete galaxie nasa etoile univers cosmos astronaute fusee orbite satellite "
              "lune soleil mars jupiter saturne nebuleuse telescope astronomie trou noir apollo "
              "interstellaire space planet galaxy star universe",
    "emotion": "amour perte deuil souvenir famille tristesse larme coeur mere pere enfant enfance "
               "nostalgie solitude adieu mort naissance espoir pardon amitie reconnaissance "
               "love loss memory family grief hope",
    "histoire": "histoire siecle antiquite moyen medieval civilisation revolution egypte rome grec "
                "pharaon pyramide cathedrale colonisation republique monarchie archeologie ancien "
                "prehistoire neolithique renaissance history ancient century",
    "techno": "technologie intelligence artificielle robot ordinateur futur internet numerique "
              "algorithme cyber puce processeur logiciel application smartphone drone donnees "
              "innovation startup tech technology digital computer future",
    "energie": "motivation succes argent sport travail objectif reussir performance discipline "
               "entrepreneur business productivite habitude victoire croissance champion entrainement "
               "ambition richesse success money goal winner habit",
    "joyeux": "fete joie humour drole amusant rire cadeau anniversaire vacances jeu insolite "
              "incroyable surprenant cuisine recette gourmand delicieux sourire fun funny party",
    "nature": "nature ocean mer foret animal oiseau montagne riviere climat ecologie jungle desert "
              "fleur arbre oceans baleine dauphin biodiversite environnement paysage "
              "forest river mountain wildlife animals",
    "zen": "calme meditation serenite philosophie bienetre sante sommeil respiration yoga relaxation "
           "equilibre sagesse stoicisme apaisement silence detente mindfulness wellness sleep peace",
}
_MOOD_SETS = {m: {_norm(w) for w in words.split()} for m, words in _MOOD_WORDS.items()}
_MOOD_ORDER = tuple(_MOOD_WORDS)
_LEGACY_MOOD = {"epique": "epique", "drama": "tension", "energie": "energie", "mystere": "mystere",
                "triste": "emotion", "zen": "zen", "chill": "nature", "happy": "joyeux", "techno": "techno"}
_NEUTRAL_MOODS = ("histoire", "nature", "joyeux", "emotion", "energie", "mystere")

# Un profil par ambiance : tempo, modes, dosage des instruments, rythme.
_PROFILES = {
    "epique":  dict(bpm=(84, 100), modes=("mineur", "dorien", "phrygien"), calm=False, pad=(.05, .065), organ=(.03, .07),
                    strings=(.08, .12), brass=(.06, .10), piano=(.07, .12), bell=(0, 0), bass=0., drums="taiko",
                    riser=True, bars=(2, 2), melody="piano", intensity=.9, density=.6, arp=1.),
    "tension": dict(bpm=(70, 88), modes=("phrygien", "mineur"), calm=True, pad=(.06, .08), organ=(.06, .10),
                    strings=(.05, .09), brass=(.03, .06), piano=(.04, .08), bell=(.03, .05), bass=0., drums="tick",
                    riser=True, bars=(2, 3), melody="piano", intensity=.8, density=.3, arp=1.),
    "mystere": dict(bpm=(54, 66), modes=("phrygien", "mineur", "dorien"), calm=True, pad=(.07, .09), organ=(.05, .10),
                    strings=(.03, .06), brass=(0, 0), piano=(.05, .09), bell=(.05, .08), bass=0., drums="tick_soft",
                    riser=False, bars=(3, 4), melody="bell", intensity=.55, density=.25, arp=1.),
    "espace":  dict(bpm=(58, 72), modes=("lydien", "dorien"), calm=True, pad=(.08, .10), organ=(.14, .24),
                    strings=(.03, .07), brass=(0, 0), piano=(.10, .18), bell=(.05, .09), bass=0., drums="none",
                    riser=False, bars=(3, 4), melody="piano", intensity=.6, density=.3, arp=1.),
    "emotion": dict(bpm=(58, 72), modes=("mineur", "dorien", "majeur"), calm=True, pad=(.05, .07), organ=(0, .04),
                    strings=(.08, .13), brass=(0, 0), piano=(.16, .24), bell=(0, .03), bass=0., drums="none",
                    riser=False, bars=(2, 4), melody="piano", intensity=.45, density=.4, arp=1.),
    "histoire": dict(bpm=(72, 88), modes=("dorien", "mineur"), calm=False, pad=(.05, .07), organ=(.03, .07),
                     strings=(.08, .12), brass=(.03, .06), piano=(.09, .15), bell=(0, 0), bass=0., drums="march",
                     riser=False, bars=(2, 2), melody="piano", intensity=.7, density=.5, arp=1.),
    "techno":  dict(bpm=(100, 120), modes=("dorien", "mineur"), calm=False, pad=(.04, .06), organ=(0, 0),
                    strings=(0, 0), brass=(0, 0), piano=(.04, .08), bell=(.06, .10), bass=.16, drums="techno",
                    riser=True, bars=(2, 2), melody="bell", intensity=.8, density=.7, arp=.25),
    "energie": dict(bpm=(100, 124), modes=("majeur", "dorien"), calm=False, pad=(.04, .06), organ=(0, .04),
                    strings=(.03, .06), brass=(.03, .06), piano=(.09, .15), bell=(.04, .07), bass=.15, drums="pop",
                    riser=True, bars=(2, 2), melody="piano", intensity=.85, density=.7, arp=.5),
    "joyeux":  dict(bpm=(100, 116), modes=("majeur", "lydien"), calm=False, pad=(.04, .06), organ=(0, 0),
                    strings=(.03, .05), brass=(0, 0), piano=(.10, .16), bell=(.06, .10), bass=.10, drums="pop_light",
                    riser=False, bars=(2, 2), melody="bell", intensity=.65, density=.7, arp=.5),
    "nature":  dict(bpm=(58, 72), modes=("lydien", "majeur", "dorien"), calm=True, pad=(.08, .10), organ=(0, .05),
                    strings=(.05, .09), brass=(0, 0), piano=(.08, .14), bell=(.04, .08), bass=0., drums="none",
                    riser=False, bars=(3, 4), melody="piano", intensity=.4, density=.35, arp=1.),
    "zen":     dict(bpm=(50, 62), modes=("lydien", "majeur"), calm=True, pad=(.09, .11), organ=(0, .05),
                    strings=(0, .04), brass=(0, 0), piano=(.04, .08), bell=(.04, .08), bass=0., drums="none",
                    riser=False, bars=(3, 4), melody="bell", intensity=.3, density=.25, arp=1.),
}


def detect_mood(text, preset="epique", rng=None):
    """Choisit l'ambiance d'apres TOUT le script. Retourne (ambiance, raison)."""
    tokens = {_norm(w) for w in re.findall(r"[^\W\d_]{3,}", text or "")}
    scores, found = {}, {}
    for mood, words in _MOOD_SETS.items():
        hits = sorted(w for w in words
                      if w in tokens or (len(w) >= 5 and any(t.startswith(w) for t in tokens)))
        if hits:
            scores[mood] = float(min(len(hits), 5))
            found[mood] = hits
    try:
        legacy, _hits = analyze_mood(text)
        for key, value in legacy.items():
            mood = _LEGACY_MOOD.get(key)
            if mood:
                scores[mood] = scores.get(mood, 0.) + .5 * min(float(value), 2.)
    except Exception:
        pass
    if preset in _LEGACY_MOOD:
        mood = _LEGACY_MOOD[preset]
        scores[mood] = scores.get(mood, 0.) + 1.5
    if scores and max(scores.values()) >= 1.:
        best = max(scores, key=lambda m: (scores[m], -_MOOD_ORDER.index(m)))
        words = ", ".join(found.get(best, [])[:3]) or "ton du script"
        return best, f"{best} (signaux : {words})"
    pick = int(rng.integers(len(_NEUTRAL_MOODS))) if rng is not None else 0
    return _NEUTRAL_MOODS[pick], f"{_NEUTRAL_MOODS[pick]} (sujet neutre, ambiance variee)"


def score_plan(preset="epique", text="", seed=None, *, mood=None):
    """Composition reproductible : meme script = meme musique, scripts differents = musiques differentes."""
    if seed is None:
        if (text or "").strip():
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        else:
            seed = int.from_bytes(os.urandom(8), "big")
    rng = np.random.default_rng(seed)
    if mood is None:
        mood, reason = detect_mood(text, preset, rng)
    else:
        reason = f"{mood} (ambiance sélectionnée)"
    prof = _PROFILES[mood]

    def level(key):
        lo, hi = prof[key]
        return float(rng.uniform(lo, hi)) if hi > 0 else 0.0

    mode = str(rng.choice(prof["modes"]))
    scale = _MODES[mode]
    picks = rng.choice(len(_DEGREE_PROGRESSIONS), 3, replace=False)
    progs = tuple(_DEGREE_PROGRESSIONS[int(i)] for i in picks)
    low, high = prof["bpm"]
    lo_b, hi_b = prof["bars"]
    return {
        "seed": int(rng.integers(0, 2**53)),
        "mood": mood, "mood_reason": reason,
        "mode": mode, "scale": scale,
        "intensity": prof["intensity"],
        "spatial": mood == "espace",
        "calm": prof["calm"],
        "bpm": int(rng.integers(low, high + 1)),
        "root": int(rng.choice([43, 45, 46, 47, 48, 50, 52])),
        "lift": int(rng.choice([0, 2, 5])),
        "progs": progs,
        "progression": tuple(scale[d] for d in progs[0]),
        "motif": tuple(int(v) for v in rng.choice([0, 2, 4, 7, 9, 11], 6)),
        "bars_per_chord": int(rng.integers(lo_b, hi_b + 1)),
        "pad": level("pad"), "organ": level("organ"), "strings": level("strings"),
        "brass": level("brass"), "piano": level("piano"), "arp": level("bell"),
        "bass": float(prof["bass"]), "pulse": float(rng.uniform(.01, .03)),
        "drums": prof["drums"], "riser": bool(prof["riser"]),
        "melody": prof["melody"], "density": prof["density"], "arp_div": prof["arp"],
    }


def _drum_pattern(style, seg):
    """Coups (position en temps dans la mesure, son, gain) pour une mesure de la partie `seg`."""
    if style == "taiko" and seg >= 1:
        hits = [(0, "tom", 1.0), (2, "tom", .8)]
        if seg == 2:
            hits += [(1, "tom", .5), (3, "tom", .5), (3.5, "tom", .6)]
        return hits
    if style == "march" and seg in (1, 2):
        return [(0, "tom", .6), (1.5, "tom", .3), (2, "tom", .5), (3.5, "tom", .3)]
    if style == "tick":
        hits = [(0, "tick", .5), (1, "tick", .3), (2, "tick", .4), (3, "tick", .3)]
        return hits + ([(0, "tom", .6), (.5, "tom", .35)] if seg >= 2 else [])
    if style == "tick_soft" and seg in (1, 2):
        return [(0, "tick", .35), (2, "tick", .25), (0, "heart", .5), (.45, "heart", .3)]
    if style in ("pop", "pop_light"):
        snare = 1.0 if style == "pop" else .55
        if seg == 1:
            return [(0, "kick", 1.0), (2, "kick", .8)] + [(b, "hat", .3) for b in (0, 1, 2, 3)]
        if seg == 2:
            hits = [(0, "kick", 1.0), (1, "snare", .8 * snare), (2, "kick", .9), (3, "snare", .8 * snare)]
            hits += [(b / 2, "hat", .32 if style == "pop" else .22) for b in range(8)]
            return hits + ([(2.5, "kick", .6)] if style == "pop" else [])
        return [(0, "kick", .7)] if seg == 3 else []
    if style == "techno" and seg >= 1:
        hits = [(b, "kick", .85) for b in (0, 1, 2, 3)] + [(b + .5, "hat", .4) for b in (0, 1, 2, 3)]
        if seg == 2:
            hits += [(1, "snare", .5), (3, "snare", .5)] + [(b + .25, "hat", .18) for b in (0, 1, 2, 3)]
        return hits
    return []


def cinematic_background(duration, preset="epique", path=None, *, text="", seed=None, scene_durations=None, plan=None):
    """Partition instrumentale stereo adaptee au script, sans voix ni echantillon.

    L'ambiance (epique, mystere, espace, emotion, histoire, techno, energie...) est deduite
    du script ; elle fixe tempo, mode, instruments et rythme.  4 parties (intro, montee,
    climax, resolution), un theme melodique qui revient, une montee de tonalite au climax.
    """
    plan = plan if plan is not None else score_plan(preset, text, seed)
    rng = np.random.default_rng(plan["seed"])
    duration = float(duration)
    n = max(1, int(duration * SR))
    mix = np.zeros((n, 2), dtype=np.float64)
    beat = 60.0 / plan["bpm"]
    bar = beat * 4
    chord_time = bar * plan["bars_per_chord"]
    scale = plan["scale"]
    boundaries = np.cumsum([0, *(scene_durations or [])])
    boundaries = boundaries / max(float(boundaries[-1]), .01) if len(boundaries) > 1 else None

    def arc_at(position):
        position = float(np.clip(position, 0, 1))
        if boundaries is not None:
            scene = min(len(boundaries) - 2, max(0, int(np.searchsorted(boundaries, position)) - 1))
            position = (scene + .5) / (len(boundaries) - 1)
        arc = np.interp(position, [0, .15, .55, .78, 1], [.3, .5, .8, 1, .35])
        return arc * (.65 + .35 * plan["intensity"])

    def add_note(start, length, midi, gain, kind, pan=0.):
        offset = max(0, int(start * SR))
        count = min(int(length * SR), n - offset)
        if count <= 0:
            return
        t = np.arange(count, dtype=np.float64) / SR
        freq = m2f(midi)
        phase = rng.uniform(0, 2 * np.pi)
        life = count / SR
        if kind == "piano":
            tone = (np.sin(2*np.pi*freq*t) + .22*np.sin(2*np.pi*freq*2*t) + .07*np.sin(2*np.pi*freq*3*t))
            env = (1-np.exp(-t*55))*np.exp(-t/1.4)
        elif kind == "organ":
            tone = (np.sin(2*np.pi*freq*t+phase) + .25*np.sin(2*np.pi*freq*2*t+phase)
                    + .08*np.sin(2*np.pi*freq*4*t+phase))
            env = np.minimum(t/1.5, 1.) * np.minimum((life-t)/2., 1.)
        elif kind == "bell":
            tone = (np.sin(2*np.pi*freq*t) + .32*np.sin(2*np.pi*freq*2.01*t) + .14*np.sin(2*np.pi*freq*3.98*t))
            env = (1-np.exp(-t*220))*np.exp(-t/1.6)
        elif kind == "string":
            ph = 2*np.pi*freq*t + .25*np.sin(2*np.pi*5.1*t + phase)
            tone = np.sin(ph) + .5*np.sin(2*ph) + .28*np.sin(3*ph) + .14*np.sin(4*ph)
            env = np.minimum(t/1.4, 1.) * np.minimum((life-t)/1.8, 1.)
        elif kind == "brass":
            ph = 2*np.pi*freq*t + phase
            tone = sum(w*np.sin(k*ph) for k, w in enumerate((1, .7, .5, .4, .25, .15), 1))
            env = np.minimum(t/.35, 1.) * np.minimum((life-t)/1.0, 1.)
        elif kind == "bass":
            ph = 2*np.pi*freq*t
            tone = np.sin(ph) + .35*np.sin(2*ph)
            env = (1-np.exp(-t*120))*np.exp(-t/.28)
        else:  # pad
            tone = (np.sin(2*np.pi*freq*t+phase) + .35*np.sin(2*np.pi*freq*1.0015*t+phase)
                    + .12*np.sin(2*np.pi*freq*2*t))
            env = np.sin(np.pi*np.minimum(t/life, 1.))**1.3
        tone *= env * gain * arc_at((start + length/2) / max(duration, .01))
        mix[offset:offset+count, 0] += tone * np.sqrt((1-pan)/2)
        mix[offset:offset+count, 1] += tone * np.sqrt((1+pan)/2)

    # Sons de percussion : crees une fois, puis places.
    def drum_samples():
        def noise(length):
            return rng.standard_normal(int(length * SR))
        tk = np.arange(int(.35*SR)) / SR
        kick = np.sin(2*np.pi*(45*tk + 75*(1-np.exp(-tk*18))/18)) * np.exp(-tk*14)
        tt = np.arange(int(.7*SR)) / SR
        tom = (np.sin(2*np.pi*(62*tt + 55*(1-np.exp(-tt*10))/10)) * np.exp(-tt*5.5)
               + .12*np.diff(noise(.7), prepend=0) * np.exp(-tt*30))
        ts = np.arange(int(.22*SR)) / SR
        snare = (np.diff(noise(.22), prepend=0) * np.exp(-ts*24) * .6 + np.sin(2*np.pi*190*ts) * np.exp(-ts*30) * .5)
        th = np.arange(int(.08*SR)) / SR
        hat = np.diff(noise(.08), prepend=0) * np.exp(-th*70) * .5
        tc = np.arange(int(.04*SR)) / SR
        tick = np.sin(2*np.pi*1900*tc) * np.exp(-tc*90)
        th2 = np.arange(int(.3*SR)) / SR
        heart = np.sin(2*np.pi*52*th2) * np.exp(-th2*16)
        return {"kick": kick, "tom": tom, "snare": snare, "hat": hat, "tick": tick, "heart": heart}
    drums = drum_samples() if plan["drums"] != "none" else {}
    drum_gain = {"kick": .55, "tom": .60, "snare": .30, "hat": .22, "tick": .08, "heart": .50}

    def add_drum(start, kind, gain):
        sample = drums[kind]
        offset = int(start * SR)
        count = min(len(sample), n - offset)
        if count <= 0:
            return
        level = gain * drum_gain[kind] * arc_at(start / max(duration, .01)) * (.5 + .5 * plan["intensity"])
        pan = float(rng.uniform(-.25, .25)) if kind in ("hat", "tick") else 0.
        mix[offset:offset+count, 0] += sample[:count] * level * np.sqrt((1-pan)/2)
        mix[offset:offset+count, 1] += sample[:count] * level * np.sqrt((1+pan)/2)

    def add_riser(start, length, gain):
        offset = max(0, int(start * SR))
        count = min(int(length * SR), n - offset)
        if count < SR // 2:
            return
        window = np.ones(120) / 120
        tt = np.linspace(0, 1, count)
        env = tt**2.2 * np.minimum((1-tt)*20, 1.)
        for ch in (0, 1):
            noise = np.convolve(rng.standard_normal(count), window, mode="same")
            noise /= (np.std(noise) + 1e-9)
            mix[offset:offset+count, ch] += noise * env * gain * arc_at((start + length) / max(duration, .01))

    # Theme melodique : une cellule par partie, reprise a chaque mesure avec une variante,
    # et la partie finale rejoue la cellule de l'intro (retour du theme).
    templates = ([(0, 2), (0, 1.5, 3), (0, 2.5), (0, 1, 3)] if plan["density"] < .45 else
                 [(0, 1, 2.5, 3), (0, .5, 1.5, 2, 3), (0, 1.5, 2, 3.5), (0, 1, 2, 3), (0, .75, 1.5, 3)])

    def make_cell():
        offsets = templates[int(rng.integers(len(templates)))]
        degree = int(rng.choice([0, 2, 4]))
        cell = []
        for off in offsets:
            cell.append((off, degree))
            degree = int(np.clip(degree + int(rng.choice([-2, -1, -1, 1, 1, 2])), -2, 9))
        variant = list(cell)
        last_off, last_deg = variant[-1]
        variant[-1] = (last_off, int(np.clip(last_deg + int(rng.choice([-2, -1, 1, 2])), -2, 9)))
        return cell, variant
    cells = [make_cell() for _ in range(3)]
    cells.append(cells[0])
    dropout = (.45, .25, .10, .45)

    segments = ((0, .16), (.16, .48), (.48, .76), (.76, 1.01))
    prog_of_segment = (0, 1, 2, 0)
    counters = [0, 0, 0, 0]
    bar_counter = [0, 0, 0, 0]
    last_note = None
    t0 = 0.0
    section = 0
    while t0 < duration:
        frac = t0 / max(duration, .01)
        seg = next(i for i, (a, b) in enumerate(segments) if a <= frac < b)
        prog = plan["progs"][prog_of_segment[seg]]
        degree = prog[counters[seg] % len(prog)]
        counters[seg] += 1
        key_root = plan["root"] + (plan["lift"] if seg == 2 else 0)
        base = scale[degree]
        stack = [scale[(degree + k) % 7] + 12 * ((degree + k) // 7) - base for k in (0, 2, 4, 6)]
        chord_root = key_root + base
        third, fifth = stack[1] % 12, stack[2] % 12
        seventh = stack[3] % 12 + (12 if section % 2 else 0)
        voicing = (0, fifth, third + 12, seventh)
        pcs = {(chord_root + iv) % 12 for iv in (0, third, fifth, stack[3] % 12)}

        # Harmonie : nappes + basse profonde
        for j, interval in enumerate(voicing):
            add_note(t0, chord_time + 2, chord_root + interval, plan["pad"], "pad", (j - 1.5) * .35)
        add_note(t0, chord_time + 1, chord_root - 12, .065, "pad", -.1)
        if plan["organ"] > 0 and (seg >= 1 or plan["mood"] in ("espace", "mystere", "tension")):
            add_note(t0, chord_time + 1, chord_root + 12, plan["organ"], "organ", .15)
        if plan["strings"] > 0 and seg >= 1:
            gain = plan["strings"] * (1.25 if seg == 2 else 1.0)
            add_note(t0, chord_time + 1.5, chord_root + 12 + third, gain, "string", -.4)
            add_note(t0, chord_time + 1.5, chord_root + 12 + fifth, gain, "string", .4)
        if plan["brass"] > 0 and seg == 2:
            add_note(t0, chord_time + 1, chord_root + 12, plan["brass"], "brass", -.2)
            add_note(t0, chord_time + 1, chord_root + 12 + fifth, plan["brass"] * .8, "brass", .2)

        # Arpeges (cloches)
        if plan["arp"] > 0:
            tones = [0, third, fifth, 12]
            if section % 2:
                tones = tones[::-1]
            step = beat * plan["arp_div"] if not plan["calm"] else beat * (1 if plan["mood"] != "mystere" else 2)
            for k in range(int(chord_time / step)):
                if rng.random() < .15:
                    continue
                midi = chord_root + 12 + tones[k % len(tones)] + (12 if seg == 2 else 0)
                add_note(t0 + k*step, 2.4, midi, plan["arp"] * rng.uniform(.7, 1), "bell", rng.uniform(-.6, .6))

        # Basse rythmique et percussions, mesure par mesure ; theme melodique
        bars = max(1, int(round(chord_time / bar)))
        for b in range(bars):
            bar_start = t0 + b * bar
            for pos, kind, gain in _drum_pattern(plan["drums"], seg):
                add_drum(bar_start + pos * beat, kind, gain)
            if plan["bass"] > 0 and seg >= 1:
                positions = (.5, 1.5, 2.5, 3.5) if plan["drums"] == "techno" else (0, 1.5, 2, 3)
                for i, pos in enumerate(positions):
                    add_note(bar_start + pos * beat, beat * .9, chord_root - 12 + (12 if i % 2 and plan["drums"] == "techno" else 0),
                             plan["bass"], "bass", 0)
            cell, variant = cells[seg]
            notes = cell if bar_counter[seg] % 2 == 0 else variant
            bar_counter[seg] += 1
            for idx, (off, deg) in enumerate(notes):
                if idx > 0 and rng.random() < dropout[seg]:
                    continue
                note = key_root + 12 + scale[deg % 7] + 12 * (deg // 7) + (12 if seg == 2 and not plan["calm"] else 0)
                if off in (0, 2):  # temps forts : se poser sur une note de l'accord
                    for shift in (0, -1, 1, -2, 2):
                        if (note + shift) % 12 in pcs:
                            note += shift
                            break
                if note == last_note:
                    note += 7
                last_note = note
                kind = "bell" if plan["melody"] == "bell" else "piano"
                gain = (plan["piano"] if kind == "piano" else max(plan["piano"], plan["arp"]) * .9)
                add_note(bar_start + off * beat + rng.uniform(0, .04), 4.0 if kind == "piano" else 3.0, note,
                         gain * rng.uniform(.75, 1) * (1.15 if off == 0 else 1.0), kind, rng.uniform(-.5, .5))
        if seg >= 1:
            for k in range(int(chord_time / (2*beat))):
                add_note(t0 + k*2*beat, beat, chord_root - 12, plan["pulse"], "piano", 0)

        # Montee puis choc a l'entree du climax
        if seg == 2 and counters[2] == 1 and t0 > 3.5:
            if plan["riser"]:
                add_riser(t0 - 3.5, 3.5, .05)
            if plan["mood"] in ("epique", "tension", "histoire"):
                tom = drums.get("tom")
                if tom is None:
                    tom = np.sin(2*np.pi*55*np.arange(int(.7*SR))/SR) * np.exp(-np.arange(int(.7*SR))/SR*5)
                    drums["tom"] = tom
                    drum_gain.setdefault("tom", .6)
                add_drum(t0, "tom", 1.6)

        t0 += chord_time
        section += 1

    # Retards stereo puis reverberation (reponse impulsionnelle bruitee, calculee par blocs)
    for seconds, amount in ((.31, .10), (.67, .06)):
        delay = int(seconds * SR)
        if delay < n:
            mix[delay:] += mix[:-delay, ::-1].copy() * amount
    wet = .24 if plan["calm"] else .14
    ir_len = int(1.9 * SR)
    ir_t = np.arange(ir_len) / SR
    block = 1 << 17
    size = 1 << 18
    tail = np.zeros((ir_len, 2))
    reverb = np.zeros_like(mix)
    for ch in (0, 1):
        ir = rng.standard_normal(ir_len) * np.exp(-ir_t * 3.6)
        ir = np.convolve(ir, np.ones(6)/6, mode="same")
        ir[:int(.02*SR)] *= np.linspace(0, 1, int(.02*SR))
        ir /= (np.sqrt((ir**2).sum()) + 1e-9)
        ir_f = np.fft.rfft(ir, size)
        for start in range(0, n, block):
            seg_in = mix[start:start+block, ch]
            out = np.fft.irfft(np.fft.rfft(seg_in, size) * ir_f, size)[:len(seg_in) + ir_len - 1]
            end = min(n, start + len(out))
            reverb[start:end, ch] += out[:end - start]
    mix += reverb * wet
    fade = min(n // 2, int(2.5 * SR))
    if fade:
        mix[:fade] *= np.linspace(0, 1, fade)[:, None]
        mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    ref = np.percentile(np.abs(mix), 99.5) or 1.
    mix *= .6 / ref
    mix = .85 * np.tanh(mix / .85)
    peak = np.max(np.abs(mix)) or 1.
    mix *= min(1., .72 / peak)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "music.wav")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes((mix*32767).astype("<i2").tobytes())
    return path


def m2f(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _saw(phase):
    return 2.0 * (phase % 1.0) - 1.0


def _env(n, attack=0.01, release=0.15):
    e = np.ones(n)
    a = min(n, max(1, int(attack * SR)))
    r = min(n, max(1, int(release * SR)))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.linspace(1, 0, r)
    return e


def _lowpass(x, alpha=0.18):
    # filtre 1er ordre très léger
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y


def _kick(n):
    t = np.arange(n) / SR
    f0, f1 = 120.0, 45.0
    phase = np.cumsum((f1 + (f0 - f1) * np.exp(-t * 25)) / SR) * 2 * np.pi
    return np.sin(phase) * np.exp(-t * 9)


def _hat(n):
    return np.random.default_rng(7).standard_normal(n) * np.exp(-np.arange(n) / SR * 60) * 0.5


def synthesize(duration, preset="energie", path=None):
    """Génère une boucle musicale de `duration` secondes et l'écrit en WAV 16 bits."""
    p = PRESETS.get(preset, PRESETS["energie"])
    n = int(duration * SR)
    if p["style"] == "none" or n <= 0:
        y = np.zeros(max(1, n))
    else:
        bpm = p["bpm"]
        beat = 60.0 / bpm
        bar = beat * 4
        chords = p["chords"]
        y = np.zeros(n)
        nbars = int(np.ceil(duration / bar))
        for b in range(nbars):
            chord = chords[b % len(chords)]
            start = int(b * bar * SR)
            end = min(n, int((b + 1) * bar * SR))
            if start >= end:
                break
            seg = end - start
            t = np.arange(seg) / SR
            root = chord[0]
            # Basse (une octave sous la fondamentale)
            bass = np.sin(2 * np.pi * m2f(root - 12) * t) * 0.5
            if p["style"] == "drive":
                # pompe façon sidechain sur chaque temps
                pump = np.ones(seg)
                for bt in range(4):
                    bi = int(bt * beat * SR)
                    if bi >= seg:
                        break
                    ln = min(seg - bi, int(beat * SR))
                    pump[bi:bi + ln] *= 1.0 - 0.45 * np.exp(-np.arange(ln) / SR * 6)
                bass *= pump
            y[start:end] += bass * _env(seg, 0.01, 0.2)
            # Nappes / arpèges
            if p["style"] in ("pad",):
                for note in chord[1:]:
                    det = _saw(m2f(note) * t) * 0.10 + _saw(m2f(note) * 1.003 * t) * 0.10
                    y[start:end] += det * _env(seg, 0.3, 0.4)
            else:
                arp_notes = chord + [chord[0] + 12]
                step = beat / 2.0
                for i, note in enumerate(arp_notes * 8):
                    si = int(i * step * SR)
                    if si >= seg:
                        break
                    ln = min(seg - si, int(step * SR))
                    tt = np.arange(ln) / SR
                    if p["style"] == "pluck":
                        tone = np.sin(2 * np.pi * m2f(note) * tt) * np.exp(-tt * 8) * 0.25
                    else:
                        tone = _saw(m2f(note) * tt) * np.exp(-tt * 5) * 0.12
                    y[start + si:start + si + ln] += tone
            # Batterie
            if p["drums"]:
                for bt in range(4):
                    ki = int(bt * beat * SR)
                    if ki >= seg:
                        break
                    ln = min(seg - ki, int(0.25 * SR))
                    y[start + ki:start + ki + ln] += _kick(ln) * (0.9 if p["style"] == "drive" else 0.55)
                    if p["style"] == "drive" or bt in (1, 3):
                        hi = int((bt + 0.5) * beat * SR)
                        if hi < seg:
                            ln2 = min(seg - hi, int(0.06 * SR))
                            y[start + hi:start + hi + ln2] += _hat(ln2) * 0.5
        # léger filtrage + saturation douce
        y = np.tanh(y * 1.1) * 0.9
        # fondu entrée/sortie global
        fade = int(0.25 * SR)
        if len(y) > 2 * fade:
            y[:fade] *= np.linspace(0, 1, fade)
            y[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(y)) or 1.0
    y = y / max(peak, 0.9)
    pcm = (y * 32767).astype(np.int16)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "music.wav")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path
