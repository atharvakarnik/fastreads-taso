# FastReads Taso — Codex maintenance instructions

## Project status and scope

FastReads Taso is an **already implemented** local, offline, axial-only NIfTI review viewer for conventional FLAIR and long-TE/3D-derived FLAIR. The initial MVP has been built. Future work is incremental maintenance, bug fixing, verification, and incorporation of **explicitly confirmed** changes from Ilya/Manuel. Do not reinitialize the project or implement the original MVP specification again.

The software supports physician image review and note-taking; it does not perform image processing or clinical diagnosis and has not been clinically validated.

Read the relevant current code and `README.md` before each change. Treat `README.md` as the description of supported behavior, data layout, usage, known limitations, and physician questions; **confirm behavior against the implementation and tests rather than assuming documentation is always current**. This file governs how to make changes, not a standing request to implement missing features. A new user request/task prompt supplies the scope for each session.

## Current architecture

Keep the existing simple, self-contained architecture unless a change genuinely requires otherwise:

- `server.py`: Python 3.10+ standard-library local HTTP server, controlled file discovery, review state/API, and TSV export.
- `viewer.html` and `viewer.js`: vanilla browser UI, axial NiiVue rendering and review workflow.
- `niivue.umd.js`: locally bundled, licensed NiiVue renderer. Preserve the upstream notices and `licenses/NiiVue-LICENSE.txt`.
- `launch.py` with `Start_Viewer.bat`, `Start_Viewer.command`, `Start_Viewer.sh`: cross-platform launch and same-installation readiness checks.
- `tests/`: Python and optional synthetic-data browser tests.
- `README.md`: operational documentation; `NOTICE.md`: code provenance and third-party notices.

Runtime requires no Node/npm, frontend build, pip packages, internet service, database, or sibling repository. The local server uses `127.0.0.1:8002`. Do not introduce heavyweight dependencies, a frontend framework, or a general configuration subsystem without a demonstrated requirement and user approval.

The neighboring `../fastreads` and `../fastreads-jcb` repositories are **optional, read-only historical references**, not required dependencies. Do not modify them or import their implementations wholesale.

## Data and review contract — preserve unless explicitly revised

- Local, Git-ignored input directory is `data/<INDD>/P<n>/`, where `P1`, `P2`, etc. are distinct visits. Accepted image filenames are `flair2d.nii.gz` (reference) and `3d_resliced.nii.gz` (candidate). `spcX_ir_2mm_p4_te980_corr.nii.gz` is optional and is **not** automatically substituted or included in normal reading queues.
- Keep **axial-only** display, correct interpretation of NIfTI spatial metadata, one displayed volume per reading task, and candidate initial window `-200 / 200`. Never silently resample, register, flip, normalize or modify source images.
- Maintain two separate review protocols: `independent` (blinded, individually randomized reference/candidate tasks) and `candidate-only` (long-TE-only). Preserve reproducible persisted queue/order, opaque task labels during blinded reading, correct underlying INDD/visit/sequence provenance, per-mode review separation, and previously completed work when data are added or missing.
- Review fields currently consist of notes, completed/reviewed, and flag-for-follow-up. Do not invent clinical scoring categories. The true sequence/visit mapping may appear in appropriately gated TSV exports, not on the blinded reading screen.
- Review state and assignments are written under `state/`; preserve atomic writes, revision/concurrent-write checks, one-step backup behavior, fail-closed handling of corrupt state, and prevention of lost unsaved edits. Do not silently regenerate or overwrite persisted assignments or reviews.
- The application is intended for one reviewer per local copy. Do not add multi-user coordination or claim that masking is stronger than the current application-level blinding without a separately defined requirement.

## Privacy and security invariants

Treat all real images, patient/visit identifiers, review results, assignments, exports, reports, screenshots, and locally derived metadata as sensitive. Never commit, upload, log, screenshot, or include them in tests or examples. Use generated synthetic/de-identified fixtures only; do not access the clinical Box folder from Codex.

Retain `.gitignore` protections for `data/`, `state/`, exports, backups, archives, and medical image/report formats. Never bypass ignores with `git add -f`. Keep the HTTP service loopback-only; enforce discovered-file allowlists and path/symlink restrictions. Preserve appropriate no-store and browser-origin protections. Do not add remote endpoints, CDNs, telemetry, analytics, cloud storage or arbitrary filesystem access.

Do not modify real input data or destructively reorganize persisted review state. No code or dataset should be published, pushed, or packaged with clinical data without explicit direction. Preserve license/provenance documentation during distribution changes.

## How to approach future changes

1. Read the user’s actual new request and inspect the relevant code, tests, and README. Scope the smallest coherent change; identify implications for blinding, task identity, persisted state, exports, launchers, and prior records.
2. Clearly distinguish **confirmed physician requirements** from plausible interpretations or engineering preferences. If a requirement is unresolved, retain the existing behavior where safe; do not silently settle study-design or grading decisions.
3. Prefer focused edits and regression tests over rewrites. Keep UI, API, persistence, and documentation consistent. If modifying persisted state or TSV schema, plan backward compatibility and verify existing records survive; do not reset them for convenience.
4. Update `README.md` when user-visible behavior, input layout, installation, exports, limitations or physician questions change. Add or revise tests for each changed contract. Do not create a new perpetual task/status Markdown file for routine changes.
5. Before finishing, report files changed, checks actually run, untested platforms/browser behavior, and any outstanding physician decisions. Do not claim tests passed without executing them. Do not commit/push or open a release unless explicitly asked.

## Validation

Run applicable checks after code changes (some require installed development tools):

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py launch.py tests/*.py
bash -n Start_Viewer.sh Start_Viewer.command
node --check viewer.js
git diff --check
git ls-files data state
```

For viewer behavior changes, also run the optional synthetic-data WebGL browser checks when Chrome/Node are available:

```bash
python3 tests/run_browser.py
python3 tests/run_browser.py --empty
```

Verify the affected workflows, particularly independent/candidate-only mode isolation, stable review/task identities on restart, safe data discovery, save/reload/export, axial orientation and display defaults, and that no sensitive files were added to Git. State any Windows, macOS, Linux, or manual physician visual QA that was not actually performed.

## Pending physician input

The initial implementation is **not a finalized clinical review protocol**. The rubric, exact reading/randomization protocol, handling of previously reviewed reference FLAIR, identity visibility, report access, finalization rules, and the optional full 3D acquisition's role remain subject to confirmation. See the current `README.md` for the detailed questions. Apply confirmed new decisions only through scoped tasks; update tests/documentation accordingly.
