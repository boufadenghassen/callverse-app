import { BadRequestException, Body, Controller, Get, HttpCode, NotFoundException, Param, Post, Query, Render, Res } from '@nestjs/common';
import type { Response } from 'express';
import { AgentGateway } from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import { lineChart } from './charts';
import { DIFFICULTIES, INTENTS, PERSONAS } from './client-simulator';

const CHART_W = 640, CHART_H = 280;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const QA_ADVISORS = ['Karim B.', 'Hela M.', 'Sami R.', 'Rania K.', 'Mehdi T.', 'Ines F.'];

/**
 * Server-rendered pages, one per persona. Controllers stay thin: validate input, ask the gateway,
 * hand data to the template. Access rules live in the @Roles decorators and AccessGuard.
 */
@Controller()
export class PagesController {
  constructor(private readonly agents: AgentGateway) {}

  @Get() @Render('home')
  async home() {
    // A live number is a nicety: if its agent is down the home page must still load.
    const live: Record<string, string> = {};
    const numbers: Record<string, () => Promise<string>> = {
      advisor: async () => `${(await this.agents.customerContext('YT-1042')).openTickets} open ticket`,
      workforce: async () => `peak ${Math.max(0, ...(await this.agents.forecast('B')).map((f) => f.forecast))} calls/h`,
      quality: async () => `${Math.min(...(await this.agents.recentReviews()).map((r) => r.overall))} lowest score`,
      complaints: async () => `${(await this.agents.openComplaints()).filter((c) => c.escalationRisk >= 80).length} need a supervisor`,
      training: async () => `${(await this.agents.scenarios()).length} scenarios ready`,
      sales: async () => `${(await this.agents.opportunities()).length} open offers`,
    };
    await Promise.all(Object.entries(numbers).map(async ([key, fn]) => { try { live[key] = await fn(); } catch { /* leave it out */ } }));
    return { live };
  }

  // ---- Karim: advisor console ----------------------------------------------------------------

  @Roles('ADVISOR') @Get('advisor') @Render('advisor')
  async advisor(@Query('customer') customerParam?: string, @Query('q') qParam?: string) {
    const customerId = customerParam || 'YT-1042', raw = qParam || 'double charge on monthly bill';
    if (typeof customerId !== 'string' || !/^[A-Z]{2}-\d{4}$/.test(customerId)) throw new BadRequestException('Invalid customer id');
    if (typeof raw !== 'string' || raw.length < 3 || raw.length > 200) throw new BadRequestException('Search must be 3 to 200 characters');
    const query = raw.replace(/\p{Cc}/gu, ' ').trim();
    const [customer, answer] = await Promise.all([this.agents.customerContext(customerId), this.agents.suggestAnswer(customerId, query)]);
    return { customer, query, answer, personas: PERSONAS, difficulties: DIFFICULTIES, intents: INTENTS };
  }

  // ---- Sana: workforce twin ------------------------------------------------------------------

  @Roles('WORKFORCE') @Get('workforce') @Render('workforce')
  workforce() {
    return this.workforcePage('B', { queue: 'B', extraAdvisors: '2', from: '14:00', to: '16:00' });
  }

  @Roles('WORKFORCE') @Post('workforce/simulate') @HttpCode(200) @Render('workforce')
  async simulate(@Body() body: Record<string, unknown>) {
    const str = (v: unknown) => (typeof v === 'string' ? v.trim() : '');
    const form = { queue: str(body.queue), extraAdvisors: str(body.extraAdvisors), from: str(body.from), to: str(body.to) };
    const errors: Record<string, string> = {};
    if (!/^[A-E]$/.test(form.queue)) errors.queue = 'Queue must be A to E';
    const n = Number(form.extraAdvisors);
    if (!/^-?\d+$/.test(form.extraAdvisors)) errors.extraAdvisors = 'Enter a whole number';
    else if (n < -5) errors.extraAdvisors = 'At least -5';
    else if (n > 10) errors.extraAdvisors = 'At most 10';
    if (!HHMM.test(form.from)) errors.from = 'Use HH:mm';
    if (!HHMM.test(form.to)) errors.to = 'Use HH:mm';
    if (!errors.from && !errors.to && form.from >= form.to) errors.to = 'End time must be after start time';

    const result = Object.keys(errors).length ? null : await this.agents.simulate({ ...form, extraAdvisors: n });
    return this.workforcePage(errors.queue ? 'B' : form.queue, form, errors, result);
  }

  private async workforcePage(queue: string, form: object, errors: Record<string, string> = {}, result: object | null = null) {
    const hours = await this.agents.forecast(queue);
    return { queue, form, errors, result, hours, chart: lineChart(hours, CHART_W, CHART_H), plan: await this.agents.routing(), schedule: await this.agents.schedule() };
  }

  // ---- Nour, Amine, Rim, Leila ---------------------------------------------------------------

  @Roles('COMPLAINT') @Get('complaints') @Render('complaints')
  async complaints() {
    const cases = await this.agents.openComplaints();
    const lanes: Record<string, typeof cases> = {};
    for (const severity of ['Critical', 'High', 'Medium']) lanes[severity] = cases.filter((c) => c.severity === severity);
    const avgRisk = cases.length ? Math.round(cases.reduce((sum, c) => sum + c.escalationRisk, 0) / cases.length) : 0;
    return { cases, lanes, critical: lanes.Critical.length, avgRisk };
  }

  @Roles('TRAINER') @Get('training') @Render('training')
  async training(@Query('advisor') advisorParam?: string, @Query('replay') replayId?: string) {
    const advisor = typeof advisorParam === 'string' && advisorParam.trim() ? advisorParam.trim().slice(0, 60) : 'Karim B.';
    const [analytics, opportunities] = await Promise.all([this.agents.qualityAnalytics(), this.agents.opportunities()]);
    const report = analytics.advisors.find((item) => item.advisor === advisor) ?? null;
    const selectedAdvisor = advisor;
    const weaknesses = report
      ? Object.entries(report.avgByCriterion).map(([criterion, score]) => ({ criterion, score: score * 10 }))
      : [];
    const [plan, reviews] = await Promise.all([
      weaknesses.length
        ? this.agents.trainingPlan(selectedAdvisor, weaknesses)
        : Promise.resolve({ advisor_id: selectedAdvisor, needs_training: false, focus: [], scenarios: [], rationale: ['No Quality Analyst weaknesses are available for this advisor yet.'] }),
      this.agents.recentReviews({ advisor: selectedAdvisor }),
    ]);
    const scenarios = await this.agents.scenarios();
    const advisorNames = analytics.advisors.length ? analytics.advisors.map((item) => item.advisor) : QA_ADVISORS;
    // Replaying only reads (the same seed gives the same scenario); anything that creates a scenario is a POST below.
    let action: Awaited<ReturnType<AgentGateway['replayScenario']>> | null = null;
    if (typeof replayId === 'string' && replayId) {
      try { action = await this.agents.replayScenario(replayId.slice(0, 80)); } catch { throw new NotFoundException('Scenario not found'); }
    }
    // Offers are the team's best of the day (they belong to customers, not to this advisor), so the same list is shown for every advisor.
    // (nunjucks' `slice(n)` splits a list into n columns, so the first items are taken here)
    return { scenarios, history: scenarios.slice(0, 12), advisor: selectedAdvisor, report, reviews: reviews.slice(0, 3), opportunities: opportunities.slice(0, 3), plan, advisorNames, action };
  }

  @Roles('TRAINER') @Get('training/scenarios/:id') @Render('training-scenario')
  async trainingScenario(@Param('id') id: string, @Query('advisor') advisor?: string) {
    let scenario: Awaited<ReturnType<AgentGateway['scenario']>>;
    try {
      scenario = await this.agents.scenario(id);
    } catch {
      throw new NotFoundException('Scenario not found');
    }
    const lineage = await this.agents.scenarioLineage(id);
    return { scenario, lineage, advisor: typeof advisor === 'string' ? advisor : 'Karim B.' };
  }

  /** The scenario builder: a new scenario from the generator, then its detail page. */
  @Roles('TRAINER') @Post('training/generate')
  async generateTrainingScenario(@Body() body: Record<string, unknown>, @Res() res: Response) {
    const levels: Record<string, number | null> = { '': null, Easy: 2, Medium: 3, Hard: 4 };
    const choice = body.difficulty === undefined ? '' : body.difficulty;
    if (typeof choice !== 'string' || !Object.hasOwn(levels, choice)) throw new BadRequestException();
    const advisor = typeof body.advisor === 'string' && body.advisor.trim() ? `?advisor=${encodeURIComponent(body.advisor.trim().slice(0, 60))}` : '';
    const scenario = await this.agents.generateScenario(levels[choice]);
    return res.redirect(`/training/scenarios/${encodeURIComponent(scenario.id)}${advisor}`);
  }

  @Roles('TRAINER') @Post('training/scenarios/:id/mutate')
  async mutateTrainingScenario(@Param('id') id: string, @Body() body: Record<string, unknown>, @Query('advisor') advisor: string | undefined, @Res() res: Response) {
    const operation = body.op === 'easier' ? 'easier' : 'harder';
    const scenario = await this.agents.mutateScenario(id, operation);
    const suffix = typeof advisor === 'string' ? `?advisor=${encodeURIComponent(advisor)}` : '';
    return res.redirect(`/training/scenarios/${encodeURIComponent(scenario.id)}${suffix}`);
  }

  @Roles('TRAINER') @Post('training/scenarios/:id/delete')
  async deleteTrainingScenario(@Param('id') id: string, @Res() res: Response) {
    await this.agents.deleteScenario(id);
    return res.redirect('/training');
  }
}
