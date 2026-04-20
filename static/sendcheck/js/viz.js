class Visualizer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx2d = canvas.getContext('2d');
    this.displayMs = 7000;
    this.refIntervals = [];
    this.userIntervals = [];

    // Layout constants — referenced by both draw() and hit-test methods
    this.BAR_H      = 22;
    this.ROW_GAP    = 6;
    this.AXIS_H     = 20;
    this.BAND_MARGIN = 14;
    this.TOP_PAD    = 14;
    this.X_OFF      = 8;
  }

  get _bandTotalH() {
    return this.BAR_H * 2 + this.ROW_GAP + this.AXIS_H + this.BAND_MARGIN;
  }

  get _scaleX() {
    return (this.canvas.width - this.X_OFF * 2) / this.displayMs;
  }

  setDisplaySec(sec) {
    this.displayMs = sec * 1000;
  }

  update(ref, user) {
    this.refIntervals = ref;
    this.userIntervals = user;
    this.draw();
  }

  // Returns index into userIntervals for the bar under canvas pixel (px, py), or -1.
  hitTestUser(px, py) {
    const band  = Math.floor((py - this.TOP_PAD) / this._bandTotalH);
    const bandY = this.TOP_PAD + band * this._bandTotalH;
    const userY = bandY + this.BAR_H + this.ROW_GAP;

    if (py < userY || py > userY + this.BAR_H) return -1;

    const tMs = (px - this.X_OFF) / this._scaleX + band * this.displayMs;

    for (let i = 0; i < this.userIntervals.length; i++) {
      if (tMs >= this.userIntervals[i].start && tMs <= this.userIntervals[i].end) return i;
    }
    return -1;
  }

  // Convert a horizontal pixel delta to milliseconds.
  pixelDeltaToMs(dx) {
    return dx / this._scaleX;
  }

  draw() {
    const c   = this.ctx2d;
    const W   = this.canvas.width;
    const { BAR_H, ROW_GAP, AXIS_H, BAND_MARGIN, TOP_PAD, X_OFF } = this;
    const BAND_H = BAR_H * 2 + ROW_GAP;

    const allEnds = [...this.refIntervals, ...this.userIntervals].map(i => i.end);
    const maxEnd  = allEnds.length ? Math.max(...allEnds) : this.displayMs;
    const numBands = Math.max(1, Math.ceil(maxEnd / this.displayMs));

    const totalH = TOP_PAD + numBands * (BAND_H + AXIS_H + BAND_MARGIN);
    if (this.canvas.height !== totalH) this.canvas.height = totalH;

    c.clearRect(0, 0, W, this.canvas.height);
    c.fillStyle = '#0d0d1a';
    c.fillRect(0, 0, W, this.canvas.height);

    const scaleX = (W - X_OFF * 2) / this.displayMs;

    for (let band = 0; band < numBands; band++) {
      const t0    = band * this.displayMs;
      const t1    = t0 + this.displayMs;
      const bandY = TOP_PAD + band * (BAND_H + AXIS_H + BAND_MARGIN);

      this._drawBars(t0, t1, scaleX, X_OFF, bandY,                   BAR_H, this.refIntervals,  '#4ade80', -1);
      this._drawBars(t0, t1, scaleX, X_OFF, bandY + BAR_H + ROW_GAP, BAR_H, this.userIntervals, '#f87171', this._dragIdx ?? -1);
      this._drawAxis(t0, t1, scaleX, X_OFF, bandY + BAND_H + 4, W);
    }
  }

  // highlightIdx: draw that bar brighter to confirm the drag target
  _drawBars(t0, t1, scale, xOff, y, h, intervals, color, highlightIdx) {
    const c = this.ctx2d;
    for (let i = 0; i < intervals.length; i++) {
      const { start, end } = intervals[i];
      if (end < t0 || start > t1) continue;
      const cs = Math.max(start, t0);
      const ce = Math.min(end, t1);
      const x  = (cs - t0) * scale + xOff;
      const w  = Math.max(1, (ce - cs) * scale);
      c.fillStyle = (i >= highlightIdx && highlightIdx !== -1) ? '#fca5a5' : color;
      c.fillRect(x, y, w, h);
    }
  }

  _drawAxis(t0, t1, scale, xOff, y, W) {
    const c = this.ctx2d;
    c.fillStyle = '#555';
    c.fillRect(xOff, y, W - xOff * 2, 1);
    c.fillStyle = '#666';
    c.font = '10px monospace';
    c.textAlign = 'center';
    const startSec = Math.ceil(t0 / 1000);
    const endSec   = Math.floor(t1 / 1000);
    for (let s = startSec; s <= endSec; s++) {
      const x = (s * 1000 - t0) * scale + xOff;
      c.fillRect(x, y, 1, 4);
      c.fillText(`${s}s`, x, y + 14);
    }
  }
}
