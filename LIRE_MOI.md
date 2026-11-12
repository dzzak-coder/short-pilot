# LIVRAISON — FICHIERS À INTÉGRER DANS LE DÉPÔT

**Destination :** `C:\Users\farhi\OneDrive\Desktop\ShortPilot STUDIO\shortpilot\`
**Contenu :** 7 fichiers, 3 dossiers.
**Aucune génération d'image. Aucune modification de modèle, workflow ou artefact de preuve.**

---

## 1. Copie

Extraire l'archive à la **racine du dépôt**, en conservant l'arborescence :

```
fix_prompts/__init__.py
fix_prompts/anchor_translations.py
fix_prompts/prompt_builder.py
fix_prompts/PROMPTS_V2.txt
tools/normalize_tts_text.py
tools/prepare_narration.py
diag/diagnose_campaign_mapping.py
```

> **Attention :** `tools/normalize_tts_text.py` et `tools/prepare_narration.py` vont dans le dossier `tools/` **du dépôt**, à côté de `run_kheops_campaign.py` et `assemble_kheops_campaign.py`. L'archive les place au bon endroit.

`fix_prompts/__init__.py` est présent mais vide : nécessaire pour que `fix_prompts` soit un paquet importable.

---

## 2. Empreintes à vérifier avant intégration

```powershell
Get-FileHash fix_prompts\prompt_builder.py, fix_prompts\anchor_translations.py, fix_prompts\PROMPTS_V2.txt, tools\normalize_tts_text.py, tools\prepare_narration.py, diag\diagnose_campaign_mapping.py -Algorithm SHA256 | Select-Object Hash,Path
```

| Fichier | SHA-256 attendu |
|---|---|
| `fix_prompts/prompt_builder.py` | `43159722caf7b6b62751bb1b995366c59156755e0077d25c2552eec235577de1` |
| `fix_prompts/anchor_translations.py` | `3ccc57c0db9cee8043b95da0fb282b06424660ebb740d48fe42d55deff2c2688` |
| `fix_prompts/PROMPTS_V2.txt` | `70f697e579c46176ee825fce6db7a98fb678d124d6c0e077d945757895b4705d` |
| `tools/normalize_tts_text.py` | `add445c650b05ece14fe1df98d9b6623b15ebfb1ef2c5a134d0a2c32ca3db9d0` |
| `tools/prepare_narration.py` | `c06b00b67488bf9d013726df24b94f041ecae40ea3a9a7bbf200025abf631b77` |
| `diag/diagnose_campaign_mapping.py` | `b8d28531d3d1560ed68efe489a5abe5f2baa1bf9f490b3f6710daff210d5f7f9` |

**Un hash qui ne correspond pas = fichier corrompu ou modifié. Ne pas intégrer avant explication.**

---

## 3. Changement d'approche à acter

**`fix_prompts/prompt_builder.py` EST la version canonique.** Il remplace et supplante :

- la génération de prompt actuellement branchée dans `core/content.py` ;
- les fonctions `framing_for` / `build_image_prompts` de la version antérieure d'`anchor_translations.py` (conservée uniquement pour `translate_anchor` / `EXCLUDED`, et **non utilisée** par le builder v2).

**`prompt_builder.py` est volontairement AUTONOME.** Il ne dépend d'aucun autre module du projet :

- `EXCLUDED` et `category_from_id` sont définis localement ;
- la traduction passe par `SUBJECT_BY_ANCHOR`, **indexée par `anchor_id`**, et non par label.

Raison : `corridor` et `niche` sont des mots anglais valides. Une traduction par label, ou un contrôle « aucun mot français » par liste de mots, produit des faux positifs. `english_subject(anchor_id)` lève `ValueError` si l'ancrage est inconnu — **jamais** de repli en français.

### Ce que le v2 change concrètement

| Point | Implémentation antérieure | `prompt_builder.py` (canonique) |
|---|---|---|
| Contexte | `inside or around the Great Pyramid` partout | **EXT / INT séparés**, avec lumière cohérente (10 EXT / 13 INT) |
| `mechanism` | catégorie unique → `système de décharge` en close-up | **scindée** : les volumes sont en plan large, seuls les objets en close-up |
| Style | absent | `Documentary photograph, 35mm, natural colour, fine grain, no text, no people.` sur les 23 |
| Traduction | par label français | **par `anchor_id`** (`SUBJECT_BY_ANCHOR`) |
| Doublons | variantes de cadrage par catégorie | variantes **par ancrage** (`VARIANT`), `ValueError` si unicité impossible |
| Répétition du sujet | « Great Pyramid of Khufu » écrit 2× | supprimée quand le sujet est déjà dans le contexte |

**Résultat vérifié :** 23 prompts, **23 distincts**, 10 EXT / 13 INT, style présent sur 23/23.

---

## 4. API à brancher (Phase A1–A4)

```python
from fix_prompts.prompt_builder import build_image_prompts_v2

# assignments : liste de dicts {image_index, scene, anchor_id, label}
prompts = build_image_prompts_v2(assignments, log=print)

# -> liste de dicts {image_index, scene, anchor_id, label, prompt, exterior}
#    Les ancrages exclus (basilique, cathédrale, île, canal, momie) sont
#    journalisés puis écartés : ils ne produisent aucun prompt.
```

Autres fonctions utiles :

- `build_prompt_v2(anchor_id, label)` → un prompt unique
- `english_subject(anchor_id)` → sujet anglais, `ValueError` si inconnu
- `context_for(anchor_id)` → contexte EXT ou INT
- `framing_for_v2(anchor_id)` → cadrage
- `is_exterior(anchor_id)` → booléen
- `SUBJECT_BY_ANCHOR` → table des 39 sujets indexés par `anchor_id`

### Critères d'acceptation (A2–A4)

| # | Test | Attendu |
|---|---|---|
| A2 | Unicité | 23 prompts, 23 distincts ; `ValueError` sur doublon |
| A3 | Absence de français | Contrôle sur `SUBJECT_BY_ANCHOR`, **pas** sur une liste de mots (faux positifs `corridor` / `niche`) |
| A4 | Exclusions | `basilique`, `cathédrale`, `île`, `canal`, `momie` → écartés, jamais injectés |

---

## 5. Outils de narration (Phase C)

### `tools/normalize_tts_text.py`

Normalisation déterministe, hors ligne, sans IA. Idempotente.

```
239 m          -> 239 mètres
m3             -> mètres cubes
26° 26′        -> 26 degrés 26 minutes
2 500 av. J.-C.-> 2 500 ans avant Jésus-Christ
Khéops         -> Kéops
Gizeh          -> Guizè
Hérodote       -> Érodote
```

CLI : `--file`, `--ssml`, `--spell-numbers`, `--out`, `--json`.

### `tools/prepare_narration.py`

```python
from tools.prepare_narration import prepare_scenes, write_report

prepared = prepare_scenes(scenes, language="fr")
for scene in prepared["scenes"]:
    synth(scene["text_tts"])        # JAMAIS scene["text_original"]

write_report(prepared, "outputs/<campagne>/narration_report.json")
```

Produit : `text_original`, `text_tts`, `sha256_original`, `sha256_tts`, `chars`, `seconds_estimated`, le **diff** de chaque scène modifiée, et `sha256_texte_envoye`.

Refuse une langue non française : la table `PRONUNCIATION` est calibrée pour le fr.

### RAPPEL CRITIQUE — décision CPS (§6.5 de la passation)

La normalisation **allonge le texte de +13,2 %** (mesuré : 355 → 402 caractères sur 6 phrases Khéops, soit 3,3 s sur 25 s).

- **Budget de durée, nombre de mots, budget visuel : sur le texte BRUT.** Inchangé.
- **Seul le texte envoyé à Hortense est normalisé.**
- Journaliser les **deux** longueurs et les **deux** SHA-256.
- **Aucun recalibrage de CPS. Aucune mesure `ffprobe` supplémentaire.**

Le `sha256_texte_envoye` change par rapport aux assemblages antérieurs : **c'est attendu et correct.**

---

## 6. Outil de diagnostic

### `diag/diagnose_campaign_mapping.py`

```powershell
.venv\Scripts\python.exe diag\diagnose_campaign_mapping.py outputs\kheops_campaign_2026-11-10
```

Liste les PNG avec leur SHA-256, extrait tous les prompts des rapports JSON (descente récursive), signale ceux qui ne contiennent aucun terme du sujet.

**Note :** ce script a servi au diagnostic D1 et a rempli son rôle. Il n'est plus indispensable maintenant que la cause est connue, mais il reste utile comme contrôle de non-régression après régénération.

---

## 7. Pièges spécifiques à ces fichiers

| Piège | Réalité |
|---|---|
| `python` n'existe pas dans le PATH | `.venv\Scripts\python.exe` |
| `pytest` sur `normalize_tts_text` | Le fichier de test fait un `SystemExit` → `INTERNALERROR`. Lancer avec `python test_normalize_tts.py` (sortie `OK`) |
| `prepare_narration` importe en relatif | Un `try/except ImportError` gère l'exécution directe depuis `tools/`. Ne pas le « nettoyer » |
| `prompt_builder` paraît dupliquer `anchor_translations` | Non : il est autonome **par choix**. Ne pas rebrancher `translate_anchor` dedans |
| `PROMPTS_V2.txt` | Fichier de **contrôle**, pas une source. Il doit rester identique au hash `70f697e5…` |

---

## 8. Ce qui suit (rappel du plan)

1. **A1–A4** : brancher `build_image_prompts_v2`, écrire les tests, tout vert.
2. **A5** : produire les 23 prompts et **s'arrêter** pour validation humaine écrite.
3. **B1** : vérifier le format réel des PNG sortants (720×1280, 9:16 — les captures fournies montrent du quasi-carré, à contrôler avant toute génération).
4. **B2–B7** : campagne neuve, un seul `POST`, inspection des 23 images, `accepted: null`.

**Aucune génération d'image avant validation explicite à A5.**

---

## 9. AJOUT — CHAÎNE DE NARRATION SSML (corrige l'effet « haché »)

### 9.1 Ce qui est corrigé

L'assemblage actuel synthétise **19 WAV séparés** puis les colle avec 0,55 s de silence. Chaque clip démarre et finit à plat : aucune continuité d'intonation entre les phrases. C'est une part importante de l'effet « robotique » perçu, **indépendamment du timbre SAPI**.

Deux nouveaux fichiers :

| Fichier | Rôle |
|---|---|
| `tools/build_ssml_narration.py` | texte normalisé → **un seul** document SSML, avec `<mark>` et `<break>` |
| `tools/synthesize_ssml_hortense.ps1` | SSML → **un seul** WAV + JSON des temps exacts par scène |

### 9.2 Pourquoi c'est mieux que l'assemblage actuel

| Aspect | Avant | Après |
|---|---|---|
| Synthèse | 19 passes isolées | **1 passe continue** |
| Pauses | silences collés après coup | `<break time="550ms"/>` prononcés par le moteur |
| Synchronisation | durées estimées, dérive possible | `<mark>` → temps exacts via `BookmarkReached` |
| Débit | `atempo` sur l'audio fini (dégrade) | `<prosody rate>` **à la source** (ne dégrade pas) |

### 9.3 Point capital — `prosody rate` ≠ `atempo`

- **`atempo`** étire un signal déjà synthétisé → artefacts, effet métallique accentué. La règle « `atempo` ≥ 1,0 » existe précisément pour éviter ça.
- **`<prosody rate>`** demande au moteur de parler plus ou moins vite **nativement** → aucune dégradation.

Ce sont deux leviers différents. Le second est celui à utiliser pour ajuster le débit. Le premier ne doit rester qu'un secours technique.

### 9.4 Usage

```powershell
# 1. normalisation (obligatoire, avant tout)
.venv\Scripts\python.exe -c "
from tools.prepare_narration import prepare_scenes
import json
scenes = json.load(open('scenes.json', encoding='utf-8'))
r = prepare_scenes(scenes['scenes'], language='fr')
json.dump(r['scenes'], open('scenes_tts.json','w',encoding='utf-8'), ensure_ascii=False)
"

# 2. SSML
.venv\Scripts\python.exe -c "
import json
from tools.build_ssml_narration import build_ssml, write_ssml
scenes = json.load(open('scenes_tts.json', encoding='utf-8'))
doc = build_ssml(scenes, rate='+0%')
write_ssml(doc, 'narration.ssml')
print(doc['scene_count'], 'scènes,', len(doc['marks']), 'marques')
"

# 3. synthèse
.\tools\synthesize_ssml_hortense.ps1 -SsmlPath narration.ssml -OutPath narration.wav
```

### 9.5 Réglage du débit — à faire à l'écoute

`RATE_OPTIONS` propose `+0%`, `-5%`, `-10%`, `-15%`.

**`-10%` est la valeur la plus prometteuse** pour atténuer l'effet robotique : un débit légèrement plus lent rend les transitions entre syllabes moins abruptes. À valider à l'oreille, pas par principe.

Attention : ralentir **allonge la durée**. Tout changement de débit impose de recalculer le budget visuel. Mesurer avec `ffprobe` après chaque essai.

### 9.6 La phonétique — pourquoi elle manque encore

Le MP4 `voice-fix2` a été produit **avant** `normalize_tts_text.py`. La normalisation n'est donc **pas** dans ce fichier : `Khéops`, `m3`, `av. J.-C.` partent encore en clair.

Elle sera branchée en Phase C. Le `sha256_texte_envoye` changera : c'est attendu.

Rappel de la décision CPS (§6.5 de la passation) : budget de durée sur le texte **brut**, envoi de la voix sur le texte **normalisé**. Aucun recalibrage.

### 9.7 Limite honnête

Hortense reste une voix SAPI de 2009. La synthèse continue, les pauses natives et la normalisation la rendent **nettement plus écoutable** — elles ne la rendront pas humaine. Ne promets pas l'inverse à l'utilisateur, et ne cherche pas à l'obtenir en réglant la voix : le seul levier restant est le texte.

---

## 10. AJOUT — CONTRÔLE PLAN ↔ GRAPHE COMPILÉ (à faire AVANT tout `POST /prompt`)

### 10.1 Le trou dans la procédure

`plan.json` peut être parfait et le **graphe compilé faux**. Le bug d'origine (étiquettes françaises injectées brutes) a produit 23 images **correctement associées** à leurs scènes, avec des **prompts faux**. Un contrôle « 23/23 plans conformes » ne l'aurait jamais vu : il faut comparer le **texte**, pas les index.

Rien dans la procédure actuelle ne vérifie que le texte présent dans les nœuds `TextEncodeQwenImage21` est bien celui du plan.

### 10.2 `tools/verify_compiled_prompts.py`

```powershell
# a) contrôle du plan seul (rapide, avant compilation)
.venv\Scripts\python.exe tools\verify_compiled_prompts.py outputs\kheops_campaign_2026-11-11-v2\plan.json

# b) contrôle plan <-> graphe compilé (le contrôle décisif)
.venv\Scripts\python.exe tools\verify_compiled_prompts.py plan.json workflow.json
```

**Ce qu'il vérifie :**

| Contrôle | Détail |
|---|---|
| Unicité | 23 prompts distincts, sinon liste les doublons |
| Mots français | Recherche par **mot entier** (pas sous-chaîne), sans faux positif sur `corridor`/`niche` |
| Contexte | `egypt` / `great pyramid of khufu` / `giza` présent sur chacun |
| Longueur | Signale le max en tokens (T5 tronque à 512) |
| **Plan ↔ graphe** | Chaque prompt du plan est présent **tel quel** dans un nœud ; liste les **absents** et les **textes parasites** |
| Correspondance | Affiche `image N -> nœud X/inputs/prompt` pour les 23 |

**Code de sortie :** `0` = OK, `1` = échec. Utilisable en garde avant génération.

### 10.3 Résultats des tests de l'outil (fixtures)

Outil validé sur trois cas construits à la main :

| Cas | Attendu | Obtenu |
|---|---|---|
| Plan seul, cohérent | OK / exit 0 | OK / exit 0 |
| Plan + graphe identique | OK / exit 0 | OK / exit 0 |
| Plan + graphe contenant un ancien prompt français | ÉCHEC / exit 1, image fautive identifiée | ÉCHEC / exit 1, `image 1 -> ABSENT`, texte parasite listé |

**Le troisième cas est exactement le bug d'origine.** L'outil l'attrape.

### 10.4 Intégration dans la Phase B

Avant le `POST /prompt` unique :

1. `verify_compiled_prompts.py plan.json` → doit sortir `0`.
2. Compiler le graphe **sans l'envoyer**, l'écrire sur disque.
3. `verify_compiled_prompts.py plan.json workflow_compiled.json` → doit sortir `0`.
4. **Seulement ensuite** le `POST /prompt`.

Un échec au point 3 invalide la campagne : ne pas générer, corriger le compilateur.
