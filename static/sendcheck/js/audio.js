class AudioManager {
  constructor() {
    this.ctx = null;
    this.stream = null;
    this.analyser = null;
    this.rafId = null;

    this.isRecording = false;
    this.startTime = 0;
    this.intervals = [];       // completed {start, end} intervals
    this._onStart = null;      // ms timestamp of current open interval, or null
    this._holdTimer = null;    // setTimeout id for hold debounce

    this.onUpdate   = null;    // callback(intervals) on each change
    this.onAutoStop = null;    // callback() when silence timeout fires
  }

  async startRecording({ pitch, sensitivity, wpm }) {
    if (this.isRecording) return;

    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === 'suspended') await this.ctx.resume();

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation:   false,
        noiseSuppression:   false,
        autoGainControl:    false,
      },
      video: false,
    });
    const source = this.ctx.createMediaStreamSource(this.stream);

    const filter = this.ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = pitch;
    // Q=8 gives ring-down τ = Q/(π·f) ≈ 3.6ms @ 700Hz → ~1.7% overestimate on dahs.
    // Higher Q sounds cleaner but adds systematic length; lower Q is noisier but more accurate.
    filter.Q.value = 8;

    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 256;  // 5.8ms window @ 44100Hz — faster than 512 (11.6ms)

    source.connect(filter);
    filter.connect(this.analyser);

    this.intervals = [];
    this._onStart = null;
    this._holdTimer = null;
    this.startTime = performance.now();
    this.isRecording = true;

    // Hold time = 1/3 of a dit — absorbs brief noise dropouts within an element
    this._holdMs = (1200 / wpm) / 3;
    this._threshold = sensitivity * 0.25;
    this._lastActiveTime = performance.now();
    this._autoStopMs = 3000;

    this._poll();
  }

  _poll() {
    if (!this.isRecording) return;

    const buf = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(buf);

    let rms = 0;
    for (const v of buf) rms += v * v;
    rms = Math.sqrt(rms / buf.length);

    const now = performance.now() - this.startTime;
    const active = rms >= this._threshold;

    if (active) {
      this._lastActiveTime = performance.now();
      if (this._holdTimer !== null) {
        clearTimeout(this._holdTimer);
        this._holdTimer = null;
      }
      if (this._onStart === null) {
        this._onStart = now;
      }
    } else {
      if (this._onStart !== null && this._holdTimer === null) {
        const dropTime = now;  // capture when signal actually stopped, not when timer fires
        this._holdTimer = setTimeout(() => {
          this.intervals.push({ start: this._onStart, end: dropTime });
          this._onStart = null;
          this._holdTimer = null;
          if (this.onUpdate) this.onUpdate([...this.intervals]);
        }, this._holdMs);
      }

      if (this.intervals.length > 0 && performance.now() - this._lastActiveTime >= this._autoStopMs) {
        this.stopRecording();
        if (this.onAutoStop) this.onAutoStop();
        return;
      }
    }

    this.rafId = requestAnimationFrame(() => this._poll());
  }

  stopRecording() {
    if (!this.isRecording) return;
    this.isRecording = false;
    cancelAnimationFrame(this.rafId);
    if (this._holdTimer) clearTimeout(this._holdTimer);

    if (this._onStart !== null) {
      const end = performance.now() - this.startTime;
      this.intervals.push({ start: this._onStart, end });
      this._onStart = null;
    }

    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
    if (this.onUpdate) this.onUpdate([...this.intervals]);
  }

  // Play an array of {start, end} intervals (ms) as sine tones at given pitch.
  playIntervals(intervals, pitch) {
    if (!intervals.length) return;
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === 'suspended') this.ctx.resume();

    const now = this.ctx.currentTime;

    intervals.forEach(({ start, end }) => {
      const s = start / 1000;
      const e = end / 1000;
      const ramp = Math.min(0.005, (e - s) / 4);

      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = pitch;
      gain.gain.setValueAtTime(0, now + s);
      gain.gain.linearRampToValueAtTime(0.4, now + s + ramp);
      gain.gain.setValueAtTime(0.4, now + e - ramp);
      gain.gain.linearRampToValueAtTime(0, now + e);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now + s);
      osc.stop(now + e + 0.01);
    });
  }
}
