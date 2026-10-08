/**
 * Customer insights for the presentation: do service results differ by age band, sex or region?
 * Demo data only: 720 synthetic customers with a few differences built in, so the page has patterns to find.
 * Groups smaller than MIN_GROUP are never shown (nobody can be picked out of a tiny group). To remove this
 * feature: delete this file, the /insights route in deck.controller.ts, views/insights.njk and the sidebar/home links.
 */
export const MIN_GROUP = 10;

export const DIMENSIONS = {
  age: { label: 'Age', values: ['18-25', '26-35', '36-50', '51+'] },
  sex: { label: 'Sex', values: ['Female', 'Male'] },
  region: { label: 'Region', values: ['Tunis', 'Sfax', 'Sousse', 'Nabeul', 'Other'] },
} as const;
export type DimKey = keyof typeof DIMENSIONS;

/** `worse` says which direction is bad, so the bars can be coloured honestly. */
export const METRICS = {
  churn: { label: 'Churn risk', unit: '%', worse: 'high' },
  wait: { label: 'Average wait', unit: ' s', worse: 'high' },
  qa: { label: 'QA score', unit: '/100', worse: 'low' },
  mood: { label: 'Client mood', unit: '/100', worse: 'low' },
  complaints: { label: 'Complaint rate', unit: '%', worse: 'high' },
} as const;
export type MetricKey = keyof typeof METRICS;

interface Customer { age: string; sex: string; region: string; churn: number; wait: number; qa: number; mood: number; complaint: 0 | 1 }

// ---- deterministic synthetic customers (same data on every start) ----------------------------------
function rng(seed: number) { // mulberry32
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const CUSTOMERS: Customer[] = (() => {
  const rand = rng(42);
  const normal = () => Math.sqrt(-2 * Math.log(rand() || 1e-9)) * Math.cos(2 * Math.PI * rand());
  const pick = (values: readonly string[], weights: number[]) => {
    let r = rand() * weights.reduce((a, b) => a + b, 0);
    return values[weights.findIndex((w) => (r -= w) < 0)] ?? values[0];
  };
  const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));
  const ageEffect: Record<string, number> = { '18-25': 14, '26-35': 5, '36-50': -3, '51+': -8 };
  const regionWait: Record<string, number> = { Tunis: 0, Sfax: 50, Sousse: 10, Nabeul: 5, Other: 30 };
  const regionChurn: Record<string, number> = { Tunis: 0, Sfax: 6, Sousse: -1, Nabeul: -2, Other: 4 };
  return Array.from({ length: 720 }, () => {
    const age = pick(DIMENSIONS.age.values, [22, 30, 28, 20]);
    const sex = pick(DIMENSIONS.sex.values, [52, 48]);
    const region = pick(DIMENSIONS.region.values, [40, 22, 16, 10, 12]);
    const churn = clamp(30 + ageEffect[age] + regionChurn[region] + (sex === 'Male' ? 1 : 0) + normal() * 9);
    const wait = Math.round(clamp(150 + regionWait[region] + (age === '51+' ? 20 : 0) + normal() * 35, 30, 400));
    const qa = Math.round(clamp(78 + (age === '51+' ? -4 : 0) + (region === 'Other' ? -3 : 0) + normal() * 7));
    const mood = Math.round(clamp(70 - churn * 0.4 + normal() * 8));
    const complaint = rand() < 0.12 + (age === '18-25' ? 0.06 : 0) + (region === 'Sfax' ? 0.04 : 0) ? 1 : 0;
    return { age, sex, region, churn: Math.round(churn), wait, qa, mood, complaint };
  });
})();

// ---- statistics -------------------------------------------------------------------------------------
const mean = (rows: Customer[], m: MetricKey) =>
  rows.length === 0 ? 0 : rows.reduce((s, r) => s + (m === 'complaints' ? r.complaint * 100 : r[m]), 0) / rows.length;
const round = (v: number) => Math.round(v);

export interface Filters { age: string; sex: string; region: string; metric: MetricKey }

export function buildInsights(f: Filters) {
  const rows = CUSTOMERS.filter((c) => (!f.age || c.age === f.age) && (!f.sex || c.sex === f.sex) && (!f.region || c.region === f.region));
  const small = rows.length < MIN_GROUP;
  const metric = METRICS[f.metric];
  const overall = small ? 0 : mean(rows, f.metric);

  const kpis = (Object.keys(METRICS) as MetricKey[]).map((m) => ({
    key: m, label: METRICS[m].label, value: small ? null : round(mean(rows, m)), unit: METRICS[m].unit,
  }));

  // one chart per dimension, for the chosen metric; a dimension that is filtered to one value has nothing to compare
  const dims = (Object.keys(DIMENSIONS) as DimKey[]).map((d) => {
    const groups = DIMENSIONS[d].values.map((key) => {
      const g = rows.filter((c) => c[d] === key);
      return { key, n: g.length, hidden: g.length < MIN_GROUP, value: g.length < MIN_GROUP ? 0 : round(mean(g, f.metric)) };
    }).filter((g) => g.n > 0);
    return { key: d, label: DIMENSIONS[d].label, groups };
  });
  const top = Math.max(1, ...dims.flatMap((d) => d.groups.map((g) => g.value))) * 1.1;
  const BAR_X = 96, BAR_W = 190, ROW = 30;
  const charts = dims.map((d) => ({
    key: d.key, label: d.label, height: d.groups.length * ROW + 8, overallX: BAR_X + Math.round((overall / top) * BAR_W),
    rows: d.groups.map((g, i) => {
      const dev = g.hidden || overall === 0 ? 0 : (g.value - overall) / overall;
      const bad = metric.worse === 'high' ? dev : -dev;
      return {
        ...g, y: i * ROW + 4, width: Math.max(2, Math.round((g.value / top) * BAR_W)), labelX: BAR_X - 8, valueX: BAR_X + Math.round((g.value / top) * BAR_W) + 6,
        tone: g.hidden || Math.abs(dev) < 0.1 ? '' : bad > 0 ? 'bad' : 'good',
      };
    }),
  }));

  // the strongest differences across every metric and dimension that is still free to compare
  const found: { score: number; text: string; bad: boolean }[] = [];
  for (const d of dims) {
    if (d.groups.length < 2) continue;
    for (const m of Object.keys(METRICS) as MetricKey[]) {
      const base = mean(rows, m);
      if (base === 0) continue;
      for (const g of d.groups.filter((x) => !x.hidden)) {
        const v = mean(rows.filter((c) => c[d.key] === g.key), m);
        const dev = (v - base) / base;
        if (Math.abs(dev) < 0.12) continue;
        const bad = METRICS[m].worse === 'high' ? dev > 0 : dev < 0;
        found.push({
          score: Math.abs(dev), bad,
          text: `${DIMENSIONS[d.key].label} ${g.key}: ${METRICS[m].label.toLowerCase()} ${round(v)}${METRICS[m].unit} against ${round(base)}${METRICS[m].unit} overall (${dev > 0 ? '+' : ''}${Math.round(dev * 100)}%, ${g.n} customers).`,
        });
      }
    }
  }
  const patterns = found.sort((a, b) => b.score - a.score).slice(0, 4);

  return { total: CUSTOMERS.length, n: rows.length, small, kpis, charts, patterns, metricLabel: metric.label, metricUnit: metric.unit, overall: small ? null : round(overall) };
}

/** Real numbers from the emotion notebook (emotion_v3_improved, CREMA-D test actors), not demo data. */
export const FAIRNESS = {
  source: 'Emotion model, CREMA-D test actors (1,066 clips, 13 actors). Few actors: differences of a few points can be noise.',
  bySex: [{ key: 'Female', value: 75.5 }, { key: 'Male', value: 78.3 }],
  byEmotion: [
    { key: 'anger', model: 92.9, humans: 51.6 }, { key: 'disgust', model: 65.9, humans: 28.3 }, { key: 'fear', model: 75.3, humans: 31.4 },
    { key: 'happy', model: 79.7, humans: 28.4 }, { key: 'neutral', model: 85.3, humans: 75.4 }, { key: 'sad', model: 61.5, humans: 24.9 },
  ],
};
