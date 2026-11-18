// Optional development test driver. Uses Node's built-in WebSocket, no npm packages.
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {writeFile} from 'node:fs/promises';
const [debugPort, appURL] = process.argv.slice(2);
let pages;
for (let i = 0; i < 80; i++) {
  try { pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json(); break; }
  catch { await delay(150); }
}
assert(pages, 'Chrome debugging endpoint unavailable');
const target = pages.find(p => p.type === 'page');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {ws.onopen = resolve; ws.onerror = reject;});
let sequence = 0;
const waiting = new Map(), errors = [], external = [];
ws.onmessage = ({data}) => {
  const event = JSON.parse(data);
  if (event.id) {
    const pending = waiting.get(event.id); waiting.delete(event.id);
    if (event.error) pending?.reject(new Error(JSON.stringify(event.error)));
    else pending?.resolve(event.result);
  } else if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.text + ': ' + (event.params.exceptionDetails.exception?.description || ''));
  else if (event.method === 'Network.requestWillBeSent') {
    const url = event.params.request.url;
    if (!url.startsWith(appURL.replace(/\/viewer.html$/, '')) && !url.startsWith('data:') && !url.startsWith('blob:')) external.push(url);
  }
};
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    waiting.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params}));
  });
}
async function js(expression) {
  const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
async function until(expression, description) {
  for (let i = 0; i < 120; i++) {
    if (await js(expression)) return;
    await delay(100);
  }
  throw new Error(`${description}: ${await js('document.body.innerText')}`);
}
try {
  await send('Runtime.enable'); await send('Network.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1400,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate', {url: appURL});
  await until(`typeof el === 'function' && document.getElementById('start') && !el('start').disabled`, 'setup ready');
  if (process.argv[4] === '--empty') {
    assert.match(await js(`el('inventory').textContent`), /0 distinct visits/);
    await js(`el('start').click()`);
    await until(`!el('reading').hidden && typeof tasks !== 'undefined' && tasks.length === 0`, 'empty UI');
    assert.match(await js(`el('cover').textContent`), /No review inputs/);
    assert.equal(await js(`el('review').disabled`), true);
    assert.equal(await js('nv.volumes.length'), 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log('PASS: Chrome empty-data startup, protocol initialization, clear layout guidance, disabled empty review form.');
  } else {
  assert.match(await js(`el('inventory').textContent`), /3 distinct visits/);
  await js(`el('start').click()`);
  await until(`typeof imageReady !== 'undefined' && imageReady`, 'first image loaded');
  assert.equal(await js('nv.volumes.length'), 1);
  assert.equal(await js('nv.opts.sliceType'), 0);
  assert.equal(await js('nv.opts.isRadiologicalConvention'), true);
  assert.equal(await js('nv.opts.dragAndDropEnabled'), false);
  assert.equal(await js('nv.volumes[0].name'), 'volume.nii.gz');
  const shape = await js('Array.from(nv.volumes[0].dimsRAS).slice(1,4)');
  assert([[10,16,18],[16,18,10]].some(s=>JSON.stringify(s) === JSON.stringify(shape)), 'coded sform or qform orientation');
  if (process.env.TASO_SYNTHETIC_SCREENSHOT) {
    const shot = await send('Page.captureScreenshot', {format:'png'});
    await writeFile(process.env.TASO_SYNTHETIC_SCREENSHOT, Buffer.from(shot.data,'base64'));
  }
  assert(!/INDD00|flair2d|3d_resliced|spcX/.test(await js('document.body.innerText')), 'reading labels remain masked');
  await js(`nv.setSliceType(3)`);
  assert.equal(await js('nv.opts.sliceType'), 0);
  await send('Input.dispatchKeyEvent', {type: 'keyDown', code: 'KeyV', key: 'v'});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', code: 'KeyV', key: 'v'});
  assert.equal(await js('nv.opts.sliceType'), 0);
  const slice = await js('nv.frac2vox(nv.scene.crosshairPos)[2]');
  await js(`el('sliceNext').click()`);
  assert.equal(await js('nv.frac2vox(nv.scene.crosshairPos)[2]'), slice + 1);
  await js(`el('zoom').value=2; el('zoom').dispatchEvent(new Event('input'))`);
  assert.equal(await js('nv.scene.pan2Dxyzmm[3]'), 2);
  await js(`el('reset').click()`);
  assert.equal(await js('nv.scene.pan2Dxyzmm[3]'), 1);
  await js(`el('minimum').value=-100; el('maximum').value=500; el('applyRange').click()`);
  assert.deepEqual(await js('[nv.volumes[0].cal_min,nv.volumes[0].cal_max]'), [-100,500]);
  await js(`el('defaultRange').click()`);
  await js(`el('notes').value=${JSON.stringify('Synthetic browser note\tα\nsecond line')}; el('notes').dispatchEvent(new Event('input')); el('completed').click(); el('flag').click(); el('save').click()`);
  await until(`!dirty && !saving`, 'save acknowledged');
  assert.match(await js(`el('saveStatus').textContent`), /Saved/);
  const savedId = await js('tasks[index].id');
  const queueIds = await js('tasks.map(t=>t.id)');
  await js('window.beforeReload = true');
  await send('Page.reload');
  await until(`window.beforeReload !== true && typeof el === 'function' && document.getElementById('start') && !el('start').disabled`, 'reload ready');
  await js(`el('start').click()`);
  await until(`typeof imageReady !== 'undefined' && imageReady`, 'resume rendered');
  assert.deepEqual(await js('tasks.map(t=>t.id)'), queueIds);
  await js(`el('jump').value=${queueIds.indexOf(savedId) + 1}; el('go').click()`);
  await until(`imageReady && tasks[index].id === '${savedId}'`, 'saved task restored');
  assert.match(await js(`el('notes').value`), /Synthetic browser note/);
  assert.equal(await js(`el('completed').checked && el('flag').checked`), true);
  // Slow decoding an older task must never replace the newest selected task.
  await js(`window.realDecode = niivue.NVImage.loadFromUrl; niivue.NVImage.loadFromUrl = async options => { const n = window.decodeNumber = (window.decodeNumber || 0) + 1; const image = await realDecode.call(niivue.NVImage, options); if(n === 1) await new Promise(r => setTimeout(r, 700)); image.testMarker = n; return image; }; void selectTask(1);`);
  await delay(120);
  await js('selectTask(2)');
  await until(`imageReady && index === 2 && nv.volumes[0].testMarker === 2`, 'latest task rendered');
  await delay(900);
  assert.equal(await js('nv.volumes[0].testMarker'), 2);
  assert.equal(await js('nv.volumes.length'), 1);
  await js('niivue.NVImage.loadFromUrl = realDecode');
  // Check required defaults across every task without sending the backend mapping to the UI.
  const ranges = [], shapes = [];
  for (let i = 0; i < queueIds.length; i++) {
    await js(`selectTask(${i})`);
    await until(`imageReady && index === ${i}`, 'task rendered for defaults');
    ranges.push(await js('[Number(el("minimum").value),Number(el("maximum").value)]'));
    shapes.push(await js('Array.from(nv.volumes[0].dimsRAS).slice(1,4)'));
  }
  assert(shapes.some(s=>JSON.stringify(s) === '[10,16,18]'), 'permuted sform applied');
  assert(shapes.some(s=>JSON.stringify(s) === '[16,18,10]'), 'qform applied');
  assert(ranges.some(r => r[0] === -200 && r[1] === 200), 'candidate default');
  assert(ranges.some(r => r[0] !== -200 || r[1] !== 200), 'reference defaults independent');
  // Simulated write failure blocks navigation and keeps draft text.
  await js(`window.realFetch=window.fetch; window.fetch = async (path, options) => String(path).endsWith('/review') ? new Response(JSON.stringify({error:'Synthetic save failure'}), {status:503,headers:{'Content-Type':'application/json'}}) : realFetch(path,options); el('notes').value='Keep this draft'; el('notes').dispatchEvent(new Event('input')); selectTask(0);`);
  await until(`el('saveStatus').textContent.includes('Synthetic save failure')`, 'save failure visible');
  assert.equal(await js('index'), queueIds.length - 1);
  assert.equal(await js('dirty'), true);
  assert.equal(await js(`el('notes').value`), 'Keep this draft');
  await js('window.fetch=realFetch; el("save").click()');
  await until('!dirty && !saving', 'save retry succeeded');
  await js(`el('end').click()`);
  await until(`!el('finished').hidden`, 'reading ended');
  assert.equal(await js('nv.volumes.length'), 0);
  assert.equal(await js(`el('export').disabled`), true);
  await js(`el('acknowledge').click()`);
  assert.equal(await js(`el('export').disabled`), false);
  // Read the export programmatically; keep it in memory, do not write sensitive files.
  const tsv = await js(`(async()=> (await request('/api/independent/export',{unblind:true})).text())()`);
  assert.match(tsv, /INDD001/); assert.match(tsv, /flair2d.nii.gz/); assert.match(tsv, /3d_resliced.nii.gz/);
  await js(`el('setupAgain').click()`);
  await until(`!el('setup').hidden && !el('start').disabled`, 'mode selection');
  await js(`el('mode').value='candidate-only'; el('start').click()`);
  await until(`!el('reading').hidden && imageReady && mode === 'candidate-only'`, 'candidate mode rendered');
  assert.equal(await js('tasks.length'), 2);
  assert(!queueIds.includes(await js('tasks[index].id')));
  assert.equal(await js('tasks.filter(t=>t.review.completed).length'), 0);
  assert.deepEqual(await js('[nv.volumes[0].cal_min,nv.volumes[0].cal_max]'), [-200,200]);
  assert.deepEqual(errors, [], 'no unhandled browser errors');
  assert.deepEqual(external, [], 'no external browser asset or network requests');
  console.log('PASS: Chrome WebGL2 synthetic UI, spatial axis orientation, axial lock, single-volume masking, slice/zoom/range, save/reload, stale loads, failed-save retention, export gate, separate candidate mode, offline requests.');
  }
} finally { ws.close(); }
