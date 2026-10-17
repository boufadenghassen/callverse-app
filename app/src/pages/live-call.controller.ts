import { Body, Controller, HttpCode, Post, Res } from '@nestjs/common';
import type { Response } from 'express';
import { AgentDownError, AgentGateway, UnknownCallError } from '../agents/agent.gateway';
import { Roles } from '../auth/access.guard';
import { DIFFICULTIES, INTENTS, PERSONAS } from './client-simulator';

const CUSTOMER_ID = 'YT-1042'; // the demo customer the advisor console shows

const oneOf = <T extends object>(table: T, v: unknown): keyof T | undefined =>
  typeof v === 'string' && Object.prototype.hasOwnProperty.call(table, v) ? (v as keyof T) : undefined;

/**
 * Karim's live call: the advisor talks to the simulated customer agent and the advisor agent suggests the next answer
 * from what the customer just said. Answers JSON (not the HTML error pages) because the console's script calls it.
 */
@Controller('advisor/live')
export class LiveCallController {
  constructor(private readonly agents: AgentGateway) {}

  @Roles('ADVISOR') @HttpCode(200) @Post('start')
  async start(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const persona = oneOf(PERSONAS, b.persona), difficulty = oneOf(DIFFICULTIES, b.difficulty), intent = oneOf(INTENTS, b.intent);
    const mix = b.mix ? oneOf(PERSONAS, b.mix) : null;
    if (!persona || !difficulty || !intent || (b.mix && !mix)) return res.status(400).json({ error: 'Choose a customer, a difficulty and a reason for the call.' });
    return this.run(res, async () => {
      const call = await this.agents.startCall({ persona, mix: mix ?? null, difficulty, intent, memory: b.memory === true });
      return { ...call, suggestion: await this.agents.suggestAnswer(CUSTOMER_ID, call.opening) };
    });
  }

  @Roles('ADVISOR') @HttpCode(200) @Post('say')
  async say(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const text = typeof b.text === 'string' ? b.text.replace(/\p{Cc}/gu, ' ').trim() : '';
    if (typeof b.id !== 'string' || !/^[0-9a-f]{16}$/.test(b.id)) return res.status(400).json({ error: 'This call is not valid. Start a new one.' });
    if (text.length < 1 || text.length > 300) return res.status(400).json({ error: 'Write a reply of 1 to 300 characters.' });
    return this.run(res, async () => {
      const reply = await this.agents.say(b.id as string, text);
      // the advisor agent reads what the customer just said, unless the call is over
      return { ...reply, suggestion: reply.client ? await this.agents.suggestAnswer(CUSTOMER_ID, reply.client) : null };
    });
  }

  private async run(res: Response, work: () => Promise<object>) {
    try {
      return res.json(await work());
    } catch (e) {
      if (e instanceof UnknownCallError) return res.status(404).json({ error: 'This call was lost (the agents restarted). Start a new one.' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The agents are not responding. Start them (see app/README.md), then try again.' });
      throw e;
    }
  }
}
