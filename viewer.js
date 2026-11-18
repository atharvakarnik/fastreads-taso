/* Adapted from the original fastreads single-page viewer. See NOTICE.md. */
"use strict";
const el = id => document.getElementById(id);
let token = "", mode = "", tasks = [], index = -1, nv = null;
let dirty = false, saving = false, transitioning = false, imageReady = false;
let generation = 0, controller = null, initialRange = null;
const modeName = value => value === "independent" ? "Blinded independent reads" : "Long-TE only · separate protocol";
function message(id, text, error = false) {
  el(id).textContent = text;
  el(id).classList.toggle("error", error);
}
async function request(path, body) {
  const options = body === undefined ? {} : {method: "POST", headers: {
    "Content-Type": "application/json", "X-FastReads-Token": token
  }, body: JSON.stringify(body)};
  const response = await fetch(path, {...options, cache: "no-store"});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "Local request failed. Check the server window.");
  }
  return response;
}
async function inventory() {
  const data = await (await request("/api/status")).json();
  token = data.token;
  const s = data.summary;
  el("inventory").textContent = `${s.visits} distinct visits: ${s.paired} with both inputs, ${s.reference_only} reference only, ${s.candidate_only} long-TE only, ${s.neither} without a supported review input. ${s.optional} optional full acquisitions excluded. ${s.rejected} unsafe or ambiguous entries excluded.`;
  el("start").disabled = false;
}
function controls() {
  el("previous").disabled = saving || transitioning || index <= 0;
  el("next").disabled = saving || transitioning || index >= tasks.length - 1;
  el("go").disabled = saving || transitioning || !tasks.length;
  el("end").disabled = saving || transitioning;
  el("review").disabled = saving || transitioning || index < 0;
  // A failed/missing image cannot be newly marked complete.
  el("completed").disabled = !imageReady;
  el("display").disabled = !imageReady;
}
function progress() {
  const complete = tasks.filter(t => t.review.completed).length;
  el("progress").textContent = `${complete} / ${tasks.length} tasks completed`;
}
function clearImage(text) {
  imageReady = false;
  el("cover").hidden = false;
  el("cover").textContent = text;
  if (nv) for (const volume of [...nv.volumes]) nv.removeVolume(volume);
  controls();
}
async function renderer() {
  if (nv) return;
  const {Niivue} = window.niivue || {};
  if (!Niivue) throw new Error("The local NiiVue bundle is missing. Restore niivue.umd.js.");
  nv = new Niivue({sliceType: 0, isRadiologicalConvention: true, isColorbar: false,
    isOrientCube: false, dragAndDropEnabled: false, drawingEnabled: false,
    crosshairWidth: 0.2, crosshairWidthUnit: "percent",
    showLegend: false, logLevel: "silent", viewModeHotKey: "", clipPlaneHotKey: "",
    cycleClipPlaneHotKey: "", dragMode: 0, dragModePrimary: 0});
  // Lock the renderer as well as hiding view controls; V cannot enable other planes.
  const setSliceType = nv.setSliceType.bind(nv);
  nv.setSliceType = () => setSliceType(0);
  nv.onLocationChange = sliceLabel;
  try { await nv.attachToCanvas(el("canvas")); }
  catch (error) { nv.cleanup(); nv = null; throw error; }
  nv.setSliceType(0);
}
function sliceLabel() {
  if (!imageReady || !nv.volumes.length) return;
  const z = nv.frac2vox(nv.scene.crosshairPos)[2];
  el("sliceLabel").textContent = `${z + 1} / ${nv.volumes[0].dimsRAS[3]}`;
}
function setRange(min, max) {
  const volume = nv?.volumes[0];
  if (!volume || !Number.isFinite(min) || !Number.isFinite(max) || min >= max) {
    message("rangeStatus", "Enter finite values with min less than max.", true);
    return;
  }
  volume.cal_min = min;
  volume.cal_max = max;
  el("minimum").value = min;
  el("maximum").value = max;
  nv.updateGLVolume();
  message("rangeStatus", "Display range applied.");
}
async function selectTask(nextIndex) {
  if (saving || transitioning || !tasks[nextIndex]) return;
  transitioning = true;
  controls();
  if (!await saveCurrent()) { transitioning = false; controls(); return; }
  index = nextIndex;
  const task = tasks[index], ticket = ++generation;
  controller?.abort();
  controller = new AbortController();
  transitioning = false;
  dirty = false;
  initialRange = null;
  clearImage("Loading selected task…");
  el("taskLabel").textContent = `Task ${index + 1} of ${tasks.length} · ${task.id.slice(0, 8)}`;
  el("heading").textContent = `${modeName(mode)} · Task ${index + 1}`;
  el("jump").value = index + 1;
  el("jump").max = tasks.length;
  el("notes").value = task.review.notes;
  el("completed").checked = task.review.completed;
  el("flag").checked = task.review.flag;
  message("saveStatus", task.review.revision ? "Saved record restored." : "No changes.");
  message("imageStatus", "Loading selected image…");
  message("rangeStatus", "");
  progress(); controls();
  try {
    if (!task.available) throw new Error("Input unavailable. Restore this task's original file and restart. Saved records are retained.");
    // Decode separately from NiiVue's scene. Only the latest generation may add a volume.
    const response = await fetch(`/api/${mode}/${task.id}/image`, {signal: controller.signal, cache: "no-store"});
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Image unavailable.");
    }
    const range = response.headers.get("X-Display-Range");
    const buffer = await response.arrayBuffer();
    const image = await window.niivue.NVImage.loadFromUrl({url: "volume.nii.gz", name: "volume.nii.gz", buffer, colormap: "gray"});
    if (ticket !== generation) return;
    if (!image?.hdr || image.hdr.dims.slice(4).some(d => d > 1))
      throw new Error("A single 3D NIfTI volume is required. This input cannot be reviewed here.");
    if (!(image.hdr.sform_code > 0 || image.hdr.qform_code > 0))
      throw new Error("No coded NIfTI spatial orientation. Ask the data preparer to check this input.");
    nv.scene.crosshairPos = [0.5, 0.5, 0.5];
    nv.setPan2Dxyzmm([0, 0, 0, 1]);
    el("zoom").value = 1;
    nv.addVolume(image);
    initialRange = range === "-200,200" ? [-200, 200] : [image.cal_min, image.cal_max];
    setRange(...initialRange);
    nv.setSliceType(0);
    nv.setCrosshairWidth(el("crosshair").checked ? 0.2 : 0);
    imageReady = true;
    el("cover").hidden = true;
    sliceLabel(); controls();
    message("imageStatus", "Ready · one axial image. Scroll or use slice buttons.");
  } catch (error) {
    if (ticket !== generation || error.name === "AbortError") return;
    clearImage("Image unavailable. See the sidebar for details.");
    message("imageStatus", error.message || "Could not render this image. Use a browser with WebGL2.", true);
  }
}
function changed() {
  dirty = true;
  message("saveStatus", "Unsaved changes. Save before closing.");
  el("saveStatus").classList.remove("saved");
}
async function saveCurrent() {
  if (!dirty || index < 0) return true;
  if (saving) return false;
  const task = tasks[index];
  saving = true; controls();
  message("saveStatus", "Saving…");
  try {
    const data = await (await request(`/api/${mode}/${task.id}/review`, {
      notes: el("notes").value, completed: el("completed").checked,
      flag: el("flag").checked, revision: task.review.revision
    })).json();
    task.review = data.review;
    dirty = false;
    message("saveStatus", "Saved to local review storage.");
    el("saveStatus").classList.add("saved");
    progress();
    return true;
  } catch (error) {
    message("saveStatus", error.message, true);
    return false;
  } finally { saving = false; controls(); }
}
el("start").addEventListener("click", async () => {
  el("start").disabled = true;
  try {
    const selectedMode = el("mode").value;
    const data = await (await request("/api/session", {mode: selectedMode})).json();
    await renderer();
    mode = selectedMode;
    tasks = data.tasks;
    index = -1;
    el("setup").hidden = true;
    el("reading").hidden = false;
    el("modeLabel").textContent = modeName(mode);
    el("acknowledge").checked = false;
    el("export").disabled = true;
    if (tasks.length) {
      const first = tasks.findIndex(t => !t.review.completed);
      await selectTask(first < 0 ? 0 : first);
    } else {
      el("notes").value = "";
      el("completed").checked = false;
      el("flag").checked = false;
      message("saveStatus", "No changes.");
      clearImage("No review inputs for this protocol. Add supported files under data/<INDD>/P<n>/, then restart and resume.");
      el("taskLabel").textContent = "No tasks available";
      message("imageStatus", "No supported inputs for the selected protocol.");
      progress(); controls();
    }
  } catch (error) { message("setupStatus", error.message || "WebGL2 initialization failed. Try a current desktop browser.", true); }
  finally { el("start").disabled = false; }
});
el("previous").addEventListener("click", () => selectTask(index - 1));
el("next").addEventListener("click", () => selectTask(index + 1));
el("go").addEventListener("click", () => {
  const number = Number(el("jump").value);
  if (Number.isInteger(number) && number >= 1 && number <= tasks.length) selectTask(number - 1);
  else message("imageStatus", `Enter a task number from 1 to ${tasks.length}.`, true);
});
for (const id of ["notes", "completed", "flag"]) el(id).addEventListener(id === "notes" ? "input" : "change", changed);
el("save").addEventListener("click", saveCurrent);
el("slicePrevious").addEventListener("click", () => nv.moveCrosshairInVox(0, 0, -1));
el("sliceNext").addEventListener("click", () => nv.moveCrosshairInVox(0, 0, 1));
el("zoom").addEventListener("input", () => nv.setPan2Dxyzmm([0, 0, 0, Number(el("zoom").value)]));
el("reset").addEventListener("click", () => {
  nv.setPan2Dxyzmm([0, 0, 0, 1]); el("zoom").value = 1;
  nv.scene.crosshairPos = [0.5, 0.5, 0.5]; nv.drawScene(); sliceLabel();
});
el("crosshair").addEventListener("change", () => nv.setCrosshairWidth(el("crosshair").checked ? 0.2 : 0));
el("applyRange").addEventListener("click", () => {
  const min = el("minimum").value.trim(), max = el("maximum").value.trim();
  setRange(min ? Number(min) : NaN, max ? Number(max) : NaN);
});
el("defaultRange").addEventListener("click", () => { if (initialRange) setRange(...initialRange); });
el("end").addEventListener("click", async () => {
  if (saving || transitioning) return;
  transitioning = true; controls();
  if (await saveCurrent()) {
    ++generation; controller?.abort(); clearImage("Reading ended.");
    el("reading").hidden = true; el("finished").hidden = false;
    el("heading").textContent = `${modeName(mode)} · reading ended`;
  }
  transitioning = false; controls();
});
el("acknowledge").addEventListener("change", () => { el("export").disabled = !el("acknowledge").checked; });
el("export").addEventListener("click", async () => {
  el("export").disabled = true;
  try {
    const response = await request(`/api/${mode}/export`, {unblind: true});
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = `fastreads-taso-${mode}.tsv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    message("exportStatus", "TSV download requested. Keep it in approved local storage.");
  } catch (error) { message("exportStatus", error.message, true); }
  finally { el("export").disabled = !el("acknowledge").checked; }
});
el("setupAgain").addEventListener("click", async () => {
  el("finished").hidden = true; el("setup").hidden = false;
  message("setupStatus", "Choose the protocol explicitly. Previous results are retained.");
  try { await inventory(); } catch (error) { message("setupStatus", error.message, true); }
});
// Keep text-entry keys away from NiiVue's window keyboard handlers.
for (const event of ["keydown", "keyup"]) window.addEventListener(event, e => {
  if (e.target !== el("canvas")) e.stopImmediatePropagation();
  else if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) e.stopImmediatePropagation();
}, true);
window.addEventListener("beforeunload", e => { if (dirty || saving) { e.preventDefault(); e.returnValue = ""; } });
inventory().catch(error => message("setupStatus", error.message || "Start the local server using your platform launcher.", true));
