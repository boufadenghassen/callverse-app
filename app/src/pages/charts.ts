import { ForecastPoint, QualityReview } from '../agents/models';

/**
 * Charts are built on the server as SVG attributes, so they need no JavaScript and the CSP can block all scripts.
 */
const PAD_X = 40, PAD_TOP = 12, PAD_BOTTOM = 28;

export function lineChart(points: ForecastPoint[], width: number, height: number) {
  const n = points.length;
  const max = Math.max(1, ...points.map((p) => Math.max(p.forecast, p.actual ?? 0)));
  const top = Math.ceil(max / 20) * 20;
  const plotW = width - 2 * PAD_X, plotH = height - PAD_TOP - PAD_BOTTOM;
  const y = (v: number) => PAD_TOP + plotH - (plotH * v) / top;
  const pt = (x: number, yy: number) => `${x.toFixed(1)},${yy.toFixed(1)} `;

  let forecast = '', actual = '';
  const labels: string[] = [], labelX: number[] = [];
  points.forEach((p, i) => {
    const x = PAD_X + (n === 1 ? 0 : (plotW * i) / (n - 1));
    labels.push(p.hour);
    labelX.push(Math.round(x));
    forecast += pt(x, y(p.forecast));
    if (p.actual !== null) actual += pt(x, y(p.actual));
  });
  const gridValues: number[] = [], gridY: number[] = [];
  for (let v = 0; v <= top; v += 20) { gridValues.push(v); gridY.push(Math.round(y(v))); }
  return { width, height, labels, labelX, forecastPoints: forecast.trim(), actualPoints: actual.trim(), gridValues, gridY, labelY: height - 8 };
}

/** A review plus a timeline of the moments that cost points (x is in SVG units, viewBox 0..600). */
const LEFT = 24, WIDTH = 552;

const seconds = (mmss: string) => {
  const [m, s] = mmss.split(':').map(Number);
  return Number.isFinite(m) && Number.isFinite(s) ? m * 60 + s : 0;
};

/** Points for a small line chart of values that may have gaps (null): polylines in a width x height box, higher is better, scaled around the data. */
export function sparkline(values: (number | null)[], width = 120, height = 32): string[] {
  const known = values.filter((v): v is number => v !== null);
  if (!known.length) return [];
  let lo = Math.floor(Math.min(...known) - 5), hi = Math.ceil(Math.max(...known) + 5);
  if (hi - lo < 20) { const mid = (hi + lo) / 2; lo = mid - 10; hi = mid + 10; }       // a gentle scale around the data, so small changes stay visible
  const n = values.length, pad = 3;
  const segments: string[] = [];
  let run = '';
  values.forEach((v, i) => {
    if (v === null) { if (run) segments.push(run.trim()); run = ''; return; }
    const x = pad + (n === 1 ? 0 : ((width - 2 * pad) * i) / (n - 1));
    const y = pad + (height - 2 * pad) * (1 - (v - lo) / (hi - lo));
    run += `${x.toFixed(1)},${y.toFixed(1)} `;
  });
  if (run) segments.push(run.trim());
  return segments;
}

export function qualityView(review: QualityReview) {
  const longest = Math.max(0, ...review.criteria.map((c) => seconds(c.timestamp)));
  const total = review.durationSec ? Math.max(60, Math.ceil((review.durationSec + 10) / 30) * 30) : Math.max(120, Math.ceil((longest + 45) / 60) * 60);
  const pins = review.criteria.map((c, index) => {
    const lost = c.max - c.score;
    return {
      index, criterion: c.name, time: c.timestamp, lost,
      x: LEFT + Math.round((WIDTH * seconds(c.timestamp)) / total), radius: 7 + lost,
      bad: (c.max === 0 ? 0 : Math.round((100 * c.score) / c.max)) < 70,
    };
  });
  // the customer's mood through the call (viewBox 600 x 56, mood 0 at the bottom)
  const curve = (review.moodCurve ?? []).map(([t, mood]) => `${(LEFT + (WIDTH * Math.min(t, total)) / total).toFixed(1)},${(50 - 0.45 * mood).toFixed(1)}`).join(' ');
  const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`;
  const turns = (review.turns ?? []).map((t, i) => ({
    ...t, time: mmss(t.start),
    errors: (review.errors ?? []).filter((e) => e.turn === i), strengths: (review.strengths ?? []).filter((g) => g.turn === i),
  }));
  const moodNote = review.moodSource === 'text' ? 'a word list on what she said' : review.source === 'recording' ? 'the emotion model, listening to her voice' : 'the customer simulator';
  return { review, pins, curve, turns, moodNote, length: `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}` };
}
