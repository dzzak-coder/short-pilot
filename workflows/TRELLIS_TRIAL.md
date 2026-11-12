# Essai TRELLIS.2 local — 25 octobre 2026

**RETIRÉ à la demande de l’utilisateur le 25 octobre 2026.** Le bouton, le service,
les graphes, les cinq modèles ajoutés et le dossier de test sur E ont été supprimés.
Le manifeste conserve uniquement la trace des fichiers retirés. La description
ci-dessous documente l’essai passé ; ce n’est plus une procédure disponible.

Dans Studio 3D, saisir un objet dans **Créer**, puis utiliser le bouton séparé
**Test TRELLIS.2 — texte → image → 3D**. Le menu Qwen n'est pas utilisé par ce bouton.
Le serveur de test ComfyUI démarre automatiquement sur `127.0.0.1:8189`, avec les
custom nodes désactivés et les entrées/sorties isolées dans
`E:/ShortPilot-AI/Trellis2-Trial`. Les workflows ComfyUI existants ne sont pas modifiés.

Une image de référence est générée avec le checkpoint RealVisXL déjà présent,
détourée par BiRefNet puis recadrée sur fond noir, conformément à l’entrée attendue
par TRELLIS. TRELLIS produit une forme 512, réduite à 100 000 faces et texturée en 1024.
Le résultat GLB est automatiquement importé dans le Studio avec ses matériaux.
Le test est local, sans clé API. Éviter les autres travaux GPU simultanés.

## Vérifications réalisées

- Cinq modèles téléchargés sur E (TRELLIS + détourage BiRefNet de 444 Mo) ;
  taille et SHA256 vérifiés dans le manifeste.
- Image de moto produite et examinée visuellement.
- Forme GLB calculée en 39,77 s sur la RTX 4060 Ti 16 Go.
- Passe texture calculée en 54,32 s, réutilisant la forme en cache ; GLB de 4,2 Mo.
  Ces durées ne constituent pas une mesure complète d'un nouveau rendu.
- Parcours depuis le bouton testé avec une demande en français : image générée,
  GLB produit et importé automatiquement. Le fond reconstruit a révélé la nécessité
  du détourage. Même référence retraitée avec BiRefNet + ImageCropToMask : GLB
  corrigé en 70,75 s, importé et examiné sous plusieurs angles dans le Studio.
- 21 tests Python passent (service TRELLIS et intégration Studio) ; compilation Vite réussie.

## Limites constatées

Sans détourage, le premier test reconstruisait aussi le fond. Le détourage est
maintenant inclus ; le test corrigé montre une moto sans ce fond parasite, avec
des détails encore anguleux/approximatifs. Un objet reconnaissable ne signifie
pas une reproduction exacte. Les parties cachées sont estimées.
TRELLIS donne un maillage, pas une nomenclature mécanique ni un assemblage de pièces CAO.
Le mode reste un essai séparé ; aucune promesse de reconstruction universelle.

## Retrait sur demande

Le manifeste `trellis2_trial_manifest.json` liste les cinq fichiers de modèles
ajoutés pour cet essai. Aucun package Python ni custom node n'a été ajouté.
Le dossier de test contient uniquement ses journaux et ses rendus. Pour retirer
l'essai, arrêter uniquement son serveur 8189, puis retirer ses modèles et fichiers
identifiés ; conserver les checkpoints, autres modèles et workflows préexistants.
