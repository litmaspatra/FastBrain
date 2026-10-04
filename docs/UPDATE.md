# Updating FastBrain

```bash
cd ~/FastBrain
bash scripts/update-fastbrain.sh
```

The updater runs `git pull --ff-only` (if this is a git checkout), re-runs the installer, and restarts
the router and the MiniLM service **only if they were already running**.

Preserved across updates: `~/.fastbrain/fastbrain.env`, `fastbrain.db`, `router/`, `models/`, `minilm/`,
`helpers/` and all cached aliases. Only `~/.fastbrain/app` (the code) and the `bin/` adapters are replaced,
and the swap is atomic: a failed copy leaves the previous install in place.

## Python version

The installer picks the first interpreter that is Python 3.13 or newer from:
`$FASTBRAIN_PYTHON`, `python3.13`, `python3.14`, `python3`. The chosen path is baked into
`~/.fastbrain/fastbrain`. To pin it, set `FASTBRAIN_PYTHON=/path/to/python` before running the installer.

The optional MiniLM service needs `numpy` + `onnxruntime`; `start-minilm` picks the first of
`$FASTBRAIN_MINILM_PYTHON`, `python3.14`, `python3.13`, `python3` that can import both.

## Verify

```bash
~/.fastbrain/fastbrain doctor
bash scripts/validate-termux.sh
```
