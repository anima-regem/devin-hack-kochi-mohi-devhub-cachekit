# Recorded inputs

Generate recorded inputs with:

```sh
uv run --no-sync python -m demo_app.traffic --out data/demo
```

The generated `inputs.jsonl`, `requests_before.jsonl`, and `manifest.json` live
under gitignored `data/demo/`. Keep raw request logs out of Git, including when
using another output directory.

Each input records the exact timestamp, random seed, and process hash seed used
by the BEFORE builder. Re-render using `demo_app.traffic.render_inputs` so tool
order is reproduced in a worker process with that `PYTHONHASHSEED`.
