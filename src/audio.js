// Procedural audio: every sound is synthesized. Mechanical steam, wood, metal —
// restrained, functional, no carnival steampunk.

let ac = null;
let master = null;
let musicGain = null;
let musicOn = true;
let sfxT = {};          // per-sound throttle timestamps
let ambientStarted = false;

export function initAudio() {
  if (ac) return;
  try {
    ac = new (window.AudioContext || window.webkitAudioContext)();
    master = ac.createGain();
    master.gain.value = 0.5;
    master.connect(ac.destination);
    musicGain = ac.createGain();
    musicGain.gain.value = 0.16;
    musicGain.connect(master);
  } catch (e) {
    console.warn('audio unavailable', e);
  }
}

export function resumeAudio() {
  if (ac && ac.state === 'suspended') ac.resume();
  if (ac && !ambientStarted) { ambientStarted = true; startAmbient(); startMusic(); }
}

export function toggleMusic() {
  musicOn = !musicOn;
  if (musicGain) musicGain.gain.value = musicOn ? 0.16 : 0;
  return musicOn;
}

function noiseBuffer(dur = 1) {
  const buf = ac.createBuffer(1, ac.sampleRate * dur, ac.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return buf;
}

let _noise = null;
const getNoise = () => (_noise = _noise || noiseBuffer(2));

function env(gainNode, t0, a, peak, dur) {
  gainNode.gain.setValueAtTime(0.0001, t0);
  gainNode.gain.linearRampToValueAtTime(peak, t0 + a);
  gainNode.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
}

function throttle(name, ms) {
  const now = performance.now();
  if ((sfxT[name] || 0) > now - ms) return true;
  sfxT[name] = now;
  return false;
}

export function sfx(name, opts = {}) {
  if (!ac || ac.state !== 'running') return;
  const t = ac.currentTime;
  switch (name) {
    case 'click': { // UI / selection acknowledge
      if (throttle('click', 40)) return;
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = 'square'; o.frequency.value = 880;
      env(g, t, 0.002, 0.06, 0.05);
      o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.06);
      break;
    }
    case 'order': { // command confirm: two wooden ticks
      if (throttle('order', 80)) return;
      for (let i = 0; i < 2; i++) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'triangle'; o.frequency.value = 440 - i * 120;
        env(g, t + i * 0.05, 0.003, 0.09, 0.06);
        o.connect(g); g.connect(master); o.start(t + i * 0.05); o.stop(t + i * 0.05 + 0.07);
      }
      break;
    }
    case 'arrow': {
      if (throttle('arrow', 60)) return;
      const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
      s.buffer = getNoise();
      f.type = 'bandpass'; f.frequency.setValueAtTime(3200, t); f.frequency.exponentialRampToValueAtTime(900, t + 0.18);
      env(g, t, 0.005, 0.1, 0.2);
      s.connect(f); f.connect(g); g.connect(master); s.start(t); s.stop(t + 0.22);
      break;
    }
    case 'steamshot': { // pressure bow discharge: hiss + thunk
      if (throttle('steamshot', 90)) return;
      const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
      s.buffer = getNoise();
      f.type = 'highpass'; f.frequency.value = 1800;
      env(g, t, 0.004, 0.22, 0.35);
      s.connect(f); f.connect(g); g.connect(master); s.start(t); s.stop(t + 0.4);
      const o = ac.createOscillator(), g2 = ac.createGain();
      o.type = 'sine'; o.frequency.setValueAtTime(140, t); o.frequency.exponentialRampToValueAtTime(60, t + 0.12);
      env(g2, t, 0.002, 0.3, 0.14);
      o.connect(g2); g2.connect(master); o.start(t); o.stop(t + 0.16);
      break;
    }
    case 'melee': {
      if (throttle('melee', 110)) return;
      const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
      s.buffer = getNoise();
      f.type = 'bandpass'; f.frequency.value = 500 + Math.random() * 2500; f.Q.value = 2;
      env(g, t, 0.002, 0.12, 0.1);
      s.connect(f); f.connect(g); g.connect(master); s.start(t); s.stop(t + 0.12);
      break;
    }
    case 'death': {
      if (throttle('death', 150)) return;
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = 'sawtooth'; o.frequency.setValueAtTime(160, t); o.frequency.exponentialRampToValueAtTime(50, t + 0.3);
      env(g, t, 0.005, 0.08, 0.32);
      o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.34);
      break;
    }
    case 'charge': { // hoofbeat rumble + steam
      if (throttle('charge', 300)) return;
      const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
      s.buffer = getNoise();
      f.type = 'lowpass'; f.frequency.value = 240;
      env(g, t, 0.01, 0.25, 0.5);
      s.connect(f); f.connect(g); g.connect(master); s.start(t); s.stop(t + 0.55);
      break;
    }
    case 'rally': {
      // a short horn
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = 'sawtooth';
      o.frequency.setValueAtTime(220, t);
      o.frequency.setValueAtTime(220, t + 0.18);
      o.frequency.setValueAtTime(330, t + 0.2);
      env(g, t, 0.03, 0.14, 0.8);
      const f = ac.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 1200;
      o.connect(f); f.connect(g); g.connect(master); o.start(t); o.stop(t + 0.85);
      break;
    }
    case 'capture': {
      for (let i = 0; i < 3; i++) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'triangle'; o.frequency.value = [392, 494, 587][i];
        env(g, t + i * 0.09, 0.01, 0.09, 0.3);
        o.connect(g); g.connect(master); o.start(t + i * 0.09); o.stop(t + i * 0.09 + 0.32);
      }
      break;
    }
    case 'alarm': {
      for (let i = 0; i < 2; i++) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'square'; o.frequency.value = 340 - i * 60;
        env(g, t + i * 0.14, 0.01, 0.07, 0.12);
        o.connect(g); g.connect(master); o.start(t + i * 0.14); o.stop(t + i * 0.14 + 0.14);
      }
      break;
    }
    case 'victory': {
      [392, 494, 587, 784].forEach((fr, i) => {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'triangle'; o.frequency.value = fr;
        env(g, t + i * 0.13, 0.01, 0.12, 0.5);
        o.connect(g); g.connect(master); o.start(t + i * 0.13); o.stop(t + i * 0.13 + 0.52);
      });
      break;
    }
    case 'defeat': {
      [330, 294, 247].forEach((fr, i) => {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'triangle'; o.frequency.value = fr;
        env(g, t + i * 0.2, 0.02, 0.1, 0.6);
        o.connect(g); g.connect(master); o.start(t + i * 0.2); o.stop(t + i * 0.2 + 0.62);
      });
      break;
    }
  }
}

// Battle effect queue → sounds.
export function consumeEffectsAudio(effects) {
  for (const e of effects) {
    if (e.type === 'shot') sfx('arrow');
    else if (e.type === 'steamshot') sfx('steamshot');
    else if (e.type === 'melee') sfx('melee');
    else if (e.type === 'death') sfx('death');
    else if (e.type === 'charge') sfx('charge');
    else if (e.type === 'rally') sfx('rally');
    else if (e.type === 'order') sfx('order');
  }
}

// Gentle countryside bed: filtered noise wind.
function startAmbient() {
  if (!ac) return;
  const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
  s.buffer = getNoise(); s.loop = true;
  f.type = 'lowpass'; f.frequency.value = 300;
  g.gain.value = 0.03;
  s.connect(f); f.connect(g); g.connect(master);
  s.start();
  // slow wind swells
  const lfo = ac.createOscillator(), lg = ac.createGain();
  lfo.frequency.value = 0.07; lg.gain.value = 0.015;
  lfo.connect(lg); lg.connect(g.gain);
  lfo.start();
}

// Sparse procedural score: low drone, military taps, occasional low strings.
function startMusic() {
  if (!ac) return;
  const root = 98; // G2
  const drone = ac.createOscillator(), dg = ac.createGain(), df = ac.createBiquadFilter();
  drone.type = 'sawtooth'; drone.frequency.value = root;
  df.type = 'lowpass'; df.frequency.value = 220;
  dg.gain.value = 0.16;
  drone.connect(df); df.connect(dg); dg.connect(musicGain);
  drone.start();
  const drone2 = ac.createOscillator(), dg2 = ac.createGain();
  drone2.type = 'sine'; drone2.frequency.value = root * 1.5;
  dg2.gain.value = 0.05;
  drone2.connect(dg2); dg2.connect(musicGain);
  drone2.start();

  // rhythmic mechanical tick + drum pattern via lookahead scheduler
  let step = 0;
  const scheduleBar = () => {
    if (!ac) return;
    const t0 = ac.currentTime + 0.05;
    const bpm = 76, spb = 60 / bpm;
    for (let i = 0; i < 8; i++) {
      const tt = t0 + i * spb / 2;
      // muffled field drum on beats, ghost taps off-beats
      if (i % 4 === 0 || (i === 6 && step % 2 === 1)) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'sine'; o.frequency.setValueAtTime(120, tt); o.frequency.exponentialRampToValueAtTime(55, tt + 0.1);
        env(g, tt, 0.003, i % 4 === 0 ? 0.5 : 0.2, 0.16);
        o.connect(g); g.connect(musicGain); o.start(tt); o.stop(tt + 0.2);
      }
      // mechanical texture: quiet tick
      if (i % 2 === 1) {
        const s = ac.createBufferSource(), g = ac.createGain(), f = ac.createBiquadFilter();
        s.buffer = getNoise();
        f.type = 'highpass'; f.frequency.value = 4000;
        env(g, tt, 0.001, 0.03, 0.03);
        s.connect(f); f.connect(g); g.connect(musicGain); s.start(tt); s.stop(tt + 0.04);
      }
    }
    // slow modal melody note every other bar (dorian-ish over G)
    if (step % 2 === 0) {
      const notes = [root * 2, root * 2 * 9 / 8, root * 2 * 6 / 5, root * 2 * 4 / 3, root * 2 * 3 / 2];
      const n = notes[(step / 2) % notes.length | 0];
      const o = ac.createOscillator(), g = ac.createGain(), f = ac.createBiquadFilter();
      o.type = 'sawtooth'; o.frequency.value = n;
      f.type = 'lowpass'; f.frequency.value = 900;
      env(g, t0, 0.4, 0.12, spb * 4);
      o.connect(f); f.connect(g); g.connect(musicGain); o.start(t0); o.stop(t0 + spb * 4 + 0.1);
    }
    step++;
    setTimeout(scheduleBar, spb * 4 * 1000 - 60);
  };
  scheduleBar();
}
