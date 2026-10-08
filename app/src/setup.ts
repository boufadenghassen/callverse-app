import { NestExpressApplication } from '@nestjs/platform-express';
import compression from 'compression';
import { createHash, randomBytes } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import express from 'express';
import session from 'express-session';
import helmet from 'helmet';
import * as nunjucks from 'nunjucks';

// the project folder, whether we run from src, dist or the compiled tests
const ROOT = [join(__dirname, '..'), join(__dirname, '..', '..')].find((d) => existsSync(join(d, 'views')))!;

/** Everything between "Nest created the app" and "routes run": views, static files, security headers, sessions. */
export function setup(app: NestExpressApplication) {
  const server = app.getHttpAdapter().getInstance();
  server.disable('x-powered-by');

  // ---- views: Nunjucks, autoescaped. asset() appends a content hash so long-cached files refresh on change.
  const env = nunjucks.configure(join(ROOT, 'views'), { autoescape: true, express: server, noCache: process.env.NODE_ENV !== 'production' });
  const hashes = new Map<string, string>();
  env.addGlobal('asset', (path: string) => {
    if (!hashes.has(path)) hashes.set(path, createHash('md5').update(readFileSync(join(ROOT, 'public', path))).digest('hex').slice(0, 10));
    return `${path}?v=${hashes.get(path)}`;
  });
  env.addFilter('pct', (v: number) => `${Math.round(v * 100)}%`);
  app.setBaseViewsDir(join(ROOT, 'views'));
  app.setViewEngine('njk');

  // ---- health + static files come before sessions, so they never create one
  server.get('/actuator/health', (_req: express.Request, res: express.Response) => res.json({ status: 'UP' }));
  server.use(compression());
  server.use(express.static(join(ROOT, 'public'), { maxAge: '7d', index: false }));

  // ---- strict CSP: no inline scripts or styles, nothing loaded from other origins
  server.use(helmet({
    contentSecurityPolicy: {
      useDefaults: false,
      directives: {
        'default-src': ["'self'"], 'script-src': ["'self'"], 'style-src': ["'self'"], 'img-src': ["'self'", 'data:'], 'font-src': ["'self'"],
        'object-src': ["'none'"], 'base-uri': ["'self'"], 'form-action': ["'self'"], 'frame-ancestors': ["'none'"],
      },
    },
    frameguard: { action: 'deny' },
    referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
    strictTransportSecurity: { maxAge: 31_536_000, includeSubDomains: true },
  }));
  server.use((_req: express.Request, res: express.Response, next: express.NextFunction) => {
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()');
    next();
  });

  // ponytail: in-memory session store; swap for Redis if the app runs on more than one instance.
  server.use(session({
    name: 'CVSESSION',
    secret: process.env.SESSION_SECRET ?? randomBytes(32).toString('hex'),
    resave: false, saveUninitialized: false, rolling: true,
    cookie: { httpOnly: true, sameSite: 'strict', secure: process.env.CALLVERSE_COOKIE_SECURE !== 'false', maxAge: 30 * 60_000 },
  }));

  // ---- what every template needs: CSRF token and who is signed in
  server.use((req: express.Request, res: express.Response, next: express.NextFunction) => {
    req.session.csrf ??= randomBytes(24).toString('hex');
    const role = req.session.user?.role;
    res.locals.csrf = req.session.csrf;
    res.locals.user = req.session.user?.name;
    res.locals.isAdmin = role === 'ADMIN';
    res.locals.can = (...roles: string[]) => role === 'ADMIN' || (!!role && roles.includes(role));
    next();
  });
}
