## Release / Gate PR Checklist

Provide a short summary of the change and why it needs a release gate run.

Checklist (required for release PRs):

- [ ] Summary: short description of change
- [ ] Ran `python tools/release_checks.py` and attached `release_checks_report.json`
- [ ] Ran `python tools/ocr_smoke.py` (if Tesseract present) or noted it's not applicable
- [ ] Ran `python tools/benchmark_audit.py` (if applicable)
- [ ] Ran `python tools/run_release_gate.py` and attached `release_logs/*/release_gate_summary.json`
- [ ] Confirmed `constraints.txt` is present and referenced by CI
- [ ] Confirmed `MODEL_STRATEGY.md` documents model decisions for this PR
- [ ] Verified release gate is non-interactive (no prompts)
- [ ] CI passes (if configured) and artifacts uploaded

How to reproduce locally:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt -c constraints.txt
python tools/release_checks.py
python tools/ocr_smoke.py
python tools/benchmark_audit.py
python tools/run_release_gate.py
```

Attach the following artifacts to the PR or provide links:

- `release_checks_report.json`
- `release_logs/<timestamp>/release_gate_summary.json`
- `constraints.txt` (if changed)

Reviewer notes: focus on CI artifacts and any skipped tests in `release_gate_summary.json`.
## Release-readiness PR checklist

Please fill in and confirm before merging. The release gate tooling should be green and artifacts available.

- [ ] `tools/release_checks.py` run locally and `release_checks_report.json` attached
- [ ] `python tools/benchmark_audit.py` run and no critical benchmark regressions
- [ ] `python tools/run_release_gate.py` run locally (non-interactive) and `release_gate_summary.json` present
- [ ] `constraints.txt` exists and CI uses it (`pip install -r requirements-dev.txt -c constraints.txt`)
- [ ] Model strategy documented in `MODEL_STRATEGY.md` and PR notes whether model artefacts are required
- [ ] README/TESTING/RELEASE_ENV consistent (no conflicting instructions)
- [ ] Reviewer notes: check `release_checks_report.json` and `release_logs/*/release_gate_summary.json` artifacts if CI fails

If CI fails due to missing model or OCR, check whether the failure is expected (missing env) or a deterministic regression.
