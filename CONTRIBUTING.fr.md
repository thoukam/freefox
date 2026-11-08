[English](CONTRIBUTING.md) · **Français**

# Contribuer à FreeFox

Merci de vouloir améliorer FreeFox ! Toutes les contributions sont les bienvenues, quelle que soit
leur taille. Les issues et pull requests peuvent être écrites en **français ou en anglais**.

## Comment aider

- **Utilisez-le et faites un retour.** Les retours de terrain sur de vrais robots (matériel, réseau,
  taille des bags) sont précieux.
- **Signalez des bugs** avec le [modèle de rapport de bug](https://github.com/thoukam/freefox/issues/new/choose).
- **Améliorez la documentation** : étapes peu claires, exemples, traductions entre `docs/fr/` et `docs/en/`.
- **Prenez une issue** étiquetée [`good first issue`](https://github.com/thoukam/freefox/labels/good%20first%20issue)
  ou [`help wanted`](https://github.com/thoukam/freefox/labels/help%20wanted).
- **Construisez un élément de la feuille de route** : métriques Prometheus, authentification du
  dashboard, nouveaux backends, règles d'upload… Ouvrez d'abord une issue pour qu'on se mette
  d'accord sur la conception.

## Environnement de développement

Prérequis : Linux, Python 3.10+, `rsync` (pour le backend rsync).

```bash
git clone https://github.com/<vous>/freefox && cd freefox
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,s3]"
.venv/bin/python -m pytest
```

> **ROS 2 sourcé dans votre shell ?** ROS ajoute ses propres plugins pytest au `PYTHONPATH`, ce qui
> peut casser la collecte des tests. Lancez les tests dans un shell propre ou avec
> `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_timeout`.

Scripts utiles :

| Commande | Rôle |
|---|---|
| `scripts/local_smoke.py` | Test de bout en bout sur un dossier local, sans compte cloud |
| `scripts/dashboard.py --config <cfg>` | Dashboard local sur `http://127.0.0.1:8765` |
| `scripts/queue_status.py <queue.db>` | Inspecter la file SQLite |
| `scripts/gdrive_smoke.py`, `scripts/s3_smoke.py` | Vérifications réelles, à lancer manuellement |

Lisez [docs/fr/architecture.md](docs/fr/architecture.md) avant de toucher à la file, aux workers ou
à un backend.

## Proposer une modification

1. Forkez le dépôt et créez une branche depuis `main` : `feat/prometheus-metrics`, `fix/rsync-timeout`, `docs/...`.
2. Gardez des pull requests ciblées : une fonctionnalité ou un correctif par PR.
3. Ajoutez ou mettez à jour les tests. Ils ne doivent nécessiter ni réseau ni vrais credentials :
   utilisez des faux clients (voir `tests/conftest.py`).
4. Mettez à jour la documentation et le `CHANGELOG.md` (section *Unreleased*) quand le comportement
   ou la configuration change. Les documents existent en français et en anglais (`X.fr.md` / `X.md`,
   `docs/fr/` / `docs/en/`). Mettez à jour les deux si vous le pouvez, sinon indiquez dans la PR
   qu'une traduction manque et quelqu'un vous aidera.
5. Vérifiez que les contrôles passent : `ruff format freefox scripts tests`, `ruff check freefox scripts tests`
   et `pytest`. La CI lance les mêmes commandes.
6. Ouvrez la pull request et remplissez le modèle.

### Messages de commit

Nous utilisons les [Conventional Commits](https://www.conventionalcommits.org/fr/) :

```text
feat(s3): prise en charge du chiffrement SSE-KMS
fix(watcher): ignorer les fichiers supprimés avant d'être stables
docs: traduire le guide Docker en anglais
```

### Règles de code

- Le code est formaté avec [ruff](https://docs.astral.sh/ruff/) (lignes de 100 caractères). Lancez `ruff format` avant de commiter.
- Ciblez Python 3.10 et utilisez des annotations de type sur les fonctions publiques.
- Les SDK optionnels (boto3, …) s'importent à l'intérieur du backend, au moment où il est utilisé.
- Ne journalisez et ne stockez jamais de secrets. Masquez les messages d'erreur des fournisseurs
  (voir `s3._safe_message`).
- Préservez les garanties : aucune perte de données, aucun écrasement silencieux, retries idempotents.
- Préférez un code clair à des one-liners astucieux : le code est bien plus souvent lu qu'écrit.

## Signaler une faille de sécurité

**N'ouvrez pas** d'issue publique. Voir [SECURITY.fr.md](SECURITY.fr.md).

## Code de conduite

Ce projet suit le [Contributor Covenant](CODE_OF_CONDUCT.fr.md). Soyez bienveillant et partez du
principe que les autres sont de bonne foi.

## Licence

En contribuant, vous acceptez que vos contributions soient publiées sous
[licence Apache 2.0](LICENSE).
