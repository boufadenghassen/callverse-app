import { Controller, Get, HttpCode, Post, Render, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { Roles } from '../auth/access.guard';

/** Where the Python emotion service (models/src/serve.py) listens. */
export const EMOTION_URL = () => process.env.CALLVERSE_EMOTION_URL ?? 'http://localhost:8001';

/** Nour uploads a call recording; the real fine-tuned WavLM model scores the emotion. */
@Controller()
export class CallReviewController {
  @Roles('QUALITY') @Get('call-review') @Render('call-review')
  page() {
    return {};
  }

  /** Answers JSON (not the HTML error pages) because the page's script calls it. */
  @Roles('QUALITY') @HttpCode(200) @Post('call-review/analyze')
  async analyze(@Req() req: Request, @Res() res: Response) {
    const fail = (status: number, error: string) => res.status(status).json({ error });
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) return fail(400, 'Choose an audio file first.');
    let upstream: globalThis.Response;
    try {
      upstream = await fetch(`${EMOTION_URL()}/emotion/analyze`, { method: 'POST', body: new Uint8Array(req.body), signal: AbortSignal.timeout(60_000) });
    } catch {
      return fail(503, 'The emotion service is not running. Start it (see models/README.md), then try again.');
    }
    const data = await upstream.json().catch(() => ({})) as { detail?: string };
    if (!upstream.ok) return fail(upstream.status === 400 ? 400 : 502, data.detail ?? 'The emotion service failed.');
    res.json(data);
  }
}
