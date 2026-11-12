# Chantier 3 — cahier des charges figé avant implémentation

Statut : spécification validée, non implémentée. Aucune génération, publication ou soumission ComfyUI n'est incluse dans sa validation.

## Objet et contrat de décision

La reconnaissance aide la revue humaine à déterminer si les objets physiques explicitement demandés sont reconnaissables, avec leurs états, attributs et relations. Elle est générique : aucun vocabulaire d'objets codé en dur. Elle peut refuser automatiquement une contradiction démontrée, mais ne peut jamais accepter automatiquement. `accepted=true` exige une revue humaine signée. Le succès technique ComfyUI reste séparé et n'entre pas dans la décision visuelle.

Les faits contrôlés proviennent du plan structuré : tous les `subject` et `secondary` explicitement demandés, ainsi que leurs faits `state`, `color`, `count`, `action`, `relation` ou autres attributs visuels explicitement reliés à ces objets. `required_terms` vérifie le prompt et ne sert pas d'inventaire. Les éléments facultatifs ou inventés par le décor ne fondent aucun refus.

Chaque fait du plan porte `required: true|false`, déterminé génériquement à partir de la demande, sans liste lexicale fixe, et relu par un humain avec le plan. Valeur par défaut logique : `false`. Pour un plan ancien où le champ est absent, le fait n'est pas éligible au refus automatique : le système ne peut pas déduire `true`. Le refus exige la version du plan et des indicateurs `required` revue par l'humain, identifiée par empreinte ; une modification ultérieure exige une nouvelle revue.

## Observations

Chaque fait donne `present`, `absent` ou `indeterminate`, avec identifiant du fait et des objets propriétaires, zone examinée, justification, preuve positive éventuelle et motif d'incertitude. Pour un objet, `absent` ne peut jamais résulter de la seule non-détection : celle-ci donne `indeterminate`. Pour un attribut, état ou relation, `absent` signifie que le fait demandé est positivement contredit par une observation exploitable, par exemple l'objet demandé visible avec une couleur opposée, ou un planning visiblement ouvert alors que fermé est demandé. Une relation est `indeterminate` si l'un des objets nécessaires ne peut pas être évalué. Aucun état `indeterminate` n'est converti en `present` ou `absent`.

## Refus automatique

Un rapport séparé `rejected_by_vision` est permis seulement si toutes les conditions suivantes sont réunies :

1. Le fait contredit porte explicitement `required: true` dans le plan revu par l'humain.
2. Une preuve positive montre la contradiction ; la non-détection ne suffit jamais.
3. Le même verdict et la même justification tiennent sur l'image entière et sur le recadrage de la zone pertinente. Un désaccord ou une zone non localisable donne `indeterminate`.
4. La zone est évaluable : ni flou disqualifiant, ni masquage, ni objet minuscule, ni objet hors cadre. Au moindre doute sur la qualité ou l'identité, pas de refus.

Le rapport de refus référence l'image, son SHA-256, la zone, les deux observations, les faits et l'empreinte du plan revu. Il conserve l'image et les preuves. Il n'écrase jamais le rapport technique ComfyUI et ne supprime aucun artefact. Une erreur d'analyse ne déclenche ni acceptation ni refus : elle reste `indeterminate`.

## Évaluation

Utiliser en lecture seule les images existantes de `outputs/visual_states_validation` et d'autres dossiers visuels, complétées par des cas synthétiques de cadrage, échelle, masquage, état, attribut et relation. Aucune image existante n'est présumée annotée. Une vérité de référence humaine par fait et par image, avec zone et qualité évaluables, précède le réglage. Séparer les images de réglage de celles d'évaluation ; éviter qu'une variante de la même image se retrouve dans les deux ensembles.

Rapporter séparément par type de fait les `present` erronés, les `absent` erronés et les `indeterminate`, y compris leur fréquence. Un faux refus est classé après revue de la source et du plan en **erreur de reconnaissance** (image ou fait correctement spécifiés, contradiction inventée ou mal lue) ou **erreur de plan** (fait ou `required` injustifié par la source). Publier ces deux nombres séparément, sans les agréger dans un seul taux de faux refus. Les cas non attribuables restent explicitement non résolus.

## Revue et orchestration

La revue humaine est enregistrée séparément en append-only avec décision, identité du réviseur, date, signature, justification, identifiant du rapport technique, empreinte du plan revu et SHA-256 de l'image. Le rapport technique reste immuable. Seule une décision humaine signée peut établir `accepted=true` ; un refus automatique ne fabrique pas de signature humaine.

Si la reconnaissance utilise Ollama local, elle s'exécute après la fermeture de `render_phase`, sous `text_phase`. Les phases exclusives du chantier 1 et les garanties one-shot du chantier 2 ne sont pas modifiées. La validation du chantier 3 utilise uniquement des images existantes et des cas synthétiques, sans génération, Short ou publication. Les artefacts historiques seed 70001 restent intacts.
