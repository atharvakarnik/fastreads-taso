# FastReads Taso — Codex repository instructions

## Purpose and instruction boundaries

Build and maintain a **local, lightweight, axial-only NIfTI review viewer** for a long-TE/3D FLAIR evaluation. Its users are physician reviewers; the software facilitates viewing and recording reads, not diagnosis or image processing. Read `TASK.md` for the **initial implementation scope and acceptance criteria**. After initialization, treat this file as the continuing maintenance guide and update `TASK.md` to reflect completed work or replace it with a scoped task file.

This repository is `fastreads-taso`. The sibling `../fastreads` repository is the **primary read-only source** for the original Python + single-page NiiVue viewer. The sibling `../fastreads-jcb` repository is an **optional read-only reference** for more robust data discovery, review saving, access validation, cross-platform startup, and shipment packaging. Sibling folders may not exist in all Codex environments: work from the copied baseline files here and do not depend on siblings at runtime. **Never modify sibling repositories.** Do not import JCB's application wholesale.

## Architecture and scope

- Prefer the original simple architecture: `server.py` using Python 3.10+ standard library, `viewer.html` with vanilla HTML/CSS/JavaScript, and a locally bundled `niivue.umd.js` (respect its third-party license). Keep runtime offline and bind HTTP to `127.0.0.1`, preferably on port `8002` to avoid the older viewers on `8000`.
- Keep the original Windows, macOS, and Linux startup paths working: `Start_Viewer.bat`, `Start_Viewer.command`, and `Start_Viewer.sh`. Rework their URLs, application identity, and readiness checks; no PET-specific strings or assumptions should survive. Optional Windows stop launcher may be retained if it works correctly.
- Do not introduce Node/npm, Vite, React, databases, or heavyweight imaging Python dependencies without a demonstrated need. If a new dependency is unavoidable, explain and document it before introducing it.
- Reuse useful original navigation and display controls, not its PET/MNI/Centiloid datasets, overlays, PET-specific controls, clinical labels, or hard-coded paths.
- Preserve code provenance and NiiVue license/attribution. Build a self-contained shipment without coupling to sibling repositories, internet services, or developer-only tools.

## Data contract

Data are **local, untracked, and supplied separately**, relative to this repository's `server.py`:

```text
data/
  <INDD>/
    P1/
      flair2d.nii.gz
      3d_resliced.nii.gz
      spcX_ir_2mm_p4_te980_corr.nii.gz    # optional; not automatically substituted
    P2/
      flair2d.nii.gz
      3d_resliced.nii.gz
    ...
```

`INDD` is the source patient identifier; `P1 ... Pn` are distinct sequential scan visits. Discover only actual matching visit directories and exact supported NIfTI files. Some sequences or visits may be absent; report missing inputs clearly and do not make up or silently substitute files. The primary comparison is between `flair2d.nii.gz` (reference conventional FLAIR) and `3d_resliced.nii.gz` (long-TE/3D-derived image). The third file is the optional full 3D acquisition and is **not** the comparison candidate unless explicitly requested later.

A review item is identified internally by **INDD + visit + actual sequence**. Never conflate visits or overwrite one sequence's record with another. Validate every requested file against the discovered allowlist, prevent path traversal and symlink escape, and never provide an arbitrary-path endpoint. Do not send the entire data directory listing or identifiable filesystem paths to the browser unnecessarily.

## Review behavior and integrity

- **Axial display only**. Honor NIfTI spatial orientation; do not improvise slice flips or claim images are aligned. Do not do resampling, registration, segmentation, or quantitative analysis in this viewer.
- The initial intensity display for `3d_resliced.nii.gz` is `min=-200`, `max=200`; the reader must be able to adjust its display. Do not apply this range to `flair2d.nii.gz` unless independently justified.
- The design must support **independent, randomized reading** of the two sequences to limit bias. The normal reading screen shows only **one image/sequence per task**, not a synchronized comparison or preview of the companion sequence. Hide the actual filename/sequence identity and any other obvious cues that reveal allocation while a blinded read is ongoing; the exported result must retain the true sequence identity.
- Randomization order must be reproducible and **persisted**, not reshuffled on browser refresh/restart. Persist any mapping from opaque review-task IDs to true INDD/visit/sequence only on the local backend. Ensure separate records for each task. If new data are added later, preserve existing review task IDs and completed reads.
- The email also raises a possible **long-TE-only reading workflow** for a reviewer who already assessed conventional FLAIR. Make it possible to select this as a distinct review mode at session initialization, without pretending it is the same as the blinded two-sequence protocol. Do not silently change modes or merge their results.
- Preserve sensible slice navigation, zoom/reset, crosshair toggle if useful, window/level adjustments, progress indicator, previous/next task, and clear missing-data/error states. Prevent asynchronous image loads from overwriting a newer selected task.
- Record only minimal, **non-diagnostic** fields until the physician specifies a scoring rubric: free-text notes, reviewed/completed indicator, and optional flag-for-follow-up. Never invent clinical classifications or derive grades from the images.
- Autosave or explicit save must be reliable and visibly acknowledged. Use atomic local writes for persisted progress; preserve all prior completed records, and provide a UTF-8 TSV export containing an unambiguous link between each review record and its INDD, visit, actual sequence, and selected mode. Quote/escape tabs and newlines safely. Preserve a recoverable local source-of-truth, e.g. JSON, separate from exports.
- Do not implement a PDF/report viewer unless separately requested; the email mentions retrieving findings from an existing report, not necessarily displaying that report in this app.

## Privacy and safety

- Treat NIfTI images, patient IDs, review results, assignments, reports, and real screenshots as potentially sensitive clinical data. **Never commit, push, upload, or include them in examples, tests, console logs, telemetry, analytics, or screenshots.** Use synthetic/de-identified data for tests. Never access the physician's Box share from the coding agent.
- Keep `data/`, local state, review exports, archives that contain data, and sensitive file types ignored by Git. Do not bypass ignores with `git add -f`.
- Do not expose a non-loopback server or add external script/CDN calls, third-party storage, user analytics, authentication services, or remotely callable APIs. HTTP responses containing images or review results should be uncached where appropriate.
- Preserve local data on errors; never destructively reorganize clinical files. Do not imply clinical or diagnostic validation.

## Development, validation, and delivery

- At the start of a task, inspect the current files, read `TASK.md` if it applies, and briefly state the proposed changes and assumptions. Favor a small working increment over a broad rewrite. Keep new functionality maintainable and appropriately tested.
- Before sign-off, verify: subject/visit discovery and natural P-number ordering; partial/missing sequences; safe paths; axial-only viewing; correct display defaults; independent/blinded tasks; stable randomized assignment on restart; distinct review keys; save/reload/export; no stale image responses; and launchers on supported operating systems as far as locally testable.
- Implement backend tests with Python's `unittest` or similarly small tools, using *generated synthetic* NIfTI fixtures when useful. If browser tests cannot run, state exactly what still needs manual verification rather than claiming success.
- Keep end-user startup independent of npm, `pip install`, and sibling repositories. Shipment generation, if added, must be code-only by default, verify the files being packaged, and require an unmistakable explicit opt-in before local clinical data are included.
- Never push to GitHub, publish a release, upload data, or overwrite external content without the user's explicit instruction. At completion report changed files, observed tests, assumptions needing physician confirmation, and how to run the program.
