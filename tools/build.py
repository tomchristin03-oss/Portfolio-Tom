#!/usr/bin/env python3
"""Construit le site public (dossier site/) à partir de la page de l'artifact Claude.

Usage : python3 tools/build.py chemin/vers/index.html
- lit l'état du site (pf-state) dans la page de l'artifact ;
- vérifie que chaque média référencé (/_blob/<id>) existe dans site/media/<id>.<ext> ;
  sinon affiche "MISSING <id>" (un par ligne) et sort avec le code 2 ;
- écrit site/index.html (sans mode édition, médias servis depuis media/) ;
- supprime de site/media les fichiers qui ne sont plus utilisés.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site'); MEDIA = os.path.join(SITE, 'media')

def main(live_path):
    s = open(live_path, encoding='utf-8').read()
    body = s[s.index('<title>'):s.rindex('</body>')]
    m = re.search(r'<script[^>]*id="pf-state"[^>]*>(.*?)</script>', body, re.S)
    st = json.loads(m.group(1))
    ids = sorted(set(re.findall(r'/_blob/([A-Za-z0-9_-]+)', json.dumps(st))))
    os.makedirs(MEDIA, exist_ok=True)
    have = {f.split('.')[0]: f for f in os.listdir(MEDIA)}
    missing = [i for i in ids if i not in have]
    if missing:
        for i in missing: print('MISSING', i)
        sys.exit(2)
    urls = {i: 'media/' + have[i] for i in ids}
    body = re.sub(r'<title>.*?</title>', '', body, count=1, flags=re.S)
    body = body.replace('<meta name="claude:viewport-fit-sides" content="cover">', '', 1)
    inj = '<script type="application/json" id="pf-urls">' + json.dumps(urls) + '</script>\n'
    k = body.index('<script id="pf-app"'); body = body[:k] + inj + body[k:]
    head = ('<!doctype html>\n<html lang="fr"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
      '<title>Tom Christin-Leymarie — Direction artistique & design graphique</title>'
      '<meta name="description" content="Portfolio de Tom Christin-Leymarie, directeur artistique et graphiste basé à Paris : identité visuelle, édition, typographie, textile, IA.">'
      '<meta property="og:title" content="Tom Christin-Leymarie — Portfolio"><meta property="og:type" content="website">'
      '<style>body{margin:0}</style></head><body>\n')
    open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8').write(head + body + '\n</body></html>\n')
    used = set(have[i] for i in ids)
    for f in os.listdir(MEDIA):
        if f not in used: os.remove(os.path.join(MEDIA, f))
    print('OK', len(ids), 'médias')

if __name__ == '__main__':
    main(sys.argv[1])
