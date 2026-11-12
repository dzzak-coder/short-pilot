# Point de reprise — ShortPilot / Qwen Turbo

Mis à jour le 7 novembre 2026. Ce document décrit uniquement l’état réellement obtenu et vérifié.

## Résultat actuel

ShortPilot est passé du backend image SDXL/RealVisXL à **Qwen-Image-2.1 Turbo** dans ComfyUI.

- Une génération réelle Qwen, seed `70001`, a été produite avec succès :
  `E:\ComfyUI_windows_portable\ComfyUI\output\ShortPilot_Qwen_Turbo_seed70001_00001.png`.
- Le rendu contient le minuteur rouge, le bureau en bois, le planning fermé et une lumière douce du matin. Il est visuellement plus conforme que l’ancien essai RealVisXL.
- Le workflow ComfyUI actif et sans erreur est `qwen_image_2_1_t2i`.
- Le workflow importé `real_final9.json` a été migré sous le nom `real_final9_qwen_turbo`.

## Modèles conservés

Les seuls poids image nécessaires sont :

- `models/diffusion_models/qwen_image_2.1_turbo_int8_convrot.safetensors` — 6,83 Go
- `models/text_encoders/qwen3vl_8b_w4a8.safetensors` — 5,88 Go
- `models/vae/qwen_image_2.1_vae_bf16.safetensors` — 0,63 Go

Le modèle `ace_step_v1_3.5b.safetensors` est conservé exclusivement pour la musique ; ce n’est pas un modèle image.

## Éléments supprimés

Envoyés dans la Corbeille Windows (récupérables) :

- `RealVisXL_V5.0_fp16.safetensors`
- `RealVisXL_V5.0_Lightning_fp16.safetensors`
- `sd_xl_turbo_1.0_fp16.safetensors`
- `face_yolov8m.pt`, `hand_yolov8s.pt`, `person_yolov8m-seg.pt`
- `4x-UltraSharp.pth`

Les anciens workflows `real_final*`, astronautes et fonds d’écran existent encore comme archives utilisateur, mais ne doivent pas être exécutés : ils réclament les modèles SDXL supprimés.

## Code modifié

Les changements Qwen sont dans :

- `core/aiimg.py` : détection prioritaire de Qwen Turbo et construction du workflow Qwen natif (`UNETLoader`, `CLIPLoader`, `VAELoader`, `TextEncodeQwenImage21`, `KSampler` 8 étapes).
- `tools/verify_visual_states.py` : le scénario de preuve utilise maintenant Qwen Turbo.
- `tools/verify_timer_visual.py` : même bascule vers Qwen Turbo.

Les préférences nommant les trois checkpoints supprimés basculent vers Qwen au lieu d’envoyer un workflow mort à ComfyUI.

## Vérifications effectuées

Après la bascule Qwen :

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_visual*.py'
```

Résultat : **36 tests visuels OK**.

```powershell
.venv\Scripts\python.exe tools\verify_visual_states.py --test
```

Résultat : **133 tests Python OK**.

Le constructeur Qwen a également été contrôlé localement : graphe Qwen attendu, huit étapes, et nœud `TextEncodeQwenImage21` présent.

Les 30 tests JavaScript Studio3D étaient aussi OK avant la dernière petite bascule du backend image ; ils ne touchent pas le pipeline image.

## Workflow migré : `real_final9_qwen_turbo`

Le fichier source `real_final9.json` était un workflow SDXL avec checkpoint RealVisXL, detailers visage/mains et upscale. Ces composants sont incompatibles avec Qwen et ont donc été retirés dans la version migrée.

Conservé dans `real_final9_qwen_turbo` :

- format portrait `832 × 1216` ;
- seed principale `67497826661668` ;
- préfixe de sortie `real_final9_qwen_turbo`.

Le prompt dynamique du fichier source était vide. La migration contient donc un texte de remplacement à modifier avant toute exécution ; ne pas lancer ce workflow sans saisir la scène voulue.

## Reprise demain — ordre recommandé

1. Lancer ComfyUI (`E:\ComfyUI_windows_portable\run_nvidia_gpu.bat`) s’il n’est pas déjà accessible sur `http://127.0.0.1:8188`.
2. Dans ComfyUI, ouvrir `real_final9_qwen_turbo` ou `qwen_image_2_1_t2i` — ne pas ouvrir les anciens onglets `real_final*` SDXL.
3. Renseigner le prompt de scène dans `real_final9_qwen_turbo`, puis générer une image de contrôle.
4. Inspecter le rendu avant de lancer une nouvelle variante : Qwen n’emploie ni ControlNet, ni régions, ni detailers SDXL.
5. Pour ShortPilot, redémarrer l’application afin de charger les changements de `core/aiimg.py`, puis faire un rendu test depuis l’interface ShortPilot.

## Important

- Le dépôt est déjà très modifié et possède de nombreux fichiers non suivis. Ne pas faire de `git reset --hard`, de restauration globale ou de nettoyage Git large.
- Ne pas télécharger les fichiers que proposent les anciens workflows (`RealVisXL`, `qwen_3_4b`, `z_image_turbo`, etc.) : ils ne font pas partie du système Qwen Turbo retenu.
- Les sorties historiques et preuves précédentes doivent rester en place.
