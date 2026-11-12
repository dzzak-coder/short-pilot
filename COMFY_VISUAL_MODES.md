# Modes visuels ComfyUI

## Backend actif : Qwen Turbo

ShortPilot utilise exclusivement **Qwen-Image-2.1 Turbo** avec le planificateur Ollama exact
`qwen3.8:27b`. Le constructeur minimal produit une image **720 × 1280** avec 8 étapes, CFG 1,
Euler et scheduler `simple`; le nœud d'encodage exécuté est `TextEncodeQwenImage21`. Les trois
composants Qwen (UNET, encodeur texte et VAE) doivent être présents, sinon la génération échoue
explicitement : aucun checkpoint conventionnel ou SDXL ne peut servir de repli.

Le socket négatif du graphe Qwen reste volontairement vide avec CFG 1. Les rapports déclarent donc
`negative_prompt_active: false` et `negative_prompt_verified: null`; aucune exclusion n'est
présentée comme active dans ce négatif. Les contraintes indispensables, y compris l'absence
d'humains et la limitation aux objets décrits, sont formulées dans le positif.

La preuve Qwen est isolée dans `outputs/qwen_turbo_visual_validation`. Les historiques
`simple_70001.visual.json` et leurs marqueurs sont des preuves RealVisXL et restent conservés,
mais ne constituent pas une preuve Qwen. `real_final9` est seulement un workflow graphique de
référence réglé en 1:1 ; il n'est ni chargé ni intégré à ShortPilot, dont le constructeur reste
en 720 × 1280.

Le planificateur général utilise Ollama local et un modèle texte installé (dans l'environnement vérifié : `qwen2.5:7b-instruct`). Il traite ensemble le titre et les scènes, traduit les descriptions physiques et choisit une métaphore pour les idées abstraites. Il n'utilise plus de grammaire limitée à une liste d'objets. Aucune nouvelle clé API ni dépendance lourde n'est ajoutée.

Le planificateur version 5 invalide les anciens plans automatiques, y compris les plans expérimentaux. Les contraintes atomiques contiennent la catégorie (sujet, couleur, nombre, objet secondaire, état, action, relation, décor, lumière), le propriétaire `entity`, l'extrait source et sa formulation anglaise. Les états ouverts/fermés nomment une forme physique générique. Un volume relié fermé doit montrer sa couverture extérieure, avec les couvertures jointes ; le négatif exclut les pages exposées de cet objet précis. Les contre-exemples restent liés à leur propriétaire, pour permettre par exemple un carnet fermé à côté d'une boîte ouverte.

`required_terms` rassemble les faits et leurs preuves textuelles. `negative_terms` est propagé dans le rendu et le constructeur ComfyUI, puis dédupliqué avec le négatif technique et le contrôle humain. Seules les natures mortes explicitement classées comme telles limitent les accessoires et doublons. Les marquages fonctionnels restent permis ; les exclusions de texte ciblent les incrustations, sous-titres, filigranes et logos. Pour les descriptions explicites, tous les mots significatifs de la source doivent être couverts par les extraits. Une seconde tentative textuelle bornée corrige un contrat rejeté. Après échec ou indisponibilité d'Ollama, un message demande un plan explicite ; aucun objet de remplacement n'est envoyé à ComfyUI. Les plans anglais manuels avec `visual_plans_locked: true` restent acceptés.

Les accroches, transitions et CTA reprennent un plan de référence validé et ses contraintes. Si seul le titre fournit le sujet, il est planifié comme référence. `required_terms` est vérifié dans le rendu et juste avant l'appel ComfyUI ; les omissions sont bloquées. La suppression humaine est ajoutée uniquement dans `aiimg`, selon les contrôles structurés. La vérification textuelle ne garantit pas la fidélité de l'image produite : celle-ci doit toujours être inspectée.

`comfy` utilise le workflow Qwen minimal vertical 720 × 1280, Euler / `simple`, 8 étapes et CFG 1. La seed de la scène *n* est `70000 + n`. Le plan, le positif soumis et le positif exécuté doivent être identiques. Aucun guide structurel, conditionnement régional, ControlNet ou upscale n'est utilisé. Les branches SDXL/`comfy_quality` sont historiques et ne sont pas autorisées pour ce backend.

Chaque rendu ComfyUI crée un fichier `.visual.json` voisin de la vidéo. Il contient les prompts soumis et exécutés (positif et négatif), leurs indicateurs de vérification, le workflow de l'historique ComfyUI, la seed, le checkpoint, les paramètres et l'identifiant ComfyUI. La vérification n'est vraie qu'après comparaison exacte du graphe exécuté au graphe soumis. Les scènes `forbidden` ajoutent l'exclusion humaine une seule fois ; les scènes `hands_only` ne le font pas.

La preuve isolée utilise `tools/verify_visual_states.py --plan`, puis `--test` (suite complète), puis `--generate`. Une empreinte du code bloque la génération après toute modification et un marqueur exclusif bloque toute deuxième tentative. La seed est fixée à 70001 ; aucune vidéo ni publication n'est lancée. Les anciens essais restent dans leurs dossiers de preuves. Le modèle expérimental précédemment téléchargé reste inactif sur disque ; aucun chargement ni téléchargement n'est déclenché.
