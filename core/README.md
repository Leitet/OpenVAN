# OpenVan Core

The offline-first, AI-first brain of OpenVan. See the [repository README](../README.md)
for the full picture and the [CLAUDE.md](../CLAUDE.md) for architecture and rules.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # run the tests
python -m openvan_core # start Core on http://127.0.0.1:8000
```
