import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { NestExpressApplication } from '@nestjs/platform-express';
import { client, startApp } from './helpers';
import { buildInsights, DIMENSIONS, METRICS, MetricKey, MIN_GROUP } from '../src/pages/insights';

const none = { age: '', sex: '', region: '', metric: 'churn' as MetricKey };

describe('insights statistics', () => {
  test('the same filters always give the same numbers', () => {
    assert.deepEqual(buildInsights(none), buildInsights(none));
    assert.equal(buildInsights(none).n, 720);
  });

  test('no group smaller than the minimum is ever shown, whatever the filters', () => {
    const ages = ['', ...DIMENSIONS.age.values], sexes = ['', ...DIMENSIONS.sex.values], regions = ['', ...DIMENSIONS.region.values];
    let tiny = 0;
    for (const age of ages) for (const sex of sexes) for (const region of regions) for (const metric of Object.keys(METRICS) as MetricKey[]) {
      const r = buildInsights({ age, sex, region, metric });
      if (r.small) { tiny++; assert.equal(r.charts.length > 0 && r.kpis.every((k) => k.value === null), true); continue; }
      for (const c of r.charts) for (const row of c.rows) {
        if (row.n < MIN_GROUP) assert.ok(row.hidden && row.value === 0, `${age}/${sex}/${region} shows a group of ${row.n}`);
      }
    }
    assert.ok(tiny > 0, 'some filter combinations should be too small to show');
  });

  test('the built-in pattern is found: young clients churn more than average', () => {
    const young = buildInsights(none).patterns.find((p) => p.text.includes('Age 18-25') && p.text.includes('churn risk'));
    assert.ok(young?.bad, 'expected a "worse" pattern for ages 18-25');
  });

  test('a filtered dimension has nothing to compare, so it gets no pattern about itself', () => {
    const r = buildInsights({ ...none, sex: 'Female' });
    assert.ok(r.patterns.every((p) => !p.text.startsWith('Sex ')));
  });
});

describe('insights page', () => {
  let app: NestExpressApplication;
  before(async () => { app = await startApp(); });
  after(async () => { await app.close(); });

  test('every signed-in user can open it, and it is in the sidebar', async () => {
    const html = (await (await client(app, 'karim')).get('/insights').expect(200)).text;
    assert.match(html, /Customer insights/);
    assert.match(html, /href="\/insights"/);
    assert.match(html, /Privacy/);
    assert.match(html, /Accuracy by sex/);
  });

  test('anonymous users are sent to login', async () => {
    await (await client(app)).get('/insights').expect(302);
  });

  test('filters narrow the customers and bad values are rejected', async () => {
    const karim = await client(app, 'karim');
    const html = (await karim.get('/insights').query({ age: '18-25', metric: 'wait' })).text;
    assert.match(html, /Average wait by region/);
    await karim.get('/insights').query({ age: 'senior' }).expect(400);
    await karim.get('/insights').query({ metric: 'salary' }).expect(400);
  });

  test('a filter that leaves too few customers shows a notice instead of numbers', async () => {
    const html = (await (await client(app, 'karim')).get('/insights').query({ age: '51+', sex: 'Female', region: 'Nabeul' })).text;
    assert.match(html, /Fewer than 10 customers/);
  });
});
