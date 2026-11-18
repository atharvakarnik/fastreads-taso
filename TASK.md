# FastReads Taso — initial implementation specification

## Source-grounded request (May 29, 2026 email thread)

Ilya requested a FastReads adaptation for Manuel Taso's FLAIR review data. Manuel described folders arranged by unique patient `INDD`, then sequential scans `P1 ... Pn`. A visit has a conventional reference `flair2d.nii.gz`, the long-TE/3D-derived sequence `3d_resliced.nii.gz` (initial min/max window `-200 / 200`), and possibly `spcX_ir_2mm_p4_te980_corr.nii.gz` (full 3D acquisition). Ilya explicitly requires **axial images only**. He asked for independent randomized evaluation of the two sequences to reduce bias; Manuel agreed. Manuel also suggested Ilya could perhaps read **only the long-TE sequence** because he had already reviewed the conventional FLAIR and relevant prior findings could be retrieved from the report.

The email **does not specify** a clinical rubric, mandatory annotation columns, number of reviewers, whether masking must hide the patient or visit identity, the precise randomization unit/seed, or inclusion of reports in the UI. Do not pretend that it does. Treat details below beyond the email as engineering defaults for an MVP, and document them for physician confirmation.

## Deliverable

A functioning **local, offline, axial-only NiiVue viewer** derived from the supplied baseline files in this repository. No physician data or Box access should be required for development. Preserve the simple Python standard-library server and standalone frontend if practical.

### Required interactions

1. Detect `data/<INDD>/P<n>/` and enumerate valid, uniquely identified subject-visits. Keep `P1`, `P2`, etc. distinct, and display a useful empty-state message if no data exist.
2. Default to a blinded **two-sequence independent-read mode**. Construct an ordered review queue with one item for each available reference or candidate sequence; use an opaque label on the reading screen, not the actual source filename. Persist the queue and true-to-opaque mapping so the order and any completed reads survive restarts. The reviewer must not be shown both sequences together or be unexpectedly told the actual sequence during the blinded session. Avoid consecutive presentation of paired sequences where reasonably possible, but do not claim a research-validated randomization protocol.
3. Provide a separate, clearly identified **long-TE-only mode** that queues only `3d_resliced.nii.gz`. Its review records must be distinguishable from records from the two-sequence mode; switching modes must not overwrite prior results.
4. Display a single NIfTI volume in axial orientation, with previous/next slice, zoom/reset, a way to adjust window min/max, and a progress indicator. Start candidate sequence display with min/max `-200` and `200`; the reference can use a suitable NiiVue default. Do not impose the candidate's window on the reference.
5. Offer basic notes, a completed status, and a flag for follow-up, stored independently for each task. Save safely (atomic writes), restore on restart, and export tab-separated results with `INDD`, `visit`, `sequence`, `mode`, `review_task_id`, `completed`, `flag`, and `notes`. Include a clear indication when a save has succeeded or failed.
6. Keep optional full 3D acquisition out of routine read queues until its role is explicitly clarified. Do not silently fall back to it when the candidate is missing.
7. Validate the source directory and allowed filenames server-side; protect against traversal, bad IDs, symlinks, and absent or duplicate candidate files. Bind the local server to `127.0.0.1` on `8002` (or explain a safer conflict-free alternative). Update all platform launchers and make startup clearly identifiable as FastReads Taso.
8. Keep patient data and review state outside Git and outside code-only shipments. Document placing data, running the viewer, exporting reviews, and restoring a backup.

### UX boundaries

- Reuse the original viewer's restrained sidebar/navigation and NiiVue rendering where it makes sense. Remove PET/MNI-specific controls and data logic, rather than concealing dead code.
- Avoid a separate frontend build tool unless the current baseline genuinely prevents required behavior.
- No report/PDF tab, segmentation, registration, automatic diagnosis, side-by-side comparison, or mandatory classification form in this first iteration.
- Prefer simple, explicit reader workflows to configurability that creates opportunities for accidental unblinding.

## Steps for Codex

1. **Read-only preflight:** inspect `AGENTS.md`, the supplied baseline `viewer.html`, `server.py`, NiiVue bundle, platform launchers, and `.gitignore`. Examine sibling `../fastreads` and `../fastreads-jcb` only as needed and only if readable. Identify code that can be reused, mismatches with this spec, and uncertainties. Do not edit the sibling directories.
2. **Implement the MVP:** adapt discovery, API, frontend, review persistence, export, and launchers in this repository. Keep changes small and well organized; extract small modules if `server.py` or `viewer.html` becomes difficult to maintain. Avoid unrequested refactoring.
3. **Verify:** write and execute Python backend tests against generated, synthetic fixtures (multiple INDDs, multiple visits, missing images, invalid input). Check stable queue order and separate review records across restarts. Run Python syntax checks and `git diff --check`. Manually verify browser interaction if browser tools are available; otherwise document a concise manual QA checklist.
4. **Document:** create or update `README.md` with installation-free end-user launch instructions, data layout, review-mode distinction, review storage and TSV export, and known limitations. Include license/attribution information for reused source and NiiVue.
5. **Report:** list files changed, exact tests run and results, decisions/assumptions, and physician confirmation questions. Do not push or create a GitHub release without explicit permission.

## Acceptance checks

- With no `data/`, app launches and explains expected layout without crashing.
- With synthetic `INDD001/P1`, `INDD001/P2`, and `INDD002/P1`, the UI identifies three distinct visits and correct sequence availability.
- In two-sequence mode the reading screen exposes only one NIfTI series per task and does not reveal its filename, while the exported mapping preserves actual provenance.
- The randomized task order, review IDs, notes, and completion state remain stable after refresh/restart.
- Long-TE-only mode never queues `flair2d.nii.gz`, and its records do not collide with two-sequence-mode records.
- `3d_resliced.nii.gz` initially uses `-200 / 200`. Axial views are correctly oriented from NIfTI headers, without unauthorized spatial transformations.
- A missing third image does not cause errors; the third image is never silently substituted for the candidate.
- Invalid requests cannot access arbitrary files. HTTP server is loopback-only.
- Windows, macOS and Linux launch scripts are updated; where an OS cannot be tested, describe the manual validation required.
- `git status` and `git ls-files` verify that clinical files, local review state, and exports have not been staged or tracked.

## Questions for physician confirmation (do not block the MVP)

- What exact findings/grades, if any, should the form capture beyond notes, reviewed, and flag?
- Is the reader expected to perform paired blinded independent assessments, long-TE-only assessments, or both for different readers?
- Is randomized order by image, subject-visit, or by separate sequence blocks preferred, and how separated should paired images be?
- Should reviewers be shown INDD/visit during blinded reads, or only an opaque task number?
- Should prior reports/clinical findings ever be shown in the viewer, and if so, only after a blinded read is committed?

Keep these as open decisions, not settled clinical requirements.
