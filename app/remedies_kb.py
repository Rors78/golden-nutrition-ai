"""The Apothecary knowledge base — natural remedies from 11 world traditions.

Distilled from the user's own research archive (~350 remedies spanning
Egyptian, Native American, TCM/Ayurvedic, Greco-European, modern integrative,
Japanese/Korean, Middle Eastern, South American/Pacific, Tibetan/SE Asian
traditions, healing foods, and non-plant practices), each entry carrying its
evidence grade (1-5, the archive's own star system), preparation, and
safety/interaction warnings.

House rules: complementary, never alternative. Interactions are load-bearing.
This is reference information, not medical advice — the UI says so, always.
"""
import json
from pathlib import Path

REMEDIES_DIR = Path(__file__).parent / 'remedies'

CATEGORIES = ('immune', 'digestion', 'pain', 'heart', 'blood-pressure',
              'blood-sugar', 'sleep', 'stress-mood', 'skin', 'wounds',
              'respiratory', 'energy', 'mens-health', 'womens-health',
              'brain', 'joints', 'cancer-support', 'general')

_cache = None


def load_kb():
    """All remedies, cross-tradition duplicates merged, best evidence first."""
    global _cache
    if _cache is None:
        entries = []
        for f in sorted(REMEDIES_DIR.glob('*.json')):
            try:
                entries.extend(json.loads(f.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        _cache = _merge(entries)
    return _cache


def _merge(entries):
    by_name = {}
    for e in entries:
        name = str(e.get('name', '')).strip()
        if not name:
            continue
        key = name.lower()
        cats = [c for c in e.get('categories', []) if c in CATEGORIES] or ['general']
        if key in by_name:
            m = by_name[key]
            tradition = str(e.get('tradition', '')).strip()
            if tradition and tradition not in m['traditions']:
                m['traditions'].append(tradition)
            m['categories'] = sorted(set(m['categories']) | set(cats))
            if int(e.get('evidence', 1)) > m['evidence']:
                m['evidence'] = int(e['evidence'])
                m['summary'] = str(e.get('summary', m['summary']))
            for field in ('how', 'safety'):
                if len(str(e.get(field, ''))) > len(m[field]):
                    m[field] = str(e[field])
            aka = str(e.get('aka', '')).strip()
            if aka and aka.lower() not in m['aka'].lower():
                m['aka'] = f"{m['aka']}; {aka}".strip('; ')
        else:
            by_name[key] = {
                'id': str(e.get('id', key.replace(' ', '-'))),
                'name': name,
                'aka': str(e.get('aka', '')).strip(),
                'traditions': [t for t in [str(e.get('tradition', '')).strip()] if t],
                'categories': cats,
                'evidence': max(1, min(5, int(e.get('evidence', 1)))),
                'summary': str(e.get('summary', '')),
                'how': str(e.get('how', '')),
                'safety': str(e.get('safety', '')),
                'origin': str(e.get('origin', '')),
            }
    return sorted(by_name.values(), key=lambda x: (-x['evidence'], x['name']))


def search_kb(query, limit=12):
    """Cheap relevance ranking to ground the AI without shipping the whole KB."""
    tokens = [t for t in query.lower().split() if len(t) > 2]
    scored = []
    for r in load_kb():
        hay_name = f"{r['name']} {r['aka']}".lower()
        hay_cats = ' '.join(r['categories'])
        hay_text = f"{r['summary']} {r['origin']}".lower()
        score = 0
        for t in tokens:
            if t in hay_name:
                score += 5
            if t in hay_cats:
                score += 3
            if t in hay_text:
                score += 1
        if score:
            scored.append((score + r['evidence'] * 0.1, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def kb_stats():
    kb = load_kb()
    traditions = set()
    for r in kb:
        traditions.update(r['traditions'])
    return {'count': len(kb), 'traditions': len(traditions)}
