import { Body, Controller, Get, HttpCode, NotFoundException, Param, Post, Query, Render, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AgentDownError, AgentGateway, NeedsRealAgentsError, RejectedError } from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import type { ComplaintAct } from '../agents/models';

const CUSTOMER_ID = /^[A-Z]{2}-\d{4}$/;
const CASE_ID = /^CMP-\d{1,6}$/;
const CALL_ID = /^CALL-\d+$/;
const ACTIONS: ComplaintAct['action'][] = ['take', 'escalate', 'severity', 'alert', 'resolve', 'close', 'reopen'];
const LEVELS = ['Critical', 'High', 'Medium', 'Low'];
const RESOLUTIONS = ['refunded', 'fixed', 'explained', 'goodwill', 'supervisor', 'no_action'];
const CHANNELS = ['call', 'email', 'chat', 'social', 'branch', 'app'];
/** The five customers of the demo file, for the "triage a complaint" form. */
const CUSTOMERS = [['YT-1042', 'Yasmine Toumi'], ['MS-0007', 'Mounir Sassi'], ['IK-2210', 'Ines Kacem'], ['WF-3391', 'Walid Ferjani'], ['SH-5520', 'Salma Hammami']].map(([id, name]) => ({ id, name }));
const SAMPLES = [
  { label: 'Charged twice, third time', customerId: 'YT-1042', text: 'I was charged twice for 180 dinars on my September bill and this is the third time I contact you about it. This is unacceptable, I will post this online and cancel my contract.' },
  { label: 'Legal threat', customerId: 'WF-3391', text: 'The cancellation fee of 350 dinars is a fraud, nobody explained it. I will contact a lawyer and the consumer protection association.' },
  { label: 'Slow internet', customerId: '', text: 'My internet has been slow for two weeks. The whole building has the same problem and nobody tells us when it will be fixed.' },
];
const clean = (v: unknown, max: number) => (typeof v === 'string' ? v.replace(/\p{Cc}/gu, ' ').trim().slice(0, max) : '');

/**
 * Amine's complaint workspace: open cases in severity lanes with their reasons, an early warning, a way to read a new complaint, the cases that start from bad calls,
 * what is waiting for the follow-up call, and where complaints come from. Reading a complaint answers JSON (the page's script calls it); every move on a case is a
 * form (POST with the CSRF token) that goes back to the page, and the signed-in user is the one who acted.
 */
@Controller()
export class ComplaintsController {
  constructor(private readonly agents: AgentGateway) {}

  @Roles('COMPLAINT') @Get('complaints') @Render('complaints')
  async page(@Query('error') error?: string) {
    const cases = await this.agents.openComplaints();
    const real = cases.some((c) => c.severityFactors);
    const [insights, followUps, candidates] = real
      ? await Promise.all([this.agents.complaintInsights().catch(() => null), this.agents.complaintFollowUps().catch(() => []), this.agents.complaintCandidates().catch(() => [])])
      : [null, [], []];
    const lanes: Record<string, typeof cases> = {};
    for (const severity of real ? LEVELS : LEVELS.slice(0, 3)) lanes[severity] = cases.filter((c) => c.severity === severity);
    const avgRisk = cases.length ? Math.round(cases.reduce((sum, c) => sum + c.escalationRisk, 0) / cases.length) : 0;
    const warnings = real ? cases.filter((c) => c.warning) : cases.filter((c) => c.escalationRisk >= 80);
    return {
      cases, lanes, critical: lanes.Critical.length, avgRisk, real, insights, followUps, candidates, warnings, overdue: cases.filter((c) => c.deadline?.overdue).length,
      customers: real ? CUSTOMERS : [], samples: real ? SAMPLES : [], error: clean(error, 200), weekMax: Math.max(1, ...(insights?.weeks ?? [1])),
    };
  }

  /** A complaint in words: the root cause, how serious, how likely to escalate, the deadline and the first actions, with the reasons. Nothing is saved. */
  @Roles('COMPLAINT') @HttpCode(200) @Post('complaints/triage')
  async triage(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const text = clean(b.text, 1500), id = typeof b.customerId === 'string' && b.customerId ? b.customerId : null;
    if (text.length < 10 || (id && !CUSTOMER_ID.test(id))) return res.status(400).json({ error: 'Write the complaint in at least a sentence.' });
    return this.json(res, () => this.agents.complaintTriage(text, id));
  }

  /** Open a case from the form. */
  @Roles('COMPLAINT') @Post('complaints/new')
  async create(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const text = clean(b.text, 1500), id = typeof b.customerId === 'string' && b.customerId ? b.customerId : null;
    const channel = typeof b.channel === 'string' && CHANNELS.includes(b.channel) ? b.channel : 'call';
    if (text.length < 10 || (id && !CUSTOMER_ID.test(id))) return res.redirect(`/complaints?error=${encodeURIComponent('Write the complaint in at least a sentence.')}`);
    return this.go(res, '/complaints', async () => `/complaints/${(await this.agents.complaintCreate(text, id, channel)).id}`);
  }

  /** Open a case from a call the quality analyst scored. */
  @Roles('COMPLAINT') @Post('complaints/from-call')
  async fromCall(@Body() b: Record<string, unknown>, @Res() res: Response) {
    if (typeof b.callId !== 'string' || !CALL_ID.test(b.callId)) return res.redirect(`/complaints?error=${encodeURIComponent('This call is not valid.')}`);
    const callId = b.callId;
    return this.go(res, '/complaints', async () => `/complaints/${(await this.agents.complaintFromCall(callId)).id}`);
  }

  @Roles('COMPLAINT') @Get('complaints/:id') @Render('complaint')
  async detail(@Param('id') id: string, @Query('error') error?: string) {
    if (!CASE_ID.test(id)) throw new NotFoundException();
    try {
      return { c: await this.agents.complaint(id), error: clean(error, 200), resolutions: RESOLUTIONS, levels: LEVELS };
    } catch (e) {
      if (e instanceof RejectedError || e instanceof NeedsRealAgentsError) throw new NotFoundException();
      throw e;
    }
  }

  /** A move on a case: take, escalate, set a level, alert a supervisor, resolve (with how), close after the follow-up (does the customer trust us again?) or reopen. */
  @Roles('COMPLAINT') @Post('complaints/:id/:action')
  async act(@Param('id') id: string, @Param('action') action: string, @Body() b: Record<string, unknown>, @Req() req: Request, @Res() res: Response) {
    if (!CASE_ID.test(id) || !(ACTIONS as string[]).includes(action)) throw new NotFoundException();
    const back = b.back === 'list' ? '/complaints' : `/complaints/${id}`;
    const resolution = clean(b.resolution, 20), level = clean(b.level, 10);
    const trusted = b.trusted === 'yes' ? true : b.trusted === 'no' ? false : undefined;
    if ((action === 'resolve' && !RESOLUTIONS.includes(resolution)) || (action === 'severity' && !LEVELS.includes(level)) || (action === 'close' && trusted === undefined)) {
      return res.redirect(`${back}${back.includes('?') ? '&' : '?'}error=${encodeURIComponent('Choose an answer for this step first.')}`);
    }
    const act: ComplaintAct = { action: action as ComplaintAct['action'], by: req.session.user?.name ?? 'agent', note: clean(b.note, 300), resolution: resolution || undefined, level: level || undefined, trusted };
    return this.go(res, back, async () => { await this.agents.complaintAct(id, act); return back; });
  }

  private async json(res: Response, work: () => Promise<object>) {
    try {
      return res.json(await work());
    } catch (e) {
      if (e instanceof RejectedError) return res.status(400).json({ error: e.message });
      if (e instanceof NeedsRealAgentsError) return res.status(503).json({ error: 'The complaint agent needs the real agents (AGENTS_MODE=http, see services/agents/README.md).' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The agents are not responding. Start them, then try again.' });
      throw e;
    }
  }

  /** Run a move and redirect to where it leads; a refusal comes back to the page with its message. */
  private async go(res: Response, failTo: string, work: () => Promise<string>) {
    try {
      return res.redirect(await work());
    } catch (e) {
      const sep = failTo.includes('?') ? '&' : '?';
      if (e instanceof RejectedError) return res.redirect(`${failTo}${sep}error=${encodeURIComponent(e.message.slice(0, 200))}`);
      if (e instanceof NeedsRealAgentsError) return res.redirect(`${failTo}${sep}error=${encodeURIComponent('This needs the real agents (AGENTS_MODE=http).')}`);
      throw e;
    }
  }
}
