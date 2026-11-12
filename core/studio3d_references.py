"""Small, bounded Wikipedia lookup for 3D documentation (no arbitrary URLs)."""
from urllib.parse import urlsplit


def lookup_references(topic):
    import requests
    query = ' '.join(str(topic or '').split())[:180]
    if not query:
        return {'sources': [], 'warning': 'Aucun objet à documenter.'}
    try:
        response = requests.get('https://fr.wikipedia.org/w/api.php', params={
            'action': 'query', 'format': 'json', 'generator': 'search',
            'gsrsearch': query, 'gsrlimit': 2, 'prop': 'extracts|info|langlinks',
            'lllang': 'en', 'lllimit': 1,
            'explaintext': 1, 'exintro': 1, 'exchars': 1200, 'inprop': 'url',
        }, headers={'User-Agent': 'ShortPilotStudio/1.0 (local 3D documentation)'}, timeout=(3, 10))
        response.raise_for_status()
        pages = response.json().get('query', {}).get('pages', {})
        sources = []
        for page in sorted(pages.values(), key=lambda p: p.get('index', 999)):
            url = page.get('fullurl', '')
            if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'fr.wikipedia.org':
                continue
            excerpt = str(page.get('extract') or '').strip()[:1600]
            if excerpt:
                sources.append({'title': str(page.get('title') or '')[:180], 'url': url, 'excerpt': excerpt})
        visual_query = query
        for page in sorted(pages.values(), key=lambda p: p.get('index', 999)):
            english = next((link.get('*') for link in page.get('langlinks', []) if link.get('lang') == 'en'), None)
            if english:
                visual_query = str(english)[:180]
                break
        return {'sources': sources, 'visualQuery': visual_query, 'warning': '' if sources else 'Aucune référence Wikipédia trouvée pour cette description.'}
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {'sources': [], 'warning': 'Wikipédia indisponible : génération sans documentation Web.'}
