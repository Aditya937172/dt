import * as THREE from 'three';
import {OrbitControls} from 'three/addons/OrbitControls.js';
import {createIcons, RotateCcw, Circle, Square} from '/static/vendor/lucide.js';

const $ = id => document.getElementById(id);
$('reset').innerHTML = '<i data-lucide="rotate-ccw"></i>';
$('record').innerHTML = '<i data-lucide="circle"></i> Record';
$('stop').innerHTML = '<i data-lucide="square"></i> Stop';
createIcons({icons: {RotateCcw, Circle, Square}});

const names = ['thumb', 'index', 'middle', 'ring', 'pinky'];
$('curls').innerHTML = names.map(name =>
  '<div class="curl">' + name.toUpperCase() + '<strong id="' + name + '">--</strong>' +
  '<div class="bar"><i id="' + name + 'bar"></i></div></div>'
).join('');

const viewport = $('viewport');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#0b1112');
scene.fog = new THREE.FogExp2('#0b1112', 0.035);
const camera = new THREE.PerspectiveCamera(43, 1, 0.1, 100);
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
viewport.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
function resetView() {
  camera.position.set(0, 2.1, 10.5);
  controls.target.set(0, 0.2, 0);
  controls.update();
}
resetView();
$('reset').onclick = resetView;

scene.add(new THREE.HemisphereLight(0xfff4eb, 0x293035, 2.2));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.7);
keyLight.position.set(3, 5, 6);
scene.add(keyLight);
const edgeLight = new THREE.DirectionalLight(0xffd6ba, 1.4);
edgeLight.position.set(-4, 2, -4);
scene.add(edgeLight);
const grid = new THREE.GridHelper(16, 32, 0x407d77, 0x1a3433);
grid.position.y = -2.2;
grid.visible = false;
scene.add(grid);
$('grid').onchange = event => { grid.visible = event.target.checked; };

const edgePairs = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],
  [5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],
  [13,17],[0,17],[17,18],[18,19],[19,20]];
const jointGeometry = new THREE.SphereGeometry(1, 18, 12);
const segmentGeometry = new THREE.CylinderGeometry(0.83, 1, 1, 16, 1);
const yAxis = new THREE.Vector3(0, 1, 0);
const handModels = new Map();

const demoToggle = $('demoFsr');
const demoSliders = [$('demoFsr1'), $('demoFsr2')];
demoToggle.checked = new URLSearchParams(location.search).get('demo') === '1';
function updateDemoControls() {
  $('demoControls').hidden = !demoToggle.checked;
  $('zeroFsr').disabled = demoToggle.checked;
  $('pressFsr').disabled = demoToggle.checked;
  $('fsrNote').textContent = demoToggle.checked
    ? 'SIMULATED FSR values follow the sliders. Turn off demo mode to see live ESP32 ADC readings.'
    : 'Set baseline with both pads untouched, then hold both pads and set the pressed range.';
}
demoToggle.onchange = updateDemoControls;
demoSliders.forEach((slider, index) => {
  slider.oninput = () => { $('demoFsr' + (index + 1) + 'Value').textContent = slider.value + '%'; };
});
updateDemoControls();
function fsrForDisplay(liveFsr) {
  if (!demoToggle.checked) return liveFsr;
  return {status: 'SIMULATED', channels: demoSliders.map(slider => {
    const level = Number(slider.value) / 100;
    return {raw: Math.round(150 + level * 3800), level, range: 0, unstable: false};
  })};
}

function segmentBetween(mesh, a, b) {
  const delta = b.clone().sub(a);
  const length = Math.max(delta.length(), 0.001);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.scale.y = length;
  mesh.quaternion.setFromUnitVectors(yAxis, delta.divideScalar(length));
}

function makeHand(id, side) {
  const group = new THREE.Group();
  scene.add(group);
  const isLeft = side.toLowerCase() === 'left';
  const color = isLeft ? 0x72e3ce : 0xf8bd89;
  const skin = new THREE.MeshPhysicalMaterial({color: 0xc58d6e, roughness: 0.82,
    metalness: 0, clearcoat: 0.06, clearcoatRoughness: 0.9});
  const nailMaterial = new THREE.MeshPhysicalMaterial({color: 0xe5c5b8, roughness: 0.46,
    clearcoat: 0.2});
  const joints = Array.from({length: 21}, (_, index) => {
    const mesh = new THREE.Mesh(jointGeometry, skin);
    const radius = index === 0 ? 0.17 : [4, 8, 12, 16, 20].includes(index) ? 0.075
      : [5, 9, 13, 17].includes(index) ? 0.13 : 0.095;
    mesh.scale.setScalar(radius);
    group.add(mesh);
    return mesh;
  });
  const segments = edgePairs.map(([a, b]) => {
    const mesh = new THREE.Mesh(segmentGeometry, skin);
    const radius = a === 0 ? 0.16 : [1, 5, 9, 13, 17].includes(a) ? 0.12
      : [2, 6, 10, 14, 18].includes(a) ? 0.1 : 0.078;
    mesh.scale.x = radius;
    mesh.scale.z = radius * 0.9;
    group.add(mesh);
    return mesh;
  });
  const palm = new THREE.Mesh(jointGeometry, skin);
  group.add(palm);
  const thenar = new THREE.Mesh(jointGeometry, skin);
  thenar.scale.set(0.24, 0.34, 0.15);
  palm.add(thenar);
  thenar.position.set(isLeft ? 0.45 : -0.45, -0.16, 0.05);
  const wrist = new THREE.Mesh(jointGeometry, skin);
  wrist.scale.set(0.23, 0.3, 0.17);
  group.add(wrist);
  const nails = [4, 8, 12, 16, 20].map(() => {
    const mesh = new THREE.Mesh(jointGeometry, nailMaterial);
    mesh.scale.set(0.055, 0.08, 0.012);
    group.add(mesh);
    return mesh;
  });
  const pressureMaterial = new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0.12, depthWrite: false});
  const pressure = new THREE.Mesh(new THREE.TorusGeometry(0.58, 0.025, 6, 48), pressureMaterial);
  group.add(pressure);
  const pads = [0x72e5c8, 0xf2b776].map(color => {
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 12),
      new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0, depthWrite: false}));
    group.add(mesh);
    return mesh;
  });
  const model = {group, joints, segments, palm, wrist, nails, pressure, pads};
  handModels.set(id, model);
  return model;
}

function pressureLevel(fsr) {
  if (!['LIVE', 'RECORDED', 'SIMULATED'].includes(fsr?.status) || fsr.channels?.length !== 2) return 0;
  return Math.max(...fsr.channels.map(channel => channel.unstable ? 0 : (channel.level || 0)));
}

function applyState(state) {
  const activeHands = new Set();
  for (const [handIndex, hand] of (state.robot_hands || []).entries()) {
    const id = hand.track_id;
    activeHands.add(id);
    const model = handModels.get(id) || makeHand(id, hand.hand);
    model.group.visible = true;
    const points = hand.landmarks.map(point => new THREE.Vector3(point[0], point[1], point[2]));
    points.forEach((point, index) => model.joints[index].position.copy(point));
    edgePairs.forEach(([a, b], index) => segmentBetween(model.segments[index], points[a], points[b]));
    const orientation = hand.palm_orientation;
    const matrix = new THREE.Matrix4().set(orientation[0], orientation[3], orientation[6], 0,
      orientation[1], orientation[4], orientation[7], 0,
      orientation[2], orientation[5], orientation[8], 0, 0, 0, 0, 1);
    const palmPoint = new THREE.Vector3(...hand.palm_position);
    model.palm.position.copy(palmPoint);
    model.palm.quaternion.setFromRotationMatrix(matrix);
    model.palm.scale.set(Math.max(0.3, hand.palm_width * 0.48),
      Math.max(0.3, hand.palm_length * 0.48), 0.15);
    model.wrist.position.copy(points[0]);
    model.wrist.quaternion.copy(model.palm.quaternion);
    [4, 8, 12, 16, 20].forEach((tip, index) => {
      const nail = model.nails[index];
      const direction = points[tip].clone().sub(points[tip - 1]).normalize();
      nail.position.copy(points[tip]).addScaledVector(direction, -0.025);
      nail.position.z += 0.07;
      nail.quaternion.copy(model.palm.quaternion);
    });
    const mappedHand = handIndex === ($('swapFsr').checked ? 1 : 0);
    const pressure = mappedHand ? pressureLevel(state.fsr) : 0;
    model.pressure.position.copy(palmPoint).add(new THREE.Vector3(0, 0, 0.22));
    model.pressure.scale.setScalar(1 + pressure * 0.8);
    model.pressure.material.opacity = mappedHand && pressure > 0 ? pressure * 0.75 : 0;
    for (const [padIndex, landmarkIndex] of [4, 8].entries()) {
      const pad = model.pads[padIndex];
      pad.position.copy(points[landmarkIndex]);
      const channel = state.fsr?.channels?.[padIndex];
      pad.material.opacity = mappedHand && ['LIVE', 'RECORDED', 'SIMULATED'].includes(state.fsr?.status)
        && !channel?.unstable ? (channel?.level || 0) * 0.8 : 0;
      pad.scale.setScalar(0.8 + (channel?.level || 0) * 1.3);
    }
  }
  for (const [id, model] of handModels) model.group.visible = activeHands.has(id);

  $('objectStatus').textContent = state.grasp_state || 'NO TRACKING';
}

function updateFsr(fsr) {
  const transportLabel = fsr?.transport === 'wifi' ? ' · WI-FI'
    : fsr?.transport === 'serial' ? ' · USB' : '';
  $('fsrStatus').textContent = (fsr?.status || 'NO DATA')
    + (['LIVE', 'STALE', 'CHECK SIGNAL'].includes(fsr?.status) ? transportLabel : '');
  $('fsrStatus').classList.toggle('live', fsr?.status === 'LIVE');
  $('fsrStatus').classList.toggle('simulated', fsr?.status === 'SIMULATED');
  if (!demoToggle.checked && !replayActive && fsr?.status === 'NO WIFI DATA') {
    $('fsrNote').textContent = `Waiting for ESP32 Wi-Fi packets on UDP ${fsr.wifi_port}. Connect the laptop and ESP32 to the same network.`;
  }
  if (!demoToggle.checked && !replayActive && fsr?.calibration_error) {
    $('fsrNote').textContent = fsr.calibration_error
      + (fsr.calibrated ? '' : ' · Bars show inverted raw ADC, not pressure.');
  }
  [0, 1].forEach(index => {
    const channel = fsr?.channels?.[index];
    const number = index + 1;
    $('fsr' + number + 'raw').textContent = channel ? String(channel.raw).padStart(4, '0') : '--';
    const barLevel = channel ? (fsr.calibrated || fsr.status === 'SIMULATED'
      ? channel.level || 0 : (4095 - channel.raw) / 4095) : 0;
    $('fsr' + number + 'bar').style.width = Math.round(barLevel * 100) + '%';
    $('fsr' + number + 'quality').textContent = channel
      ? (channel.unstable ? 'CHECK SIGNAL' : !fsr.calibrated && fsr.status !== 'SIMULATED'
        ? 'RAW ONLY · CALIBRATE' : Math.round((channel.level || 0) * 100) + '% RELATIVE') + ' · RAW ' + channel.raw
      : 'NO DATA';
    $('fsr' + number + 'quality').classList.toggle('unstable', !!channel?.unstable);
    if (fsr?.status === 'SIMULATED') $('fsr' + number + 'quality').textContent = 'SIMULATED / MANUAL';
  });
}

let ws, latest = null, lastArrival = 0, lastFrame = -1, clockOffset = 0, pingStart = 0, rtt = null;
const metrics = {frames: 0, latency: null, rtt: null};
window.liveDiagnostics = {metrics, handModels, renderer, scene, camera};
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onopen = () => {
    pingStart = Date.now();
    ws.send(JSON.stringify({type: 'ping', client_ms: pingStart}));
  };
  ws.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.type === 'pong') {
      rtt = Date.now() - pingStart;
      clockOffset = data.server_ms - (pingStart + Date.now()) / 2;
      ws.send(JSON.stringify({type: 'next'}));
      return;
    }
    latest = data;
    lastArrival = performance.now();
  };
  ws.onclose = () => {
    $('connection').textContent = 'DISCONNECTED';
    $('connection').className = '';
    setTimeout(connect, 1000);
  };
  ws.onerror = () => ws.close();
}
connect();

let previewBusy = false;
async function updatePreview() {
  if (previewBusy || replayActive) return;
  previewBusy = true;
  try {
    const response = await fetch('/api/preview', {cache: 'no-store'});
    const blob = await response.blob();
    if (blob.size) {
      const image = $('preview');
      const old = image.src;
      image.src = URL.createObjectURL(blob);
      $('cameraStatus').textContent = '';
      if (old.startsWith('blob:')) URL.revokeObjectURL(old);
    }
  } finally {
    previewBusy = false;
  }
}
setInterval(() => updatePreview().catch(() => {}), 100);

function display(state) {
  const shownFsr = fsrForDisplay(state.fsr);
  applyState({...state, fsr: shownFsr});
  updateFsr(shownFsr);
  const hand = state.hands?.[0];
  const age = Math.max(0, Date.now() + clockOffset - (state.captured_unix_ms || Date.now()));
  metrics.frames++;
  metrics.latency = age;
  metrics.rtt = rtt;
  const values = {
    fps: (state.fps || 0).toFixed(1),
    latency: Math.round(age) + ' ms',
    hand: state.hands?.map(item => item.handedness.toUpperCase()).join(' + ') || '--',
    pose: hand?.grip_pose || '--',
    confidence: hand?.confidence != null ? (hand.confidence * 100).toFixed(0) + '% CONFIDENCE' : '--',
    camera: state.camera || 'CAMO',
    session: state.recording ? 'REC / ' + state.session : 'READY'
  };
  for (const [id, value] of Object.entries(values)) $(id).textContent = value;
  $('connection').textContent = state.status;
  $('connection').className = hand ? 'live' : '';
  $('lost').textContent = hand ? '' : state.status;
  $('record').disabled = state.recording;
  $('stop').disabled = !state.recording;
  for (const name of names) {
    $(name).textContent = hand ? hand.curls[name].toFixed(2) : '--';
    $(name + 'bar').style.width = (hand ? hand.curls[name] * 100 : 0) + '%';
  }
}

for (const [id, action] of [['record', 'start'], ['stop', 'stop']]) {
  $(id).onclick = async () => {
    await fetch('/api/record/' + action, {method: 'POST'});
    if (action === 'stop') setTimeout(refreshSessions, 1000);
  };
}
$('zeroFsr').onclick = async () => {
  await fetch('/api/fsr/calibrate', {method: 'POST'});
  $('zeroFsr').textContent = 'Baseline requested';
  setTimeout(() => { $('zeroFsr').textContent = 'Set untouched baseline'; }, 1500);
};
$('pressFsr').onclick = async () => {
  await fetch('/api/fsr/calibrate-pressed', {method: 'POST'});
  $('pressFsr').textContent = 'Pressed range requested';
  setTimeout(() => { $('pressFsr').textContent = 'Set both pressed range'; }, 1500);
};

const timelineCanvas = $('timeline');
const timelineContext = timelineCanvas.getContext('2d');
const replayVideo = $('replayVideo');
const livePoints = [];
let replayActive = false;
let replayPlaying = false;
let replaySession = null;
let replayData = null;
let replayTime = 0;
let replayLastTick = performance.now();
let replayFetchId = 0;
let replayLoading = false;

function addLivePoint(state) {
  if (state.fsr?.status !== 'LIVE' || state.fsr.channels?.length !== 2) return;
  const value = channel => state.fsr.calibrated ? channel.level || 0 : (4095 - channel.raw) / 4095;
  livePoints.push({t: state.session_time_ms ?? state.timestamp_ms,
    p1: value(state.fsr.channels[0]), p2: value(state.fsr.channels[1])});
  const cutoff = livePoints[livePoints.length - 1].t - 20000;
  while (livePoints.length && livePoints[0].t < cutoff) livePoints.shift();
  $('timelineEvent').textContent = state.grasp_state || 'NO EVENTS';
  $('timelineMode').textContent = state.fsr.calibrated ? 'LIVE · RELATIVE PRESSURE' : 'LIVE · RAW ADC TREND';
}

async function refreshSessions() {
  try {
    const response = await fetch('/api/sessions');
    if (!response.ok) throw new Error('Could not list sessions');
    const sessions = await response.json();
    const previous = $('sessionPicker').value;
    $('sessionPicker').replaceChildren(new Option('Live stream', ''));
    for (const session of sessions) {
      $('sessionPicker').add(new Option(
        `SESSION ${String(session.id).padStart(3, '0')} · ${session.frame_count} FRAMES${session.purpose === 'implementation_smoke_test' ? ' · TEST' : ''}`,
        String(session.id)));
    }
    if ([...$('sessionPicker').options].some(option => option.value === previous)) $('sessionPicker').value = previous;
    window.availableSessions = sessions;
  } catch (error) {
    $('timelineMode').textContent = 'SESSION INDEX UNAVAILABLE';
  }
}

function chartLevel(row, channelIndex) {
  const saved = channelIndex === 0 ? row.thumb_pressure : row.index_pressure;
  return saved == null ? (4095 - (channelIndex === 0 ? row.fsr1_raw : row.fsr2_raw)) / 4095 : saved;
}

async function loadReplayWindow(position) {
  if (!replaySession) return;
  const fetchId = ++replayFetchId;
  replayLoading = true;
  const start = Math.max(replaySession.start_ms || 0, position - 5000);
  try {
    const response = await fetch(`/api/sessions/${replaySession.id}/replay?start_ms=${start}&duration_ms=20000`);
    if (!response.ok) throw new Error('Replay data unavailable');
    const data = await response.json();
    if (fetchId !== replayFetchId) return;
    replayData = {...data, windowStart: start, windowEnd: start + 20000};
    renderReplay();
  } finally {
    if (fetchId === replayFetchId) replayLoading = false;
  }
}

function closestBefore(rows, position) {
  if (!rows?.length) return null;
  if (rows[0].session_time_ms > position) return null;
  let low = 0, high = rows.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (rows[middle].session_time_ms <= position) low = middle;
    else high = middle - 1;
  }
  return rows[low];
}

function videoFrameAtIndex(rows, index) {
  if (!rows?.length) return null;
  let low = 0, high = rows.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (rows[middle].video_frame_index <= index) low = middle;
    else high = middle - 1;
  }
  return rows[low];
}

function renderReplay() {
  if (!replayActive || !replayData) return;
  const frame = closestBefore(replayData.frames, replayTime);
  const sample = closestBefore(replayData.fsr, replayTime);
  const event = closestBefore(replayData.events, replayTime);
  const fsr = sample ? {status: 'RECORDED', calibrated: sample.quality === 'valid', channels: [
    {raw: sample.fsr1_raw, level: sample.thumb_pressure ?? 0, range: 0, unstable: sample.quality === 'check_signal'},
    {raw: sample.fsr2_raw, level: sample.index_pressure ?? 0, range: 0, unstable: sample.quality === 'check_signal'}
  ]} : {status: 'NO DATA', channels: []};
  if (frame) {
    display({...frame, fsr, grasp_state: frame.grasp_state || event?.event || frame.hands?.[0]?.grip_pose || 'OPEN',
      status: 'RECORDED REPLAY', camera: 'RECORDED', recording: false,
      session: `session_${String(replaySession.id).padStart(3, '0')}`, fps: 0,
      captured_unix_ms: Date.now()});
  } else {
    updateFsr(fsr);
  }
  $('connection').textContent = 'RECORDED REPLAY';
  $('connection').className = 'simulated';
  $('fsrStatus').textContent = sample ? 'RECORDED' : 'NO DATA';
  $('timelineEvent').textContent = event?.event || 'NO EVENTS';
  $('timelineMode').textContent = `${fsr.calibrated ? 'REPLAY' : 'RAW REPLAY'} · SESSION ${String(replaySession.id).padStart(3, '0')}`;
  $('timelineReadout').textContent = ((replayTime - replaySession.start_ms) / 1000).toFixed(1) + ' S';
  $('scrub').value = String(replayTime);
  $('record').disabled = true;
  $('stop').disabled = true;
  $('session').textContent = `REPLAY / SESSION ${String(replaySession.id).padStart(3, '0')}`;
}

function stopReplayPlayback() {
  replayPlaying = false;
  replayVideo.pause();
  $('replayToggle').textContent = 'Play';
}

async function enterReplay(session) {
  stopReplayPlayback();
  replaySession = session;
  replayActive = true;
  replayTime = session.start_ms || 0;
  $('scrub').disabled = false;
  $('scrub').min = String(session.start_ms || 0);
  $('scrub').max = String(session.end_ms || session.start_ms || 0);
  $('scrub').step = '1';
  $('replayToggle').disabled = false;
  demoToggle.checked = false;
  updateDemoControls();
  $('fsrNote').textContent = 'Recorded data. Uncalibrated sessions show raw ADC trends only.';
  $('zeroFsr').disabled = true;
  $('pressFsr').disabled = true;
  $('preview').hidden = true;
  replayVideo.hidden = !session.has_video;
  replayVideo.removeAttribute('src');
  if (session.has_video) replayVideo.src = `/api/sessions/${session.id}/video`;
  try {
    await loadReplayWindow(replayTime);
  } catch (error) {
    $('timelineMode').textContent = 'REPLAY LOAD FAILED';
  }
}

function leaveReplay() {
  stopReplayPlayback();
  replayActive = false;
  replaySession = null;
  replayData = null;
  replayVideo.hidden = true;
  replayVideo.removeAttribute('src');
  replayVideo.load();
  $('preview').hidden = false;
  $('scrub').disabled = true;
  $('replayToggle').disabled = true;
  $('zeroFsr').disabled = demoToggle.checked;
  $('pressFsr').disabled = demoToggle.checked;
  updateDemoControls();
  $('timelineMode').textContent = 'LIVE · LAST 20 S';
  $('timelineReadout').textContent = 'LIVE';
}

$('refreshSessions').onclick = refreshSessions;
$('sessionPicker').onchange = () => {
  const selected = window.availableSessions?.find(session => String(session.id) === $('sessionPicker').value);
  if (selected) enterReplay(selected);
  else leaveReplay();
};
$('replayToggle').onclick = async () => {
  if (!replayActive) return;
  if (replayPlaying) { stopReplayPlayback(); return; }
  replayPlaying = true;
  replayLastTick = performance.now();
  $('replayToggle').textContent = 'Pause';
  if (!replayVideo.hidden) {
    try { await replayVideo.play(); } catch { /* Replay can continue from data alone. */ }
  }
};
$('scrub').oninput = () => {
  if (!replayActive) return;
  replayTime = Number($('scrub').value);
  if (!replayVideo.hidden && replayData?.video_start_ms != null) {
    const videoFrame = closestBefore(replayData.video_frames, replayTime);
    replayVideo.currentTime = videoFrame
      ? videoFrame.video_frame_index / replayData.video_fps : 0;
  }
  if (!replayData || replayTime < replayData.windowStart || replayTime > replayData.windowEnd - 1000) {
    loadReplayWindow(replayTime).catch(() => { $('timelineMode').textContent = 'REPLAY LOAD FAILED'; });
  } else renderReplay();
};

function tickReplay() {
  if (!replayActive || !replaySession) return;
  const now = performance.now();
  if (replayPlaying) {
    const videoIndex = !replayVideo.hidden && !replayVideo.paused && replayData
      ? Math.floor(replayVideo.currentTime * replayData.video_fps) : null;
    const videoFrame = videoIndex == null ? null : videoFrameAtIndex(replayData.video_frames, videoIndex);
    replayTime = videoFrame
      ? videoFrame.session_time_ms + Math.max(0, videoIndex - videoFrame.video_frame_index)
        * 1000 / replayData.video_fps
      : replayTime + Math.min(100, now - replayLastTick);
    if (replayTime >= replaySession.end_ms) {
      replayTime = replaySession.end_ms;
      stopReplayPlayback();
    }
    if (replayData && !replayLoading && replayTime > replayData.windowEnd - 1000) {
      loadReplayWindow(replayTime).catch(() => stopReplayPlayback());
    }
  }
  replayLastTick = now;
  renderReplay();
}

function drawTimeline() {
  const bounds = timelineCanvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const ratio = Math.min(devicePixelRatio || 1, 2);
  const width = Math.round(bounds.width * ratio), height = Math.round(bounds.height * ratio);
  if (timelineCanvas.width !== width || timelineCanvas.height !== height) {
    timelineCanvas.width = width; timelineCanvas.height = height;
  }
  const ctx = timelineContext;
  ctx.clearRect(0, 0, width, height);
  const pad = 18 * ratio, plotH = height - 2 * pad;
  ctx.strokeStyle = '#31504b'; ctx.lineWidth = ratio;
  for (let i = 0; i <= 4; i++) {
    const y = pad + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }
  const start = replayActive ? replayData?.windowStart : Math.max(0, (livePoints.at(-1)?.t || 0) - 20000);
  const end = replayActive ? replayData?.windowEnd : start + 20000;
  if (start == null || end == null) return;
  const rows = replayActive ? (replayData?.fsr || []).map(row => ({t: row.session_time_ms,
    p1: chartLevel(row, 0), p2: chartLevel(row, 1)})) : livePoints;
  for (const [key, color] of [['p1', '#72e5c8'], ['p2', '#f2b776']]) {
    ctx.strokeStyle = color; ctx.lineWidth = 2 * ratio; ctx.beginPath();
    let started = false;
    for (const row of rows) {
      if (row.t < start || row.t > end) continue;
      const x = (row.t - start) / (end - start) * width;
      const y = height - pad - row[key] * plotH;
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    if (started) ctx.stroke();
  }
  if (replayActive && replayData) {
    ctx.font = `${10 * ratio}px Consolas`;
    for (const event of replayData.events) {
      const x = (event.session_time_ms - start) / (end - start) * width;
      ctx.strokeStyle = '#d9e7dd88'; ctx.beginPath(); ctx.moveTo(x, pad); ctx.lineTo(x, height - pad); ctx.stroke();
      ctx.fillStyle = '#d9e7dd'; ctx.fillText(event.event, x + 4 * ratio, height - 5 * ratio);
    }
    const x = (replayTime - start) / (end - start) * width;
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = ratio; ctx.beginPath();
    ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
  }
}

refreshSessions();

new ResizeObserver(() => {
  const {width, height} = viewport.getBoundingClientRect();
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}).observe(viewport);

renderer.setAnimationLoop(() => {
  if (latest) {
    if (!replayActive && latest.frame_id !== lastFrame) {
      display(latest);
      addLivePoint(latest);
      lastFrame = latest.frame_id;
    }
    latest = null;
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: 'next'}));
  }
  if (!replayActive && performance.now() - lastArrival > 1000) {
    $('connection').textContent = ws?.readyState === WebSocket.OPEN ? 'TRACKING STALE' : 'DISCONNECTED';
    $('lost').textContent = 'TRACKING LOST';
    for (const model of handModels.values()) model.group.visible = false;
  }
  controls.update();
  if (replayActive) tickReplay();
  drawTimeline();
  renderer.render(scene, camera);
});
