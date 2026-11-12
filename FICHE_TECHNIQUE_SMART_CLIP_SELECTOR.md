# Fiche technique à transmettre à l’autre agent — Module de sélection intelligente des meilleurs passages vidéo

## Objectif

Concevoir un module Python autonome à intégrer plus tard dans ShortPilot, sans modifier ShortPilot ni reconstruire ses fonctions existantes. À partir d’un fichier vidéo local obtenu légalement, le module détecte les meilleurs passages pouvant devenir des Shorts.

## Périmètre et entrées

Entrées attendues :

- chemin vers une vidéo locale ;
- nombre de passages demandé ;
- durée minimale et maximale, respectivement `30–60 s` par défaut ;
- langue facultative, avec détection automatique lorsqu’elle n’est pas fournie.

Le module ne traite que des fichiers locaux obtenus légalement.

## Traitement attendu

1. Vérifier l’intégrité et la durée de la vidéo avec FFmpeg.
2. Extraire un audio temporaire.
3. Transcrire localement avec faster-whisper et des timestamps mot à mot.
4. Détecter les phrases et les silences.
5. Générer des candidats qui commencent et se terminent sur des phrases complètes.
6. Noter chaque candidat selon :
   - l’accroche des 3 premières secondes ;
   - l’information ;
   - l’émotion ;
   - la conclusion ;
   - l’autonomie du passage ;
   - l’énergie audio ;
   - le rythme ;
   - les changements de scène via PySceneDetect.
7. Utiliser un LLM local Ollama pour la notation sémantique.
8. Sélectionner les meilleurs passages en évitant les chevauchements importants.

## Interface obligatoire

```python
analyze_video(
    video_path: str,
    count: int = 3,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
    language: str | None = None,
) -> list[ClipCandidate]
```

Définir une dataclass `ClipCandidate` comprenant exactement les champs suivants :

```python
start
end
duration
score
transcript
hook_score
emotion_score
information_score
conclusion_score
autonomy_score
audio_energy_score
scene_change_score
justification
```

Prévoir aussi un export JSON stable et documenté des résultats.

## Contraintes techniques

- Python 3.11 ou supérieur ;
- Windows et Linux ;
- exécution locale ;
- cible matérielle : RTX 4060 Ti avec 16 Go de VRAM ;
- zéro service payant et aucune clé API ;
- aucun téléchargement YouTube ;
- aucune publication ;
- aucune interface web ;
- aucun montage vidéo ;
- nettoyage des fichiers temporaires même en cas d’erreur ;
- timeouts et messages d’erreur explicites ;
- typage complet ;
- architecture modulaire ;
- versions des dépendances figées.

## Structure souhaitée

```text
smart_clip_selector/
├── __init__.py
├── models.py
├── probe.py
├── transcription.py
├── sentence_boundaries.py
├── audio_analysis.py
├── scene_analysis.py
├── semantic_scoring.py
├── selector.py
└── json_export.py

tests/
├── fixtures/
├── test_probe.py
├── test_boundaries.py
├── test_scoring.py
├── test_selector.py
└── test_integration.py

requirements.lock.txt
README.md
```

Prévoir des fixtures et des tests dédiés à la sonde vidéo, aux limites de phrases, au scoring, au sélecteur et à l’intégration.

## Critères d’acceptation

- Fonctionnement sur un vrai MP4 local.
- Transcription avec timestamps mot à mot.
- Aucun mot coupé entre le début et la fin d’un passage.
- Débuts et fins de phrases respectés.
- Durées minimale et maximale respectées.
- Chaque résultat contient un score et une justification.
- Export JSON stable et documenté.
- Tests unitaires et test d’intégration fournis.
- Commande de démonstration fournie.
- README expliquant l’installation, Ollama, le modèle utilisé et les limites connues.

## Livraison attendue

Livrer une archive contenant uniquement le module, ses tests, les dépendances figées et la documentation. Ne pas inclure de copie de ShortPilot et ne modifier aucun fichier de ShortPilot.
