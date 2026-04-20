const audio = new AudioManager();
let viz = null;
let lines = [];
let lineIdx = 0;
let refIntervals = [];
let userIntervals = [];
let recording = false;
let playingTimer = null;   // setTimeout handle while playback is running

// --- Settings ---
function pitch()        { return parseFloat(document.getElementById('pitch').value); }
function wpm()          { return parseFloat(document.getElementById('wpm').value); }
function wordSpacing()  { return parseFloat(document.getElementById('wordSpacing').value); }
function sensitivity()  { return parseFloat(document.getElementById('sensitivity').value); }

// --- Text / line management ---
function splitLines(text) {
  return text.split('\n').map(l => l.trim()).filter(Boolean);
}

function loadText() {
  lines = splitLines(document.getElementById('sourceText').value);
  if (!lines.length) lines = [''];
  lineIdx = Math.min(lineIdx, lines.length - 1);
  newLine();
}

// Called when the line changes — clears user recording and rebuilds everything.
function newLine() {
  userIntervals = [];
  buildReference();
}

// Called when only WPM or word spacing changes — recomputes reference only,
// preserving the user's recorded bars for post-hoc comparison.
function buildReference() {
  const line = lines[lineIdx] || '';
  document.getElementById('currentLine').textContent = line;
  document.getElementById('lineCounter').textContent =
    `Line ${lineIdx + 1}/${lines.length}`;

  const { intervals } = textToTiming(line, wpm(), wordSpacing());
  refIntervals = intervals;
  viz.update(refIntervals, userIntervals);
}

function prevLine() {
  if (lineIdx > 0) { lineIdx--; newLine(); }
}

function nextLine() {
  if (lineIdx < lines.length - 1) { lineIdx++; newLine(); }
}

// Shift intervals so the first one starts at t=0, matching the reference origin.
function alignToZero(ivs) {
  if (!ivs.length) return ivs;
  const offset = ivs[0].start;
  return ivs.map(iv => ({ start: iv.start - offset, end: iv.end - offset }));
}

// --- Recording ---
async function startStop() {
  if (recording) {
    audio.stopRecording();
    recording = false;
    setStartBtn(false);
    setButtonStates();
  } else {
    try {
      userIntervals = [];
      viz.update(refIntervals, userIntervals);
      audio.onUpdate = (ivs) => {
        userIntervals = alignToZero(ivs);
        viz.update(refIntervals, userIntervals);
      };
      audio.onAutoStop = () => {
        recording = false;
        setStartBtn(false);
        setButtonStates();
      };
      await audio.startRecording({ pitch: pitch(), sensitivity: sensitivity(), wpm: wpm() });
      recording = true;
      setStartBtn(true);
      setButtonStates();
    } catch (e) {
      alert('Microphone access denied or unavailable: ' + e.message);
    }
  }
}

function setStartBtn(isRecording) {
  const btn = document.getElementById('startBtn');
  btn.textContent = isRecording ? '⏹ Stop' : '⟳ Start Listening';
  btn.classList.toggle('recording', isRecording);
}

function setButtonStates() {
  const playing = playingTimer !== null;
  document.getElementById('startBtn').disabled    = playing;
  document.getElementById('playRefBtn').disabled  = recording || playing;
  document.getElementById('playUserBtn').disabled = recording || playing;
}

// --- Playback ---
function startPlayback(intervals, pitchHz) {
  if (playingTimer !== null) return;
  const durationMs = Math.max(...intervals.map(iv => iv.end));
  audio.playIntervals(intervals, pitchHz);
  playingTimer = setTimeout(() => {
    playingTimer = null;
    setButtonStates();
  }, durationMs + 200);   // small buffer past last note
  setButtonStates();
}

function playReference() {
  if (!refIntervals.length) return;
  startPlayback(refIntervals, pitch());
}

function playUser() {
  if (!userIntervals.length) { alert('No user recording yet.'); return; }
  startPlayback(userIntervals, pitch() + 50);
}

// --- Drag to realign user intervals ---
// Grabbing element N and dragging shifts N and everything after it,
// leaving prior elements fixed — compensates for extra word spacing mid-send.
let dragState = null;  // { idx, startX, snapshot }

function initDrag(canvas) {
  function canvasXY(e) {
    const r = canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  canvas.addEventListener('mousedown', e => {
    const [px, py] = canvasXY(e);
    const idx = viz.hitTestUser(px, py);
    if (idx === -1) return;
    dragState = {
      idx,
      startX: px,
      snapshot: userIntervals.map(iv => ({ ...iv })),
    };
    viz._dragIdx = idx;
    canvas.style.cursor = 'grabbing';
    e.preventDefault();
  });

  canvas.addEventListener('mousemove', e => {
    const [px, py] = canvasXY(e);

    if (!dragState) {
      canvas.style.cursor = viz.hitTestUser(px, py) !== -1 ? 'ew-resize' : 'default';
      return;
    }

    const deltaMs = viz.pixelDeltaToMs(px - dragState.startX);
    userIntervals = dragState.snapshot.map((iv, i) =>
      i < dragState.idx
        ? { ...iv }
        : { start: iv.start + deltaMs, end: iv.end + deltaMs }
    );
    viz.update(refIntervals, userIntervals);
  });

  function endDrag() {
    if (!dragState) return;
    dragState = null;
    viz._dragIdx = -1;
    viz.draw();
    canvas.style.cursor = 'default';
  }

  canvas.addEventListener('mouseup',    endDrag);
  canvas.addEventListener('mouseleave', endDrag);
}

// --- Scale bar (drag to set seconds-per-row) ---
function initScaleBar(bar) {
  const label = document.getElementById('scaleLabel');
  let scaleState = null;  // { startX, startMs }

  function updateLabel() {
    label.textContent = `◂ ${(viz.displayMs / 1000).toFixed(1)} seconds/row ▸`;
  }

  bar.addEventListener('mousedown', e => {
    scaleState = { startX: e.clientX, startMs: viz.displayMs };
    bar.classList.add('dragging');
    document.body.style.cursor = 'ew-resize';
    e.preventDefault();
  });

  // Use window so the drag continues even if pointer leaves the bar.
  window.addEventListener('mousemove', e => {
    if (!scaleState) return;
    const deltaMs = (e.clientX - scaleState.startX) * 40;  // 40 ms per pixel
    const newMs = Math.max(1000, Math.min(60000, scaleState.startMs + deltaMs));
    viz.setDisplaySec(newMs / 1000);
    viz.draw();
    updateLabel();
  });

  window.addEventListener('mouseup', () => {
    if (!scaleState) return;
    scaleState = null;
    bar.classList.remove('dragging');
    document.body.style.cursor = '';
  });

  updateLabel();
}

// --- Init ---
window.addEventListener('load', () => {
  const canvas = document.getElementById('vizCanvas');
  viz = new Visualizer(canvas);

  function syncCanvasWidth() {
    canvas.width = canvas.offsetWidth;
    viz.draw();
  }
  window.addEventListener('resize', syncCanvasWidth);
  syncCanvasWidth();

  initDrag(canvas);
  initScaleBar(document.getElementById('scaleBar'));

  // Wire up settings changes
  document.getElementById('wpm').addEventListener('change', buildReference);
  document.getElementById('wordSpacing').addEventListener('change', buildReference);
  document.getElementById('pitch').addEventListener('input', () => {
    document.getElementById('pitchVal').textContent = pitch() + ' Hz';
  });

  // Load default text
  loadText();
});
