# ShortPilot Studio

ShortPilot crée des Shorts, Reels et TikToks verticaux depuis un script : voix,
sous-titres, montage, musique et visuels. Les images IA sont générées localement
avec ComfyUI et le nœud KSampler.

## Studio 3D intégré (HoloForge) — dont Objaverse

L’onglet **Studio 3D** réunit HoloForge et ShortPilot sur la même adresse locale.
Le dossier fourni a été copié dans `studio3d/` ; l’original n’est pas modifié.

**Nouveauté : Objet 3D depuis Objaverse (800k+ modèles ouverts)**
- Onglet 🌐 **Objaverse** dans Créer : recherche par mot-clé (FR → EN), galerie de 5–10 miniatures rotatives, sélection manuelle, téléchargement GLB unique, cache local, assemblage hologramme (3 phases : dispersion filaire cyan → glissement + flash → balayage lumineux + rotation).
- Filtrage : multi-pièces (meilleur assemblage) / licences / limite résultats.
- Routes API : `/api/studio3d/objaverse/search`, `/download`, `/serve`, `/stats`, `/clear-cache`.
- Backend : `core/objaverse_integration.py` (annotations HF + cache `models/objaverse/`).

1. Générez votre script dans **Créer**, puis cliquez sur **Créer en 3D**.
2. **Objaverse** : tapez un mot (ex. « avion de chasse », « vélo »), sélectionnez dans la galerie, cliquez **Importer & Assembler**.
3. Le studio récupère le sujet, la narration et la durée (20 à 180 secondes),
   puis construit la scène avec son générateur procédural ou le modèle importé.

1. Générez votre script dans **Créer**, puis cliquez sur **Créer en 3D**.
2. Le studio récupère le sujet, la narration et la durée (20 à 180 secondes),
   puis construit la scène avec son générateur procédural. Les sujets techniques
   reconnus disposent de modèles dédiés ; un objet quelconque n’est pas garanti fidèle.
3. Réglez le rendu, la caméra ou importez un modèle STL/OBJ/GLB.
4. **Exporter Vidéo** enregistre la scène et le son ; la capture est convertie
   en MP4 et ajoutée à la **Bibliothèque**, avec une miniature et sa légende.
5. Téléchargez ou publiez depuis le parcours habituel ShortPilot.

Les ponts Ollama/LM Studio et voix système sont intégrés au serveur Python.
Aucun serveur Vite séparé n’est requis. Le bundle compilé est fourni ; pour le
reconstruire après une modification : `cd studio3d`, `npm ci`, `npm run build`.
Le lanceur Windows construit automatiquement le studio si le bundle est absent.
La capture vidéo tourne en temps réel dans le navigateur ; gardez l’onglet visible
pendant l’enregistrement. La voix système capturable dépend des voix installées.

## Modes visuels classiques

- `Images locales directes` : une image ComfyUI par scène, sans clé API ni mouvement de caméra.
- `Images animées gratuites` : les mêmes images ComfyUI avec zooms, panoramiques
  et déplacements verticaux variés au montage, sans clé API ni service externe.
- `Photos réelles CC` et `Arrière-plans graphiques` : rendus rapides sans
  génération IA locale.

Une ligne dans le champ **Scènes** correspond à une image ou un clip. Séparez
les actions successives sur plusieurs lignes afin de les montrer dans l’ordre.

## Démarrage Windows

1. Lancez ComfyUI local sur `http://127.0.0.1:8188` avec un checkpoint image.
2. Double-cliquez sur [ShortPilot.bat](ShortPilot.bat).
3. Ouvrez `http://localhost:8000` si le navigateur ne s’ouvre pas seul.

Les deux modes ComfyUI sont gratuits et locaux. Ils n’utilisent ni clé API,
ni crédits externes, ni abonnement ChatGPT.

## Pipeline gratuit avec mouvement de montage

```text
Script, une ligne par scène
  → image ComfyUI / KSampler locale
  → mouvement de caméra au montage (zoom, panoramique ou déplacement vertical)
  → montage, voix, sous-titres et musique
```

## Vérification développeur

### IA locale du Studio 3D

Ollama portable est installé séparément dans `E:\ShortPilot-AI\Ollama\runtime` ;
les modèles restent dans `E:\ShortPilot-AI\Ollama\models`. Le lanceur ShortPilot
démarre le serveur local s'il est installé et pas encore actif. Aucun service
Windows, démarrage système ou changement global du PATH n'est ajouté.

Dans **Studio 3D → Moteur d'Ingénierie IA**, sélectionner **Ollama** et
`qwen2.5-coder:14b`. Le moteur choisi est mémorisé dans le navigateur.
Ce moteur génère du code de construction : il ne recherche pas le Web et ne
garantit pas une géométrie exacte. L'option **Aide Wikipédia** peut désormais
documenter la demande : elle envoie au maximum 180 caractères de sa description
à Wikipédia, récupère deux introductions et affiche les liens sources dans
Créer. Décochez-la pour un fonctionnement sans documentation Web. Une panne
Web est signalée dans le journal et n'empêche pas la génération locale.
Les références documentent le contexte, pas des dimensions de fabrication certifiées.

Si la sortie JavaScript atteint la limite de tokens, le serveur demande une seule
continuation au modèle. Une reprise incomplète est refusée ; elle n'est pas exécutée
et ne déclenche pas de substitution par un objet du catalogue. Lorsque Node est
disponible, `node --check` contrôle la syntaxe sans exécuter le code avant de le
transmettre au navigateur. Un ancien fragment déjà présent dans Code doit être
régénéré pour profiter de ce contrôle.
La génération normale laisse jusqu'à 240 secondes au moteur pour sa première
réponse. Un dépassement de délai est distingué d'une connexion refusée. Si le
moteur choisi échoue, le studio affiche l'erreur sans construire automatiquement
un objet du catalogue ; le mode procédural reste disponible par sélection explicite.

L'option expérimentale **Photos et schémas**, désactivée par défaut, recherche jusqu'à quatre références sur Wikimedia
Commons (le titre anglais de Wikipédia améliore la recherche internationale).
Les miniatures, licences et liens sources apparaissent dans Créer. Deux images
au maximum sont téléchargées depuis les serveurs Wikimedia autorisés, normalisées,
puis analysées **localement** par `qwen2.5vl:7b` dans Ollama, installé sur E
(environ 6 Go supplémentaires). Ses observations de volumes, positions et connexions
sont ensuite transmises à Qwen Coder. La réponse visuelle est structurée et bornée ;
dans ce parcours, Coder décrit 6 à 20 volumes en JSON (forme, dimensions relatives,
position finale, rotation, matériau, étape). Le serveur valide ces données et émet
uniquement des appels CAD pris en charge. Les positions toutes superposées, coordonnées
non finies et types inconnus sont rejetés. Cela évite de confondre déplacement
d'animation et position finale, sans garantir la fidélité de la silhouette.
un échec arrête cette demande sans substituer silencieusement un objet du catalogue.
Le lecteur visuel libère sa mémoire après l'analyse pour laisser place au modèle Coder.
Le détail des observations est consultable ; il reste estimatif et ne constitue
ni une reconstruction exacte, ni un plan de fabrication. Décocher également cette
option pour ne faire aucune recherche d'images. Ce parcours exige Ollama ; il n'est
pas encore implémenté avec LM Studio. Aucun abonnement ni clé API n'est requis.
Le premier test complet d'hélicoptère s'exécute mais son assemblage reste insuffisant :
cette option ne doit pas être considérée comme une reconstruction 3D fiable.

Pour les demandes commençant par « vélo » ou « bicyclette », Qwen fournit uniquement
des paramètres JSON contrôlés (rayon, empattement, matériau). Le studio utilise
ensuite une base géométrique illustrative avec raccords vérifiés, au lieu
d'exécuter une reconstruction arbitraire de toutes les pièces. Cette garantie
de structure ne s'applique pas encore aux autres familles d'objets.
Éviter un rendu ComfyUI simultané pour laisser
de la mémoire vidéo au modèle. Le serveur écoute uniquement sur `127.0.0.1:11434`.

```powershell
python -m unittest discover -s tests -t . -v
```
#   s h o r t  
 #   s h o r t - p i l o t -  
 #   s h o r t - p i l o t -  
 