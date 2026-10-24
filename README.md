# Portfolio — Tom Christin-Leymarie

Site public généré à partir de l'artifact Claude (le back-office d'édition).
Netlify publie le dossier `site/` à chaque push sur `main`.

Mise à jour : `python3 tools/build.py <index.html de l'artifact>` puis commit + push.
Les médias manquants sont listés (`MISSING <id>`) : les télécharger depuis l'artifact dans `site/media/<id>.<ext>`.
