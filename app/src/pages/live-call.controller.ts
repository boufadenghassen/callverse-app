import { Body, Controller, HttpCode, Post, Res } from '@nestjs/common';
import type { Response } from 'express';
import { AgentDownError, AgentGateway, NeedsRealAgentsError, RejectedError, UnknownCallError } from '../agents/agent.gateway';
import type { Tone } from '../agents/models';
import { Roles } from '../auth/access.guard';
import { DIFFICULTIES, INTENTS, PERSONAS } from './client-simulator';
import { cleanTurns } from './sales.controller';

const CUSTOMER_ID = 'YT-1042'; // the demo customer the advisor console shows

const EMOTIONS = ['anger', 'disgust', 'fear', 'happy', 'neutral', 'sad'];
/** A tone from the page (the emotion model's reading of a voice note), or null when it is missing or not valid. */
const toneOf = (v: unknown): Tone | null => {
  const t = v as Record<string, unknown> | null;
  return t && typeof t.emotion === 'string' && EMOTIONS.includes(t.emotion) && typeof t.mood === 'number' && Number.isInteger(t.mood) && t.mood >= 0 && t.mood <= 100
    ? { emotion: t.emotion, mood: t.mood } : null;
};

const oneOf = <T extends object>(table: T, v: unknown): keyof T | undefined =>
  typeof v === 'string' && Object.prototype.hasOwnProperty.call(table, v) ? (v as keyof T) : undefined;

/**
 * Karim's live call: the advisor talks to the simulated customer agent and the advisor agent suggests the next answer
 * from what the customer just said. Answers JSON (not the HTML error pages) because the console's script calls it.
 */
@Controller('advisor/live')
export class LiveCallController {
  constructor(private readonly agents: AgentGateway) {}

  @Roles('ADVISOR', 'TRAINER') @HttpCode(200) @Post('start')
  async start(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const persona = oneOf(PERSONAS, b.persona), difficulty = oneOf(DIFFICULTIES, b.difficulty), intent = oneOf(INTENTS, b.intent);
    const mix = b.mix ? oneOf(PERSONAS, b.mix) : null;
    if (!persona || !difficulty || !intent || (b.mix && !mix)) return res.status(400).json({ error: 'Choose a customer, a difficulty and a reason for the call.' });
    return this.run(res, async () => {
      const call = await this.agents.startCall({ persona, mix: mix ?? null, difficulty, intent, memory: b.memory === true });
      return { ...call, suggestion: await this.agents.suggestAnswer(CUSTOMER_ID, call.opening) };
    });
  }

  @Roles('ADVISOR', 'TRAINER') @HttpCode(200) @Post('say')
  async say(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const text = typeof b.text === 'string' ? b.text.replace(/\p{Cc}/gu, ' ').trim() : '';
    if (typeof b.id !== 'string' || !/^[0-9a-f]{16}$/.test(b.id)) return res.status(400).json({ error: 'This call is not valid. Start a new one.' });
    if (text.length < 1 || text.length > 300) return res.status(400).json({ error: 'Write a reply of 1 to 300 characters.' });
    // what the call is about (the customer's opening line) keeps the suggestion on topic when her reply is short
    const topic = typeof b.topic === 'string' ? b.topic.replace(/\p{Cc}/gu, ' ').trim().slice(0, 200) : '';
    return this.run(res, async () => {
      const reply = await this.agents.say(b.id as string, text, toneOf(b.tone));
      // the advisor agent reads what the customer just said, unless the call is over
      return { ...reply, suggestion: reply.client ? await this.agents.suggestAnswer(CUSTOMER_ID, `${topic} ${reply.client}`.trim()) : null };
    });
  }

  /** The offers worth keeping in mind, read from the conversation so far (the console asks after each customer message). */
  @Roles('ADVISOR', 'TRAINER') @HttpCode(200) @Post('offers')
  async offers(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const turns = cleanTurns(b.turns);
    if (!turns.length) return res.status(400).json({ error: 'There is no conversation yet.' });
    return this.run(res, async () => {
      const detection = await this.agents.salesDetect(CUSTOMER_ID, turns);
      return { ...detection, offers: detection.offers.slice(0, 2) };
    });
  }

  /** The advisor agent's own reply at this point of the call, for the automatic call (the page sends it like a typed reply). */
  @Roles('ADVISOR', 'TRAINER') @HttpCode(200) @Post('auto')
  async auto(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const topic = typeof b.topic === 'string' ? b.topic.replace(/\p{Cc}/gu, ' ').trim().slice(0, 300) : '';
    const turn = typeof b.turn === 'number' && Number.isInteger(b.turn) ? b.turn : -1;
    const style = b.style === undefined ? 'careful' : b.style;
    if (topic.length < 3 || turn < 0 || turn > 10 || (style !== 'careful' && style !== 'rushed')) return res.status(400).json({ error: 'The call is not valid. Start a new one.' });
    return this.run(res, () => this.agents.autoReply(topic, turn, style));
  }

  private async run(res: Response, work: () => Promise<object>) {
    try {
      return res.json(await work());
    } catch (e) {
      if (e instanceof UnknownCallError) return res.status(404).json({ error: 'This call was lost (the agents restarted). Start a new one.' });
      if (e instanceof RejectedError) return res.status(400).json({ error: e.message });
      if (e instanceof NeedsRealAgentsError) return res.status(503).json({ error: 'Offers need the real agents (AGENTS_MODE=http).' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The agents are not responding. Start them (see app/README.md), then try again.' });
      throw e;
    }
  }
}
