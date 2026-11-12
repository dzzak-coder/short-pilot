# Jeu d'annotation du chantier 3

Inventaire initial : 46 fichiers image, 42 contenus SHA-256 distincts. Parmi eux, 31 rendus `comfy_*.png` ont un plan identifiable et 41 faits structurés candidats : 31 objets, 2 états, 6 attributs (couleur, contexte, lumière), 2 relations. Ce sont des faits **candidats**, pas une vérité terrain humaine. Les 31 rendus ont la même source textuelle ; les 11 autres contenus distincts sont des miniatures ou guides sans plan associé exploitable automatiquement. Les guides ne sont pas des sorties du détecteur. Un inventaire de fichiers n'établit pas que les 41 faits sont visuellement évaluables.

`tools/vision_dataset.py init` a créé une fiche JSON par contenu image dans `annotations/`, sans toucher aux images. Chaque fiche est initialement `split: "unassigned"`. Le champ `source_group` lie toutes les variantes de la même scène ; aucune variante ne peut traverser la frontière réglage/évaluation. Les images de référence existantes restent en lecture seule.

## Annotation humaine

Le réviseur examine l'image et son plan. Il corrige ou ajoute les faits atomiques, avec `id`, `type` (`object`, `state`, `attribute`, `relation`), `category`, `entity`, `source_span`, `requested`, `required` booléen et `required_reviewed: true`. Chaque fait reçoit `status` (`present`, `absent`, `indeterminate`), `bbox_xyxy` en pixels ou `null`, `quality`, `reason` et `evidence` positive pour `absent`. Non-détection, flou, occlusion, taille insuffisante et hors cadre restent `indeterminate`. La fiche reçoit `annotator`, `annotated_at` (ISO 8601) et `signature` authentifiée par un mécanisme à définir avant la collecte ; une simple chaîne saisie dans JSON n'est pas une signature vérifiable.

Un enregistrement de **revue humaine finale**, distinct de la fiche de vérité terrain et du rapport ComfyUI, contiendra `review_id`, `technical_report_id`, `image_sha256`, `plan_sha256`, `reviewer_id`, `reviewed_at`, `decision` (`accepted`, `rejected`, `indeterminate`), `reason`, `signature_scheme`, `signature` et l'empreinte du contenu signé. Il sera append-only. `accepted=true` n'est dérivé que d'une décision `accepted` dont la signature est vérifiée.

## Réglage et scellement

Attribuer `tuning` ou `evaluation` uniquement après annotation et contrôle des familles. Le jeu d'évaluation doit comprendre au moins une **autre source indépendante** que le réglage ; avec les 31 rendus actuels, cette condition ne peut pas être remplie. Les miniatures ne deviennent éligibles qu'avec une source et des faits authentifiés par un humain. Une transformation synthétique hérite du `source_group` de son image parent ; elle reste dans le même tas.

Avant la première ligne du détecteur, exécuter `tools/vision_dataset.py seal`. La commande refuse les annotations d'évaluation incomplètes, une famille commune aux deux tas et un doublon d'image. Elle crée exclusivement `evaluation.seal.json`, avec les SHA-256 des images **et** des fichiers d'annotation. `verify-seal` contrôle ces empreintes avant et après l'évaluation. Le manifest et ses annotations ne doivent pas être consultés pendant le développement ; le détecteur ne reçoit que le jeu de réglage. Le scellement n'a pas encore été effectué : aucune vérité terrain humaine ni deuxième famille de scènes n'existe dans cet inventaire.

## Cas synthétiques

À partir d'une image parent déjà attribuée au réglage ou à l'évaluation, produire une variante dans un répertoire distinct avec une recette versionnée : parent SHA-256, opération (`occlusion`, `scale`, `crop`), paramètres exacts, graine si nécessaire, SHA-256 de sortie. Ne jamais écraser le parent. Un humain annote la variante sans recopier automatiquement les statuts du parent ; les régions deviennent `indeterminate` si l'objet est masqué, trop petit ou hors cadre. Toutes les variantes restent dans le tas et la famille du parent. Aucune transformation n'a été exécutée dans cette étape.
