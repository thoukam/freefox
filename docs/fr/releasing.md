[English](../en/releasing.md) · **Français**

# Publier une version

FreeFox est publié depuis GitHub. Publier une release GitHub déclenche deux workflows :

| Workflow | Résultat |
|---|---|
| `publish-pypi.yml` | Construit le paquet et l'envoie sur [PyPI](https://pypi.org/project/freefox/) |
| `docker-publish.yml` | Construit et pousse `ghcr.io/thoukam/freefox:<version>` pour amd64 et arm64 |

## Configuration unique : Trusted Publishing PyPI

Le Trusted Publishing permet à GitHub Actions de publier sur PyPI sans stocker de token d'API.

1. Créez un compte sur <https://pypi.org> et activez l'authentification à deux facteurs.
2. Allez dans **Your account → Publishing → Add a new pending publisher** et remplissez :
   - PyPI project name : `freefox`
   - Owner : `thoukam`
   - Repository name : `freefox`
   - Workflow name : `publish-pypi.yml`
   - Environment name : `pypi`
3. Sur GitHub, allez dans **Settings → Environments → New environment** et nommez-le `pypi`.
   En option, ajoutez-vous comme *required reviewer* : chaque publication attendra alors votre
   validation.

La première publication réussie crée le projet `freefox` sur PyPI. Ensuite, le *pending publisher*
devient un *trusted publisher* normal.

## À chaque version

1. Vérifiez que la CI est verte sur `main`.
2. Mettez la version dans `freefox/__init__.py` (`__version__ = "X.Y.Z"`), selon le
   [versionnage sémantique](https://semver.org/lang/fr/) :
   - `Z` pour des correctifs uniquement,
   - `Y` pour de nouvelles fonctionnalités rétrocompatibles,
   - `X` pour un changement incompatible (avant la 1.0, un changement incompatible incrémente `Y`).
3. Dans `CHANGELOG.md` et `CHANGELOG.fr.md`, renommez *Unreleased* / *Non publié* en
   `[X.Y.Z] - AAAA-MM-JJ`, ajoutez une nouvelle section vide et mettez à jour les liens en bas.
4. Commitez via une pull request : `chore: release X.Y.Z`.
5. Sur GitHub, allez dans **Releases → Draft a new release** :
   - tag : `vX.Y.Z`, créé sur `main`,
   - titre : `vX.Y.Z`,
   - description : collez la section du CHANGELOG.
6. Cliquez sur **Publish release**, puis vérifiez l'onglet **Actions** : les deux workflows doivent
   réussir. Si le tag et `__version__` diffèrent, le workflow PyPI s'arrête avant d'envoyer quoi que
   ce soit.

## Vérifier la version publiée

```bash
python3 -m venv /tmp/ff && /tmp/ff/bin/pip install "freefox[s3]==X.Y.Z"
/tmp/ff/bin/freefox --help
docker pull ghcr.io/thoukam/freefox:X.Y.Z
```

Une version envoyée sur PyPI ne peut jamais être remplacée. En cas de problème, corrigez et publiez
`X.Y.Z+1`. Vous pouvez aussi *yanker* la mauvaise version sur PyPI pour que `pip` ne la choisisse plus.

## Tester le build en local

```bash
.venv/bin/pip install -e ".[dev]"
rm -rf dist && .venv/bin/python -m build && .venv/bin/twine check dist/*
```
