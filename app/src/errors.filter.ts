import { ArgumentsHost, Catch, ExceptionFilter, HttpException, Logger, NotFoundException, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AgentDownError } from './agents/agent.gateway';

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
      message = 'An agent service is not responding. Try again in a moment.';
    } else if (e instanceof HttpException) {
      status = e.getStatus();
      if (status === 400) message = 'Some of the values in the request were not valid.';
    } else {
      this.log.error(e);
    }
    res.status(status).render('error', { status, message });
  }
}
