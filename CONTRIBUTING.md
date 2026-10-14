# Contributing

## Set up

Two separate Python environments, because the engine needs GPU libraries the web app does not.

```
# web app
python -m venv .venv-web && .venv-web\Scripts\activate        # Linux/macOS: source .venv-web/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env                                         # then edit it (see the comments inside)
cd web && python manage.py migrate && python manage.py createsuperuser

# engine (install PyTorch first, with the CUDA build that matches your driver)
python -m venv .venv-engine && .venv-engine\Scripts\activate
pip install -r engine/requirements.txt
copy engine\config\engine.example.yaml engine\config\engine.yaml
```

## Tests and style

```
cd web && python manage.py test              # web
python -m pytest engine/tests -q             # engine, from the project root, no GPU needed
ruff check . && ruff format --check .        # lint and format
```

CI runs the same commands. A pull request needs all of them green.

## Rules

- Django never processes video. All detection, tracking and image work stays in `engine/`.
- The engine talks to the web app only through `engine/web_client/` and the API in `docs/engine_api.md`.
  If an API field changes, update that document in the same pull request.
- Every number the engine uses (thresholds, sizes, times) comes from `engine.yaml`.
- Simple names, one job per file, English comments, type hints.
- New text in the interface: wrap it in `{% translate %}` / `_()`, add the Persian text to
  `web/locale/fa/LC_MESSAGES/django.po`, run `python scripts/compile_translations.py`.
- No made-up data in the shipped code. Test doubles belong in `engine/tests/` or test files.
- Never commit `.env`, databases, model weights, videos or snapshots.

## Adding a module

See "Adding a module" in [`docs/architecture.md`](docs/architecture.md).
