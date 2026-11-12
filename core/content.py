# -*- coding: utf-8 -*-
"""ShortPilot — moteur de génération de scripts pour vidéos courtes.

Produit un script structuré : hook (accroche), scènes, CTA, légende + hashtags.
Base de contenu intégrée FR/EN extensible via data/content_extra.json.
"""
import hashlib
import json
import math
import os
import random
import re
import logging
from pathlib import Path
from . import visual_corpus, visual_planner

VISUAL_PLANNER_VERSION = 13

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")

NICHES = {
    "motivation":   {"fr": "💪 Motivation",        "en": "💪 Motivation",        "badge_fr": "MINDSET",        "badge_en": "MINDSET"},
    "faits":        {"fr": "🤯 Faits insolites",   "en": "🤯 Fun facts",         "badge_fr": "LE SAVAIS-TU ?", "badge_en": "DID YOU KNOW?"},
    "psychologie":  {"fr": "🧠 Psychologie",       "en": "🧠 Psychology",        "badge_fr": "TON CERVEAU",    "badge_en": "YOUR BRAIN"},
    "argent":       {"fr": "💰 Argent & Business", "en": "💰 Money & Business",  "badge_fr": "ARGENT",         "badge_en": "MONEY"},
    "productivite": {"fr": "⚡ Productivité",      "en": "⚡ Productivity",      "badge_fr": "PRODUCTIVITÉ",   "badge_en": "PRODUCTIVITY"},
    "sante":        {"fr": "🌿 Santé & Bien-être", "en": "🌿 Health",            "badge_fr": "SANTÉ",          "badge_en": "HEALTH"},
    "tech":         {"fr": "🤖 Tech & IA",         "en": "🤖 Tech & AI",         "badge_fr": "TECH & IA",      "badge_en": "TECH & AI"},
    "histoire":     {"fr": "🏛️ Histoire",          "en": "🏛️ History",           "badge_fr": "HISTOIRE",       "badge_en": "HISTORY"},
    "actu":        {"fr": "📰 Actualité", "en": "📰 Current affairs", "badge_fr": "DÉCRYPTAGE", "badge_en": "EXPLAINED"},
    "jour":        {"fr": "📅 Ce jour-là", "en": "📅 On this day", "badge_fr": "CE JOUR-LÀ", "badge_en": "ON THIS DAY"},
    "science":     {"fr": "🔬 Science & découvertes", "en": "🔬 Science & discoveries", "badge_fr": "DÉCOUVERTE", "badge_en": "DISCOVERY"},
    "mythes":      {"fr": "🧠 Mythes & réalité", "en": "🧠 Myths & facts", "badge_fr": "MYTHE OU RÉALITÉ ?", "badge_en": "MYTH OR FACT?"},
    "surprise":    {"fr": "🎲 Surprends-moi", "en": "🎲 Surprise me", "badge_fr": "À DÉCOUVRIR", "badge_en": "DISCOVER"},
    "sujet":        {"fr": "✏️ Sujet libre",       "en": "✏️ Custom topic",      "badge_fr": "À SAVOIR",       "badge_en": "MUST KNOW"},
}

COMMON_TAGS_FR = ["shorts", "pourtoi", "fyp", "viral", "apprendresurtiktok"]
COMMON_TAGS_EN = ["shorts", "fyp", "viral", "learnontiktok", "facts"]

DATA = {
    # ------------------------------------------------------------------ FR
    "motivation": {
        "fr": {
            "hooks": ["Personne ne te dira ça.", "Écoute ça si tu veux abandonner.", "Ta vie change aujourd'hui.",
                      "3 vérités qui piquent mais qui changent tout.", "Si tu vois cette vidéo, ce n'est pas un hasard.",
                      "Le secret que 99% des gens ignorent.", "Arrête de scroller. Écoute ça.", "Lis ça avant de dormir ce soir."],
            "items": ["Le succès, c'est 1% de talent et 99% de constance.",
                      "Personne ne viendra te sauver. C'est à toi de bouger.",
                      "Tu n'as pas besoin de motivation. Tu as besoin de discipline.",
                      "Chaque jour où tu procrastines, quelqu'un d'autre prend ta place.",
                      "Ta zone de confort est l'endroit le plus dangereux du monde.",
                      "Dans 5 ans, tu regretteras de ne pas avoir commencé aujourd'hui.",
                      "Les gens qui réussissent ont peur aussi. Ils agissent quand même.",
                      "Ton seul concurrent, c'est la personne que tu étais hier.",
                      "Le doute tue plus de rêves que l'échec.",
                      "Commence petit. Mais commence maintenant.",
                      "La motivation te fait démarrer. L'habitude te fait continuer.",
                      "Tu es à une décision d'une vie complètement différente.",
                      "Personne ne se souvient de ceux qui ont abandonné.",
                      "Fais aujourd'hui ce que les autres ne veulent pas. Tu vivras demain ce que les autres ne peuvent pas.",
                      "Le meilleur moment pour commencer, c'était il y a 10 ans. Le deuxième, c'est maintenant.",
                      "L'échec n'est pas le contraire du succès. Il en fait partie.",
                      "Travaille en silence. Laisse le succès faire le bruit.",
                      "Les champions s'entraînent. Les perdants se plaignent.",
                      "Un petit progrès chaque jour donne de grands résultats.",
                      "Ta seule limite, c'est celle que tu t'imposes.",
                      "Ne compte pas les jours. Fais que les jours comptent.",
                      "Sois trop occupé à construire ta vie pour critiquer celle des autres."],
            "ctas": ["Abonne-toi pour ta dose quotidienne.", "Suis-nous si tu refuses d'abandonner.",
                     "Enregistre cette vidéo pour les jours difficiles.", "Envoie ça à quelqu'un qui en a besoin.",
                     "Abonne-toi. On construit quelque chose de grand ici."],
            "tags": ["motivation", "mindset", "developpementpersonnel", "discipline", "succes", "citation"],
        },
        "en": {
            "hooks": ["Nobody will tell you this.", "Watch this before you give up.", "Your life changes today.",
                      "3 hard truths that change everything.", "If you're seeing this, it's not a coincidence.",
                      "The secret 99% of people ignore.", "Stop scrolling. Listen to this."],
            "items": ["Success is 1% talent and 99% consistency.",
                      "Nobody is coming to save you. It's on you.",
                      "You don't need motivation. You need discipline.",
                      "Every day you procrastinate, someone else takes your spot.",
                      "Your comfort zone is the most dangerous place on earth.",
                      "In 5 years, you'll wish you had started today.",
                      "Successful people are scared too. They act anyway.",
                      "Your only competition is who you were yesterday.",
                      "Doubt kills more dreams than failure ever will.",
                      "Start small. But start now.",
                      "Motivation gets you started. Habit keeps you going.",
                      "You are one decision away from a completely different life.",
                      "Work in silence. Let success make the noise.",
                      "Champions train. Losers complain.",
                      "Small progress every day adds up to big results.",
                      "Your only limit is the one you set yourself.",
                      "Don't count the days. Make the days count."],
            "ctas": ["Follow for your daily dose.", "Follow if you refuse to give up.",
                     "Save this for the hard days.", "Send this to someone who needs it."],
            "tags": ["motivation", "mindset", "discipline", "success", "quotes"],
        },
    },
    "faits": {
        "fr": {
            "hooks": ["Ce fait va te rendre fou.", "99% des gens ignorent ça.", "Ton cerveau ne va pas y croire.",
                      "Le savais-tu ?", "Tu ne verras plus le monde pareil.", "Ce fait a choqué même les scientifiques."],
            "items": ["Les pieuvres ont trois cœurs et le sang bleu.",
                      "Le miel ne périme jamais. On en a trouvé dans des tombes vieilles de 3000 ans.",
                      "Un éclair est 5 fois plus chaud que la surface du soleil.",
                      "Il y a plus d'atomes dans un verre d'eau que de verres d'eau dans tous les océans.",
                      "Les bananes sont des baies. Les fraises, non.",
                      "Ton corps produit 25 millions de nouvelles cellules chaque seconde.",
                      "Un jour sur Vénus dure plus longtemps qu'une année sur Vénus.",
                      "Les requins existaient avant les arbres.",
                      "Le cœur d'une baleine bleue est si grand qu'un humain pourrait nager dans ses artères.",
                      "L'eau chaude peut geler plus vite que l'eau froide. C'est l'effet Mpemba.",
                      "Ton estomac fabrique une nouvelle paroi tous les 3 jours pour ne pas se digérer lui-même.",
                      "Un nuage moyen pèse environ 500 000 kilos.",
                      "Les humains partagent environ 60% de leur ADN avec les bananes.",
                      "La fosse des Mariannes pourrait engloutir l'Everest avec 2 km de marge.",
                      "La tour Eiffel grandit de 15 cm en été à cause de la chaleur.",
                      "Il y a plus de bactéries dans ta bouche que d'humains sur Terre.",
                      "La lumière du soleil met 8 minutes et 20 secondes à nous atteindre.",
                      "Le Sahara était une forêt luxuriante il y a seulement 6000 ans.",
                      "Ton cerveau génère assez d'électricité pour allumer une petite ampoule.",
                      "Les dauphins ont des noms et s'appellent entre eux.",
                      "Les paresseux mettent jusqu'à un mois pour digérer un repas."],
            "ctas": ["Abonne-toi pour un fait par jour.", "Suis-nous pour devenir incollable.",
                     "Lequel t'a le plus choqué ? Dis-le en commentaire.", "Partage ça à un pote curieux."],
            "tags": ["faits", "savaistu", "science", "culture", "insolite"],
        },
        "en": {
            "hooks": ["This fact will blow your mind.", "99% of people don't know this.", "Your brain won't believe this.",
                      "Did you know?", "You'll never see the world the same way."],
            "items": ["Octopuses have three hearts and blue blood.",
                      "Honey never expires. Some was found in 3000-year-old tombs.",
                      "A lightning bolt is 5 times hotter than the surface of the sun.",
                      "There are more atoms in a glass of water than glasses of water in all the oceans.",
                      "Bananas are berries. Strawberries are not.",
                      "Your body makes 25 million new cells every second.",
                      "A day on Venus lasts longer than a year on Venus.",
                      "Sharks existed before trees.",
                      "A blue whale's heart is so big a human could swim through its arteries.",
                      "An average cloud weighs about 500,000 kilograms.",
                      "Humans share about 60% of their DNA with bananas.",
                      "The Eiffel Tower grows 15 cm taller in summer.",
                      "There are more bacteria in your mouth than humans on Earth.",
                      "Sunlight takes 8 minutes and 20 seconds to reach us.",
                      "Your brain generates enough electricity to power a small light bulb."],
            "ctas": ["Follow for one fact a day.", "Follow to become unbeatable at trivia.",
                     "Which one shocked you most? Comment below."],
            "tags": ["facts", "didyouknow", "science", "funfacts"],
        },
    },
    "psychologie": {
        "fr": {
            "hooks": ["Ton cerveau te ment.", "Ces astuces psychologiques sont terrifiantes.",
                      "Apprends ça et personne ne pourra plus te manipuler.", "La psychologie en 30 secondes.",
                      "3 biais cognitifs qui ruinent ta vie."],
            "items": ["Effet de simple exposition : plus tu vois quelqu'un, plus tu l'apprécies.",
                      "Biais de confirmation : ton cerveau cherche ce qui confirme tes croyances et ignore le reste.",
                      "Effet Zeigarnik : ton cerveau retient mieux les tâches inachevées.",
                      "Ancrage : le premier chiffre que tu entends influence toutes tes décisions.",
                      "Effet de halo : si tu trouves quelqu'un beau, tu le juges aussi plus compétent.",
                      "Effet de rareté : ce qui est limité paraît plus précieux.",
                      "La loi de Pareto : 20% de tes actions produisent 80% de tes résultats.",
                      "Effet Dunning-Kruger : moins on sait, plus on se croit compétent.",
                      "Dissonance cognitive : ton cerveau déteste les contradictions et ment pour les effacer.",
                      "Effet spectateur : plus il y a de témoins, moins quelqu'un agit.",
                      "Illusion de transparence : tu crois que les autres lisent en toi. Ils ne lisent pas.",
                      "Effet de dotation : tu surévalues ce que tu possèdes déjà.",
                      "Règle du pic et de la fin : tu juges une expérience par son sommet et sa fin.",
                      "Effet d'amorçage : ce que tu vois juste avant influence ta décision d'après.",
                      "Réactance : interdire quelque chose le rend plus désirable.",
                      "Ton cerveau préfère une petite récompense immédiate à une grande récompense lointaine.",
                      "Loi de Parkinson : le travail s'étend pour remplir le temps disponible.",
                      "Effet Benjamin Franklin : demander un petit service rend les gens plus aimables avec toi.",
                      "Biais de négativité : une critique pèse plus lourd que dix compliments.",
                      "Faux consensus : tu surestimes le nombre de gens qui pensent comme toi.",
                      "Effet IKEA : tu aimes davantage ce que tu as construit toi-même.",
                      "Biais rétrospectif : après coup, tout semblait évident."],
            "ctas": ["Abonne-toi pour comprendre ton cerveau.", "Sauvegarde ça. Ça peut te servir demain.",
                     "Tu savais déjà ça ? Réponds en commentaire."],
            "tags": ["psychologie", "cerveau", "biaiscognitifs", "manipulation", "developpementpersonnel"],
        },
        "en": {
            "hooks": ["Your brain is lying to you.", "These psychology tricks are terrifying.",
                      "Learn this and nobody will manipulate you again.", "Psychology in 30 seconds.",
                      "3 cognitive biases ruining your life."],
            "items": ["Mere exposure effect: the more you see someone, the more you like them.",
                      "Confirmation bias: your brain seeks what confirms your beliefs and ignores the rest.",
                      "Zeigarnik effect: your brain remembers unfinished tasks better.",
                      "Anchoring: the first number you hear influences every decision after.",
                      "Halo effect: if you find someone attractive, you also judge them more competent.",
                      "Scarcity effect: what's limited feels more valuable.",
                      "Pareto law: 20% of your actions produce 80% of your results.",
                      "Dunning-Kruger effect: the less you know, the more competent you feel.",
                      "Bystander effect: the more witnesses, the less anyone acts.",
                      "Endowment effect: you overvalue what you already own.",
                      "Your brain prefers a small reward now over a big reward later.",
                      "Parkinson's law: work expands to fill the time available.",
                      "Benjamin Franklin effect: ask a small favor and people will like you more.",
                      "Negativity bias: one criticism outweighs ten compliments.",
                      "IKEA effect: you love more what you've built yourself."],
            "ctas": ["Follow to understand your brain.", "Save this. It might save you tomorrow."],
            "tags": ["psychology", "brain", "bias", "mindset"],
        },
    },
    "argent": {
        "fr": {
            "hooks": ["Les riches connaissent ça. Pas toi.", "Personne ne t'a appris l'argent à l'école.",
                      "3 erreurs qui te gardent pauvre.", "Si tu gagnes moins que tu veux, écoute ça.",
                      "La règle d'or des millionnaires."],
            "items": ["La règle des 50-30-20 : 50% besoins, 30% envies, 20% épargne.",
                      "Un actif met de l'argent dans ta poche. Un passif en sort.",
                      "Paye-toi en premier : épargne avant de dépenser, pas après.",
                      "Avec les intérêts composés, 100€ placés à 10% doublent tous les 7 ans.",
                      "Ne dépense jamais pour impressionner des gens que tu n'aimes pas.",
                      "Un salaire te fait vivre. Un système te fait vivre sans toi.",
                      "Le temps est plus précieux que l'argent. On regagne de l'argent, jamais du temps.",
                      "Gagne plus, dépense pareil.",
                      "Un problème résolu, c'est une opportunité business.",
                      "Ton réseau vaut plus que ton CV.",
                      "Ne mets pas tous tes œufs dans le même panier.",
                      "L'inflation mange ton argent dormant. Fais-le travailler.",
                      "Commence tôt. Le temps est ton meilleur levier.",
                      "Crée plus d'une source de revenus.",
                      "Dépense moins que tu gagnes. Investis la différence.",
                      "La richesse, c'est le temps que tu peux tenir sans travailler.",
                      "Les pauvres achètent des choses. Les riches achètent du temps.",
                      "Un budget n'est pas une prison. C'est un plan de jeu.",
                      "Automatise ton virement d'épargne le jour de la paie.",
                      "Renégocie tes abonnements une fois par an : 10 minutes, 200 euros.",
                      "Un matelas de sécurité de 3 à 6 mois change ta relation au risque.",
                      "Coût d'opportunité : chaque euro dépensé est un euro qui ne travaille plus."],
            "ctas": ["Abonne-toi pour apprendre l'argent gratuitement.", "Sauvegarde cette vidéo et applique-la ce soir.",
                     "Suis-nous si tu veux ta liberté financière."],
            "tags": ["argent", "finance", "investir", "business", "libertefinanciere", "entrepreneur"],
        },
        "en": {
            "hooks": ["The rich know this. You don't.", "School never taught you about money.",
                      "3 mistakes keeping you broke.", "If you earn less than you want, listen up.",
                      "The golden rule of millionaires."],
            "items": ["The 50-30-20 rule: 50% needs, 30% wants, 20% savings.",
                      "An asset puts money in your pocket. A liability takes it out.",
                      "Pay yourself first: save before you spend, not after.",
                      "With compound interest, $100 at 10% doubles every 7 years.",
                      "Never spend to impress people you don't like.",
                      "A salary makes you a living. A system makes you a fortune.",
                      "Time is worth more than money. You can earn money back, never time.",
                      "Earn more, spend the same.",
                      "A solved problem is a business opportunity.",
                      "Inflation eats idle money. Put it to work.",
                      "Start early. Time is your best leverage.",
                      "Build more than one income stream.",
                      "Wealth is how long you can last without working.",
                      "A budget isn't a prison. It's a game plan.",
                      "Automate your savings transfer on payday.",
                      "An emergency fund of 3-6 months changes your relationship with risk.",
                      "Opportunity cost: every dollar spent is a dollar that no longer works."],
            "ctas": ["Follow to learn money for free.", "Save this and apply it tonight."],
            "tags": ["money", "finance", "investing", "business", "wealth"],
        },
    },
    "productivite": {
        "fr": {
            "hooks": ["Arrête de perdre ton temps.", "3 techniques que les gens productifs gardent pour eux.",
                      "Tu fais tout à l'envers.", "La productivité, sans blabla."],
            "items": ["Règle des 2 minutes : si ça prend moins de 2 minutes, fais-le tout de suite.",
                      "Technique Pomodoro : 25 minutes de focus, 5 minutes de pause.",
                      "Planifie ta journée la veille. Ton futur toi te dira merci.",
                      "Fais la chose la plus dure en premier. Le reste paraîtra facile.",
                      "Chaque oui te coûte du temps. Apprends à dire non.",
                      "Groupe les tâches similaires. Le cerveau déteste changer de contexte.",
                      "3 priorités par jour. Pas 10.",
                      "Le multitâche te rend moins efficace sur tout.",
                      "Fini vaut mieux que parfait.",
                      "Travaille par blocs de 90 minutes : c'est le rythme naturel du cerveau.",
                      "Automatise ce qui se répète.",
                      "Réduis les décisions futiles : habits, repas, planning.",
                      "Commence par 5 minutes. L'élan fera le reste.",
                      "Note tes idées tout de suite. Elles ne repassent pas.",
                      "Matrice d'Eisenhower : urgent n'est pas important. Trie avant d'agir.",
                      "Emails : 2 lectures par jour suffisent largement.",
                      "Un non poli protège des semaines de travail.",
                      "Une réunion sans ordre du jour est une pause déguisée.",
                      "Fais le point le vendredi : qu'est-ce qui a vraiment avancé ?",
                      "Ta productivité commence la nuit d'avant. Dors bien."],
            "ctas": ["Abonne-toi pour devenir une machine.", "Essaie-en une demain et reviens me dire.",
                     "Sauvegarde pour ta prochaine flemme."],
            "tags": ["productivite", "organisation", "focus", "habitudes", "astuces"],
        },
        "en": {
            "hooks": ["Stop wasting your time.", "3 techniques productive people keep to themselves.",
                      "You're doing it all wrong.", "Productivity, no fluff."],
            "items": ["2-minute rule: if it takes less than 2 minutes, do it now.",
                      "Pomodoro technique: 25 minutes of focus, 5 minutes of rest.",
                      "Plan your day the night before. Future you will thank you.",
                      "Do the hardest thing first. Everything else will feel easy.",
                      "Every yes costs you time. Learn to say no.",
                      "Batch similar tasks. The brain hates switching contexts.",
                      "3 priorities a day. Not 10.",
                      "Multitasking makes you worse at everything.",
                      "Done beats perfect.",
                      "Work in 90-minute blocks: it's the brain's natural rhythm.",
                      "Start with just 5 minutes. Momentum does the rest.",
                      "Eisenhower matrix: urgent isn't important. Sort before you act.",
                      "A polite no protects weeks of work.",
                      "A meeting without an agenda is a break in disguise.",
                      "Your productivity starts the night before. Sleep well."],
            "ctas": ["Follow to become a machine.", "Try one tomorrow and report back."],
            "tags": ["productivity", "focus", "habits", "tips"],
        },
    },
    "sante": {
        "fr": {
            "hooks": ["Ce que personne ne t'a dit sur ta santé.", "3 habitudes qui changent tout.", "Ton corps te parle. Écoute."],
            "items": ["Bois un grand verre d'eau au réveil : ton corps est déshydraté.",
                      "Marche 10 minutes après manger. Ta glycémie te dira merci.",
                      "Dors 7 à 9 heures. C'est le seul supplément vraiment magique.",
                      "Le soleil du matin calibre ton horloge interne.",
                      "Ton cerveau consomme 20% de ton énergie. Nourris-le bien.",
                      "Des protéines au petit-déjeuner, et fini le coup de barre de 10h.",
                      "Bouge toutes les heures. La position assise prolongée est un vrai poison.",
                      "Un écran de moins avant de dormir, c'est un sommeil plus profond.",
                      "Fais de la musculation. Tes muscles sont ta banque pour la vieillesse.",
                      "Le rire, la marche, l'eau : le trio santé le plus simple.",
                      "Passe 30 minutes dehors chaque jour. La nature recharge.",
                      "Prévenir vaut mieux que guérir. Fais tes bilans.",
                      "Bois avant d'avoir soif : la soif est déjà un retard.",
                      "Les escaliers comptent : chaque étage est un micro-exercice.",
                      "Une chambre fraîche, 18-19 degrés, améliore vraiment le sommeil.",
                      "Mange des couleurs : une assiette variée couvre plus de nutriments.",
                      "Un seul objectif santé à la fois : l'empilement tue les habitudes.",
                      "Bouge tes épaules et ton cou toutes les heures devant un écran."],
            "ctas": ["Abonne-toi pour prendre soin de toi.", "Partage ça à quelqu'un qui néglige sa santé."],
            "tags": ["sante", "bienetre", "habitudes", "sommeil", "sport"],
        },
        "en": {
            "hooks": ["What nobody told you about your health.", "3 habits that change everything.", "Your body is talking. Listen."],
            "items": ["Drink a big glass of water when you wake up: your body is dehydrated.",
                      "Walk 10 minutes after eating. Your blood sugar will thank you.",
                      "Sleep 7 to 9 hours. It's the only truly magic supplement.",
                      "Morning sunlight sets your internal clock.",
                      "Your brain burns 20% of your energy. Feed it well.",
                      "Protein at breakfast kills the 10am crash.",
                      "Move every hour. Sitting too long is a real poison.",
                      "One less screen before bed means deeper sleep.",
                      "Lift weights. Muscle is your retirement fund.",
                      "Spend 30 minutes outside daily. Nature recharges you.",
                      "Drink before you're thirsty: thirst means you're already behind.",
                      "A cool bedroom, 64-66°F, genuinely improves your sleep.",
                      "Eat the rainbow: a colorful plate covers more nutrients.",
                      "One health goal at a time: stacking kills habits."],
            "ctas": ["Follow to take care of yourself.", "Share this with someone neglecting their health."],
            "tags": ["health", "wellness", "habits", "sleep", "fitness"],
        },
    },
    "tech": {
        "fr": {
            "hooks": ["L'IA va tout changer. Voici pourquoi.", "Tu es en retard si tu ignorais ça.", "La tech expliquée simplement."],
            "items": ["ChatGPT ne sait rien. Il prédit le mot le plus probable.",
                      "Ton smartphone est des millions de fois plus puissant que l'ordinateur d'Apollo 11.",
                      "Le cloud, ce sont juste les ordinateurs des autres.",
                      "Un mot de passe long bat un mot de passe compliqué.",
                      "Les algorithmes te montrent ce qui te retient, pas ce qui est vrai.",
                      "L'automatisation ne remplace pas les gens. Elle remplace les tâches.",
                      "Une IA ne prendra pas ton travail. Une personne qui utilise l'IA, si.",
                      "Sauvegarde tes données : 3 copies, 2 supports, 1 hors de chez toi.",
                      "Le machine learning, c'est apprendre par l'exemple, pas par la règle.",
                      "Le phishing reste l'attaque n°1. La prudence reste la meilleure défense.",
                      "Les mises à jour ne sont pas optionnelles : ce sont des correctifs de sécurité.",
                      "L'IA générative crée. L'IA analytique prédit.",
                      "La double authentification bloque la majorité des piratages de comptes.",
                      "Un gestionnaire de mots de passe vaut mieux que ta mémoire.",
                      "Le mode avion recharge ton téléphone presque deux fois plus vite.",
                      "Tes photos peuvent contenir ta position GPS. Nettoie les métadonnées.",
                      "Signale les SMS frauduleux au 33700. C'est gratuit.",
                      "Vide le cache de ton navigateur chaque mois : vitesse et vie privée."],
            "ctas": ["Abonne-toi pour rester à jour sans effort.", "Suis-nous avant que l'IA ne le fasse à ta place."],
            "tags": ["tech", "ia", "ai", "technologie", "futur"],
        },
        "en": {
            "hooks": ["AI is about to change everything. Here's why.", "You're behind if you didn't know this.", "Tech explained simply."],
            "items": ["ChatGPT doesn't know anything. It predicts the most likely word.",
                      "Your smartphone is millions of times more powerful than the Apollo 11 computer.",
                      "The cloud is just someone else's computer.",
                      "A long password beats a complex password.",
                      "Algorithms show you what keeps you hooked, not what's true.",
                      "Automation doesn't replace people. It replaces tasks.",
                      "AI won't take your job. A person using AI will.",
                      "Back up your data: 3 copies, 2 media, 1 off-site.",
                      "Machine learning is learning by example, not by rules.",
                      "An AI won't take your job. A person with an AI might.",
                      "Two-factor authentication blocks most account hacks.",
                      "A password manager beats your memory.",
                      "Airplane mode charges your phone almost twice as fast.",
                      "Your photos can contain your GPS location. Clean the metadata."],
            "ctas": ["Follow to stay ahead effortlessly.", "Follow before AI does it for you."],
            "tags": ["tech", "ai", "technology", "future"],
        },
    },
    "histoire": {
        "fr": {
            "hooks": ["L'Histoire est plus folle que la fiction.", "Ce que l'école ne t'a pas raconté."],
            "items": ["Cléopâtre vivait plus près de nous que de la construction des pyramides.",
                      "L'université d'Oxford est plus vieille que l'Empire aztèque.",
                      "Nintendo vendait des cartes à jouer quand Jack l'Éventreur sévissait.",
                      "Les mammouths existaient encore quand la Grande Pyramide a été construite.",
                      "La France exécutait encore à la guillotine l'année de la sortie de Star Wars.",
                      "On a envoyé des gens sur la Lune avant d'inventer les valises à roulettes.",
                      "Le 10e président des États-Unis a eu un petit-fils vivant au 21e siècle.",
                      "Les Romains utilisaient de la poudre d'urine comme dentifrice.",
                      "La Grande Muraille se termine dans la mer.",
                      "Azincourt, Waterloo, Trafalgar : trois désastres français, trois leçons d'orgueil.",
                      "Les Vikings ont atteint l'Amérique 500 ans avant Christophe Colomb.",
                      "Le ketchup était vendu comme médicament au 19e siècle.",
                      "Les pyramides étaient blanches et brillantes, couvertes de calcaire poli.",
                      "Le mur de Berlin est tombé à la suite d'une conférence de presse confuse.",
                      "Le Titanic avait deux jumeaux : l'Olympic et le Britannic.",
                      "Le premier vol des frères Wright fut plus court que l'envergure d'un Boeing 747.",
                      "Les fuseaux horaires n'existaient pas avant les chemins de fer.",
                      "Le lait était vendu mélangé à la craie avant la réglementation alimentaire."],
            "ctas": ["Abonne-toi pour voyager dans le temps.", "Lequel t'a surpris ? Dis-le en commentaire."],
            "tags": ["histoire", "culture", "anecdotes", "savoir"],
        },
        "en": {
            "hooks": ["History is crazier than fiction.", "What school never taught you."],
            "items": ["Cleopatra lived closer to us than to the building of the pyramids.",
                      "Oxford University is older than the Aztec Empire.",
                      "Nintendo sold playing cards while Jack the Ripper was active.",
                      "Mammoths were still alive when the Great Pyramid was built.",
                      "Humans went to the Moon before suitcases had wheels.",
                      "The Romans used urine powder as toothpaste.",
                      "The Great Wall of China ends in the sea.",
                      "The Vikings reached America 500 years before Columbus.",
                      "Ketchup was sold as medicine in the 19th century.",
                      "The pyramids were originally white, covered in polished limestone.",
                      "The Berlin Wall fell because of a confused press conference.",
                      "The Titanic had two twin ships: the Olympic and the Britannic.",
                      "The Wright brothers' first flight was shorter than a Boeing 747's wingspan."],
            "ctas": ["Follow to travel through time.", "Which one surprised you? Comment below."],
            "tags": ["history", "facts", "culture", "knowledge"],
        },
    },
}


def _load_extra():
    """Contenu personnalisé optionnel : data/content_extra.json (même structure que DATA)."""
    path = os.path.join(DATA_DIR, "content_extra.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _merged(niche, lang):
    if niche in ("actu", "jour", "science", "mythes"):
        english = lang == "en"
        ctas = {
            "actu": ("Abonne-toi pour comprendre la suite.", "Follow to understand what happens next."),
            "jour": ("Abonne-toi pour découvrir une autre journée de l'histoire.", "Follow for another day in history."),
            "science": ("Abonne-toi pour explorer d'autres découvertes.", "Follow to explore more discoveries."),
            "mythes": ("Enregistre ces faits pour vérifier les idées reçues.", "Save these facts to check common beliefs."),
        }
        return {"ctas": [ctas[niche][int(english)]], "tags": {
            "actu": ["news", "actualite", "decryptage"], "jour": ["histoire", "history", "cejourla"],
            "science": ["science", "decouverte"], "mythes": ["mythes", "facts", "verification"],
        }[niche]}
    base = DATA.get(niche, {}).get(lang) or DATA.get(niche, {}).get("fr")
    extra = (_load_extra().get(niche, {}) or {}).get(lang) or {}
    if not base:
        return None
    out = {k: list(v) for k, v in base.items()}
    for k, v in extra.items():
        if isinstance(v, list):
            out.setdefault(k, [])
            out[k] = out[k] + v
    return out


def _used_path():
    return os.path.join(DATA_DIR, "used.json")


def _load_used():
    try:
        with open(_used_path(), "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _mark_used(used_set, sig):
    used_set.add(sig)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_used_path(), "w", encoding="utf-8") as f:
            json.dump(sorted(list(used_set))[-5000:], f)
    except Exception:
        pass


def _topic_script(topic, lang, target=None):
    """Fallback sujet libre : transforme le sujet en progression, pas en fiche.

    La source Web reste le choix à privilégier pour les faits. Ce plan local
    intervient uniquement hors-ligne : il n'invente donc aucun fait absent du
    sujet. Lorsque l'utilisateur donne déjà des jalons (virgules, deux-points,
    tirets), ils deviennent les scènes, dans le même ordre.
    """
    topic = topic.strip().rstrip(".")
    # A subject such as "Apollo 11 : alarme, carburant, Armstrong" contains
    # its own narrative spine. Preserve it rather than repeating the entire
    # sentence in five generic numbered prompts.
    chunks = [part.strip(" -–—:;,") for part in re.split(r"\s*(?:[,:;]|[—–])\s*", topic)
              if part.strip(" -–—:;,")]
    title = chunks[0] if chunks else topic
    cues = chunks[1:]

    if lang == "en":
        if cues:
            items = [
                f"The story begins with {title}: {cues[0]}.",
                *[f"Then, {title} reaches a new turning point: {cue}." for cue in cues[1:]],
                f"That sequence is what makes {title} worth remembering.",
            ]
        else:
            items = [
                f"Start with the real setting of {title}: where and when it matters.",
                f"Define the starting point of {title} and the people or forces involved.",
                f"Explain what existed before {title} and why the situation could not remain stable.",
                f"Introduce the first decision that set {title} in motion.",
                f"Show the obstacle that changed the expected course of {title}.",
                f"Move to the decisive moment when {title} took on its full meaning.",
                f"Explain the immediate consequence of that turning point in {title}.",
                f"Then show how the people concerned reacted to the events of {title}.",
                f"Connect that reaction to the longer-term result of {title}.",
                f"Clarify what changed permanently after {title}.",
                f"Correct the most common oversimplification about {title}.",
                f"End with the concrete legacy that still makes {title} relevant today.",
                f"That is the image the audience should retain from {title}.",
            ]
        return {
            "hooks": [f"{title}: the story in {duration_label(target, lang)}"],
            "items": items,
            "ctas": ["Follow for more stories like " + title + "."],
            "tags": [t for t in title.lower().split() if t.isalnum()][:4],
        }

    if cues:
        items = [
            f"L'histoire commence avec {title} : {cues[0]}.",
            *[f"Puis, {title} bascule sur un nouveau moment : {cue}." for cue in cues[1:]],
            f"C'est cette suite d'événements qui rend {title} mémorable.",
        ]
    else:
        items = [
            f"D'abord, pose le décor réel de {title} : le lieu, l'époque et les personnes concernées.",
            f"Définis le point de départ de {title} et les forces qui sont déjà en présence.",
            f"Explique ce qui existait avant {title} et pourquoi la situation ne pouvait pas rester stable.",
            f"Présente la première décision qui met réellement {title} en mouvement.",
            f"Montre l'obstacle qui détourne {title} de son déroulement attendu.",
            f"Arrive au moment décisif où {title} prend tout son sens.",
            f"Explique la conséquence immédiate de ce tournant dans {title}.",
            f"Montre ensuite comment les personnes concernées réagissent aux événements de {title}.",
            f"Relie cette réaction au résultat durable de {title}.",
            f"Précise ce qui change définitivement après {title}.",
            f"Corrige l'idée trop simplifiée que l'on répète souvent sur {title}.",
            f"Termine par l'héritage concret qui rend encore {title} important aujourd'hui.",
            f"C'est cette image qui doit rester quand on parle de {title}.",
        ]
    return {
        "hooks": [f"{title} : l'histoire en {duration_label(target, lang)}"],
        "items": items,
        "ctas": [f"Abonne-toi pour d'autres histoires comme {title}."],
        "tags": [t for t in title.lower().split() if t.isalnum()][:4],
    }


# Débit mesuré sur Hortense (fr-FR, SAPI, hors ligne) : 1451 car. / 100.56 s ≈ 14.43 car/s.
# Constante utilisée pour estimer la narration et dimensionner les scripts.
CPS = 14.43         # caractères/seconde (Hortense fr-FR)
PAD = 0.55          # pause de fin de scène
DURATION_OPTIONS = [0, 20, 30, 45, 60, 90, 120, 180, 240, 300]   # 0 = auto — max 5 min


def duration_label(target, lang="fr"):
    """Human label matching the duration actually requested by the user."""
    seconds = int(target or 35)
    if lang == "fr":
        if seconds == 60:
            return "une minute"
        if seconds > 60:
            minutes, remaining = divmod(seconds, 60)
            minute_text = "une minute" if minutes == 1 else f"{minutes} minutes"
            return minute_text if not remaining else f"{minute_text} et {remaining} secondes"
        return f"{seconds} secondes"
    if seconds == 60:
        return "one minute"
    if seconds > 60:
        minutes, remaining = divmod(seconds, 60)
        minute_text = "one minute" if minutes == 1 else f"{minutes} minutes"
        return minute_text if not remaining else f"{minute_text} and {remaining} seconds"
    return f"{seconds} seconds"


def visual_plan_fingerprint(scenes, *, title="", niche="", language=""):
    """Stable revision marker, including the actual planner/compiler code."""
    planner_files = ("visual_planner.py", "visual_constraints.py")
    planner_code = hashlib.sha256(b"".join(
        (Path(__file__).with_name(name)).read_bytes() for name in planner_files
    )).hexdigest()
    payload = {
        "planner_version": VISUAL_PLANNER_VERSION,
        "planner_compiler_sha256": planner_code,
        "scenes": [" ".join(str(s or "").split()) for s in (scenes or []) if str(s or "").strip()],
        "visual_proposals": visual_proposals_for_scenes(scenes),
        "title": " ".join(str(title or "").split()), "niche": str(niche or ""),
        "language": str(language or ""),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _concrete_plan(scene, *, role="beat", human_mode="auto", title="", niche="", language=""):
    """Compatibility entry point backed by the universal semantic planner."""
    del role, human_mode
    return visual_plan_bundle([scene], title=title, niche=niche, language=language)["visual_plans"][0]


_IMAGE_FRAMINGS = (
    "wide establishing shot",
    "medium documentary shot",
    "close detail shot",
    "low-angle architectural shot",
    "high-angle documentary shot",
    "three-quarter perspective",
    "symmetrical frontal composition",
    "side perspective with foreground depth",
)


def _image_assignment_bundle(scenes, image_assignments, visual_anchors):
    """Compile corpus-grounded image plans via prompt_builder v2 (canonique, autonome)."""
    try:
        from fix_prompts.prompt_builder import build_image_prompts_v2
    except Exception:
        from .fix_prompts.prompt_builder import build_image_prompts_v2  # type: ignore

    logger = logging.getLogger(__name__)
    cleaned = [str(scene or "").strip() for scene in (scenes or []) if str(scene or "").strip()]
    anchor_map = {item.get("id"): item for item in (visual_anchors or [])}
    normalized = []
    for offset, assignment in enumerate(image_assignments or []):
        if isinstance(assignment, dict):
            scene_index = int(assignment.get("scene_index") or 0)
            anchor_id = str(assignment.get("anchor_id") or "")
            image_index = int(assignment.get("image_index") or offset + 1)
            label = str(assignment.get("label") or "")
        else:
            scene_index, anchor_id = assignment
            scene_index, anchor_id, image_index = int(scene_index), str(anchor_id), offset + 1
            label = ""
        if not 1 <= scene_index <= len(cleaned) or anchor_id not in anchor_map:
            raise ValueError("Affectation image ou ancrage de corpus invalide")
        if not label:
            label = " ".join(str(anchor_map[anchor_id].get("label") or anchor_id).split())
        normalized.append({
            "image_index": image_index,
            "scene": scene_index,
            "anchor_id": anchor_id,
            "label": label,
        })

    prompt_items = build_image_prompts_v2(normalized, log=logger.info)
    if len(prompt_items) != len(normalized):
        # Des ancrages exclus ont été écartés par le builder : l'appelant doit traiter la
        # réaffectation en amont. On refuse une sortie partielle silencieuse.
        excluded = [item for item in normalized
                    if item["image_index"] not in {p.get("image_index") for p in prompt_items}]
        raise ValueError(
            f"Prompts v2 incomplets: {len(prompt_items)}/{len(normalized)} générés; "
            f"ancrages exclus/non injectés={excluded!r}"
        )

    image_plans, controls = [], []
    for item in prompt_items:
        scene_index = int(item.get("scene") or 0)
        control = {
            "kind": "explicit",
            "human_mode": "auto",
            "required_terms": [],
            "negative_terms": [],
            "source_facts": [],
            "canonical_entity": item.get("label"),
            "anchor_id": item.get("anchor_id"),
            "source_anchor_id": item.get("anchor_id"),
            "image_index": item.get("image_index"),
            "scene_index": scene_index,
            "exterior": item.get("exterior"),
        }
        image_plans.append({
            "image_index": item.get("image_index"),
            "scene_index": scene_index,
            "anchor_id": item.get("anchor_id"),
            "source_anchor_id": item.get("anchor_id"),
            "prompt": item.get("prompt"),
            "exterior": item.get("exterior"),
            "control": control,
        })
        controls.append(control)

    fingerprint = hashlib.sha256(json.dumps(
        [(item["scene_index"], item["anchor_id"], item["prompt"]) for item in image_plans],
        ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "visual_plans": [item["prompt"] for item in image_plans],
        "visual_controls": controls,
        "image_plans": image_plans,
        "visual_plan_fingerprint": fingerprint,
    }


def visual_plan_bundle(scenes, *, title="", niche="", language="",
                       image_assignments=None, visual_anchors=None):
    if image_assignments is not None:
        return _image_assignment_bundle(scenes, image_assignments, visual_anchors)
    cleaned = [str(scene or "").strip() for scene in (scenes or []) if str(scene or "").strip()]
    briefs = visual_briefs_for_scenes(cleaned)
    proposals = [brief["visual_proposition"] for brief in briefs]
    planned_indices = [i for i, brief in enumerate(briefs) if not brief["needs_context"]]
    planned = visual_planner.plan_scenes(
        [proposals[i] for i in planned_indices], title=title, niche=niche, language=language)
    plans = [""] * len(briefs)
    controls = [{"kind": "contextual", "human_mode": "auto", "required_terms": [],
                 "needs_context": True} for _ in briefs]
    if (len(planned["visual_plans"]) != len(planned_indices)
            or len(planned["visual_controls"]) != len(planned_indices)):
        raise ValueError("Le planificateur n'a pas retourné un résultat par scène planifiée")
    for offset in range(len(planned_indices)):
        scene_index = planned_indices[offset]
        plans[scene_index] = planned["visual_plans"][offset]
        controls[scene_index] = planned["visual_controls"][offset]

    anchors = [i for i in planned_indices
               if plans[i] and not controls[i].get("planning_error")]
    title_anchor = None
    if not planned_indices and briefs and title:
        title_bundle = visual_planner.plan_scenes(
            [str(title)], title="", niche=niche, language=language)
        if (title_bundle["visual_plans"] and title_bundle["visual_plans"][0]
                and not title_bundle["visual_controls"][0].get("planning_error")):
            title_anchor = (title_bundle["visual_plans"][0],
                            title_bundle["visual_controls"][0])
    for i, brief in enumerate(briefs):
        if not brief["needs_context"]:
            continue
        if not anchors and title_anchor is None:
            controls[i]["planning_error"] = (
                f"Scène {i + 1} : contexte visuel requis mais aucun ancrage validé")
            continue
        if anchors:
            anchor = min(anchors, key=lambda candidate: (abs(candidate - i), candidate > i, candidate))
            anchor_plan, anchor_control = plans[anchor], controls[anchor]
            context_ref = {"context_scene_index": anchor}
        else:
            anchor_plan, anchor_control = title_anchor
            context_ref = {"context_source": "title"}
        plans[i] = anchor_plan + ", clean negative space for captions"
        controls[i] = {**anchor_control, "kind": "contextual", "needs_context": True,
                       **context_ref,
                       "reason": "Scène non illustrable : continuité depuis l’ancrage validé voisin"}
    bundle = {"visual_plans": plans, "visual_controls": controls}
    bundle["visual_proposals"] = proposals
    bundle["visual_briefs"] = briefs
    bundle["visual_plan_fingerprint"] = visual_plan_fingerprint(
        cleaned, title=title, niche=niche, language=language)
    return bundle


def visual_plans_for_scenes(scenes, *, title="", niche="", language=""):
    """Return one concise English renderer prompt for each narration scene."""
    return visual_plan_bundle(scenes, title=title, niche=niche, language=language)["visual_plans"]


def with_visual_plans(script):
    """Attach renderer-only shot briefs while preserving the public script."""
    if not isinstance(script, dict):
        return script
    scenes = script.get("scenes") or []
    script.update(visual_plan_bundle(scenes, title=script.get("title", ""),
                                     niche=script.get("niche", ""), language=script.get("language", "")))
    suffix = ", clean negative space for captions"
    subject_keys = set()
    for plan in script.get("visual_plans") or []:
        normalized = " ".join(str(plan or "").split())
        while normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].rstrip()
        if normalized:
            subject_keys.add(normalized)
    anchors_before = len(subject_keys)
    corpus_sources = script.get("visual_corpus") or []
    corpus_anchors = visual_corpus.extract_visual_anchors(corpus_sources)
    principal_anchors = [anchor for anchor in corpus_anchors
                         if anchor.get("scope") == "principal"]
    corpus_words = sum(word_count(source.get("text", "") if isinstance(source, dict) else source)
                       for source in corpus_sources)
    script["visual_anchors"] = corpus_anchors
    distribution = visual_corpus.distribute_visual_anchors(
        scenes, corpus_anchors, visual_briefs=script.get("visual_briefs") or [])
    script["visual_anchor_distribution"] = distribution
    anchors_available = distribution["distinct_anchors_used"] if corpus_sources else anchors_before
    script["visual_budget"] = visual_corpus.visual_budget(
        script.get("target_seconds") or script.get("estimated_seconds") or 0,
        anchors_available,
        corpus_word_count=corpus_words,
        anchors_before=anchors_before,
        scene_count=distribution["scene_count"] if corpus_sources else None,
        scenes_without_anchor=distribution["scenes_without_anchor"] if corpus_sources else None,
        visually_distinct_subjects=(distribution["visually_distinct_subjects"]
                                    if corpus_sources else anchors_available),
    )
    budget = script["visual_budget"]
    if (corpus_sources and budget["verdict"] == "insufficient"
            and budget["sustainable_duration_seconds"] < budget["duration_seconds"]):
        message = (
            f"Couverture visuelle insuffisante : {distribution['scenes_without_anchor']}/"
            f"{distribution['scene_count']} scènes sans ancrage. "
            f"Durée soutenable proposée : ~{budget['sustainable_duration_seconds']:.0f} s."
        )
        if message not in script.setdefault("warnings", []):
            script["warnings"].append(message)
    errors = [f"Scène {i + 1} : {c['planning_error']}" for i, c in enumerate(script["visual_controls"])
              if c.get("planning_error")]
    if errors:
        script.setdefault("warnings", []).extend(errors)
    return script


def estimate_seconds(scenes):
    return sum(len(s) for s in scenes) / CPS + PAD * len(scenes)


# Débit de narration configurable par langue (mots par minute).
# FR calibré sur Hortense (SAPI, hors ligne): ~14.43 car/s et ~7.0 car/mot observés
# => ~124 mots/min, cohérent avec estimate_seconds (CPS).
WORDS_PER_MINUTE = {"fr": 124, "en": 155}


def word_count(text):
    return len(re.findall(r"\b[\w]+(?:['’\-][\w]+)*\b", str(text), re.UNICODE))


def target_words(target=None, lang="fr"):
    return round(float(target or 35) * WORDS_PER_MINUTE.get(lang, 155) / 60)


_SCENE_SPLIT = re.compile(
    r"(?<=[.!?])(?<!\.\.)(?<!…)\s+|(?<=\.\.)\s+(?=[A-ZÀ-ÖØ-Þ«\"“0-9])|(?<=…)\s+(?=[A-ZÀ-ÖØ-Þ«\"“0-9])|\n+")


def short_scenes(lines, max_words=22, grouped=False):
    """Déduplique et découpe les phrases sans ajouter de faits ni de remplissage."""
    groups, seen = [], set()
    for line in lines:
        for sentence in _SCENE_SPLIT.split(str(line or "")):
            sentence = re.sub(r"\s+", " ", sentence).strip()
            signature = re.sub(r"[\W_]+", "", sentence.casefold())
            if not signature or signature in seen:
                continue
            seen.add(signature)
            # A comma can introduce an apposition, relative or participial
            # group. Split only at an unambiguous clause boundary; when there
            # is none, retain the complete sentence even above the word guide.
            # Semicolons join independent clauses. A colon followed by a
            # lowercase list ("sont : la plus haute...") is not a beat.
            clauses = re.split(r"(?<=;)\s+|(?<=:)\s+(?=[A-ZÀ-ÖØ-Þ])", sentence)
            pieces = []
            current = ""
            for clause in clauses:
                joined = f"{current} {clause}".strip()
                if current and len(joined.split()) > max_words:
                    pieces.append(current)
                    current = clause
                else:
                    current = joined
            if current:
                pieces.append(current)
            groups.append(pieces)
    if not grouped:
        # Deux phrases différentes peuvent partager un même segment après découpage.
        return list(dict.fromkeys(p for g in groups for p in g))
    out, seen_pieces = [], set()
    for g in groups:
        g = [p for p in g if p not in seen_pieces]
        seen_pieces.update(g)
        if g:
            out.append(g)
    return out


_FR_FINITE_VERBS = (
    r"est|sont|suis|sommes|êtes|était|étaient|fut|furent|sera|seront|serait|seraient|"
    r"a|ont|avait|avaient|eut|eurent|aura|auront|fait|font|fit|firent|"
    r"demeure|demeurent|reste|restent|devient|deviennent|se\s+situe|se\s+situent|"
    r"forme|forment|construit|construisent|ouvre|ouvrent|éclaire|éclairent|"
    r"révèle|révèlent|présente|présentent|montre|montrent"
)
_FR_EXPLICIT_SUBJECT = re.compile(
    rf"^((?:le|la|les|l['’]|un|une|des|ce|cet|cette|ces)\s+.+?)"
    rf"(?=\s*,|\s+(?:{_FR_FINITE_VERBS})\b)", re.IGNORECASE)
_FR_EXPLICIT_HEAD = re.compile(
    r"^(?:le|la|les|l['’]|un|une|des|ce|cet|cette|ces|deux|trois|quatre|cinq|"
    r"six|sept|huit|neuf|dix)\s+[a-zà-öø-ÿ]",
    re.IGNORECASE)
_FR_SUBJECT_PRONOUN = re.compile(
    rf"\b(elle|il|ils|elles|celui-ci|celle-ci|ce dernier|cette dernière)\b"
    rf"(?=\s+(?:{_FR_FINITE_VERBS})\b)", re.IGNORECASE)
_FR_PARTICIPLE_HEAD = re.compile(
    r"^(?:en\s+)?(?:[a-zà-öø-ÿ'’-]+ant|construit(?:e|es|s)?|édifi(?:é|ée|és|ées)|"
    r"situ(?:é|ée|és|ées)|parti(?:e|es|s)?|né(?:e|es|s)?|présumé(?:e|es|s)?)\b",
    re.IGNORECASE)
_FR_ELLIPTIC_HEAD = re.compile(
    r"^(?:à|au|aux|dans|de|du|des|depuis|devant|derrière|durant|en|entre|près|"
    r"sans|sous|sur|vers)\b", re.IGNORECASE)
_EDITORIAL_CONTEXT = re.compile(
    r"^(?:abonne[ -]toi|subscribe|follow|suis[ -]nous|enregistre|partage|"
    r"regarde\s+bien|et\s+maintenant|le\s+fait\s+essentiel\s+à\s+connaître)\b|"
    r"\b(?:l['’]essentiel|l['’]histoire\s+derrière\s+le\s+sujet)\b",
    re.IGNORECASE)
_NONILLUSTRABLE_VISUAL = re.compile(
    r"(?:^c['’]est\b|\brien\s+ne\s+permet\s+d['’]affirmer\b|"
    r"\b(?:méthodes?|données|théories?)\b.*\b(?:incertain|incertaines|"
    r"fragmentaire|fragmentaires|se\s+multiplient|se\s+focalisent)\b|"
    r"\bse\s+focalisent\b|"
    r"\bspéculations?\s+pseudo-scientifiques\b)", re.IGNORECASE)


def _explicit_visual_antecedent(text):
    """Return only a source-explicit French subject; never infer an entity."""
    match = _FR_EXPLICIT_SUBJECT.search(text)
    return match.group(1).strip(" ,;:") if match else None


def _autonomous_visual_proposition(text, antecedent):
    """Resolve source ellipses deterministically, returning (text, used, needed)."""
    if _EDITORIAL_CONTEXT.match(text):
        return text, None, True
    nonillustrable = bool(_NONILLUSTRABLE_VISUAL.search(text))
    pronoun = _FR_SUBJECT_PRONOUN.search(text)
    if pronoun:
        if not antecedent:
            return text, None, True
        prefix = text[:pronoun.start()].strip()
        suffix = text[pronoun.end():].lstrip()
        location = re.search(r"\bau\s+centre\b.+$", suffix, re.IGNORECASE)
        if location:
            location_text = re.sub(
                r"\s+qui\s+se\s+situe\s+à\s+", " à ", location.group(0),
                flags=re.IGNORECASE)
            return f"{antecedent} {location_text}", antecedent, nonillustrable
        if prefix.endswith(","):
            # The autonomous proposition is the finite pronoun clause.  The
            # preceding apposition remains narrated, but is not required to
            # make this visual beat grammatical or identifiable.
            return f"{antecedent} {suffix}", antecedent, nonillustrable
        return (f"{text[:pronoun.start()]}{antecedent} {suffix}".strip(),
                antecedent, nonillustrable)

    if nonillustrable:
        return text, None, True

    requires_subject = bool(_FR_PARTICIPLE_HEAD.match(text) or _FR_ELLIPTIC_HEAD.match(text))
    main_clause = re.split(r"\b(?:qui|que|dont|où)\b", text, maxsplit=1,
                           flags=re.IGNORECASE)[0]
    if not re.search(rf"\b(?:{_FR_FINITE_VERBS})\b", main_clause, re.IGNORECASE):
        requires_subject = True
    if not requires_subject:
        return text, None, False
    if not antecedent:
        return text, None, True
    square_base = re.match(
        r"^formant\s+une\s+pyramide\s+à\s+base\s+(.+)$", text, re.IGNORECASE)
    if square_base:
        return f"{antecedent} a une base {square_base.group(1)}", antecedent, False
    # A dated introductory frame is narrated but is not a spatial ``sous``
    # relation.  Prefer the following concrete location for the visual beat.
    text = re.sub(
        r"^sous\s+(?:la|le)\s+(?:[ivxlcdm0-9]+\s+)?"
        r"(?:dynastie|règne|siècle|époque)\b[^,]*,\s*", "", text,
        count=1, flags=re.IGNORECASE)
    text = re.sub(r"\s+qui\s+se\s+situe\s+à\s+", " à ", text,
                  flags=re.IGNORECASE)
    return f"{antecedent}, {text[:1].lower() + text[1:]}", antecedent, False


def visual_briefs_for_scenes(scenes):
    """Build autonomous visual text while preserving narration byte-for-byte."""
    briefs, antecedent = [], None
    for scene in scenes or []:
        narration = str(scene or "")
        normalized = " ".join(narration.split())
        if not normalized:
            continue
        candidates = short_scenes([normalized], max_words=22)
        complete = [part for part in candidates if 5 <= word_count(part) <= 22
                    and not part.endswith(":")]
        selected = complete[0] if complete else normalized
        explicit = _explicit_visual_antecedent(normalized)
        square_base = re.search(
            r"\bformant\s+une\s+pyramide\s+à\s+base\s+([^,;.!?]+[.!?]?)",
            selected, re.IGNORECASE)
        if explicit and square_base:
            ending = square_base.group(1).rstrip(" ,;:")
            proposition, used, needs_context = (
                f"{explicit} a une base {ending}", None, False)
        else:
            proposition, used, needs_context = _autonomous_visual_proposition(selected, antecedent)
        if (needs_context and _FR_EXPLICIT_HEAD.match(selected)
                and not _NONILLUSTRABLE_VISUAL.search(selected)):
            needs_context = False
        briefs.append({
            "narration": narration,
            "visual_proposition": proposition,
            "antecedent": used,
            "needs_context": needs_context,
        })
        if explicit:
            antecedent = explicit
    return briefs


def visual_proposals_for_scenes(scenes):
    """Compatibility list backed by the autonomous derived briefs."""
    return [brief["visual_proposition"] for brief in visual_briefs_for_scenes(scenes)]


def _coverage_summary(scenes, anchors, *, generic_terms=None):
    distribution = visual_corpus.distribute_visual_anchors(
        scenes, anchors, generic_terms=generic_terms)
    return {
        "scene_count": distribution["scene_count"],
        "scenes_without_anchor": distribution["scenes_without_anchor"],
        "scenes_without_anchor_rate": distribution["scenes_without_anchor_rate"],
        "visually_distinct_subjects": distribution["visually_distinct_subjects"],
    }


def _coverage_guided_groups(groups, anchors, *, base_words, wanted,
                            generic_terms=None, minimum_groups=0, maximum_groups=None):
    """Prefer source groups with visual support, then restore source order."""
    unique, seen = [], set()
    for group in groups:
        parts = [str(part).strip() for part in group if str(part).strip()]
        signature = " ".join(parts).casefold()
        if parts and signature not in seen:
            seen.add(signature)
            unique.append(parts)
    if not unique or not anchors:
        return unique
    rows = visual_corpus.distribute_visual_anchors(
        [" ".join(group) for group in unique], anchors,
        generic_terms=generic_terms)["scenes"]
    ranked = sorted(
        range(len(unique)),
        key=lambda index: (
            rows[index]["anchors_available"] == 0,
            max(0, len({anchor["visual_subject_id"] for anchor in rows[index]["anchors"]}) - 3),
            sum(word_count(part) for part in unique[index]),
            -rows[index]["anchors_available"],
            index,
        ),
    )
    chosen, total = [], int(base_words)
    ceiling = wanted * 1.15
    for index in ranked:
        count = sum(word_count(part) for part in unique[index])
        if total + count > ceiling:
            continue
        chosen.append(index)
        total += count
        if maximum_groups is not None and len(chosen) >= maximum_groups:
            break
        if total >= wanted * .97 and len(chosen) >= minimum_groups:
            break
    return [unique[index] for index in sorted(chosen)]


def fit_script(script, target=None, *, extra_lines=()):
    """Contrôle final commun : budget de mots, plans courts et diagnostic visible."""
    lang = script.get("language", "fr")
    wanted = target_words(target, lang)
    script["warnings"] = [w for w in script.get("warnings", [])
                          if not w.startswith("Contenu insuffisant :")]
    scenes = script.get("scenes") or []
    hook = str(script.get("hook") or (scenes[0] if scenes else script.get("title", "")))
    cta = str(script.get("cta") or (scenes[-1] if scenes else ""))
    corpus_anchors = visual_corpus.extract_visual_anchors(script.get("visual_corpus") or [])
    baseline_distribution = (visual_corpus.distribute_visual_anchors(scenes, corpus_anchors)
                             if corpus_anchors and scenes else None)
    fixed_generic_terms = (baseline_distribution[
        "generic_terms_excluded_as_sole_signal"] if baseline_distribution else None)
    coverage_before = (_coverage_summary(
        scenes, corpus_anchors, generic_terms=fixed_generic_terms)
        if corpus_anchors and scenes else None)
    pool = short_scenes([*scenes[1:-1], *extra_lines], max_words=max(7, min(20, wanted // 6)),
                        grouped=True)
    if corpus_anchors:
        pool = _coverage_guided_groups(
            pool, corpus_anchors,
            base_words=word_count(hook) + word_count(cta), wanted=wanted,
            generic_terms=fixed_generic_terms,
            minimum_groups=max(0, math.ceil(float(target or 35) / 7.0) - 2),
            maximum_groups=max(0, int(math.floor(float(target or 35) / 4.0 + .5)) - 2))
    body, total = [], word_count(hook) + word_count(cta)
    for group in pool:
        count = sum(word_count(p) for p in group)
        if total + count > wanted * 1.15:
            continue
        body.extend(group)
        total += count
        if total >= wanted * .97:
            break
    script["scenes"] = [hook, *body, cta]
    if corpus_anchors:
        coverage_after = _coverage_summary(
            script["scenes"], corpus_anchors, generic_terms=fixed_generic_terms)
        previous = script.get("coverage_optimization") or {}
        baseline = previous.get("before") or coverage_before
        script["coverage_optimization"] = {
            "before": baseline,
            "after": coverage_after,
            "orphan_scenes_reduced_by": max(
                0, baseline["scenes_without_anchor"]
                - coverage_after["scenes_without_anchor"]),
            "generic_terms_used_for_both": fixed_generic_terms,
            "duration_per_scene_seconds": round(
                float(target or 35) / len(script["scenes"]), 2) if script["scenes"] else None,
            "max_duration_per_scene_seconds": 7.0,
        }
        script["coverage_optimization"]["accepted"] = (
            script["coverage_optimization"]["duration_per_scene_seconds"] <= 7.0)
    script.update(target_words=wanted, word_count=total,
                  estimated_seconds=round(total * 60 / WORDS_PER_MINUTE.get(lang, 155), 1),
                  target_seconds=int(target or 35),
                  duration_ok=wanted * .85 <= total <= wanted * 1.15)
    if not script["duration_ok"]:
        message = (f"Contenu insuffisant : {total}/{wanted} mots pour {int(target or 35)} s. "
                   "Ajoutez du contenu documenté ou choisissez une durée plus courte.")
        script.setdefault("warnings", []).append(message)
    return with_visual_plans(script)


def _pick_items_for_target(pool, target, hook, cta, preserve_order=False):
    """Choisit des items pour approcher la durée cible (sans dépasser si possible)."""
    if not preserve_order:
        random.shuffle(pool)
    base = (len(hook) + len(cta)) / CPS + 2 * PAD
    picked, acc = [], base
    for it in pool:
        if target and acc + len(it) / CPS + PAD > target and picked:
            continue
        picked.append(it)
        acc += len(it) / CPS + PAD
        if not target and len(picked) >= random.choice([4, 5]):
            break
        if target and acc >= target * 0.92:
            break
    # Never repeat the same sentence merely to make a long requested duration.
    # A shorter honest fallback is preferable to the duplicated paragraphs that
    # previously appeared when the Web source was temporarily unavailable.
    return picked


def _generate_script_core(niche="motivation", lang="fr", topic="", avoid_repeat=True, target=None,
                    source="local", log=None):
    """Retourne un script complet prêt à rendre, éditable côté UI.
    `target` = durée cible en secondes (None/0 = auto ≈ 35 s).
    `source` = "web" → matière fraîche infinie (Wikipedia, citations…, mémoire
    anti-répétition partagée) avec repli automatique sur la banque locale hors-ligne ;
    "local" → banque de gabarits intégrée (instantané)."""
    target = int(target or 0) or None
    fallback_reason = ""
    if source == "web":
        diagnostics = []
        def web_log(message):
            diagnostics.append(str(message))
            if log:
                log(message)
        try:
            from . import webcontent
            generator = webcontent.topic_script if niche == "sujet" and topic else webcontent.script_from_web
            web = generator(niche=niche, lang=lang, topic=topic,
                                             target=target, log=web_log,
                                             avoid_repeat=avoid_repeat)
            # An explicit subject is intentional. If anti-repeat exhausted the
            # first Wikipedia result set, reuse the best relevant article rather
            # than silently replacing it with a generic local outline.
            if not web and topic and avoid_repeat:
                web = generator(niche=niche, lang=lang, topic=topic,
                                                 target=target, log=web_log,
                                                 avoid_repeat=False)
            if web:
                fitted = fit_script(web, target)
                if fitted["duration_ok"]:
                    return fitted
                # Une source courte ne doit pas se présenter comme un script
                # complet de cinq minutes. La réserve locale documentée peut
                # prendre le relais en affichant explicitement cette raison.
                saved = webcontent.local_topic_script(
                    topic if niche == "sujet" and topic else "__niche_" + niche,
                    lang, target, niche,
                )
                if saved and saved["duration_ok"]:
                    reason = fitted["warnings"][-1]
                    saved["fallback_reason"] = reason
                    saved.setdefault("warnings", []).append(
                        "Source web trop courte, réserve documentée hors ligne utilisée : " + reason)
                    logging.getLogger(__name__).warning("Source web insuffisante : %s", reason)
                    return saved
                return fitted
            fallback_reason = diagnostics[-1] if diagnostics else "Aucune source pertinente et exploitable après les tentatives."
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
        logging.getLogger(__name__).warning("Échec génération web : %s", fallback_reason)
        if log:
            log("   🎲 web indisponible ou déjà vu → repli sur la banque locale")
    if niche == "sujet" and topic:
        from . import webcontent
        saved = webcontent.local_topic_script(topic, lang, target, niche)
        if saved:
            if fallback_reason:
                saved["fallback_reason"] = fallback_reason
                saved.setdefault("warnings", []).append("Web indisponible, sources locales utilisées : " + fallback_reason)
            return saved
        pack = _topic_script(topic, lang, target)
    else:
        if niche == "sujet":
            niche = "motivation"
        from . import webcontent
        saved = webcontent.local_topic_script("__niche_" + niche, lang, target, niche)
        if saved:
            if fallback_reason:
                saved["fallback_reason"] = fallback_reason
                saved.setdefault("warnings", []).append("Web indisponible, sources locales utilisées : " + fallback_reason)
            return saved
        pack = _merged(niche, lang) or _merged("motivation", lang)

    used = _load_used() if avoid_repeat else set()
    best = None
    for _ in range(30):
        hook = random.choice(pack["hooks"])
        items = _pick_items_for_target(list(pack["items"]), target, hook, random.choice(pack["ctas"]), niche == "sujet")
        if not items:
            items = [random.choice(pack["items"])]
        cta = random.choice(pack["ctas"])
        sig = hashlib.md5((niche + lang + str(target) + hook + "||" + "||".join(items)).encode()).hexdigest()[:12]
        if sig not in used:
            best = (hook, items, cta, sig)
            break
    if best is None:
        hook = random.choice(pack["hooks"])
        items = _pick_items_for_target(list(pack["items"]), target, hook, random.choice(pack["ctas"]), niche == "sujet")
        cta = random.choice(pack["ctas"])
        sig = hashlib.md5((niche + lang + hook + str(random.random())).encode()).hexdigest()[:12]
        best = (hook, items, cta, sig)
    if avoid_repeat:
        _mark_used(used, sig)
    hook, items, cta, sid = best
    scenes = [hook] + items + [cta]
    if target and target > 90 and log:
        est = estimate_seconds(scenes)
        if est < target * 0.6:
            log(f"   ⚠️ Banque locale courte (~{est:.0f}s pour {target}s demandés) — "
                "passez la source du script sur « 🌐 Web » pour remplir la durée")
    # Keep the full duration wording visible (long subjects were cutting
    # "2 minutes" to "2 minu" even though the UI accepts 120 characters).
    title = hook[:100]
    tags = list(dict.fromkeys((pack.get("tags") or []) + (COMMON_TAGS_FR if lang == "fr" else COMMON_TAGS_EN)))[:12]
    hashtags = " ".join("#" + t.replace(" ", "") for t in tags)
    if lang == "fr":
        caption = f"{hook}\n\n{items[0] if items else ''}\n\n{hashtags}"
    else:
        caption = f"{hook}\n\n{items[0] if items else ''}\n\n{hashtags}"
    result = {
        "id": sid,
        "niche": niche,
        "language": lang,
        "title": title,
        "hook": hook,
        "scenes": scenes,
        "cta": cta,
        "caption": caption,
        "hashtags": hashtags,
        "source": "local",
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
        result["warnings"] = ["Web indisponible, bascule sur la banque locale : " + fallback_reason]
    # Le sujet libre hors ligne reste explicitement un plan à documenter.
    if niche == "sujet":
        result.setdefault("warnings", []).append("Sujet libre hors ligne : trame éditoriale à compléter avec des faits vérifiés.")
    return fit_script(result, target, extra_lines=pack["items"])


def niche_labels(lang="fr"):
    return [{"id": k, "label": v.get(lang, v["fr"]), "badge": v.get("badge_" + lang, v.get("badge_fr", ""))}
            for k, v in NICHES.items()]


def badge_for(niche, lang="fr"):
    n = NICHES.get(niche)
    if not n:
        return ""
    return n.get("badge_" + lang) or n.get("badge_fr") or ""


# Editorial niches keep their specialised collectors; source now describes the medium.
EDITORIAL_NICHES = ("actu", "jour", "science", "mythes")
LEGACY_SOURCE_IDS = EDITORIAL_NICHES + ("surprise",)
SOURCE_IDS = ("web", "local", "perso")
ACCEPTED_SOURCE_IDS = SOURCE_IDS + LEGACY_SOURCE_IDS


def generate_script(niche="motivation", lang="fr", topic="", avoid_repeat=True, target=None,
                    source="local", log=None):
    """Resolve a concrete niche before choosing its facts and editorial angle."""
    # A concrete single-shot source is already a scene. Commas describe spatial
    # relations and light; splitting them into narrative beats loses the subject.
    if niche == "sujet" and source == "local" and topic:
        scene = str(topic).strip()
        bundle = visual_plan_bundle([scene], title=scene[:120], niche=niche, language=lang)
        if bundle["visual_controls"][0].get("kind") == "explicit":
            return {"title": scene[:120], "scenes": [scene], "caption": scene,
                    "niche": niche, "language": lang, "source": "local",
                    "source_name": "Description visuelle explicite", "hashtags": "", **bundle}
    if source in LEGACY_SOURCE_IDS:
        niche, source = source, "web"
    if niche == "surprise":
        niche = random.choice([key for key in NICHES if key not in ("sujet", "surprise")])
    if niche in EDITORIAL_NICHES or source == "perso":
        from . import sources as _sources
        collector = "perso" if source == "perso" else niche
        try:
            return _sources.generate(collector, niche=niche, lang=lang, topic=topic, target=target,
                                     avoid_repeat=avoid_repeat, log=log, local=source == "local")
        except _sources.SourceError as exc:
            # Never substitute motivational stock for unavailable factual material.
            return {"error": str(exc)}
    return _generate_script_core(niche=niche, lang=lang, topic=topic, avoid_repeat=avoid_repeat,
                                 target=target, source=source, log=log)
