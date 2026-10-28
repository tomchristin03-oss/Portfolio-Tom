#!/usr/bin/env python3
"""Construit le site public (dossier site/) à partir de la page de l'artifact Claude.

Usage : python3 tools/build.py chemin/vers/index.html [--raw DOSSIER]

- lit l'état du site (pf-state) dans la page de l'artifact ;
- pour chaque média référencé (/_blob/<id>) :
    * s'il a déjà été optimisé (site/media/manifest.json), on le réutilise ;
    * sinon on cherche l'original <id>.<ext> dans --raw (défaut : raw/) ou site/media/ ;
      s'il manque, on affiche "MISSING <id>" et on sort avec le code 2 à la fin ;
- optimise les médias pour que tout s'affiche vite :
    * images -> WebP redimensionné (pleine taille + miniature pour l'accueil) + aperçu flou minuscule ;
    * vidéos -> MP4 H.264 compressé, « faststart » (démarre sans attendre la fin du téléchargement) + image d'attente ;
    * GIF -> MP4 en boucle (10 à 20 fois plus léger) ;
- écrit site/index.html (sans mode édition) et supprime les fichiers devenus inutiles.
Si ffmpeg ou Pillow manquent, le média original est copié tel quel.
"""
import base64, io, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site'); MEDIA = os.path.join(SITE, 'media')
MANIFEST = os.path.join(MEDIA, 'manifest.json')
V = '1'   # changer ce numéro force la régénération de tous les médias (et vide les caches navigateur)

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
FFMPEG = shutil.which('ffmpeg')


def find_raw(i, dirs):
    for d in dirs:
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if f.split('.')[0] == i and '-' not in f.split('.')[0] and f != 'manifest.json':
                return os.path.join(d, f)
    return None


def fit(w, h, mw, mh):
    s = min(1.0, mw / w, mh / h)
    return max(1, round(w * s)), max(1, round(h * s))


def save_webp(img, path, mw, mh, q):
    w, h = fit(img.width, img.height, mw, mh)
    im = img if (w, h) == img.size else img.resize((w, h), Image.LANCZOS)
    im.save(path, 'WEBP', quality=q, method=6)


def lqip(img):
    w, h = fit(img.width, img.height, 24, 24)
    im = img.convert('RGB').resize((w, h), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'WEBP', quality=35)
    return 'data:image/webp;base64,' + base64.b64encode(b.getvalue()).decode()


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE).returncode == 0


def has_audio(src):
    r = subprocess.run([FFMPEG, '-hide_banner', '-i', src], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return 'Audio:' in r.stderr


def process(i, src):
    ext = src.rsplit('.', 1)[-1].lower()
    e = {}
    if ext in ('woff2', 'woff', 'otf', 'ttf'):
        name = i + '.' + ext; shutil.copy(src, os.path.join(MEDIA, name)); return {'k': 'font', 'u': name}
    if ext in ('jpg', 'jpeg', 'png', 'webp') and Image is not None:
        img = Image.open(src)
        if getattr(img, 'is_animated', False):
            name = i + '.' + ext; shutil.copy(src, os.path.join(MEDIA, name)); return {'k': 'image', 'u': name}
        img = ImageOps.exif_transpose(img)
        if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGBA' if 'A' in img.getbands() or img.mode == 'P' else 'RGB')
        f, t = '%s-f%s.webp' % (i, V), '%s-t%s.webp' % (i, V)
        save_webp(img, os.path.join(MEDIA, f), 2600, 1800, 80)
        save_webp(img, os.path.join(MEDIA, t), 2000, 1300, 72)
        # garde l'original s'il est plus léger que la version « optimisée »
        if os.path.getsize(os.path.join(MEDIA, f)) > os.path.getsize(src) and ext == 'webp':
            shutil.copy(src, os.path.join(MEDIA, f))
        return {'k': 'image', 'u': f, 't': t, 'l': lqip(img)}
    if ext in ('mp4', 'webm', 'mov', 'gif') and FFMPEG:
        out = '%s-v%s.mp4' % (i, V); op = os.path.join(MEDIA, out)
        scale = "scale='min(1920,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2"
        if ext == 'gif':
            ok = run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-vf', scale + ',fps=fps=25,hqdn3d=2:1:3:3', '-c:v', 'libx264', '-preset', 'medium', '-crf', '25',
                      '-maxrate', '3000k', '-bufsize', '6000k', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', op])
        else:
            aud = ['-c:a', 'aac', '-b:a', '128k'] if has_audio(src) else ['-an']
            ok = run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-vf', scale, '-c:v', 'libx264', '-preset', 'medium', '-crf', '25',
                      '-maxrate', '3500k', '-bufsize', '7000k', '-pix_fmt', 'yuv420p', '-movflags', '+faststart'] + aud + [op])
            if ok and os.path.getsize(op) > os.path.getsize(src):   # déjà bien compressée : on remet juste l'en-tête au début
                ok = run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-c', 'copy', '-movflags', '+faststart', op])
        if not ok:
            name = i + '.' + ext; shutil.copy(src, os.path.join(MEDIA, name)); return {'k': 'gif' if ext == 'gif' else 'video', 'u': name}
        e = {'k': 'gif' if ext == 'gif' else 'video', 'u': out}
        if Image is not None:
            with tempfile.TemporaryDirectory() as td:
                fr = os.path.join(td, 'f.png')
                if run([FFMPEG, '-y', '-loglevel', 'error', '-i', op, '-frames:v', '1', fr]) and os.path.exists(fr):
                    img = Image.open(fr).convert('RGB'); p = '%s-p%s.webp' % (i, V)
                    save_webp(img, os.path.join(MEDIA, p), 1600, 1600, 72); e['p'] = p; e['l'] = lqip(img)
        return e
    name = i + '.' + ext; shutil.copy(src, os.path.join(MEDIA, name))
    return {'k': 'image', 'u': name}


def walk(o, gif_ids):
    """Les GIF deviennent des vidéos en boucle dans l'état publié."""
    if isinstance(o, dict):
        m = re.match(r'^/_blob/([A-Za-z0-9_-]+)$', str(o.get('src', '')))
        if m and m.group(1) in gif_ids and o.get('kind') != 'video':
            o['kind'] = 'video'; o['gif'] = True
        for v in o.values(): walk(v, gif_ids)
    elif isinstance(o, list):
        for v in o: walk(v, gif_ids)


def main(live_path, raw_dir):
    s = open(live_path, encoding='utf-8').read()
    body = s[s.index('<title>'):s.rindex('</body>')]
    m = re.search(r'(<script[^>]*id="pf-state"[^>]*>)(.*?)(</script>)', body, re.S)
    st = json.loads(m.group(2))
    ids = sorted(set(re.findall(r'/_blob/([A-Za-z0-9_-]+)', json.dumps(st))))
    os.makedirs(MEDIA, exist_ok=True)
    man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    man = {k: v for k, v in man.items() if v.get('v') == V and all(os.path.exists(os.path.join(MEDIA, v[x])) for x in ('u', 't', 'p') if x in v)}
    missing = []
    for i in ids:
        if i in man: continue
        src = find_raw(i, [raw_dir, MEDIA])
        if not src: missing.append(i); continue
        print('optimise', os.path.basename(src), flush=True)
        e = process(i, src); e['v'] = V; man[i] = e
    if missing:
        for i in missing: print('MISSING', i)
        sys.exit(2)
    man = {i: man[i] for i in ids}
    json.dump(man, open(MANIFEST, 'w'), indent=0, sort_keys=True)

    gif_ids = {i for i, e in man.items() if e['k'] == 'gif' and e['u'].endswith('.mp4')}
    if gif_ids:
        walk(st, gif_ids)
        js = json.dumps(st, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        body = body[:m.start(2)] + js + body[m.end(2):]

    pu = {'u': {}, 't': {}, 'l': {}, 'p': {}}
    for i, e in man.items():
        pu['u'][i] = 'media/' + e['u']
        if 't' in e: pu['t'][i] = 'media/' + e['t']
        if 'p' in e: pu['p'][i] = 'media/' + e['p']
        if 'l' in e: pu['l'][i] = e['l']
    body = re.sub(r'<title>.*?</title>', '', body, count=1, flags=re.S)
    body = body.replace('<meta name="claude:viewport-fit-sides" content="cover">', '', 1)
    inj = '<script type="application/json" id="pf-urls">' + json.dumps(pu) + '</script>\n'
    k = body.index('<script id="pf-app"'); body = body[:k] + inj + body[k:]
    # les miniatures de l'accueil partent en premier
    pre = ''.join('<link rel="preload" as="image" href="media/%s" fetchpriority="high">' % man[i]['t']
                  for i in cover_ids(st)[:4] if i in man and 't' in man[i])
    head = ('<!doctype html>\n<html lang="fr"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
      '<title>Tom Christin-Leymarie — Direction artistique & design graphique</title>'
      '<meta name="description" content="Portfolio de Tom Christin-Leymarie, directeur artistique et graphiste basé à Paris : identité visuelle, édition, typographie, textile, IA.">'
      '<meta property="og:title" content="Tom Christin-Leymarie — Portfolio"><meta property="og:type" content="website">'
      + pre + '<style>body{margin:0}</style></head><body>\n')
    open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8').write(head + body + '\n</body></html>\n')

    keep = {'manifest.json'} | {e[x] for e in man.values() for x in ('u', 't', 'p') if x in e}
    for f in os.listdir(MEDIA):
        if f not in keep: os.remove(os.path.join(MEDIA, f))
    size = sum(os.path.getsize(os.path.join(MEDIA, f)) for f in os.listdir(MEDIA))
    print('OK', len(ids), 'médias,', round(size / 1e6, 1), 'Mo')


def cover_ids(st):
    out = []
    for p in st.get('projects', []):
        m = p.get('cover') or (p.get('gallery') or [None])[0]
        if m:
            mm = re.match(r'^/_blob/([A-Za-z0-9_-]+)$', str(m.get('src', '')))
            if mm: out.append(mm.group(1))
    return out


if __name__ == '__main__':
    a = sys.argv[1:]
    raw = os.path.join(ROOT, 'raw')
    if '--raw' in a:
        k = a.index('--raw'); raw = a[k + 1]; del a[k:k + 2]
    main(a[0], raw)
