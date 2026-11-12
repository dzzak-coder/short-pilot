# Point de reprise — B1 visuel Khéops

Date : 10 novembre 2026

## État validé

- Rapport : `outputs/text_diagnostics/kheops_plan_2026-11-09.json`
- 12 scènes narratives inchangées.
- 12 entrées `visual_plans` et 12 entrées `visual_controls` dans le rapport.
- 10 plans non vides.
- 2 sujets visuels distincts, comptés après retrait du suffixe de continuité.
- 8 scènes `needs_context` en continuité.
- Scènes 5 et 7 non illustrables sans invention : elles restent en échec explicite.
- 58 tests ciblés verts.
- Dernière sonde : 7 POST `/api/chat`, 0 POST `/prompt`, aucune image.

Le résultat ne représente pas dix images différentes : deux ancrages visuels alimentent
huit scènes de continuité. Les scènes 5 et 7 expriment respectivement un jugement historique
et des superlatifs ; aucune reformulation physique ne doit être inventée pour les rendre.

## Décision en attente

### Option A — image dominante

Assumer les 2 sujets existants et utiliser les 8 continuités avec des cadrages variés.
Cette option est techniquement prête, mais aucune image n'a été lancée.

### Option B — sélection concrète en amont

Modifier hors ligne la sélection des passages documentés pour privilégier les éléments
concrets de la source (blocs, carrières, chambre du roi, mesures) plutôt que les passages
sur les jugements, superlatifs et controverses.

## Contraintes de reprise

- Attendre le choix explicite A ou B.
- Ne pas relancer `plan_probe` avant cette décision.
- Ne pas reformuler les briefs 5 et 7.
- Ne pas inventer de contenu absent de la narration ou des sources conservées.
- Ne lancer aucune image et aucun POST `/prompt`.
- Conserver le modèle actuel.

## Vérification locale utilisée

```powershell
.venv\Scripts\python.exe -m unittest tests.test_plan_probe_metrics tests.test_visual_states tests.test_visual_contract tests.test_visual_planner_isolation tests.test_safe_scene_split tests.test_visual_word_coverage
```

Résultat enregistré : `Ran 58 tests ... OK`.
