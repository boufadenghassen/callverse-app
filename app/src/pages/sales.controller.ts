import { Body, Controller, Get, HttpCode, Post, Render, Res } from '@nestjs/common';
import type { Response } from 'express';
import { AgentDownError, AgentGateway, NeedsRealAgentsError, RejectedError } from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import type { SalesTurn } from '../agents/models';

const START = { calls: 1000, share: 30, minRelevance: 0, goodMomentOnly: false };   // what the simulation shows before anyone changes it

const CUSTOMER_ID = /^[A-Z]{2}-\d{4}$/;
const initials = (name: string) => { const [a, b = ''] = name.split(' '); return a.charAt(0) + b.charAt(0); };

/** Conversations to try the detector on: the customer's words are what the agent reads. */
const SAMPLES = [
  { label: 'Going abroad', customerId: 'YT-1042', text: "C: Hello, I'm travelling to Paris next week for work.\nA: Of course, how can I help?\nC: Last time my data ran out abroad and it cost me a lot." },
  { label: 'Thinking of leaving', customerId: 'SH-5520', text: "C: This is the third time I call, I am furious. I want to cancel, my bill is too expensive.\nA: I am sorry, let me look at your account.\nC: My internet has been slow for weeks." },
  { label: 'Family and data', customerId: 'MS-0007', text: "C: I run out of data every month. My wife also needs a line, can we add her?\nA: Let me check your plan.\nC: Thanks, that helps." },
];

/**
 * Leila's sales workspace: the best offer for each customer with the reasons in points, a conversation to read, and which offers convert.
 * The conversation and the outcome answer JSON, because the page's script calls them.
 */
@Controller()
export class SalesController {
  constructor(private readonly agents: AgentGateway) {}

  @Roles('SALES') @Get('sales') @Render('sales')
  async page() {
    const [found, analytics] = await Promise.all([this.agents.opportunities(), this.agents.salesAnalytics()]);
    const opportunities = found.map((o) => ({ ...o, initials: initials(o.customer) }));
    const real = opportunities.some((o) => o.factors);
    const customers = real ? opportunities.filter((o) => o.customerId).map((o) => ({ id: o.customerId!, name: o.customer })) : [];
    const simulation = real ? await this.agents.salesSimulate(START).catch(() => null) : null;
    return { opportunities, analytics, real, customers, samples: real ? SAMPLES : [], simulation };
  }

  /** A conversation as turns ({speaker, text}): the needs the customer voiced and the offers that answer them. */
  @Roles('SALES') @HttpCode(200) @Post('sales/detect')
  async detect(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const turns = Array.isArray(b.turns) ? b.turns : [];
    const clean: SalesTurn[] = [];
    for (const t of turns.slice(0, 60)) {
      const x = t as Record<string, unknown>;
      const text = typeof x.text === 'string' ? x.text.replace(/\p{Cc}/gu, ' ').trim().slice(0, 600) : '';
      if ((x.speaker === 'customer' || x.speaker === 'advisor') && text) clean.push({ speaker: x.speaker, text });
    }
    const id = typeof b.customerId === 'string' && b.customerId ? b.customerId : null;
    if (!clean.length || (id && !CUSTOMER_ID.test(id))) return res.status(400).json({ error: 'Type or choose a conversation first.' });
    return this.run(res, () => this.agents.salesDetect(id, clean));
  }

  /** The customer accepted or declined an offer: it feeds the ranking and the analytics. */
  @Roles('SALES') @HttpCode(200) @Post('sales/outcome')
  async outcome(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const id = typeof b.customerId === 'string' && b.customerId ? b.customerId : null;
    const ok = typeof b.offerId === 'string' && /^[a-z][a-z-]{2,30}$/.test(b.offerId) && (b.outcome === 'accepted' || b.outcome === 'declined')
      && Number.isInteger(b.relevance) && (b.relevance as number) >= 0 && (b.relevance as number) <= 100 && (b.cue === 'now' || b.cue === 'after_resolution')
      && typeof b.need === 'string' && /^[a-z_]{0,30}$/.test(b.need) && (!id || CUSTOMER_ID.test(id));
    if (!ok) return res.status(400).json({ error: 'This outcome is not valid.' });
    return this.run(res, async () => {
      await this.agents.salesOutcome({ customerId: id, offerId: b.offerId as string, outcome: b.outcome as 'accepted' | 'declined', relevance: b.relevance as number, cue: b.cue as string, need: b.need as string });
      return { recorded: true };
    });
  }

  /** A selling rule replayed on the history of offers: what a month of calls would earn under it. */
  @Roles('SALES') @HttpCode(200) @Post('sales/simulate')
  async simulate(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const int = (v: unknown, lo: number, hi: number) => (typeof v === 'number' && Number.isInteger(v) && v >= lo && v <= hi ? v : null);
    const calls = int(b.calls, 1, 100000), share = int(b.share, 1, 100), minRelevance = int(b.minRelevance, 0, 100);
    if (calls === null || share === null || minRelevance === null || typeof b.goodMomentOnly !== 'boolean') return res.status(400).json({ error: 'These values are not valid.' });
    return this.run(res, () => this.agents.salesSimulate({ calls, share, minRelevance, goodMomentOnly: b.goodMomentOnly as boolean }));
  }

  private async run(res: Response, work: () => Promise<object>) {
    try {
      return res.json(await work());
    } catch (e) {
      if (e instanceof RejectedError) return res.status(400).json({ error: e.message });
      if (e instanceof NeedsRealAgentsError) return res.status(503).json({ error: 'The sales agent needs the real agents (AGENTS_MODE=http, see services/agents/README.md).' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The agents are not responding. Start them, then try again.' });
      throw e;
    }
  }
}
