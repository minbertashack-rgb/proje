# Model Distribution & Strategy

This document describes the operational model strategy for AI backends used by DocVerse.

Summary recommendation: the repository does not include large model artefacts. The recommended default for CI and general automation is **remote-only (AI2)**. Local GGUF support is documented for offline or developer workflows, but operators must provide the file.

Scenarios

1) Remote-only (recommended for CI)
 - What: Use an AI2-compatible remote server (e.g. hosted or a separate machine running the AI2 server).
 - Required envs: `AI2_TABAN_ADRESI` or `AI2_BASE_URL`, optional `AI2_MODEL`.
 - Tests that run: any test that requires `AI2` will run. Local-model-only tests (`GGUF`) will be skipped.
 - Skip/Block: If AI2 is missing, tests that declare `requires: [AI2]` will be skipped or treated as blocker depending on the manifest. For CI we recommend marking AI2-backed tests as non-blocker if CI can't access a remote model.

2) Local-only (developer/offline)
 - What: Use a local `.gguf` model file and set `DOCVERSE_GGUF_PATH` (and `YEREL_MODEL_ETKIN=1`).
 - Required envs: `DOCVERSE_GGUF_PATH` pointing to a valid .gguf file, optionally `YEREL_MODEL_ETKIN=1`.
 - Tests that run: tests requiring `GGUF` or local model will run; AI2-only tests will be skipped.
 - Skip/Block: If the .gguf file is missing the local-model tests skip; CI will not have the model by default.

3) Hybrid (remote + local)
 - What: Both remote AI2 and local GGUF are available. The system can be configured to prefer remote or local depending on `YEREL_MODEL_ETKIN` and AI2 config.
 - Required envs: `AI2_TABAN_ADRESI` and/or `DOCVERSE_GGUF_PATH`.
 - Tests that run: both sets of tests may run. The `release_checks_report.json` will report `ai_model_mode: both`.

Notes for operators
 - Repo policy: The repository does NOT include model artefacts (no .gguf files). Operators must provide local models externally.
 - CI policy: CI runs without local models by default; CI will use remote AI2 if available or skip model-dependent tests. We recommend configuring a shared AI2 test endpoint for CI if full AI tests are required.
 - Where to set envs: set `DOCVERSE_GGUF_PATH`, `YEREL_MODEL_ETKIN`, `AI2_TABAN_ADRESI`, `AI2_MODEL` in the CI environment or local `.env`.

Mapping to release checks
 - `tools/release_checks.py` reports `gguf_candidates`, `ai_model_mode` and `ai2_candidate` in `release_checks_report.json`.
 - `tools/run_release_gate.py` consults the report and will skip tests whose `requires` are unmet, logging skip reasons into the `release_gate_summary.json`.

Quick operator examples
 - Remote-only (CI):
 ```bash
 export AI2_TABAN_ADRESI=http://ai2.example:8002/v1
 # CI: pip install -r requirements-dev.txt -c constraints.txt
 ```

 - Local-only (developer):
 ```bash
 export DOCVERSE_GGUF_PATH=/path/to/your-model.gguf
 export YEREL_MODEL_ETKIN=1
 python tools/ocr_smoke.py
 python tools/run_release_gate.py
 ```
