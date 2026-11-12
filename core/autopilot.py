# -*- coding: utf-8 -*-
"""ShortPilot — pilote automatique : génère et publie des vidéos aux heures choisies, chaque jour."""
import datetime
import json
import os
import random
import threading
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE, "data", "autopilot_state.json")


def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"date": "", "fired": []}


def _save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception:
        pass


def status_text(settings):
    ap = settings.get("autopilot", {})
    if not ap.get("enabled"):
        return "Pilote automatique désactivé."
    times = ", ".join(ap.get("times", [])) or "—"
    niches = ", ".join(ap.get("niches", [])) or "aléatoire"
    return f"Actif — {len(ap.get('times', []))} vidéo(s)/jour à {times} · niches : {niches} · langue : {ap.get('language', 'fr').upper()}"


def start_worker(get_settings, enqueue_render_and_publish, log=print):
    """Surveille l'horloge. À chaque heure planifiée : génère script → rendu → publication."""
    def loop():
        log("🤖 Pilote automatique démarré.")
        while True:
            try:
                settings = get_settings()
                ap = settings.get("autopilot", {})
                now = datetime.datetime.now()
                st = _load_state()
                today = now.strftime("%Y-%m-%d")
                if st.get("date") != today:
                    st = {"date": today, "fired": []}
                if ap.get("enabled"):
                    for t in ap.get("times", []):
                        key = f"{today}T{t}"
                        try:
                            hh, mm = [int(x) for x in t.split(":")]
                        except Exception:
                            continue
                        scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        if now >= scheduled and key not in st["fired"] and (now - scheduled).total_seconds() < 3600:
                            st["fired"].append(key)
                            _save_state(st)
                            niches = ap.get("niches") or ["motivation", "faits", "psychologie"]
                            niche = random.choice(niches)
                            log(f"🤖 Pilote auto : lancement d'une vidéo ({niche}) planifiée à {t}")
                            try:
                                enqueue_render_and_publish(niche=niche,
                                                           lang=ap.get("language", "fr"),
                                                           auto_publish=ap.get("auto_publish", False))
                            except Exception as e:
                                log(f"🤖 Erreur pilote auto : {e}")
                _save_state(st)
            except Exception as e:
                log(f"🤖 Pilote auto : {e}")
            time.sleep(45)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return th
