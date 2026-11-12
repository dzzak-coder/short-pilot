# Point de reprise ShortPilot — pipeline visuel simple

Pause demandée par l’utilisateur le 6 novembre 2026, pour continuer plus tard.

**Correction en cours, non validée. Aucune nouvelle image générée pendant cette session. Aucune publication, aucun Short complet. La suite complète finale n’a pas encore été exécutée.**

## Demande à conserver

Revenir au pipeline textuel simple construit dans `core/aiimg.py`, sans guides structurels, ControlNet, régions ou remplacement du sujet par un décor. Ne jamais réintroduire le fallback « A single useful object… ». Conserver les preuves des essais précédents.

Ne modifier ni checkpoint, sampler, étapes, CFG, dimensions, upscale, ni les fichiers real_final. L’évolution du mode qualité est une étape séparée. Conserver API, interface, voix, musique, montage, bibliothèque, publication et protections existantes.

Après correction et revue du code : exécuter la suite complète sur le code final, puis UNE SEULE image réelle, seed **70001**, via le workflow rapide, positif **6**, négatif **7**. Si elle échoue, enregistrer `accepted: false`, fournir l’image et le rapport, puis arrêter sans autre seed ni architecture.

Source : « Un minuteur rouge sur un bureau en bois, à côté d’un planning fermé, lumière du matin ».

Critères visuels : minuteur rouge reconnaissable, bureau en bois, planning fermé avec sa couverture visible et aucune page intérieure visible, lumière du matin, aucune plante ou autre accessoire dominant non demandé.

## Modifications présentes dans le répertoire

- `core/aiimg.py` : constructeur simple à sept nœuds pour le mode rapide ; suppression des branches de guide, de régions et de ControlNet. Le positif conserve exactement le plan. Les exclusions de scène sont fusionnées et dédupliquées avec le négatif technique et le contrôle humain. Ajout de `executed_negative_prompt`, `negative_prompt_verified`, et initialisation des indicateurs à faux avant vérification de l’historique exécuté. Le graphe exécuté entier doit être identique au graphe soumis.
- `core/content.py` : `VISUAL_PLANNER_VERSION = 5`, invalidant les anciens plans automatiques.
- `core/visual_planner.py` : suppression du glossaire spécifique au cas minuteur/planning. Contrat atomique générique avec catégorie, propriétaire `entity`, extrait source, formulation anglaise et exclusions facultatives. Catégories : sujet, couleur, nombre, secondaire, état, action, décor, lumière, relation. Validation de couverture source ; réparation textuelle bornée ; erreur explicite au lieu d’un objet générique. Les CTA conservent le sujet de référence. Aucun enrichissement régional ultérieur.
- `core/visual_constraints.py` : remplacé par un compilateur purement textuel. États ouverts/fermés selon une forme physique générique (`bound_volume`, `container`, `door`, `other`). Pour un volume relié fermé : couverture opaque visible et couvertures jointes, contre-exemples liés à cet objet. Les restrictions d’accessoires s’appliquent uniquement aux natures mortes classées comme telles, sans humain.
- `core/structural_guide.py` : supprimé.
- `core/render.py` : transmet exactement le plan, sans normalisation ou troncature ; propage et déduplique les exclusions. L’exclusion humaine reste ajoutée dans aiimg uniquement.
- `app.py` : suppression de la conversion/troncature silencieuse des plans conservés ; leur validité est contrôlée avant rendu.
- `tests/test_visual_contract.py`, `tests/test_visual_states.py` : tests de transport, conservation des termes, états génériques, genres de scènes, négatifs dédupliqués, rejet d’un historique ComfyUI altéré et absence d’activation des anciens contrôles expérimentaux.
- `tools/verify_visual_states.py` : ancien outil multi-essais remplacé par les étapes `--plan`, `--test`, `--generate`. Seed/checkpoint fixes, empreinte du code, marqueur exclusif interdisant une deuxième image. **La revue sémantique du plan doit être réussie pour générer.**
- `COMFY_VISUAL_MODES.md` : documentation actualisée, sans prétention de réussite visuelle.

Les profils rapide/qualité et la fonction `_quality_workflow` ont été comparés à leurs instantanés de début de session : identiques. Aucun fichier real_final modifié pendant cette session. Le modèle ControlNet précédemment téléchargé reste inactif sur disque ; aucun téléchargement ou chargement ajouté.

Attention : le répertoire était déjà très modifié, avec de nombreux fichiers non suivis. Ne pas attribuer tout le diff à cette correction et ne pas faire de restauration Git globale.

## Vérifications réellement effectuées

Dernier lancement ciblé :

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_visual*.py' -v
```

**34 tests passent, en 0,933 s.** Ce sont des tests ciblés, avec réponses sémantiques simulées ; ils ne prouvent pas la qualité du modèle texte réel ni celle d’une image. Le dernier petit changement du garde-fou dans l’outil de preuve a ensuite été vérifié par compilation syntaxique.

```powershell
.venv\Scripts\python.exe -m py_compile app.py core/aiimg.py core/content.py core/render.py core/visual_planner.py core/visual_constraints.py tools/verify_visual_states.py
```

Compilation réussie. **Ne pas annoncer que toute la suite finale passe.** Les anciens nombres de 104/127 tests appartiennent à des états antérieurs.

Plusieurs prévalidations exclusivement TEXTUELLES ont été exécutées avec Ollama local, via `--plan`. Aucune demande d’image ComfyUI n’a été envoyée. Le dernier plan passe la présence des quatre expressions attendues, mais échoue à la revue sémantique, comme détaillé ci-dessous.

## Blocage exact à résoudre en premier

Le fichier `outputs/simple_visual_v5_validation/plan.json` est **rejeté**, avec `semantic_review.passed: false`.

La réponse réelle du modèle texte a :

1. attribué le mot source « fermé » au minuteur (`closed timer`), alors qu’il décrit le planning ;
2. également attribué cet état au planning, en réutilisant le même extrait sans vérifier son propriétaire ;
3. classé le planning papier comme `container`, au lieu de `bound_volume`, empêchant l’ajout de la preuve de couverture visible et de l’exclusion des pages exposées.

**La couverture lexicale de la source et la présence de required_terms ne suffisent donc pas.** Il reste à corriger et vérifier génériquement le lien attribut/état ↔ objet et la classification physique. Ne créer aucune règle liée aux mots minuteur ou planning. Ajouter des régressions sur plusieurs objets et sur ce rejet réel, au lieu de considérer les réponses simulées comme une preuve suffisante.

Pour cette dernière prévalidation, le titre global est l’exemple anglais fourni par l’utilisateur : « A red kitchen timer on a wooden desk next to a closed planner, soft morning sunlight ». Cette donnée de fixture est consignée dans `plan.json` et n’est pas un dictionnaire de traduction en production. Ne pas présenter ce résultat comme une traduction automatique validée à partir de la seule source française.

Ne pas réutiliser ce plan rejeté pour une génération. Son empreinte correspond en outre à un état antérieur au dernier garde-fou de l’outil : il faudra le régénérer après correction.

## Reprise, dans cet ordre

1. Lire les instructions du projet et `.agents/skills/shortpilot-result-first/SKILL.md`, puis ce point de reprise. L’utilisateur veut des résultats concrets et peu de commentaires intermédiaires.
2. Corriger uniquement la liaison sémantique générique et sa validation ; terminer la revue de la chaîne scenes → visual_plans → visual_controls → render → aiimg → CLIP. Les états erronément attribués doivent être rejetés avant ComfyUI.
3. Refaire la prévalidation textuelle et inspecter réellement les propriétaires, formes, relations et exclusions. Inscrire la revue comme réussie uniquement si elle l’est. Garder les anciennes preuves.
4. Exécuter la suite complète sur l’état final. L’outil `--test` exécute actuellement la suite Python ; les tests JavaScript existants sont aussi à considérer dans la vérification complète. Aucun test final complet n’a été lancé à ce point d’arrêt.
5. Seulement ensuite, une seule génération réelle avec `--generate`, seed 70001 et workflow minimal. Ne pas contourner le marqueur exclusif ou réinitialiser les preuves pour réessayer.
6. Inspecter l’image puis consigner honnêtement `accepted`. Fournir image, seed, plan, prompts soumis, textes réellement exécutés des nœuds 6/7, `.visual.json` et résultats finaux. Si échec : false et arrêt.

L’environnement Python s’utilise via `.venv\Scripts\python.exe`. Les appels aux services locaux peuvent nécessiter l’exécution hors sandbox ; un refus réseau de la sandbox ne prouve pas que le serveur est arrêté.

## Processus et preuves

Le contrôle initial des ports était incomplet : une vérification ultérieure des arguments des processus a retrouvé l’instance de test **PID 4844, --port 8189**. Elle a été ciblée avec `Stop-Process` après revalidation de sa ligne de commande. Les processus ComfyUI observés avec **--port 8188**, PID **25232** et **21688**, ont été conservés. Ne pas arrêter les instances principales ni utiliser une fermeture globale des processus Python.

Les preuves historiques restent dans `outputs/visual_states_validation`, `outputs/timer_universal_validation` et les autres dossiers d’origine. Le dernier essai ControlNet historique est un échec, pas une base validée. Le dossier `outputs/simple_visual_v5_validation` ne contient à cette pause qu’un plan textuel rejeté ; ni nouvelle image, ni rapport de génération réussie, ni résultat de suite finale.
