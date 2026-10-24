# cachekit

Deterministic prompt-cache analysis and a verified source-refactoring workflow.

This is a dependency checkpoint in a current publication batch of work completed
locally. These commits use their real creation times; they do not reconstruct an
earlier event timeline. The final checkpoint contains the complete usage guide.
Organizer files are preserved; private project planning and credentials stay local.

## Available at this checkpoint

- Python contracts, schema/version CLI, health API and fictional BEFORE fixtures.

```sh
uv sync --all-packages --all-extras
uv run --no-sync cachekit --version
uv run --no-sync cachekit schema --model RequestRecord
uv run --no-sync python -m demo_app.traffic --out data/demo
uv run --no-sync pytest
```

## Limitations

Cache rates are SIMULATED. No real fixer PR, passing live golden evidence or
measured BEFORE/AFTER speedup is claimed. API/UI integration and actual screenshots
remain work in progress. Private inputs stay in gitignored data/.

See AI_USAGE.md, CHANGELOG.md and SUBMISSION.md for the current assistance,
publication record and incomplete submission items.
