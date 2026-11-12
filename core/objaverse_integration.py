"""
Objaverse integration for ShortPilot Studio 3D.
Searches 800k+ annotated 3D models, downloads GLB on demand with local cache.
"""
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import objaverse
    from huggingface_hub import hf_hub_download, HfFileSystem
    OBJAVERSE_AVAILABLE = True
except ImportError:
    OBJAVERSE_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE, "models", "objaverse")
CACHE_DIR = os.path.join(MODELS_DIR, "cache")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

_ANNOTATIONS_LOADED = False
_ANNOTATIONS_LOADING = False
_ANNOTATIONS_ERROR: Optional[str] = None
_ANNOTATIONS: Dict[str, Any] = {}
_ANNOTATIONS_LOCK = threading.Lock()
_LOAD_STATE_LOCK = threading.Lock()
_ANNOTATIONS_BY_UID: Dict[str, Dict[str, Any]] = {}
_ANNOTATIONS_INDEX: List[Tuple[str, str]] = []  # (uid, searchable_text)

# Mots-clés anglais pour les catégories courantes (fallback traduction)
CATEGORY_HINTS = {
    "avion": ["airplane", "aircraft", "jet", "fighter", "plane", "helicopter", "drone"],
    "vélo": ["bicycle", "bike", "motorcycle", "motorbike", "scooter"],
    "voiture": ["car", "automobile", "vehicle", "truck", "bus", "van"],
    "maison": ["house", "building", "home", "cabin", "villa", "architecture"],
    "bateau": ["boat", "ship", "yacht", "submarine", "vessel"],
    "robot": ["robot", "android", "mech", "cyborg"],
    "arme": ["gun", "weapon", "rifle", "pistol", "sword"],
    "meuble": ["chair", "table", "sofa", "bed", "desk", "lamp", "furniture"],
    "animal": ["dog", "cat", "bird", "horse", "animal", "dinosaur"],
    "personne": ["human", "person", "character", "figure", "man", "woman"],
    "arbre": ["tree", "plant", "flower", "forest"],
    "outil": ["tool", "hammer", "wrench", "drill", "screwdriver"],
    "instrument": ["guitar", "piano", "violin", "drum", "instrument"],
    "avion de chasse": ["fighter jet", "military aircraft", "combat aircraft"],
    "avion commercial": ["airliner", "passenger plane", "commercial aircraft"],
    "hélicoptère": ["helicopter", "rotorcraft"],
    "drone": ["drone", "quadcopter", "uav"],
    "fusée": ["rocket", "spacecraft", "missile"],
    "satellite": ["satellite", "space station"],
    "train": ["train", "locomotive", "railway"],
    "moto": ["motorcycle", "motorbike", "dirt bike"],
    "camion": ["truck", "lorry", "semi truck"],
    "bus": ["bus", "coach"],
    "tracteur": ["tractor", "farm equipment"],
    "grue": ["crane", "construction equipment"],
    "pont": ["bridge"],
    "tour": ["tower", "skyscraper"],
    "église": ["church", "cathedral"],
    "château": ["castle", "fortress"],
    "stade": ["stadium", "arena"],
    "aéroport": ["airport", "terminal"],
    "port": ["port", "harbor", "dock"],
    "phare": ["lighthouse"],
    "fontaine": ["fountain"],
    "statue": ["statue", "monument", "sculpture"],
    "horloge": ["clock", "watch"],
    "lampe": ["lamp", "light", "chandelier"],
    "ordinateur": ["computer", "laptop", "server"],
    "téléphone": ["phone", "smartphone", "mobile"],
    "caméra": ["camera"],
    "casque": ["headphones", "headset", "helmet"],
    "montre": ["watch", "smartwatch"],
    "bouteille": ["bottle", "jar", "container"],
    "verre": ["glass", "cup", "mug"],
    "assiette": ["plate", "bowl", "dish"],
    "chaise": ["chair", "seat"],
    "table": ["table", "desk"],
    "lit": ["bed"],
    "canapé": ["sofa", "couch", "armchair"],
    "étagère": ["shelf", "bookshelf", "cabinet"],
    "porte": ["door", "gate"],
    "fenêtre": ["window"],
    "escalier": ["stairs", "staircase"],
    "toit": ["roof"],
    "mur": ["wall", "fence"],
    "sol": ["floor", "ground"],
    "plafond": ["ceiling"],
}


def _load_annotations() -> bool:
    """Charge les annotations Objaverse (une seule fois)."""
    global _ANNOTATIONS_LOADED, _ANNOTATIONS, _ANNOTATIONS_BY_UID, _ANNOTATIONS_INDEX
    with _ANNOTATIONS_LOCK:
        if _ANNOTATIONS_LOADED:
            return True
        # Objaverse conserve déjà ses fragments d'annotations dans son cache.
        # Dupliquer le corpus complet ici produit un JSON de plusieurs Go et
        # ralentit chaque démarrage ; ne garder localement que les GLB choisis.
        if not OBJAVERSE_AVAILABLE:
            return False
        try:
            # Le premier chargement récupère l'index public, puis le cache
            # d'Objaverse est réutilisé par les recherches suivantes.
            _ANNOTATIONS = objaverse.load_annotations()
            _build_index()
            _ANNOTATIONS_LOADED = True
            return True
        except Exception:
            return False


def start_annotations_load() -> bool:
    """Lance le premier indexage dans un thread sans bloquer l'API web."""
    global _ANNOTATIONS_LOADING, _ANNOTATIONS_ERROR
    with _LOAD_STATE_LOCK:
        if _ANNOTATIONS_LOADED or _ANNOTATIONS_LOADING:
            return False
        _ANNOTATIONS_LOADING = True
        _ANNOTATIONS_ERROR = None

    def worker() -> None:
        global _ANNOTATIONS_LOADING, _ANNOTATIONS_ERROR
        try:
            if not _load_annotations():
                _ANNOTATIONS_ERROR = 'Le catalogue Objaverse n’a pas pu être préparé.'
        except Exception:
            _ANNOTATIONS_ERROR = 'Le catalogue Objaverse a rencontré une erreur inattendue.'
        finally:
            with _LOAD_STATE_LOCK:
                _ANNOTATIONS_LOADING = False

    threading.Thread(target=worker, name='objaverse-index', daemon=True).start()
    return True


def _build_index() -> None:
    """Construit un index de recherche à partir des annotations."""
    global _ANNOTATIONS_BY_UID, _ANNOTATIONS_INDEX
    _ANNOTATIONS_BY_UID = {}
    _ANNOTATIONS_INDEX = []
    for uid, ann in _ANNOTATIONS.items():
        if not isinstance(ann, dict):
            continue
        name = str(ann.get('name', '')).lower()
        desc = str(ann.get('description', '')).lower()
        tags = [str(t.get('name', '') if isinstance(t, dict) else t).lower() for t in ann.get('tags', []) if t]
        license_name = str(ann.get('license', '')).lower()
        searchable = ' '.join([name, desc] + tags)
        _ANNOTATIONS_BY_UID[uid] = {
            'uid': uid,
            'name': name,
            'description': desc,
            'tags': tags,
            'license': license_name,
            'file_size': ann.get('file_size', 0),
            'face_count': ann.get('face_count', 0),
            'vertex_count': ann.get('vertex_count', 0),
            'has_multiple_meshes': ann.get('mesh_count', 1) > 1,
        }
        _ANNOTATIONS_INDEX.append((uid, searchable))


def _thumbnail_url(uid: str) -> Optional[str]:
    annotation = _ANNOTATIONS.get(uid, {})
    images = (annotation.get('thumbnails') or {}).get('images') or []
    candidates = []
    for image in images:
        if not isinstance(image, dict):
            continue
        url = str(image.get('url') or '')
        parsed = urlparse(url)
        if parsed.scheme == 'https' and parsed.hostname == 'media.sketchfab.com':
            candidates.append((abs(int(image.get('width') or 0) - 720), url))
    return min(candidates)[1] if candidates else None


def _translate_to_english(text: str) -> str:
    """Traduit FR -> EN pour la recherche."""
    text = text.strip().lower()
    if not text:
        return ''
    # Les recherches du catalogue sont déjà principalement anglophones.
    # Éviter un appel de traduction externe sans délai pour les termes connus.
    for fr_kw in sorted(CATEGORY_HINTS, key=len, reverse=True):
        if text == fr_kw:
            return CATEGORY_HINTS[fr_kw][0]
    if text.isascii():
        return text
    # 1. Essai avec deep_translator
    if TRANSLATOR_AVAILABLE:
        try:
            return GoogleTranslator(source='fr', target='en').translate(text)
        except Exception:
            pass
    # 2. Fallback : correspondance catégorie
    for fr_kw, en_list in CATEGORY_HINTS.items():
        if fr_kw in text:
            return en_list[0]
    # 3. Retourne tel quel (Objaverse a des tags multilingues parfois)
    return text


def search_objaverse(query: str, limit: int = 10, min_parts: int = 1) -> List[Dict[str, Any]]:
    """
    Recherche dans les annotations Objaverse.
    Retourne liste de dicts avec uid, name, description, tags, license, etc.
    Trie par pertinence + nombre de pièces (multi-mesh) pour assemblage.
    """
    if not _load_annotations():
        return []

    en_query = _translate_to_english(query)
    terms = [t for t in re.split(r'[\s,;]+', en_query.lower()) if t]
    if not terms:
        return []

    scored = []
    for uid, searchable in _ANNOTATIONS_INDEX:
        meta = _ANNOTATIONS_BY_UID.get(uid)
        if not meta:
            continue
        if min_parts > 1 and not meta.get('has_multiple_meshes'):
            continue
        score = 0
        for term in terms:
            if term in meta['name']:
                score += 10
            if term in meta['description']:
                score += 5
            if any(term in tag for tag in meta['tags']):
                score += 3
        if score > 0:
            # Bonus pour modèles multi-pièces (meilleurs pour assemblage)
            if meta.get('has_multiple_meshes'):
                score += 2
            # Pénalité pour modèles trop gros (> 50 MB)
            if meta.get('file_size', 0) > 50_000_000:
                score -= 1
            scored.append((score, uid, meta))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, uid, meta in scored[:limit]:
        results.append({
            'uid': uid,
            'name': meta['name'],
            'description': meta['description'][:300] if meta['description'] else '',
            'tags': meta['tags'][:10],
            'license': meta['license'],
            'file_size': meta.get('file_size', 0),
            'face_count': meta.get('face_count', 0),
            'vertex_count': meta.get('vertex_count', 0),
            'has_multiple_meshes': meta.get('has_multiple_meshes', False),
            'relevance_score': score,
            # Le navigateur n'a besoin que de savoir si une miniature peut être
            # servie immédiatement. Ne jamais lui exposer un chemin local.
            'cached': get_cached_model_path(uid) is not None,
            'thumbnail_url': _thumbnail_url(uid),
        })
    return results


def _normalise_uid(uid: str) -> Optional[str]:
    """N'accepte que les UUID Objaverse afin de garder le cache cloisonné."""
    try:
        return uuid.UUID(str(uid)).hex
    except (ValueError, AttributeError, TypeError):
        return None


def download_objaverse_model(uid: str) -> Optional[str]:
    """
    Télécharge un modèle Objaverse (GLB) dans le cache local.
    Retourne le chemin local du fichier .glb ou None si échec.
    """
    uid = _normalise_uid(uid)
    if not uid or not OBJAVERSE_AVAILABLE:
        return None
    cache_path = os.path.join(CACHE_DIR, f"{uid}.glb")
    if os.path.exists(cache_path):
        return cache_path
    try:
        # objaverse.load_objects télécharge depuis S3/HF
        paths = objaverse.load_objects(uids=[uid], download_processes=1)
        if uid in paths and paths[uid]:
            src = paths[uid]
            # Copier vers cache standardisé
            import shutil
            shutil.copy2(src, cache_path)
            return cache_path
    except Exception:
        pass
    return None


def get_cached_model_path(uid: str) -> Optional[str]:
    """Retourne le chemin du modèle en cache s'il existe."""
    uid = _normalise_uid(uid)
    if not uid:
        return None
    cache_path = os.path.join(CACHE_DIR, f"{uid}.glb")
    return cache_path if os.path.exists(cache_path) else None


def clear_objaverse_cache(older_than_days: Optional[int] = None) -> int:
    """Nettoie le cache (optionnel : seulement fichiers plus vieux que N jours)."""
    import time
    count = 0
    cutoff = time.time() - (older_than_days * 86400) if older_than_days else 0
    for fname in os.listdir(CACHE_DIR):
        fpath = os.path.join(CACHE_DIR, fname)
        if os.path.isfile(fpath):
            if cutoff == 0 or os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    count += 1
                except OSError:
                    pass
    return count


def get_objaverse_stats() -> Dict[str, Any]:
    """Statistiques sur le cache et les annotations."""
    cache_files = list(Path(CACHE_DIR).glob('*.glb'))
    total_size = sum(f.stat().st_size for f in cache_files)
    return {
        'annotations_loaded': _ANNOTATIONS_LOADED,
        'annotations_loading': _ANNOTATIONS_LOADING,
        'annotations_error': _ANNOTATIONS_ERROR,
        'total_models_indexed': len(_ANNOTATIONS_BY_UID),
        'multi_mesh_models': sum(1 for m in _ANNOTATIONS_BY_UID.values() if m.get('has_multiple_meshes')) if _ANNOTATIONS_LOADED else 0,
        'cached_models': len(cache_files),
        'cache_size_mb': round(total_size / (1024 * 1024), 1),
        'cache_dir': CACHE_DIR,
    }
