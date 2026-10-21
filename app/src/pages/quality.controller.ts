import { Controller, Get, HttpCode, Post, Query, Render, Req, Res, Body } from '@nestjs/common';
import type { Request, Response } from 'express';
import {
  AgentDownError, AgentGateway, BadAudioError, NeedsRealAgentsError, RejectedError, UnknownCallError, VoiceUnavailableError,
} from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import { qualityView, sparkline } from './charts';

const SHOWN = 6;                                   // reviews on the page; the advisor filter and ?call= reach the others
const CALL_ID = /^CALL-\d{4,6}$/;

/** The name an advisor's calls are filed under: Karim is Karim B., anybody else just their name. */
const advisorName = (user?: string) => (user === 'karim' ? 'Karim B.' : user ? user[0].toUpperCase() + user.slice(1) : 'Unknown advisor');

/**
 * Nour's quality workspace: the reviews, the team analytics, a recording to review, and the advisor console's "send to quality review".
 * The upload and the review of a live call answer JSON, because the page's script calls them.
 */
@Controller()
export class QualityController {
  constructor(private readonly agents: AgentGateway) {}

  @Roles('QUALITY') @Get('quality') @Render('quality')
  async page(@Query('call') call?: string, @Query('advisor') advisor?: string) {
    const focus = typeof call === 'string' && CALL_ID.test(call) ? call : '';
    const who = typeof advisor === 'string' ? advisor.replace(/\p{Cc}/gu, ' ').trim().slice(0, 60) : '';
    const [recent, analytics] = await Promise.all([this.agents.recentReviews(who || undefined), this.agents.qualityAnalytics()]);
    let reviews = recent;
    if (focus) {
      const one = recent.find((r) => r.callId === focus) ?? await this.agents.qualityReview(focus);
      if (one) reviews = [one, ...recent.filter((r) => r.callId !== focus)];
    }
    const advisors = analytics.advisors.map((a) => ({
      ...a, lines: sparkline(a.weeks), bars: Math.round(a.avgOverall), trendWord: a.trend === null ? 'not enough weeks' : a.trend > 0 ? `up ${a.trend}` : a.trend < 0 ? `down ${-a.trend}` : 'flat',
    }));
    const team = analytics.team && { ...analytics.team, lines: sparkline(analytics.team.weeks, 240, 56) };
    return { reviews: reviews.slice(0, SHOWN + (focus ? 1 : 0)).map(qualityView), total: reviews.length, analytics: { ...analytics, team, advisors }, focus, filter: who, names: analytics.advisors.map((a) => a.advisor) };
  }

  /** A two-channel recording (advisor left, customer right) as the raw request body. */
  @Roles('QUALITY') @HttpCode(200) @Post('quality/audio')
  async audio(@Req() req: Request, @Query('advisor') advisor: string | undefined, @Res() res: Response) {
    if (!Buffer.isBuffer(req.body) || req.body.length < 100) return res.status(400).json({ error: 'Choose a recording first.' });
    const who = typeof advisor === 'string' && advisor.trim() ? advisor.replace(/\p{Cc}/gu, ' ').trim().slice(0, 60) : 'Unknown advisor';
    return this.run(res, async () => { const r = await this.agents.reviewAudio(req.body, who); return { callId: r.callId, overall: r.overall }; });
  }

  @Roles('QUALITY') @Get('quality/sample-call.wav')
  async sample(@Res() res: Response) {
    try {
      return res.type('audio/wav').set('Content-Disposition', 'attachment; filename="sample-call.wav"').send(await this.agents.sampleCall());
    } catch (e) {
      if (e instanceof NeedsRealAgentsError || e instanceof VoiceUnavailableError) return res.status(503).type('text').send('The sample call needs the real agents and the neural voice.');
      if (e instanceof AgentDownError) return res.status(503).type('text').send('The agents are not responding.');
      throw e;
    }
  }

  /** Karim sends the call he just had to the quality queue. */
  @Roles('ADVISOR') @HttpCode(200) @Post('advisor/live/review')
  async reviewLiveCall(@Body() b: Record<string, unknown>, @Req() req: Request, @Res() res: Response) {
    if (typeof b.id !== 'string' || !/^[0-9a-f]{16}$/.test(b.id)) return res.status(400).json({ error: 'This call is not valid. Start a new one.' });
    return this.run(res, async () => { const r = await this.agents.reviewCall(b.id as string, advisorName(req.session.user?.name)); return { callId: r.callId, overall: r.overall }; });
  }

  private async run(res: Response, work: () => Promise<object>) {
    try {
      return res.json(await work());
    } catch (e) {
      if (e instanceof BadAudioError || e instanceof RejectedError) return res.status(400).json({ error: e.message });
      if (e instanceof UnknownCallError) return res.status(404).json({ error: 'This call was lost (the agents restarted). Start a new one.' });
      if (e instanceof NeedsRealAgentsError) return res.status(503).json({ error: 'Reviewing needs the real agents (AGENTS_MODE=http, see services/agents/README.md).' });
      if (e instanceof VoiceUnavailableError) return res.status(503).json({ error: 'Reviewing a recording needs the speech-to-text model (see services/agents/README.md).' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The agents are not responding. Start them, then try again.' });
      throw e;
    }
  }
}
