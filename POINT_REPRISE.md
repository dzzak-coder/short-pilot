# Point de reprise — ShortPilot Studio

**Tâche visuelle en pause au 6 novembre 2026 : lire d’abord [POINT_REPRISE_VISUEL_SIMPLE_2026-11-06.md](POINT_REPRISE_VISUEL_SIMPLE_2026-11-06.md). Correction non terminée ; aucune nouvelle image autorisée avant revue et tests finaux.**

Mis à jour le 27 octobre 2026. **Denise est validée à l’écoute sur une F1 et un robot. Dernier correctif : Lecture conserve désormais séparément le rendu et la caméra choisis.** CAD et n8n OAuth restent en attente.
**Recherche Objaverse validée dans Chrome le 26 octobre.** Parcours réel ShortPilot → Studio 3D intégré → Objaverse → saisie « Formula 1 car » → clic Chercher → 10 cartes de résultats visibles. Téléchargement/import GLB et qualité d’assemblage restent à valider séparément.
Les sections archivées en fin de fichier décrivent un état ancien, pas la tâche actuelle.

### Dernier état vérifié — narration Objaverse

- **Décision utilisateur à conserver : Denise, femme naturelle, est la voix sélectionnée pour toute la narration Objaverse.** Rémi, homme dynamique, est accepté côté backend pour un futur choix masculin. Ne plus demander quelle voix choisir à la prochaine reprise.
- **Intégration Denise implémentée côté backend.** `core/voice.py` réutilise Edge-TTS, le moteur de **Créer → Voix off**, et génère le texte complet dans un unique MP3 avec `fr-FR-DeniseNeural`. Le cache distingue texte, voix et débit. `/api/local-tts/speak` accepte `voice_id`, sert `audio/mpeg` et rejette les voix inconnues. Aucun repli vers Paul, gTTS ou une autre voix n’est autorisé pour ce parcours.
- **Intégration continue implémentée côté Studio.** Les imports Objaverse utilisent `voicePolicy: single_track` et `voiceId: fr-denise`. Les huit actes sont envoyés en une requête, décodés dans un seul tampon et lus par une seule source à vitesse native. La lecture reprend au décalage correspondant à la progression, redémarre proprement au rebouclage et la durée visuelle est alignée sur la durée réelle de la piste. Web Speech et OneCore sont interdits pour ce plan.
- Le badge reconnaît le mode backend `edge_tts:fr-denise` et affiche **« DENISE — FEMME, NATURELLE »**. Cette dernière correction de compatibilité du badge comporte deux lignes et n’a pas été suivie d’un nouveau build à cause de l’interruption par la limite.
- **Vérifications terminées avant la pause :** appel Edge-TTS réel réussi avec Denise, MP3 de 22 752 octets et 3,79 secondes, mode `edge_tts:fr-denise`; 25 tests Python voix/Studio passent; 28 tests JavaScript passent; build Vite réussi. Le `git diff --check` des fichiers audio modifiés ne signale aucune erreur. Le tout dernier changement de badge doit néanmoins être couvert par une relance rapide des tests JavaScript et du build.
- **Audio validé à l’oreille par l’utilisateur.** Test réel F1 puis second test sur un robot à sept maillages : badge Denise, même voix du début à la fin et qualité jugée « excellente » puis « très très bien ». Le sous-agent navigateur a aussi confirmé une seule piste Edge-TTS continue, sans Paul ni Web Speech, pendant la progression du cycle visuel.
- **Styles et caméras indépendants validés.** Lecture ne force plus `timelapse_cad` quand un rendu statique est sélectionné. Hologramme, Brevet, Studio PBR, Blueprint ou CAO Ambre restent actifs, et la caméra choisie (trois-quarts ISO, face, dessus, côté, réalisateur CAO, orbite, manuel ou détail) n’est plus remplacée. Relancer depuis le début conserve également le rendu. Deux tests de régression dédiés ajoutés ; 30 tests JavaScript et build Vite passent. **Validation visuelle confirmée par l’utilisateur le 31 octobre 2026 : aucune action Studio restante.**
- Narration généralisée après retour utilisateur : suppression du traitement limité à la F1. Chaque import transmet maintenant le nom, la description et les tags du résultat Objaverse au narrateur, puis les combine avec le nombre et les noms de maillages réellement détectés. Profils sémantiques couverts : véhicules, aéronefs, architecture, personnages/créatures, mobilier, machines/robots, naval, spatial, plus repli universel. Testé automatiquement sur F1, cathédrale, robot, créature et sculpture ; les scripts diffèrent réellement et citent les pièces exploitables du fichier. Test navigateur réel supplémentaire : recherche puis import de « gothic cathedral », 24 maillages détectés, script architectural affichant assise, niveaux, façades, couverture et présence architecturale. 25 tests JavaScript et build Vite passent.
- Script F1 réécrit en huit séquences adaptées au cycle de 45 secondes : 91 mots, sujet monoplace, aucune reprise Eiffel. Import réel du modèle « formula1 racing car - low poly » vérifié dans Chrome ; les huit cartes du script s'affichent avec le bon titre.
- Voix OneCore Microsoft Paul FR ajoutée localement et cache WAV opérationnel au niveau technique, mais le parcours audible complet a échoué chez l’utilisateur comme décrit ci-dessus. Les huit MP3 Eiffel restent inchangés.
- Serveur ShortPilot redémarré sur la nouvelle route. Appel réel validé : réponse WAV `RIFF` de 108 622 octets.
- Vérifications techniques précédentes : 25 tests Python, 24 tests JavaScript et build Vite réussis. Elles ne valident ni le calage audible ni l’unicité de la voix ; le test utilisateur a révélé la régression actuelle.

## Pour continuer après interruption — Objaverse, 26 octobre

### Dernière vérification : recherche navigateur réparée

- Narration Objaverse corrigée ensuite : désélection du preset Eiffel et du script ShortPilot antérieur avant import, titre du modèle communiqué avant le callback d’analyse, nouveau commentaire en huit actes sans fichiers audio Eiffel ni matériaux/histoire inventés. Suppression du passage automatique en hologramme libre qui coupait les actes synchronisés. Test navigateur réel : import F1 low-poly réussi, 5 maillages, titre correct, huit actes propres au modèle, aucune occurrence Eiffel, case séquence active. Capture `tmp/objaverse_narration_verified.png`. 20 tests JS et build passent. Audio laissé silencieux pendant ce test : qualité audible non validée ; activation volontaire avec le bouton audio supérieur. Le modèle Aston Martin a également été observé avec 59 maillages et commentaire correct dans un autre onglet.

- Correctif suivant des carrés noirs : les cartes utilisent les vraies miniatures `thumbnails.images` du catalogue (hôte media.sketchfab.com, format proche de 720 px), avec message explicite si aperçu absent. Test Chrome intégré : trois premières F1 réellement chargées et visibles ; capture `tmp/objaverse_thumbnails_verified.png`. Un clic sur la première carte révèle immédiatement « Importer et assembler » et « Prévisualiser seul » au-dessus de la galerie, bordure de sélection cyan. Aperçus chargés progressivement au défilement. Build et 22 tests Python passent. Prévisualisation raccordée au téléchargement préalable, mais téléchargement/import encore non testé de bout en bout.

- Initialisation déplacée en fin de module après les variables Objaverse. Autre panne de démarrage corrigée : ajout du bouton HTML `btn-host-library` attendu par le code, en conservant le lien Pack Local.
- Erreur réelle de clic corrigée : `min_parts` n’était pas défini dans le JavaScript ; le corps JSON utilise maintenant `min_parts: minParts`.
- Case multi-maillages décochée par défaut car le catalogue n’en documente aucun. Cartes affichent « Découpage non renseigné », sans inventer un modèle monobloc ni des compteurs de zéro faces.
- Préparation : bouton désactivé, temps écoulé et nombre de modèles indexés affichés. Recherche : bouton « Recherche… », attente visible, délai client borné à 30 secondes. Le `finally` conserve le bouton désactivé si préparation active.
- Statistiques corrigées pour ne pas parcourir le dictionnaire pendant sa construction (erreur 500 possible). Tags extraits par leur nom, UID normalisés au format hexadécimal 32 caractères accepté par les routes, recherches anglaises connues sans appel de traduction externe.
- Vérification finale dans le navigateur Chrome connecté, sur une page ShortPilot réelle avec iframe Studio : 10 cartes F1 visibles après clic, notamment « formula1 racing car - low poly », « formula 1 car », « aston martin formula 1 car ». Capture `tmp/objaverse_f1_browser_verified.png`.
- Build réussi, 20 tests Python Studio et 19 tests JavaScript passent. Nouveau test de démarrage + clic Objaverse vérifie l’écouteur, le corps JSON envoyé et la remise en état après réponse vide.
- Serveur 8000 relancé après vérification des jobs ; journaux `tmp/objaverse_verified_server.log` et `.err`. Catalogue prêt sur cette instance. Rechargement navigateur nécessaire pour prendre le nouveau bundle ; pas besoin d’un nouveau redémarrage.
- Limite : le catalogue reste indexé en mémoire à chaque redémarrage du serveur ; les aperçus sans GLB en cache sont des emplacements réservés. Aucune importation F1 ni décomposition mécanique n’a été validée.

### Diagnostic antérieur conservé pour contexte (remplacé par la vérification ci-dessus)

- Demande utilisateur toujours autorisée : rendre la recherche Objaverse utilisable avec un état visible (préparation, recherche, résultat ou erreur), puis TESTER avant de livrer. Il a subi de nombreuses attentes et annonces prématurées : ne plus lui demander de relancer pour servir de testeur.
- **Défaut concret trouvé, PAS ENCORE CORRIGÉ :** `studio3d/src/main.js` appelle `window.initObjaverse()` vers la ligne 1641, alors que l’affectation `window.initObjaverse = initObjaverse` est seulement en fin de module (vers 2017). Sur un chargement frais, la propriété n’est pas encore définie : l’initialisation des écouteurs et des états Objaverse échoue. Les variables `let` Objaverse sont aussi déclarées après cet appel ; déplacer l’initialisation APRÈS leur déclaration et après la mise en place du module. Ne pas simplement remplacer l’appel global par l’appel local au même endroit.
- Prochaine action précise : corriger cet ordre d’initialisation, puis ouvrir réellement Studio 3D, cliquer Objaverse, saisir une recherche et vérifier le clic, les états visibles et la galerie. Tester sur la même instance servie à l’utilisateur. Le parcours navigateur n’a jamais été validé dans cette session.
- Backend actuel : `/api/studio3d/objaverse/prepare` démarre l’indexation dans un thread ; `/stats` expose `annotations_loaded`, `annotations_loading`, `annotations_error` ; `/search` renvoie 202 pendant la préparation. Verrou de préparation distinct du verrou d’indexation. POST exige Content-Type JSON, y compris `/prepare`.
- Frontend prévu : bouton « Préparation… » désactivé, interrogation du statut, puis « Chercher » ; clic → « Recherche… ». Vérifier aussi le `finally` de recherche, qui réactive actuellement le bouton même après une réponse 202. La classe d’attente a été corrigée de `loading-hidden` (inexistante) à `hidden`.
- Vérifications passées : build Vite réussi et 20 tests Python Studio passent. Test HTTP réel sur catalogue chargé : recherche `bicycle`, limite 1, `min_parts:1` → 200 avec « mountain-bicycle ». 798 759 modèles indexés. Aucun test réel F1 avec les options par défaut, aucun import GLB Objaverse validé visuellement.
- **Autre obstacle constaté :** les statistiques indiquent zéro modèle multi-maillage, tandis que la case « Multi-pièces seulement » est cochée par défaut. Les annotations n’établissent pas la nomenclature mécanique ; vérifier les champs réels avant d’utiliser ce filtre. Les tags reçus sont des objets, actuellement convertis en chaînes de dictionnaire. Les UID réels sont souvent 32 caractères hexadécimaux : les routes qui exigent 36 caractères et la normalisation UUID du cache doivent être harmonisées avant validation téléchargement/import.
- Objaverse 0.1.7 et dépendances installés dans `.venv`. Les 160 fragments d’annotations sont déjà dans le cache utilisateur Objaverse. Le chargement complet et son indexage en mémoire restent coûteux après chaque redémarrage. Ne pas affirmer que le cache disque évite cette préparation.
- Ancien `models/objaverse/annotations.json` de 3,1 Go supprimé à la demande explicite de l’utilisateur ; code désormais sans cette duplication. Cache des GLB conservé.
- Lors d’une restauration du Studio, des éléments HTML avaient été perdus : bloc `creation-status` et options/résultats Wikipédia/vision rétablis ; onglet Objaverse ajouté à `switchLeftTab`. Cela a corrigé les erreurs null.dataset et null.checked dans le code, mais pas validé tout le parcours navigateur.
- Dernier serveur lancé sur 8000 avec journaux `tmp/shortpilot_server.log` et `.err`. État actuel à revérifier ; ne pas arrêter des processus non identifiés ni relancer sans vérifier les tâches actives. Les redémarrages pendant le diagnostic ont été autorisés.
- Voix : huit MP3 de qualité de la démo Eiffel toujours présents. Pour de nouveaux objets, le pont Windows standard fournit la narration, plus robotique. Amélioration voix demandée pour APRÈS Objaverse ; ne pas réutiliser les paroles Eiffel pour une F1 et ne pas promettre un moteur neural local déjà installé.
- Le générateur texte a produit une roue et un bloc pour « Alpine F1 Team Châssis », avec descriptions détaillées mais géométrie insuffisante. Ce résultat n’est pas accepté. Objaverse ne garantit pas des pièces mécaniques séparées ni une reconstruction fidèle.
- Préserver les nombreuses modifications locales non commitées. Aucun sous-agent demandé. Appliquer le skill résultat d’abord.

## Dernier essai autorisé — moteur CAO séparé, 25 octobre

- L’utilisateur a autorisé le test de la chaîne plan structuré → bibliothèque CAO
  → raccordements calculés → animation existante, séparément du produit principal.
- CadQuery 2.8.0 installé depuis PyPI dans un venv Python 3.11 dédié sur E :
  `E:/ShortPilot-AI/CAD-Assembly-Trial/runtime` (environ 1,22 Go avec dépendances).
  Aucun changement à ComfyUI ou aux environnements Python existants.
- Code et documentation : `tools/cad_trial/`. Aucune nouvelle route ni bouton
  de génération ajouté à ShortPilot pour ce prototype.
- **Prototype volontairement limité à une charnière de quatre composants** :
  deux ailes à charnons complémentaires, axe traversant et rondelle. La bibliothèque
  NE contient PAS encore les pièces d’une moto, d’un vélo ou d’un hélicoptère.
- `request_plan.py` utilise Qwen Coder local pour générer des données JSON.
  Premiers essais rejetés (étape invalide puis noms de ports inventés) ; schéma
  JSON et noms de raccordements bornés ajoutés. Dernier essai réel en français
  réussi : plan enregistré dans `tmp/cad_assembly_hinge/ai.spec.json`, puis pièces
  fabriquées et contrôlées dans `tmp/cad_assembly_hinge/ai_result/`.
- Quatre solides valides, graphe connecté, résidu de raccordement nul et aucune
  interpénétration volumique détectée. Contrôle statique uniquement ; pas de
  certification mécanique ni de vérification des trajets d’insertion animés.
- Les repères de raccordement viennent des composants CAO ; leurs transformations
  sont calculées le long d’un arbre de connexions. Pas encore de solveur général
  de mécanismes articulés/bouclés.
- Script HoloScript exécuté dans un onglet de test du Studio existant : quatre
  pièces nommées, première aile seule à Fondation, pièces réunies à Finitions,
  quatre composants séparables dans la vue éclatée. Moteur d’animation inchangé.
- Suite : enrichir et valider la bibliothèque et les interfaces sur plusieurs
  objets complets. NE PAS présenter le résultat comme une génération universelle.

## État actuel — TRELLIS retiré le 25 octobre à la demande de l’utilisateur

- Bouton de test, routes, service et graphes TRELLIS retirés de ShortPilot.
- Serveur isolé 8189 arrêté ; dossier `E:/ShortPilot-AI/Trellis2-Trial` supprimé.
- Les cinq modèles ajoutés ont été vérifiés par SHA256 puis supprimés :
  **8 954 386 952 octets libérés** (environ 8,95 Go). ComfyUI, ses workflows
  préexistants et ses autres modèles sont conservés.
- Manifeste historique de retrait : `workflows/trellis2_trial_manifest.json`.
- Build réussi, 17 tests Python Studio et 18 tests JS passent après retrait.
  ShortPilot rechargé sans rendu actif ; rafraîchir la page pour retirer le bouton.
- Suite : étudier une génération CAO multipartie avec bibliothèque de composants,
  contraintes d’assemblage et vérification. Sources examinées :
  [AssemCAD](https://arxiv.org/html/2607.05123v1) et
  [Text-to-CAD Assembly](https://github.com/MountainClimberJiwen/text-to-cad-assembly).
  Ni installé ni testé. L’utilisateur a demandé la recherche et le compte rendu ;
  ne pas présenter ces projets comme une intégration déjà fonctionnelle.

## Historique de l’essai TRELLIS.2 du 25 octobre — retiré

### Rectification de l’objectif après retour utilisateur

**Le livrable est un objet reconnaissable qui s’assemble pièce par pièce en
hologramme 3D, piloté par le script. Un objet monobloc texturé ne remplit PAS
l’objectif, même si son affichage fonctionne.**

- Le script fournit déjà les étapes `foundation`, `structure`, `mechanism`,
  `envelope`, `finishes`. Le viewport calcule les fenêtres d’assemblage par étape
  et trie actuellement les pièces d’une même étape selon leur altitude.
- Le problème à résoudre est la production de vraies pièces géométriques
  reconnaissables, distinctes, correctement orientées et positionnées dans le
  même repère ; le moteur d’animation existe déjà.
- TRELLIS a été testé comme producteur de géométrie, mais son résultat monobloc
  ne valide pas l’assemblage. Ne pas présenter ce test comme la solution complète.
- Ne pas découper arbitrairement une coque en fragments pour simuler des pièces.
  Chaque pièce doit correspondre à un composant de l’objet et à une étape du script.
- Critère d’acceptation du prochain travail : montrer l’objet final reconnaissable,
  sa nomenclature réelle, puis la séquence où ces mêmes pièces se rejoignent sans
  changer leur géométrie ni leurs positions finales. La vue éclatée doit retrouver
  ces pièces. Une exécution sans erreur seule n’est jamais une validation visuelle.
- Piste à examiner : géométrie multipartie existante, ou génération de composants
  cohérents dans un repère commun. La reconstruction TRELLIS monobloc ne fournit
  pas automatiquement cette sémantique. Aucune nouvelle installation autorisée
  implicitement par cette rectification.

- Autorisé par l’utilisateur : test séparé sur E, supprimable à sa demande, sans
  remplacer les workflows existants. Quatre modèles TRELLIS Comfy-Org, plus BiRefNet
  (444 Mo, détourage requis après échec avec fond reconstruit), téléchargés et vérifiés
  par taille/SHA256 (environ 8,95 Go décimaux). Pas de custom node ni package ajouté.
- Serveur ComfyUI natif isolé sur **127.0.0.1:8189**, custom nodes désactivés,
  sorties `E:/ShortPilot-AI/Trellis2-Trial`. Modèles partagés avec le Comfy existant.
- Deux tests réels terminés : image de moto → forme GLB (39,77 s), puis texture
  avec forme en cache (54,32 s). Fichier texturé 4,2 Mo importé et examiné dans le
  Studio : moto reconnaissable, mais morceau de sol reconstruit en plus.
- Bouton séparé dans **Créer** : **Test TRELLIS.2 — texte → image → 3D**.
  Il lance une image RealVisXL locale, TRELLIS, une réduction à 100 000 faces,
  les textures, puis importe le GLB en Studio PBR. Suivi de tâche asynchrone,
  erreurs explicites, aucune substitution par le catalogue procédural.
- Import GLB corrigé pour conserver les matériaux et textures d’origine.
- Maillage uniquement : PAS de pièces mécaniques réellement séparées ni de
  garantie de fidélité universelle. Le mode reste expérimental.
- Sources : `core/trellis_trial.py`, `core/trellis_service.py` ; documentation et
  manifeste de retrait dans `workflows/TRELLIS_TRIAL.md` et
  `workflows/trellis2_trial_manifest.json`.
- Vérifications : 21 tests Python + 18 tests JS passent, build Vite réussi.
- Parcours complet depuis le bouton testé : demande française → image → GLB →
  import automatique. Ce premier parcours a révélé un fond reconstruit comme une
  boîte. Ajout du détourage natif BiRefNet et ImageCropToMask (fond noir) : même
  image retraitée, GLB corrigé en 70,75 s, importé et examiné sous plusieurs angles.
  Moto reconnaissable, fond parasite retiré, détails encore anguleux/approximatifs.
- ShortPilot rechargé avec le détourage corrigé. Rafraîchir Studio 3D pour voir le
  bouton et son suivi intégré. Aperçu conservé dans `tmp/trellis2_motorcycle_verified.png`.

## Studio 3D intégré le 24 octobre

### Correctif du 25 octobre au matin : délai et repli procédural trompeur

- Retour : « Construction de secours prête » après ~180 s. Logs Ollama : modèle
  bien chargé sur GPU, génération encore active (~2804 tokens) puis annulée lorsque
  le client serveur atteint le délai de lecture de 180 s. Ce n'était pas un Ollama absent.
- Première réponse de génération normale : délai augmenté à 240 s (vision garde
  180 s ; continuation déjà bornée à 120 s). Délai global client conservé à 400 s.
- Exceptions désormais distinctes : délai dépassé (504 MODEL_TIMEOUT), connexion
  impossible (503 MODEL_UNREACHABLE), erreur HTTP/communication (502). Toutes ces
  réponses bloquent explicitement la génération, sans code partiel.
- Le frontend n'utilise PLUS le catalogue procédural automatiquement lorsqu'un
  moteur IA choisi échoue, y compris lors d'un échec réseau/timeout du navigateur.
  Le moteur procédural reste un choix explicite dans le menu.
- 17 tests d'intégration passent, dont timeout vs connexion et erreur HTTP.
  Build Vite réussi. Serveur 8000 relancé en arrêtant parent ET enfant identifiés.
  Ne pas confondre ce correctif réseau/délai avec une validation de qualité 3D.

### Correctif du 25 octobre : JavaScript coupé en génération normale

- Retour : « Unexpected end of input » après ~196 s, parcours Wikipédia + Coder
  sans vision. Journal Ollama : sortie arrêtée à 3200 tokens. Le contrôle existait
  seulement sur la branche visuelle ; la branche normale renvoyait le fragment.
- Le backend lit désormais les fins de réponse Ollama ET LM Studio. Une seule
  continuation est autorisée pour le JavaScript tronqué, à la frontière exacte du
  fragment (y compris au milieu d’une chaîne). Reprise bornée à 2000 tokens/120 s.
- Si la reprise est encore tronquée ou échoue : erreur explicite, aucun fragment
  renvoyé et aucun remplacement par un objet du catalogue dans l’interface.
- Vérification syntaxique par `node --check` sans exécution du code lorsque Node
  est installé. La vérification du navigateur reste présente. Une réponse annoncée
  terminée mais syntaxiquement invalide est également refusée avant assemblage.
- Tests ciblés : 14 tests d’intégration passent, dont coupure au milieu d’une
  chaîne, deux fournisseurs, seconde troncature, syntaxe invalide et absence
  d’exécution lors du contrôle. Essai réel de continuation Qwen : boîte volontairement
  coupée complétée en ~4 s, syntaxChecked=true. Ce test ne valide pas la qualité 3D.
- Build Vite réussi. Un script déjà coupé doit être régénéré, pas simplement réexécuté.
- Déploiement vérifié sur 8000 : deux anciennes instances Python restaient actives
  (chaque lanceur venv a un processus enfant). Arrêter seulement le PID d’écoute
  n’avait pas suffi : les deux paires de ce projet ont été arrêtées, puis une seule
  instance relancée. Réponse réelle désormais `syntaxChecked=true`, `continuations=0`
  sur une boîte de contrôle. Pour un futur redémarrage, identifier aussi les processus
  parents/enfants du lanceur, sans toucher à d’autres projets Python.

### Ajout du 25 octobre : références visuelles (autorisé par l’utilisateur)

- Qwen2.5-VL 7B téléchargé par Ollama, vérification SHA256 terminée ; modèles sur E,
  aucun nouveau service ni API payante. Coder 14B conservé pour le JavaScript.
- Nouveau module `core/studio3d_vision.py` : recherche Commons photos + diagrammes,
  jusqu’à 4 références affichées, 2 images analysées localement. Liste stricte des
  hôtes Wikimedia, pas de redirections, taille et dimensions bornées.
- Wikipédia fournit aussi le nom anglais du sujet ; recherche internationale plus
  pertinente (hélicoptère → Helicopter). Miniatures, licences et sources cliquables.
- Option Photos et schémas EXPÉRIMENTALE, DÉSACTIVÉE par défaut ; observations
  structurées transmises à Coder, consultables dans l’interface. Vision libère sa
  mémoire avant Coder. Aucun objet procédural de secours si l’analyse visuelle échoue.
- Ne plus présenter le plan procédural générique comme des pièces analysées : ce
  parcours confirme désormais une recherche à venir. Hélicoptère retiré du raccourci
  qui sélectionnait à tort le quadricoptère.
- Premier essai réel : images lues, mais observation trop générique. Deux essais de
  sortie numérique ont atteint la limite de tokens : rejetés, pas validés. Un schéma
  JSON borné a été ajouté pour corriger la troncature. Les observations restent
  qualitatives (formes/positions relatives), les coordonnées devinées par Vision
  se sont révélées non fiables et ne sont plus demandées.
- Test du code libre : exécution possible mais pièces encore sans `pos`, erreur de
  repère et faits historiques inventés. NON validé visuellement. Nouveau parcours
  général `core/studio3d_scene.py` : Coder décrit les volumes en JSON, validation
  stricte des positions finales/dimensions/matériaux/types et émission CAD contrôlée.
  Min 6/max 20 pièces, pas une bibliothèque ajoutée objet par objet. Maquette
  approximative, pas reconstruction mécanique exacte.
- Test final réel : 2 images lues, génération structurée en 107 s, 16 volumes créés
  et exécutés en navigateur sans erreur. MAIS contrôle visuel NON satisfaisant :
  fuselage globulaire, pales/queue déconnectées ou mal orientées, tout en verre.
  Ne pas annoncer l’hélicoptère corrigé. La capacité à trouver/lire les références
  est installée ; le passage observations → géométrie reste non fiable.
- L’option porte un avertissement et son rendu est signalé comme non validé,
  sans remplacer le parcours habituel. Derniers tests : 55 Python et 18 JS passent,
  build Vite réussi (avertissement habituel de taille du bundle).
- Serveur 8000 relancé avec cette version après contrôle d’absence de rendu actif ;
  QA 8001 arrêtée. Capture de contrôle non validé :
  `tmp/studio3d_vision_test_non_valide.png`. Ne pas réutiliser les rendus d’essai
  comme preuves d’une reconstruction fidèle. Aucun modèle image→mesh installé.
- Hunyuan3D proposé puis écarté : licence excluant l’UE. TRELLIS NON installé,
  l’utilisateur préfère enrichir le moteur actuel avec photos et schémas.

### Dernière amélioration : aide documentaire et assemblage contrôlé

- Retour utilisateur : le vélo généré ressemblait à trois traits. Défauts trouvés :
  positions `.pos = [...]` et `.position.set(...)` ignorées ; géométrie Qwen non fiable
  même avec des consignes seules. Ces transformations mettent désormais à jour les
  positions finales des nœuds. `cad.tubeBetween` relie correctement deux ancrages.
- Option **Aide Wikipédia** dans Créer, activée mais décochable ; envoie au maximum
  180 caractères de description à l’API officielle fr.wikipedia.org, deux introductions,
  délai borné ; sources cliquables visibles. Échec Web explicite, pas de promesse de
  dimensions exactes. Route POST `/api/studio3d/references` et module dédié.
- Deux essais Qwen bruts sur « Vélo » restaient mauvais : NE PAS les présenter comme
  validés. Solution limitée à cette famille : le backend demande des paramètres JSON
  à Qwen (rayon, empattement, matériau), les valide, puis génère un appel `cad.bicycle`.
  Base illustrative `engine/bicycleAssembly.js` : 2 roues séparées, pneus, cadre fermé,
  fourche, selle, guidon et pédalier. Le journal indique clairement la base utilisée.
  Pas une reconstruction arbitraire par IA, ni un plan industriel ; autres objets restent
  libres et non garantis. Le code modèle arbitraire n’est pas exécuté dans cette branche.
- Parcours complet avec le seul sujet « Vélo » : deux sources Wikipédia, paramètres
  Qwen, assemblage de référence exécuté sans erreur. Silhouette reconnaissable contrôlée
  en vue Face/PBR sur la base correspondante. 18 tests JS passent.
- Tentative d’export PNG du test : l’outil navigateur a expiré, export NON validé.
  Ne pas annoncer qu’un aperçu téléchargeable est prêt.
- Le serveur utilisateur a été fermé pendant la livraison ; relancé discrètement sur
  8000 avec la nouvelle version. QA 8001 temporaire arrêtée après vérification.

- Dernier correctif : `spokedWheel` fusionnait une jante extrudée non indexée avec
  moyeu/rayons indexés ; `mergeGeometries` renvoyait null puis `rotateZ` plantait.
  Les composants sont maintenant tous non indexés avant fusion ; erreur explicite
  si la fusion échoue. Test navigateur avec les paramètres exacts de la roue du vélo
  (r=0.3, 36 rayons, flanged=true) : erreur vide, exécution réussie. 15 tests JS passent
  (6 variantes axes/rebords + variantes par défaut/barre de navire).
  Le vélo complet n’a pas été rejoué : son ancien onglet Chrome n’était plus ouvert.
  Serveur utilisateur 8000 arrêté au moment du contrôle ; QA 8001 temporaire sans
  autopilote utilisée puis arrêtée. Relancer ShortPilot normalement pour appliquer.

### IA locale autorisée et installée le 24 octobre

- Utilisateur a autorisé explicitement Ollama + Qwen2.5-Coder 14B sur E, sans ajout
  de recherche Web/Wikipédia. Ces fonctions restent séparées et non implémentées.
- Ollama portable officiel v0.40.10 : `E:\ShortPilot-AI\Ollama\runtime\ollama.exe`.
  Archive GitHub officielle vérifiée par comparaison SHA256 avant extraction.
- Modèle `qwen2.5-coder:14b` téléchargé (9 Go), empreinte validée par Ollama ;
  stockage `E:\ShortPilot-AI\Ollama\models`, pas dans ComfyUI ni sur C.
- Serveur `127.0.0.1:11434`, RTX 4060 Ti reconnue. `tools/start_ollama.ps1` le
  démarre discrètement via le lanceur ShortPilot si installé et pas déjà lancé.
  Aucun PATH global, service Windows ou démarrage système ajouté.
- Défaut modèle UI passé de 7B à 14B ; choix de moteur mémorisé dans le navigateur.
- Test réel via `/api/local-ai/generate` depuis l’interface : Qwen 14B chargé sur
  GPU (10,4 Go de VRAM, contexte 8192), code de table industrielle accepté et 7 pièces
  créées, aucune erreur console. MAIS assemblage visuel incorrect (pièces mal placées).
  Installation/connexion validées, qualité géométrique NON validée. Ne pas promettre
  de belles constructions arbitraires avant correction des consignes/API et essais.
- 42 tests passent, bundle recompilé. Le test n’a rien publié ni modifié côté ComfyUI.
- Correctifs après test utilisateur smartphone : contexte `era`/`inventor` calculé
  avant la branche de narration anatomique (supprime l’erreur de variable avant
  initialisation) ; prise en charge `cad.group().add(piece)` avec rattachement
  du vrai nœud Three.js et drapeau parent. Les échecs d’exécution ne sont plus
  annoncés comme une construction réussie.
- Même code smartphone de la fenêtre Chrome utilisateur rejoué après compilation :
  erreur vide et masquée. 3 tests JS de régression passent (`node --test tests/*.test.js`
  depuis `studio3d/`). Ceci valide l’exécution, pas la précision géométrique/factuelle
  de toutes les créations Qwen. Ne pas inventer de garantie de qualité universelle.
- Test suivant utilisateur : camion refusé par JavaScript à cause de l’apostrophe
  non échappée dans `functionDesc: 'Accès à l'intérieur du véhicule'`.
  `engine/holoScriptText.js` corrige seulement les apostrophes intramot dans les
  propriétés descriptives simples, uniquement si le script est invalide et que
  le résultat réparé passe la vérification syntaxique. Code valide inchangé,
  aucune réparation arbitraire des expressions exécutables. Consigne au modèle :
  guillemets doubles pour les chaînes descriptives. Éditeur affiche le code réparé.
- Camion original capturé dans Chrome, rechargé puis exécuté : erreur vide/masquée.
  Vérification ciblée historique réussie. La suite Studio3D complète compte 30 tests
  réussis lors du chantier 2
  (`node --test` sur les 11 fichiers `tests/*.test.js`). Précision et esthétique
  de l’objet non garanties par ce test.

### Chantier 2 validé — réserves documentaires

- Le cas `test_preflight_graph_hash_mismatch_has_zero_marker_and_post` vérifie
  uniquement le contrat du faux précontrôle. La production enregistre l'empreinte
  du graphe soumis, sans la comparer à une empreinte attendue indépendante.
- Amélioration ouverte : déplacer les contrôles locaux d'empreintes et de plan
  avant les appels de disponibilité réseau quand cela s'applique. Le déplacement
  tenté dans le harnais a été annulé ; aucun fail-fast supplémentaire n'est acquis.
- Référence finale : 174 tests Python et 30 tests JavaScript réussis. Aucun test
  JavaScript ni code de production modifié dans cette clôture documentaire.
- Suivi de création demandé : bandeau permanent sous les commandes du studio,
  état réel + temps écoulé + journal dépliable, sans pourcentage inventé.
  Analyse terminée => attente explicite de validation ; génération => boutons
  désactivés contre doubles clics ; contrôle du code => succès ou blocage visible.
  Moteur indisponible => diagnostic conservé et résultat procédural signalé comme
  secours, pas comme succès Qwen. Timeout navigateur à 190s ; après 45s, simple
  mention « réponse encore attendue », pas affirmation de blocage.
  Tests : 8 tests JS et 7 tests d’intégration backend passent. Cas HTTP 404 modèle
  absent testé dans l’interface : journal complet et boutons réactivés.
  Génération Qwen réelle terminée en 21s : bandeau succès et durée affichés.
  Code volontairement invalide testé : bandeau « Exécution bloquée », puis retour
  au succès après restauration du code valide. Recharger la page pour voir le bandeau.

- Correction responsive après retour utilisateur : l’onglet 3D utilise la hauteur
  disponible de la fenêtre (plus de cadre 82vh/minimum 700px ajouté sous l’en-tête).
  En-tête compact, commandes adaptatives ; sous 1100px, vue 3D puis panneaux dans
  un seul défilement interne. Retouches de présentation seulement, moteur inchangé.
  Recharger ShortPilot après redémarrage pour prendre le nouveau gabarit Flask.
- Deuxième retour : l’ancien gabarit était encore servi par le processus 8000.
  Serveur redémarré après vérification qu’aucun job n’était actif ; nouveau gabarit
  confirmé dans le navigateur réel. Les panneaux n’ont plus de défilement propre :
  un seul défilement dans l’espace de travail, vue 3D fixe sur grand écran.
  Studio silencieux au démarrage (voix, musique, effets désactivés) ; activation
  volontaire via le bouton audio ou les cases du mixeur.

- Demande : intégrer `C:/Users/farhi/OneDrive/Desktop/3D/holoblueprint-3d` à ShortPilot,
  pour former une seule application. Le dossier d’origine n’a pas été modifié.
- Copie complète des sources et audios dans `studio3d/`, dépendances installées,
  bundle Vite compilé sous `studio3d/dist/` avec base `/studio3d/`.
- Un seul serveur Flask et un seul lanceur ShortPilot. Aucune instance Vite nécessaire.
- Nouvel onglet **Studio 3D** et bouton **Créer en 3D** dans la page de création.
- Le script (sujet, narration, durée) est transféré au studio ; un modèle procédural
  adapté est construit automatiquement. Les modèles dédiés couvrent les familles
  du catalogue ; une géométrie arbitraire parfaite n’est pas garantie.
- Moteur Three.js, matériaux PBR/filaire, caméras, découpe, import STL/OBJ/GLB,
  code HoloScript, narration et exports conservés.
- `core/studio3d.py` sert le bundle et fournit les ponts Ollama/LM Studio et voix OS.
  Les adresses IA sont limitées à localhost/127.0.0.1/::1, sans redirections.
- Le bouton **Exporter Vidéo** envoie la capture navigateur à `/api/studio3d/import`.
  Le job `studio3d` convertit WebM/MP4 → MP4 H264/AAC, génère la miniature et ajoute
  la vidéo à la bibliothèque commune. Aucune publication automatique de ces imports.
- Le script ShortPilot reste la narration ; les fichiers vocaux Eiffel ne sont pas
  utilisés pour narrer un autre sujet importé.
- Captures limitées à 20–180 secondes ; garder l’onglet visible pendant l’enregistrement.
- Test réel navigateur : script satellite transmis, modèle satellite construit,
  voix système locale détectée, capture de 20 s créée et importée en MP4.
- Vidéo de test : `outputs/1792846794_ffa586ad.mp4`, entrée **Test 3D - Satellite ShortPilot**.
- Second test complet depuis l’interface sur le serveur normal : capture de 20 s,
  conversion automatique et entrée bibliothèque **SATELLITE ORBITAL HELIOS-IV**,
  fichier `outputs/1792847106_41d09271.mp4` (4,2 Mo), miniature contrôlée visuellement.
- Instance QA sur 8001 arrêtée. ShortPilot normal est lancé sur `http://localhost:8000/`.
  Recontrôler les services à la prochaine session avant de lancer quoi que ce soit.
- Affichage compact adapté en colonnes empilées ; studio chargé seulement à l’ouverture
  de son onglet et rendu/audio suspendus quand il est masqué (sauf capture en cours).
- Correction nécessaire rencontrée en test : les emojis de logs pouvaient tuer le
  worker dans une console Windows cp1252 ; `log_line` utilise maintenant un repli sûr.
- **42 tests passent** et `npm run build` réussit. Les dépendances `studio3d/node_modules`
  sont ignorées par Git. Le bundle compilé est fourni pour le démarrage simple.
- La connexion YouTube dans n8n reste à terminer, comme décrit ci-dessous.

## Reprendre ici : connexion Google du workflow YouTube

L’utilisateur a autorisé n8n local et la création du workflow YouTube. Il déclare
avoir créé son compte administrateur local n8n. Aucun compte social n’a été connecté
par l’agent et aucune vidéo n’a été envoyée sur YouTube ou TikTok.

- Docker Desktop installé auparavant a été démarré.
- n8n Community **2.44.6** tourne dans le conteneur `shortpilot-n8n`.
- Interface : `http://localhost:5678` ; port exposé uniquement sur `127.0.0.1`.
- Configuration : `tools/n8n/compose.yaml`.
- Données persistantes : volume `shortpilot-n8n_shortpilot_n8n_data`.
- Lanceur `Lancer_n8n.bat` dans le projet ; raccourci **Lancer n8n** sur le Bureau.
- Fuseau Europe/Paris ; stockage des vidéos reçues sur disque ; purge après 7 jours.
- L’utilisateur veut laisser n8n lancé. Revérifier son état à la prochaine session.

### Réception locale déjà testée réellement

- Workflow **ShortPilot - Reception des videos (sans publication)**,
  ID `shortpilotReception01`, source `tools/n8n/shortpilot_reception.json`.
- Importé, publié/activé, conteneur redémarré.
- Webhook : `http://127.0.0.1:5678/webhook/shortpilot-studio`.
- Cette URL est enregistrée dans les réglages ShortPilot via son API.
- Test réel avec `outputs/1792784902_a17bcb8d.mp4` : HTTP 200,
  `received: true`, `published: false`, fichier et légende reçus.
- Ce workflow ne publie rien. Ne pas confondre réception et publication.

### Workflow YouTube créé, OAuth encore manquant

- Nom **ShortPilot - YouTube prive**, ID `shortpilotYouTube01`.
- Ouvrir : `http://localhost:5678/workflow/shortpilotYouTube01`.
- Source : `tools/n8n/shortpilot_youtube_prive.json`.
- Importé dans n8n, **non activé**, aucun identifiant Google associé.
- Chaîne : Webhook → YouTube upload → réponse JSON avec lien vidéo.
- Réglé en **private**, notification aux abonnés désactivée.
- Titre : première ligne de légende ; description : légende ; catégorie 27, région FR.
- Champ binaire trouvé automatiquement parmi les fichiers reçus.
- Futur webhook : `http://127.0.0.1:5678/webhook/shortpilot-youtube`.
- Ne changer l’URL ShortPilot qu’après connexion Google et activation de ce workflow.

**Prochaine action précise :** ouvrir le nœud **YouTube - Envoyer en prive**,
puis **Credential to connect with → Create new credential**.

Créer le credential ne suffit PAS à ouvrir la connexion Google. En auto-hébergement,
il faut un client OAuth personnel configuré dans Google Cloud :

1. Créer/choisir un projet et activer **YouTube Data API v3**.
2. Configurer le consentement OAuth et ajouter le compte comme utilisateur test si nécessaire.
3. Créer un client OAuth de type **Application Web**.
4. Copier la véritable URL de redirection affichée dans n8n dans les URI Google.
   Valeur attendue : `http://localhost:5678/rest/oauth2-credential/callback` ; vérifier l’écran.
5. L’utilisateur saisit Client ID et Client Secret directement dans n8n, puis clique
   **Sign in with Google**, choisit le compte propriétaire de la chaîne et autorise.
6. Enregistrer, activer le workflow, basculer l’URL ShortPilot et tester un envoi privé.

Ne pas demander de secret dans le chat ni l’afficher dans les journaux. Ne pas annoncer
la connexion Google ou un upload YouTube réussi sans preuve. TikTok vient ensuite.

### Code ShortPilot du branchement

- `core/publish.py` autorise deux destinations locales exactes sur `127.0.0.1:5678` :
  `/webhook/shortpilot-studio` et `/webhook/shortpilot-youtube`.
- Les autres ports/chemins/adresses privées restent bloqués par défaut.
- Le succès webhook confirme la réception, pas la publication.
- `tests/test_publish_webhook.py` couvre les chemins permis et les refus.
- Redémarrer ShortPilot pour charger le correctif ; conserver n8n lancé.
- Dernière suite complète : **35 tests passent**, puis tests webhook relancés avec succès.

## Musique : nouvelle composition à chaque rendu

- `core/music.py` : `instrumental_background` appelle `cinematic_background` et
  `score_plan`, avec une nouvelle composition aléatoire par défaut.
- Accords, motif, tonalité, tempo, densité et instruments varient par rendu.
- Pour les scripts spatiaux : direction calme, 54–72 BPM, piano doux, orgue discret,
  nappes et pulsation légère. Aucun échantillon vocal ni modèle audio génératif.
- `core/render.py` transmet le texte complet au compositeur dans les deux branches.
- Sortie stéréo avec fondus ; qualité artistique à valider à l’écoute par l’utilisateur.
- Démonstrations : `tmp/musique_spatiale_demo_1.wav` et `_2.wav` (24 secondes).
  Ce sont des exemples, pas une bibliothèque limitée à deux variantes.
- Tests : mêmes graines → même audio, graines différentes → audio différent,
  durée/canaux/amplitude vérifiés. Ne pas promettre un niveau orchestral professionnel.

## État images/scripts à conserver

- L’utilisateur valide pour l’instant les scripts et les images locales qualité.
- Parcours attendu : niche/sujet → script Web → vidéo, sans retouche manuelle.
- Modes : direct rapide ; qualité Comfy complet ; images animées = mouvements de montage.
- Ne pas retirer les retouches visage/mains du mode qualité sans demande.
- Nettoyage des titres Wikipédia et des transitions répétées effectué.
- Nudité : suppression dans les prompts seulement, **aucun détecteur d’image finale**.
  Ne pas garantir l’absence de nudité : des rendus ont déjà contourné les prompts.

## Fond d’écran : sujet mis de côté

- L’utilisateur a abandonné l’extension du wallpaper pour passer à ShortPilot/n8n.
- Dernière demande séparée : activer visage/mains dans
  `C:/Users/farhi/Downloads/real_final7_astronaute_1440p.json`.
- Copie `workflows/real_final7_astronaute_1440p_detailers_actifs.json` créée,
  également sur le Bureau et dans les workflows ComfyUI sur E.
- **Seuls les nœuds FaceDetailer 22 et 31 ont changé : mode 4 → 0**.
  Différence exacte vérifiée ; aucun nouveau rendu lancé pour ce fichier.

## Règles pour la suite

- Appliquer `.agents/skills/shortpilot-result-first/SKILL.md`.
- Messages courts, pas de répétitions d’attente ou de succès non vérifiés.
- Ignorer l’audio provenant d’une vidéo que l’utilisateur regarde.
- De nombreuses modifications utilisateur existent dans le dépôt : les préserver.
- Ne pas lire les clés/secrets pour les inclure dans un récapitulatif.

---

## Archive ancienne — ne pas reprendre cette ancienne priorité

## Objectif prioritaire

Le flux doit être **entièrement automatique** :

1. l’utilisateur choisit une niche, ou écrit un sujet libre ;
2. il laisse `Source du script : Web — contenu infini` ;
3. il clique sur `Générer un script`, puis sur `Générer la vidéo`.

Aucune découpe, correction ou réécriture manuelle du script ne doit être
nécessaire.

## État vérifié

- ComfyUI local est lancé sur `http://127.0.0.1:8188`.
- Le nouveau choix **Images locales qualité — ComfyUI complet, plus lent** est
  intégré et testé réellement dans ComfyUI.
- Ce mode reprend le workflow manuel de qualité : RealVisXL Lightning,
  upscale UltraSharp, seconde passe douce, retouche visage, retouche mains et
  netteté finale.
- Le test réel avec une personne tenant une tasse a réussi ; l’utilisateur a
  jugé l’image excellente.
- Le mode **Images locales directes** reste disponible comme mode rapide.
- Le mode **Images animées gratuites** reste disponible : mêmes images locales,
  avec zoom/panoramique au montage. Il ne crée pas de vraie vidéo IA.
- Aucun de ces trois modes n’exige de clé API ni de crédit externe.

## Scripts : état actuel

- La source `Web — contenu infini` génère déjà automatiquement les scripts
  depuis Wikipédia ou les sources gratuites selon la niche.
- Le rythme a été amélioré : une transition orale est désormais attachée au
  fait qu’elle introduit, au lieu de créer une scène très courte et vide.
- Le repli local du sujet libre ne répète plus des conseils de productivité :
  si le sujet contient des jalons (`Apollo 11, alarme, carburant...`), ils sont
  transformés automatiquement en scènes dans le même ordre.
- Les tests automatisés passent : 15 tests au total.

## Point encore à finaliser avant de déclarer les scripts parfaits

Le tri automatique des sujets pour une niche large doit encore être affiné.
Un essai réel en niche `Histoire` a choisi un article trop abstrait
(`Historiographie des Croisades`) : le script est fonctionnel, mais ce n’est
pas un sujet de Short assez fort.

### Prochaine tâche précise

Améliorer le filtre de sélection Web pour écarter automatiquement les sujets
abstraits, listes, revues et notions générales, et privilégier les événements,
missions, découvertes, personnages et tournants historiques. Tester ensuite :

- une niche `Histoire` sur 45 secondes ;
- un `Sujet libre` sur 45 secondes ;
- vérifier que l’utilisateur n’a rien à éditer avant le rendu.

## Règle de collaboration

Ne pas envoyer de messages d’attente. Répondre seulement avec un résultat
vérifié, un blocage réel, ou le résumé final d’une modification.

## Reprise : publication YouTube et TikTok

### YouTube — terminé et validé

- Docker Desktop démarre le conteneur `shortpilot-n8n` automatiquement
  (`restart: unless-stopped`). Le raccourci Bureau **Lancer n8n** reste
  disponible si besoin.
- ShortPilot envoie vers le webhook de production n8n :
  `http://127.0.0.1:5678/webhook/shortpilot-youtube`.
- Le workflow **ShortPilot - YouTube privé** est publié, connecté au compte
  YouTube de l’utilisateur et testé avec succès.
- La visibilité du nœud YouTube a été changée de `Private` à `Public`, puis
  le workflow a été republié. Les prochaines vidéos ShortPilot partent donc
  en **public** sur YouTube par défaut.
- Une vidéo de test a été reçue sur la bonne chaîne, puis l’utilisateur l’a
  lui-même rendue publique dans YouTube Studio.

### TikTok — reprendre ici

#### État réel au 30 octobre 2026 — reprendre exactement ici

- Le sandbox **ShortPilot Test** est configuré : Login Kit et Content Posting
  API en mode brouillon, avec les portées `user.info.basic` et `video.upload`.
  Le compte de test `levoyagedumonde` est ajouté. Ne pas activer Direct Post.
- Les pages publiques de conditions et confidentialité, l'icône et les
  informations de l'application sont déjà renseignées dans TikTok.
- n8n est accessible sur le tunnel HTTPS temporaire. L'identifiant n8n
  **Authentification personnalisée** a été créé et sauvegardé par
  l'utilisateur ; il contient `client_key` et `client_secret` TikTok masqués.
  Ne jamais demander ni afficher ces valeurs.
- Un nouveau workflow n8n non publié, encore nommé **My workflow**, est
  ouvert dans Chrome. Il contient :
  1. un déclencheur Webhook `GET` dont le chemin est
     `tiktok-oauth-callback` ;
  2. un nœud **Requête HTTP** relié au Webhook, réglé sur `POST` vers
     `https://open.tiktokapis.com/v2/oauth/token/`.
- Le workflow est incomplet : il faut encore sélectionner l'identifiant
  d'authentification personnalisée dans le nœud HTTP, envoyer le corps
  URL-encodé (`grant_type=authorization_code`, le `code` reçu par le Webhook,
  et l'URL de retour), stocker/renouveler le jeton, puis publier et tester le
  workflow. Ne pas ouvrir l'autorisation TikTok avant ce test.
- Après publication du Webhook, remplacer dans TikTok Developer le Redirect
  URI actuel par l'URL de production n8n finissant par
  `/webhook/tiktok-oauth-callback`, appliquer les changements, puis seulement
  ouvrir la page d'autorisation TikTok et demander à l'utilisateur de cliquer
  **Autoriser**.
- La branche TikTok d'envoi de vidéo en brouillon, parallèle à YouTube, reste
  entièrement à créer et tester après l'OAuth.

- Compte TikTok for Developers créé avec l’utilisateur.
- Une organisation **ShortPilot** existe et est propre : le doublon créé par
  erreur a été supprimé. Ne pas recréer d’organisation.
- Application **ShortPilot Studio** créée dans cette organisation, en état
  **Brouillon / Production**. Elle a des identifiants TikTok générés : ne
  jamais afficher ni recopier le secret client dans le chat ou les logs.
- Aucun produit ni aucune portée OAuth ne sont encore activés ; aucune vidéo
  TikTok ne peut donc partir à ce stade.

### Prochaine action précise — TikTok

1. Rouvrir TikTok for Developers, se reconnecter si nécessaire et ouvrir
   l’application **ShortPilot Studio**.
2. Dans **Produits**, cliquer sur **Ajouter des produits**.
3. Activer d’abord **Login Kit**, requis par TikTok pour connecter le compte.
4. Activer ensuite **Content Posting API**.
5. Dans **Portées**, demander les autorisations nécessaires à la publication
   (`user.info.basic` et `video.publish`). Confirmer explicitement avec
   l’utilisateur juste avant d’accorder ces accès.
6. Configurer le retour OAuth n8n, connecter le compte TikTok et ajouter la
   branche TikTok au même workflow n8n que YouTube. Le webhook ShortPilot
   devra alors déclencher YouTube et TikTok en parallèle.

### Limite TikTok importante

TikTok autorise les essais d’une application non auditée, mais limite les
publications directes à une visibilité privée. Pour publier automatiquement
en public, l’application devra ensuite être soumise à l’examen TikTok avec
les informations publiques requises (catégorie, description, plateforme,
conditions d’utilisation, politique de confidentialité et vidéo de démo).
