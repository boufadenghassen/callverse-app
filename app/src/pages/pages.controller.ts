import { BadRequestException, Body, Controller, Get, HttpCode, Post, Query, Render } from '@nestjs/common';
import { AgentGateway } from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import { lineChart } from './charts';
import { DIFFICULTIES, INTENTS, PERSONAS } from './client-simulator';

const CHART_W = 640, CHART_H = 280;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

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
  async training() {
    return { scenarios: await this.agents.scenarios() };
  }
}
