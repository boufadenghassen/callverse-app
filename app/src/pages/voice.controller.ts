import { Body, Controller, HttpCode, Post, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AgentDownError, AgentGateway, BadAudioError, VoiceUnavailableError } from '../agents/agent.gateway';
import { EMOTION_URL } from './call-review.controller';
import { PERSONAS } from './client-simulator';
import type { Tone } from '../agents/models';

/**
 * Text to speech for every agent answer. Any signed-in user may ask (the AccessGuard still demands the CSRF token).
 * Answers JSON errors, and 503 when there is no neural voice, so the page's script falls back to the browser's voice.
 */
/** How the voice sounded, from the emotion model; null when the service is not running or cannot read the recording (the words still count). */
async function toneOf(audio: Buffer): Promise<Tone | null> {
  try {
    const res = await fetch(`${EMOTION_URL()}/emotion/analyze`, { method: 'POST', body: new Uint8Array(audio), signal: AbortSignal.timeout(20_000) });
    if (!res.ok) return null;
    const d = (await res.json()) as { emotion?: unknown; mood?: unknown };
    return typeof d.emotion === 'string' && typeof d.mood === 'number' ? { emotion: d.emotion, mood: Math.round(d.mood) } : null;
  } catch {
    return null;
  }
}

@Controller('voice')
export class VoiceController {
  constructor(private readonly agents: AgentGateway) {}

  @HttpCode(200) @Post('speak')
  async speak(@Body() b: Record<string, unknown>, @Res() res: Response) {
    const text = typeof b.text === 'string' ? b.text.replace(/\p{Cc}/gu, ' ').trim() : '';
    const persona = typeof b.persona === 'string' && Object.prototype.hasOwnProperty.call(PERSONAS, b.persona) ? b.persona : null;
    const mood = typeof b.mood === 'number' && Number.isInteger(b.mood) && b.mood >= 0 && b.mood <= 100 ? b.mood : 50;
    if (text.length < 1 || text.length > 400 || (b.role !== 'advisor' && b.role !== 'customer')) return res.status(400).json({ error: 'Nothing to read out.' });
    try {
      const audio = await this.agents.speak({ text, role: b.role, persona, mood });
      return res.type('audio/wav').set('Cache-Control', 'private, max-age=3600').send(audio);
    } catch (e) {
      if (e instanceof VoiceUnavailableError) return res.status(503).json({ error: 'No neural voice available.' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The voice service is not responding.' });
      throw e;
    }
  }

  /** A voice note from the microphone (a 16 kHz mono WAV made by the page) as text. */
  @HttpCode(200) @Post('transcribe')
  async transcribe(@Req() req: Request, @Res() res: Response) {
    if (!Buffer.isBuffer(req.body) || req.body.length < 100) return res.status(400).json({ error: 'There is no recording to read.' });
    try {
      const [transcript, tone] = await Promise.all([this.agents.transcribe(req.body), toneOf(req.body)]);
      return res.json({ ...transcript, tone });
    } catch (e) {
      if (e instanceof BadAudioError) return res.status(400).json({ error: e.message });
      if (e instanceof VoiceUnavailableError) return res.status(503).json({ error: 'Voice notes need the speech-to-text model (see services/agents/README.md). You can type instead.' });
      if (e instanceof AgentDownError) return res.status(503).json({ error: 'The voice service is not responding. You can type instead.' });
      throw e;
    }
  }
}
