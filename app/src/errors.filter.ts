import { ArgumentsHost, Catch, ExceptionFilter, HttpException, Logger, NotFoundException, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AgentDownError } from './agents/agent.gateway';

const ERRORS: Record<number, { title: string; message: string }> = {
  400: { title: "That request didn't look right", message: 'Some of the values in the request were not valid. Go back and check them.' },
  403: { title: 'This workspace is for another role', message: 'Your account does not include this page. The home page shows the workspaces you can open.' },
  404: { title: "We can't find that page", message: 'The address may be mistyped, or the page may have moved.' },
  500: { title: 'Something went wrong on our side', message: 'It is not you. Try again in a moment; if it keeps happening, tell the team.' },
  503: { title: "An agent isn't responding", message: 'An agent service is not responding. Try again in a moment.' },
};

/** Turns failures into friendly pages. Details go to the log, never to the browser. */
@Catch()
export class ErrorFilter implements ExceptionFilter {
  private readonly log = new Logger('Errors');

  catch(e: unknown, host: ArgumentsHost) {
    const http = host.switchToHttp();
    const req = http.getRequest<Request>(), res = http.getResponse<Response>();
    if (res.headersSent) return;
    if (e instanceof UnauthorizedException || (e instanceof NotFoundException && !req.session?.user)) return res.redirect('/login');

    let status = 500, message = '';
    if (e instanceof AgentDownError) {
      this.log.warn(`Agent call failed: ${e.message}`);
      status = 503;
      message = '';
    } else if (e instanceof HttpException) {
      status = e.getStatus();
    } else {
      this.log.error(e);
    }
    const page = ERRORS[status] ?? ERRORS[500];
    res.status(status).render('error', { status, heading: page.title, message: message || page.message, retry: status >= 500, signedIn: !!req.session?.user });
  }
}
