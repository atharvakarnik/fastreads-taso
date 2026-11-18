# FastReads Taso

A local, offline, axial-only NIfTI review viewer for the long-TE/3D FLAIR evaluation described in the May 29, 2026 email. It displays images and records reads. It performs no registration, resampling, segmentation, quantitative analysis or diagnostic classification. It has not been clinically validated.

## Start

You need **Python 3.10+** and a current desktop browser with **WebGL2**. There is no pip, npm, build, account or internet requirement. Keep the application in a writable local folder, outside cloud-sync folders.

- **Windows:** double-click `Start_Viewer.bat`. Python must be available as `py -3` or `python`.
- **macOS:** double-click `Start_Viewer.command`. If macOS restricts launching it, run `bash Start_Viewer.command` from Terminal inside this folder.
- **Linux:** run `bash Start_Viewer.sh` from this folder.
- **Any platform:** `python3 server.py` (Windows: `py -3 server.py`), then open **http://127.0.0.1:8002/viewer.html**.

Keep the server window open. Save changes before closing the browser; use Ctrl+C in the server window to stop. Launchers reuse a healthy server from this exact installation, reject a different app/copy on port 8002, and stop only the server they started. `NO_BROWSER=1` suppresses automatic browser opening. The server binds only to `127.0.0.1`; use that address, rather than `localhost` or a network address. If port 8002 is occupied, close the other viewer/application and retry. No automatic process killing or public bind is used.

## Supply data separately

Put local inputs beside `server.py`, using this layout. These identifiers are fictional examples:

```text
data/
  INDD001/
    P1/
      flair2d.nii.gz
      3d_resliced.nii.gz
      spcX_ir_2mm_p4_te980_corr.nii.gz  (optional, excluded from reads)
    P2/
      flair2d.nii.gz
  INDD002/
    P1/
      3d_resliced.nii.gz
```

Only exact filenames above are supported. Each visit is a distinct `P` followed by a positive integer without leading zeroes: `P1`, `P2`, … `P10`. INDD folder names accept 1–128 ASCII letters, digits, dots, underscores and hyphens, starting with a letter or digit. Discovery orders visits numerically. Unsupported visit names/files are ignored; case-colliding sequence filenames are rejected as ambiguous. All symlinks, junctions, unsafe paths and nonregular inputs are excluded. A linked `data/` root is an error. Missing files remain missing; the optional full acquisition is never a replacement for `3d_resliced.nii.gz`.

The setup screen reports counts of distinct visits, paired/reference-only/candidate-only/missing visits, optional acquisitions and rejected entries. It sends no patient directory listing to the browser. Check exact names locally if the counts differ from expectations. No `data/` folder is required to launch: the empty reading screen explains the expected layout.

Inputs must be single 3D NIfTI volumes with a coded qform or sform. Unsupported/corrupt inputs display an error, retain their task and saved record, and cannot be newly marked complete in the UI. The viewer does not repair spatial metadata. Ask the data preparer to correct inputs separately.

Stop the server before adding, moving or replacing inputs. Resume each relevant mode to append new tasks; previous order, task IDs and reviews are preserved. Removed inputs leave unavailable tasks and retained records. Restore them at their original location to resume. Replacing a file at the same INDD/visit/sequence key retains the old task and review: **do not change reviewed inputs in place**. This MVP does not version image content or compute clinical image checksums.

## Read

Choose a mode explicitly at initialization:

- **Blinded independent reads** (default): one task per available reference or candidate image. One image is visible at a time. The UI hides INDD, visit and sequence names, including file URLs. The actual mapping lives in backend state and is retained in exports.
- **Long-TE only:** queues only `3d_resliced.nii.gz`. This is a separate protocol, intended for the possible workflow where conventional FLAIR has already been assessed. Its task IDs and review records are separate from independent reads.

A random seed and the resulting queue are persisted per mode. A deterministic seeded ordering chooses tasks while avoiding consecutive images from the same subject-visit whenever possible. New inputs append without reordering old tasks. Small or incremental datasets can force adjacent pairs. This is an engineering default, not a validated study randomization or washout protocol. Separate visits from the same patient may be adjacent. Refresh/restart resumes at the first incomplete task (or the first task if all are complete); previous/next and task-number navigation reach all assigned tasks.

Only the axial plane is available, including through keyboard shortcuts; file drag/drop is disabled. NiiVue uses the NIfTI spatial header and shows orientation markers in **radiological convention** (patient right on screen left). No manual flips, registration or spatial corrections are applied. Correct orientation still depends on valid source headers; do not assume separate sequences are aligned.

Use slice buttons, mouse wheel, zoom/reset, crosshair toggle and min/max controls. `3d_resliced.nii.gz` starts at **−200 / 200**. Reference images use their own NiiVue calibration defaults. “Initial range” restores the current image's initial range; “Reset view” restores zoom and slice position. Display changes are temporary and reset on reloading a task.

Blinding hides application labels, not intrinsic image appearance. The required candidate window may itself cue allocation. Raw NIfTI metadata and the selected image's display configuration remain inspectable in developer tools. Someone with access to local state, files or exports can unblind assignments; this is not an adversarial masking system. No companion-image prefetch or preview is used.

Enter only **notes**, **reviewed/completed**, and **flag for follow-up**. Click **Save review**; “Saved to local review storage” acknowledges the backend write. Navigation and “Save & end reading” also save pending changes before leaving. Failed saves keep draft text visible and block navigation; retry after fixing the local problem. Browser close/reload prompts on unsaved changes, but the draft is not recoverable after a forced close. Nothing sensitive is written to browser localStorage. Two tabs trying to update the same revision produce a conflict: copy the unsaved text to approved local storage, reload, then reconcile manually.

Use **one reviewer per application folder**. There is no reviewer identity, multi-user account or review locking protocol. A writer lock prevents two server processes from opening the same state folder. Each reviewer needs a separate local application copy and state folder, run one at a time on port 8002. Do not merge reviewers' JSON files.

## Save, export and restore

`state/reviews.json` is the recoverable source of truth: mode seeds, ordered task mappings and reviews. Each save changes one task with a revision check. Writes use a temporary file in the same directory, flush/fsync and atomic replacement; in-memory state is updated only after success. `state/reviews.json.bak` holds the previous full state, not necessarily the previous completed task. A failed or corrupt state is **never silently reset**. Keep regular separate local backups; the one-step backup is not a full audit trail or protection against disk failure.

To export, select **Save & end reading**, acknowledge that the TSV reveals allocation, then download the selected protocol's TSV. The image is cleared before export is offered. Exports contain all assigned tasks in that mode, including incomplete and unavailable tasks. Columns:

```text
INDD  visit  sequence  mode  review_task_id  completed  flag  notes  revision  updated_at
```

Files are UTF-8 TSV, with every field CSV-quoted; tabs, newlines and quotes in notes round-trip using a TSV parser. `completed` and `flag` are `true`/`false`; timestamps are UTC. Import fields as text in spreadsheet software so free text is not interpreted as formulas. The download goes to the browser's configured destination; choose approved local storage. Export reveals identities and should normally be handled after blinded reading by the study coordinator. It does not enforce a permanent clinical read lock or prevent later edits. Export each mode separately.

To back up/restore:

1. Save and stop the server. Copy the entire `state/` folder to approved local backup storage. Retain corresponding immutable input files separately. Assignments/results are sensitive even without the images.
2. For restoration, preserve a copy of the current `state/` first. Replace it with a complete known-good backup while the server is stopped. Keep the same data layout. Restart and check task counts and saved notes.
3. If only the automatic backup is available, preserve both files, then **copy** `state/reviews.json.bak` over `state/reviews.json`. The latest operation may be absent. Never delete state just to clear an error: doing so regenerates allocation and loses review linkage.

Runtime files are `server.py`, `launch.py`, `viewer.html`, `viewer.js`, `niivue.umd.js`, all three `Start_Viewer` scripts, this README, `NOTICE.md` and `licenses/NiiVue-LICENSE.txt`. For a code-only handoff, copy **only these files**, preserving `licenses/`. There is no shipment/archive generator or option to include data. Do not copy the entire working folder. No sibling repository is needed. Preserve [source provenance and NiiVue's BSD 2-Clause license](NOTICE.md).

## Privacy and scope

Images, patient IDs, notes, assignments, reports and screenshots can be sensitive. `data/`, `state/`, exports, archives and common sensitive file formats are Git-ignored. The server exposes only four frontend routes and explicit review APIs; it has no generic file browser or arbitrary-path API. Image/review responses are `no-store`. Host/Origin/fetch-site checks and per-process write tokens restrict browser requests; CSP blocks external assets and framing. There is no telemetry, CDN or remote storage. These controls do not encrypt files or secure an untrusted computer. Keep the machine and backup/download locations appropriately restricted. Do not mutate inputs concurrently with reads.

The coding workflow never accesses Box. There is no report/PDF UI, paired comparison, clinical grade, image processing, or diagnostic validation.

## Validation

From this repository:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py launch.py tests/*.py
bash -n Start_Viewer.sh Start_Viewer.command
node --check viewer.js
git diff --check
```

The Python suite generates NIfTI fixtures in temporary directories, checks discovery and natural ordering, missing/excluded inputs, traversal/symlink denial, opaque queues, persisted independent assignments, new/removed data, distinct records/modes, save/reload/export, conflicts, failed-write preservation and corrupt-state recovery. HTTP tests need loopback socket permission. The launcher integration test uses synthetic copies, suppresses browser opening, and skips if port 8002 is already occupied.

An optional browser test uses **already installed** Chrome and Node 22+ as development tools only (no npm packages, no runtime dependency):

```sh
python3 tests/run_browser.py
python3 tests/run_browser.py --empty
```

It uses a fresh temporary Chrome profile and synthetic data; it checks actual WebGL2 rendering state, header axis orientation, axial lock, masking, one loaded volume, slice/zoom/range, save/reload, late-image protection, failed-save draft retention, export acknowledgement, candidate-mode separation and absence of external page requests. The `--empty` run checks startup without data and disabled empty review controls. Missing Chrome/Node prints `SKIP`. `CHROME` can specify the Chrome executable.

Observed validation and remaining manual checks are recorded in `TASK.md`. Before physician use, check visual orientation against a trusted synthetic landmark fixture, normal desktop mouse/touch interactions, browser download destination, and the launch/stop paths on Windows and Linux. No clinical images were used in development tests.

## Physician decisions still open

1. What findings/grades, if any, should supplement notes, completed and flag?
2. Which readers use independent two-sequence reads, long-TE-only reads, or both? How many readers, and how are prior conventional reads linked?
3. Is randomization by individual image, subject-visit, or separate sequence blocks required? What pair separation/washout and handling of incomplete pairs are required?
4. Should INDD/visit be visible during blinded reads, or should opaque tasks remain the default? Is application-label masking adequate given intrinsic appearance and window cues?
5. Should prior reports/findings ever be available in the viewer, and only after committing a blinded read? Are completed reads editable or should a finalized-read lock be added?
6. What role, if any, should the optional full 3D acquisition have? It remains excluded.
