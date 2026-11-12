# -*- coding: utf-8 -*-
"""ShortPilot — banque d'images « infinie » : photos libres (CC) choisies par scène.

Principe : pour chaque réplique, on extrait des mots-clés porteurs, puis on télécharge
une photo libre de droits qui illustre réellement la scène.
  1. Openverse  (api.openverse.org — CC0 / CC-BY, sans clé API, attribution incluse)
  2. LoremFlickr (loremflickr.com — photos CC par mot-clé, sans clé)
  3. Repli final : arrière-plan graphique procédural (aucun réseau requis, 100% offline).

Pertinence (v2) :
  - 2 mots-clés distinctifs par scène (et non un seul « mot le plus long ») ;
  - les concepts courants sont traduits FR→EN : les bases photos sont indexées en anglais ;
  - la niche du script sert d'indice dans la requête (ex. cerveau + « mind ») ;
  - une image n'est acceptée que si son titre / ses étiquettes recoupent la requête,
    sinon on essaie la requête suivante — puis repli graphique si rien de probant.
"""
import os
import re
import unicodedata
import urllib.parse

import requests

UA = {"User-Agent": "ShortPilot/1.1 (studio local de videos courtes)"}
TIMEOUT = 25

_STOP = set("""
 alors aussi assez avant avec avoir bien cela cette ceci ces chaque chez comme
 comment contre dans dès depuis deux donc encore entre être faire fait faut
 fois leur leurs lors lui mais même moins monde notre nous nous-mêmes
 pour pourquoi puisquand quand quel quelle quels quelles sans sera seront
 seraont sous sont suis sur telle telles tout toute toutes très trop voici voilà
 votre vous vôtre êtes ont ses son sa sur dans que qui quoi dont où aux par
 plus pour pas peut peuvent non oui vers après pendant l'année le monde aujourd'hui
 about above after again against along also although always among another
 anyone anything are around because been before being between both could
 does doing down during each either enough every everyone everything from
 going have having here into is itself just like make many more most much
 must never only other others out over own people same should since some
 something still such than that the their them then there these they this
 those through today under until upon very were what when where which while
 will with within without would your youre
""".split())

# Mots trop génériques / verbes courants : mauvais mots-clés photo
_STOP |= set("""
 chose choses gens enfin ainsi ailleurs notamment certes permet permettent
 produisent produire comprendre comprends comprenez influence influent influer
 marche marcher parle parler regarde regarder ecoute ecouter commence commencer
 devient devenir prendre prends prenez passer passe aller allons allez faire
 faites donnent donner donne arrive arrives arrivee rester reste restes montre
 montrer savoir savent veulent vouloir plutot toujours jamais mieux premier
 premiere deuxieme troisieme vrai vraie vraiment contre petit petite grand
 grande gros chacun chacune lorsque pendant apres avant jour jours annee
 annees moment temps cas type exemple niveau groupe nombre question questions
 croire crois croient penser pense pensent utiliser utilise utilisent garder
 garde gardent changer change changent trouver trouve trouvent sentir sens
 sentent semble semblent paraît pouvoir peuvent certain certains certaine
 traversent traverse traverser traversée toucher touche touchent
 always never better worse really actually thing things starts begin begun
 think thinks thinking feel feels feeling become becomes getting giving
 brings learn learning keeps know knowing knows want wants needs making
""".split())

def _norm(s):
    """minuscules + accents retirés : comparaisons robustes FR/EN."""
    s = (s or "").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# Traduction FR→EN des concepts visuels courants (clés normalisées par _norm, sans accents).
# Les bases de photos libres sont majoritairement indexées en anglais :
# chercher « brain » donne des photos récentes, « cerveau » surtout des gravures anciennes.
_FR_EN = dict(item.split(":") for item in """
cerveau:brain esprit:mind pensée:thought émotion:emotion émotions:emotions
peur:fear angoisse:anxiety mensonge:lie secret:secret manipulation:manipulation
habitude:habit habitudes:habits motivation:motivation discipline:discipline
comportement:behavior réaction:reaction décision:decision choix:choice
confiance:confidence estime:esteem croyance:belief subconscient:subconscious
argent:money richesse:wealth fortune:fortune investissement:investment
bourse:stock économie:economy budget:budget dette:debt épargne:savings
banque:bank salaire:salary impôts:taxes entreprise:business client:customer
technologie:technology ordinateur:computer robot:robot robots:robot
intelligence:intelligence artificielle:artificial espace:space univers:universe
science:science données:data internet:internet écran:screen écrans:screen
téléphone:phone application:app réseau:network réseaux:network numérique:digital
algorithme:algorithm algorithmes:algorithm futur:future informatique:computer
santé:health corps:body sommeil:sleep alimentation:nutrition nutrition:nutrition
sport:sport exercice:exercise régime:diet muscle:muscle muscles:muscle
vitamine:vitamin médecin:doctor hôpital:hospital maladie:disease énergie:energy
travail:work bureau:office productivité:productivity organisation:organization
projet:project objectif:goal objectifs:goal réunion:meeting planning:calendar
histoire:history guerre:war empire:empire roi:king reine:queen bataille:battle
château:castle antique:ancient antiquité:ancient armée:army armées:army
trône:throne révolution:revolution légende:legend héros:hero batailles:battle
amour:love couple:couple famille:family enfant:child enfants:child ami:friend
amis:friends foule:crowd personnes:people homme:man femme:woman visage:face
ville:city pays:country voyage:travel voyages:travel mer:sea océan:ocean
montagne:mountain forêt:forest arbre:tree fleur:flower animal:animal chien:dog
chat:cat oiseau:bird nature:nature paysage:landscape plage:beach désert:desert
nourriture:food cuisine:kitchen recette:recipe restaurant:restaurant café:coffee
eau:water feu:fire terre:earth soleil:sun lune:moon étoile:star étoiles:star
ciel:sky pluie:rain neige:snow tempête:storm saison:season hiver:winter été:summer
livre:book livres:book lecture:reading école:school étude:study études:study
université:university élève:student professeur:teacher langue:language mot:word
musique:music film:movie cinéma:cinema jeu:game jeux:game joueur:player
maison:house voiture:car avion:plane train:train route:road pont:bridge
œil:eye yeux:eye main:hand mains:hand cœur:heart sang:blood bouche:mouth
réussite:success échec:failure victoire:victory défaite:defeat danger:danger
mort:death vie:life bonheur:happiness tristesse:sadness colère:anger joie:joy
méditation:meditation religion:religion dieu:god prière:prayer temple:temple
silence:silence bruit:noise voix:voice lumière:light ombre:shadow nuit:night
matin:morning soir:evening heure:hour minute:minute seconde:second horloge:clock
piège:trap preuve:evidence preuves:evidence expérience:experiment test:test
résultat:result résultats:result méthode:method astuce:tip astuces:tip
cerveaux:brain préférence:preference jugement:judgment regard:look perception:perception
effort:effort schéma:pattern schémas:pattern action:action actions:action
quotidien:daily quotidienne:daily quotidiens:daily quotidiennes:daily
romain:roman romains:roman romaine:roman romaines:roman légion:legion légions:legion
économise:save économisent:save économiser:save répète:repeat répéter:repeat
répètent:repeat constance:consistency durable:lasting transforme:transform
""".split() if ":" in item)
_FR_EN = {_norm(k): v for k, v in _FR_EN.items()}  # clés normalisées (sans accents)

# Niche → indice anglais ajouté à la requête (ancre thématique du short)
NICHE_HINTS = {
    "psychologie": "mind",
    "motivation": "success",
    "faits": "discovery",
    "argent": "money",
    "productivite": "work",
    "sante": "health",
    "tech": "technology",
    "histoire": "history",
    "actu": "news", "jour": "history", "science": "science discovery", "mythes": "investigation",
    "sujet": "",
}

_WORD_RX = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,}")
_TERM_RX = re.compile(r"[a-z]{3,}")


def extract_keywords(text, lang="fr", n=2, all_text=""):
    """Les `n` mots-clés les plus porteurs de la réplique.

    Score = longueur + répétition locale + bonus « concept visuel connu »
    (traduisible FR→EN) + pénalité si le mot est rabâché dans tout le script
    (il donnerait la même photo à chaque scène).
    """
    words = {}
    for w in _WORD_RX.findall(text.lower()):
        if w in _STOP or len(w) < 4:
            continue
        if w.endswith(("ment", "ly")) and len(w) > 6:  # adverbes génériques
            continue
        words[w] = words.get(w, 0) + 1
    if not words:
        return []
    global_count = {}
    if all_text:
        for w in _WORD_RX.findall(all_text.lower()):
            global_count[w] = global_count.get(w, 0) + 1
    scored = []
    for w, c in words.items():
        s = len(w) + 2 * c
        if _norm(w) in _FR_EN:
            s += 3  # concept visuel connu des bases photos
        if global_count.get(w, 0) >= 3 and len(words) > 1:
            s -= 2  # mot central répété partout → peu distinctif pour CETTE scène
        scored.append((s, w))
    scored.sort(key=lambda sw: (-sw[0], sw[1]))
    return [w for _, w in scored[:max(1, n)]]


def extract_keyword(text, lang="fr"):
    """Compatibilité v1 : le meilleur mot-clé unique."""
    ks = extract_keywords(text, lang, n=1)
    return ks[0] if ks else None


def to_en(kw):
    """Anglais correspondant si le concept est connu, sinon le mot tel quel."""
    return _FR_EN.get(_norm(kw), kw)


def _terms(q):
    """Termes normalisés d'une requête (singulier approximatif)."""
    ts = set()
    for w in _TERM_RX.findall(_norm(q)):
        if len(w) >= 4:
            ts.add(w)
        if len(w) > 4 and w.endswith("s"):
            ts.add(w[:-1])
    return ts


def _blob_words(title, tags):
    """Mots normalisés du titre + étiquettes d'un résultat Openverse."""
    blob = set()
    raw = [title or ""]
    for t in (tags or []):
        raw.append(t.get("name") if isinstance(t, dict) else str(t))
    for part in raw:
        for w in _TERM_RX.findall(_norm(part)):
            blob.add(w)
            if len(w) > 4 and w.endswith("s"):
                blob.add(w[:-1])
    return blob


def _match_score(query, title, tags):
    """0 = aucun recoupement → image rejetée ; sinon nb de termes recoupés."""
    q = _terms(query)
    blob = _blob_words(title, tags)
    score = 0
    for term in q:
        if term in blob:
            score += 2
        elif any(len(term) >= 5 and len(b) >= 5 and (term in b or b in term) for b in blob):
            score += 1  # variantes de racine (brain/brains, historic/history…)
    return score


MAX_IMG_BYTES = 40 * 1024 * 1024  # garde-fou anti DoS mémoire/disque (flux distant)


def _download(url, out_path):
    """Télécharge (avec plafond de taille) et valide une image. → chemin ou None."""
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, stream=True)
        if r.status_code != 200 or not r.headers.get("Content-Type", "").lower().startswith("image"):
            return None
        total = int(r.headers.get("Content-Length") or 0)
        if total and total > MAX_IMG_BYTES:
            r.close()
            return None
        chunks, got = [], 0
        for chunk in r.iter_content(65536):
            got += len(chunk)
            if got > MAX_IMG_BYTES:
                r.close()
                return None
            chunks.append(chunk)
        r.close()
        data = b"".join(chunks)
        if len(data) < 15000:
            return None
        with open(out_path, "wb") as f:
            f.write(data)
        from PIL import Image
        im = Image.open(out_path)
        im.verify()
        return out_path
    except Exception:
        return None


# Titres promotionnels/spam fréquents dans les bases libres → rejetés
_PROMO = ("abonne", "subscribe", "follow", "sponsor", "promo", "coupon",
          "reduction", "thumbnail", "miniature", "youtube", "tiktok", "logo ")


def _openverse(query, out_dir, used=None):
    """Meilleure image Openverse pour `query`, titre/étiquettes vérifiés + attribution.

    `used` : ensemble d'URL déjà exploitées dans ce rendu (anti-doublons entre scènes).
    """
    # Du plus filtré au plus large : si un palier ne donne rien de probant, on descend.
    # category=photograph écarte illustrations, captures d'écran et dessins.
    for params in ("&aspect_ratio=tall&size=medium,large&category=photograph",
                   "&size=medium,large&category=photograph",
                   "&category=photograph",
                   ""):
        try:
            api = ("https://api.openverse.org/v1/images/?q=%s&page_size=10"
                   "&license=cc0,pdm,by%s" % (urllib.parse.quote(query), params))
            r = requests.get(api, headers=UA, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            results = (r.json() or {}).get("results") or []
            scored = []
            for it in results:
                if not it.get("url"):
                    continue
                if used and it["url"] in used:
                    continue  # déjà affichée dans une scène précédente
                title = (it.get("title") or "")
                if any(p in _norm(title) for p in _PROMO):
                    continue  # titre promotionnel / capture d'écran → hors sujet
                sc = _match_score(query, title, it.get("tags"))
                if sc >= 1:  # recoupement titre/étiquettes obligatoire (anti hors-sujet)
                    scored.append((sc, it))
            if not scored:
                continue
            scored.sort(key=lambda x: -x[0])
            for _sc, it in scored[:4]:
                url = it["url"]
                ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
                if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                    ext = ".jpg"
                out = os.path.join(out_dir, f"ov_{abs(hash((query, url))) % 99999:05d}{ext}")
                if _download(url, out):
                    lic = (it.get("license") or "cc").upper()
                    title = (it.get("title") or "image")[:60].strip() or "image"
                    creator = (it.get("creator") or "auteur inconnu")[:40].strip()
                    attrib = f"«{title}» par {creator} ({lic}) via Openverse"
                    if used is not None:
                        used.add(url)
                    return out, attrib, "Openverse"
        except Exception:
            continue
    return None


def _loremflickr(tags, out_dir, lock=1):
    """Repli : photo CC par mots-clés (LoremFlickr), tags séparés par virgule.
    `lock` varie par scène pour éviter deux fois la même photo."""
    try:
        out = os.path.join(out_dir, f"lf_{abs(hash((tags, lock))) % 99999:05d}.jpg")
        url = ("https://loremflickr.com/1080/1920/%s?lock=%d"
               % (urllib.parse.quote(tags, safe=","), int(lock)))
        if _download(url, out):
            return out, "photo libre via LoremFlickr", "LoremFlickr"
    except Exception:
        pass
    return None


def image_for_scene(text, lang, out_dir, log=None, niche="", all_text="", used=None):
    """(chemin_image, attribution, source) ou None (→ thème graphique).

    Échelle de requêtes, de la plus précise à la plus large, chacune vérifiée :
      « kw1 kw2 » (EN) → « kw1 + indice niche » → « kw1 » → « kw2 » → LoremFlickr.
    """
    kws = extract_keywords(text, lang, n=2, all_text=all_text)
    if not kws and niche:
        hint0 = NICHE_HINTS.get(niche, "")
        kws = [hint0] if hint0 else [niche]
    if not kws:
        return None
    en = [to_en(k) for k in kws]
    hint = NICHE_HINTS.get(niche, "")
    queries = []
    if len(en) >= 2 and en[0] != en[1]:
        queries.append(" ".join(en[:2]))
    if hint and _norm(hint) not in _norm(" ".join(en)):
        queries.append(f"{en[0]} {hint}")
    queries.append(en[0])
    if len(en) >= 2:
        queries.append(en[1])
    seen = set()
    queries = [q for q in queries if q and not (q in seen or seen.add(q))]

    os.makedirs(out_dir, exist_ok=True)
    for q in queries:
        res = _openverse(q, out_dir, used=used)
        if res:
            if log:
                log(f"      🖼️  image « {q} » ({res[2]}, thème vérifié)")
            return res
    res = _loremflickr(",".join(en[:2]), out_dir, lock=(len(used) + 1 if used else 1))
    if res and log:
        log(f"      🖼️  image « {' '.join(en[:2])} » ({res[2]})")
    return res
