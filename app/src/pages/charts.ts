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

export function qualityView(review: QualityReview) {
  const longest = Math.max(0, ...review.criteria.map((c) => seconds(c.timestamp)));
  const total = Math.max(120, Math.ceil((longest + 45) / 60) * 60);
  const pins = review.criteria.map((c, index) => {
    const lost = c.max - c.score;
    return {
      index, criterion: c.name, time: c.timestamp, lost,
      x: LEFT + Math.round((WIDTH * seconds(c.timestamp)) / total), radius: 7 + lost,
      bad: (c.max === 0 ? 0 : Math.round((100 * c.score) / c.max)) < 70,
    };
  });
  return { review, pins, length: `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}` };
}
