import { CanActivate, ExecutionContext, ForbiddenException, Injectable, SetMetadata, UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { timingSafeEqual } from 'node:crypto';
import type { Request } from 'express';

declare module 'express-session' {
  interface SessionData { user?: { name: string; role: string }; csrf?: string }
}

/** Page anyone may open (login). Everything else needs a signed-in user. */
export const Public = () => SetMetadata('public', true);
/** Roles allowed on a route; ADMIN is always allowed. */
export const Roles = (...roles: string[]) => SetMetadata('roles', roles);

/**
 * The single access rule for the app: CSRF token on every state-changing request, sign-in for every
 * page except @Public ones, and the role listed in @Roles (ADMIN sees everything).
 */
@Injectable()
export class AccessGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest<Request>();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && !validCsrf(req)) throw new ForbiddenException();

    const meta = <T>(key: string) => this.reflector.getAllAndOverride<T>(key, [ctx.getHandler(), ctx.getClass()]);
    if (meta<boolean>('public')) return true;

    const user = req.session.user;
    if (!user) throw new UnauthorizedException(); // the error filter turns this into a redirect to /login
    const roles = meta<string[]>('roles');
    if (roles && user.role !== 'ADMIN' && !roles.includes(user.role)) throw new ForbiddenException();
    return true;
  }
}

function validCsrf(req: Request): boolean {
  const sent = req.body?._csrf ?? req.headers['x-csrf-token'], expected = req.session.csrf;
  if (typeof sent !== 'string' || !expected || sent.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(sent), Buffer.from(expected));
}
