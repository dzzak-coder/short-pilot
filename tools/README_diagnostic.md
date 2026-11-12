# Diagnostic de planification visuelle — mode d'emploi

Outil : `tools/diagnose_line_planning.py`
But : voir, ligne par ligne, **ce qui est demandé au rendu** — avant toute image.
Aucun `POST /prompt`. Aucune image. Aucune publication.

## Pourquoi cet outil

Trois défauts possibles sont souvent confondus :

- le planificateur choisit un mauvais sujet → l'image est hors sujet ;
- des personnes apparaissent sans être demandées → l'image est habitée à tort ;
- deux lignes demandent le même rendu → le résultat peut paraître répétitif.

Ces trois causes se corrigent à des endroits différents. Le diagnostic les sépare au lieu de
les deviner.

## Installation

Le script est installé dans `tools/diagnose_line_planning.py`.

Le script résout lui-même les modules : `core.content` / `core.local_resources` quand il est
lancé depuis la racine du dépôt, `shortpilot.core.*` si le paquet est importé depuis le dossier
parent. Il fonctionne depuis la racine comme depuis `tools/`.

## Format d'entrée

Script complet :

```json
{
  "title": "Le minuteur rouge",
  "niche": "productivite",
  "language": "fr",
  "scenes": ["ligne 1", "ligne 2", "ligne 3"]
}
```

Ou simplement une liste de lignes :

```json
["ligne 1", "ligne 2", "ligne 3"]
```

## Vérification préalable (aucun service contacté)

```bat
.venv\Scripts\python.exe tools\diagnose_line_planning.py --dry-run
```

Aucun fichier requis. Affiche les modules réellement résolus et les effets de bord, sans appeler
Ollama ni ComfyUI et sans entrer dans `text_phase`.

## Exécution

```bat
.venv\Scripts\python.exe tools\diagnose_line_planning.py scripts\mon_script.json
```

Avec archivage du JSON pour comparaison ultérieure :

```bat
.venv\Scripts\python.exe tools\diagnose_line_planning.py scripts\mon_script.json --out rapports\diag_avant.json
```

## Effets de bord — à connaître avant de lancer

L'outil ne produit aucune image et n'écrit aucun fichier du dépôt — **sauf le rapport JSON
demandé explicitement avec `--out`**. En revanche il n'est **pas neutre** sur l'état des
services :

- `text_phase` envoie **`POST /free`** à ComfyUI s'il tourne (libération mémoire) ;
- il charge réellement **qwen3.8:27b** dans Ollama, puis le **décharge** à la fin ;
- si un rendu ComfyUI est en cours, le précontrôle de phase texte **échoue** au lieu de
  l'interrompre — c'est le comportement attendu, pas un bug.

Ne pas lancer pendant un rendu. `--dry-run` évite tout contact réseau.

## Ce que l'outil fait

- ouvre `local_resources.text_phase` — donc `/free` sur ComfyUI s'il tourne, puis Ollama ;
- appelle le planificateur Qwen3.8:27b ;
- **ne ferme jamais vers une phase rendu**, ne soumet rien ;
- décharge Ollama à la sortie, y compris en cas d'erreur.

## Ce que le rapport affiche

Par ligne : le texte, le type de scène, l'objet d'ancrage, les objets secondaires, les faits
atomiques avec leur extrait source et leur traduction, et le prompt final compilé.

Puis une synthèse :

| Contrôle | Ce qu'il révèle |
|---|---|
| Ancrages distincts | diversité des sujets d'ancrage planifiés |
| Ancrages répétés | sujet identique réutilisé |
| PROMPTS COMPILÉS IDENTIQUES | même demande de rendu ; ne compare ni la ressemblance ni les pixels des images. |
| PERSONNES NON DEMANDÉES | `person`/`hands` alors qu'aucun mot de personne n'est dans le script |
| CONTINUITÉ ROMPUE | même objet décrit différemment selon la ligne |
| Lignes longues | risque d'écrasement de la ligne en un seul sujet |
| Erreurs de planification | lignes rejetées par le validateur |

## Lecture des résultats

- **Beaucoup d'ancrages répétés** → problème de sélection du sujet. C'est le registre visuel
  qui corrige, pas le rendu.
- **Prompts compilés identiques** → les accroches/CTA dupliquent la scène d'ancrage. Attendu par le code
  actuel, à décider : variante de cadrage ou image différente.
- **Continuité rompue** → le même objet est réinventé à chaque ligne. C'est exactement ce que
  le registre visuel doit figer.
- **Personnes non demandées** → erreur de classification du planificateur, la plus simple à
  corriger et la plus visible.

## Limites assumées

**Sur les plans réels.** Le test mocké valide le câblage et l'affichage, pas la qualité des plans.
Il ne dit rien de ce que le vrai planificateur produira sur tes scripts.

**Sur l'image.** Ce diagnostic ne prouve **rien** sur l'image. Il montre seulement ce qui est
demandé au rendu. Un plan correct peut encore produire une image fausse — c'est le rôle du
chantier 3. Un plan fautif risque de produire une image inadaptée ; seul l'examen de l'image
permet de constater le résultat visuel.

## Ce qu'il faut faire des résultats

1. Faire tourner l'outil sur **deux scripts de niches différentes**.
2. Archiver les deux JSON.
3. Comparer : les défauts sont-ils structurels ou propres à un script ?
4. Transmettre les rapports avant toute modification du planificateur.

Aucune modification de prompt, de modèle, de workflow ou de sampler n'est demandée à ce stade.
