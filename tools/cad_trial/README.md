# Essai CAO séparé — assemblage de pièces réelles

Le but est de tester le remplacement de la génération de primitives improvisées
par un plan de composants, une bibliothèque CAO et des raccordements calculés.
Ce dossier n'est pas connecté aux boutons de génération de ShortPilot.

## Installation effectuée

- Environnement Python 3.11 isolé : `E:/ShortPilot-AI/CAD-Assembly-Trial/runtime`.
- CadQuery 2.8.0 installé depuis PyPI avec ses dépendances binaires.
- Aucun changement à ComfyUI, Ollama, au Python de ShortPilot ni à son moteur d’animation.
- Pour retirer cet essai : supprimer uniquement son environnement dédié sur E et
  ce dossier d’expérience après arrêt de ses éventuels processus.

## Prototype disponible

La bibliothèque actuelle est volontairement limitée à une **charnière complète** :
deux ailes complémentaires à charnons, un axe traversant et une rondelle.
Elle ne sait PAS encore fabriquer une moto, un hélicoptère ou un objet quelconque.

`request_plan.py` demande à Qwen installé un plan JSON contraint, sans code Python.
`assembly_trial.py` ne construit que les composants connus de sa bibliothèque.
Les raccordements sont des repères géométriques calculés par les composants.
Les transformations des pièces sont résolues par coïncidence de repères le long
d’un arbre de connexions ; aucun placement numérique n’est demandé au modèle.
Il ne s’agit pas encore d’un solveur général de mécanismes avec boucles ou articulations.

Le contrôle vérifie les solides valides, les volumes positifs, la connexion de toutes
les pièces, les raccordements, la compatibilité des hauteurs et les interpénétrations.
Une collision du premier prototype a été détectée puis corrigée dans les dégagements
des ailes ; ce contrôle repose sur les solides CAO, pas sur une simple boîte englobante.
Il ne certifie ni résistance mécanique, ni tolérances de fabrication, ni trajet
d’insertion sans collision pendant l’animation.

## Exécution

Depuis la racine de ShortPilot, dans PowerShell :

```powershell
& 'E:/ShortPilot-AI/CAD-Assembly-Trial/runtime/Scripts/python.exe' tools/cad_trial/test_assembly_trial.py
& 'E:/ShortPilot-AI/CAD-Assembly-Trial/runtime/Scripts/python.exe' tools/cad_trial/assembly_trial.py tools/cad_trial/hinge.spec.json tmp/cad_assembly_hinge
```

Sorties : assemblage STEP, STEP distinct par pièce, rapport de validation et script
HoloScript avec les mêmes quatre maillages et les étapes du Studio existant.
Les STEP sont en millimètres ; l’aperçu HoloScript est normalisé à six unités.

La définition de référence a été exécutée dans un onglet de test du Studio : quatre
composants nommés, première aile seule en phase Fondation, assemblage complet en
phase Finitions et séparation des quatre composants en vue éclatée. Captures
dans `tmp/cad_assembly_hinge/`. Aucun bouton produit n’a été ajouté sur cette base.

## Suite requise

Élargir et valider la bibliothèque, typer les interfaces et les jeux d’assemblage,
traiter les pièces spécifiques absentes, puis tester plusieurs objets complets.
Ne jamais annoncer une génération universelle sur la base de cette charnière.

Documentation du moteur : https://cadquery.readthedocs.io/en/latest/assy.html
