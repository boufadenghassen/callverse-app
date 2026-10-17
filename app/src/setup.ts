import { NestExpressApplication } from '@nestjs/platform-express';
import compression from 'compression';
import { createHash, randomBytes } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
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
  const hashes = new Map<string, { mtime: number; hash: string }>();
  env.addGlobal('asset', (path: string) => {
    const file = join(ROOT, 'public', path), mtime = statSync(file).mtimeMs;
    const known = hashes.get(path);
    if (known?.mtime === mtime) return `${path}?v=${known.hash}`;          // recomputed only when the file changed, so edits always reach the browser
    const hash = createHash('md5').update(readFileSync(file)).digest('hex').slice(0, 10);
    hashes.set(path, { mtime, hash });
    return `${path}?v=${hash}`;
  });
  env.addFilter('pct', (v: number) => `${Math.round(v * 100)}%`);
  app.setBaseViewsDir(join(ROOT, 'views'));
  app.setViewEngine('njk');

  // ---- health + static files come before sessions, so they never create one
  server.get('/actuator/health', (_req: express.Request, res: express.Response) => res.json({ status: 'UP' }));
  server.use(compression());
  server.use('/voice/transcribe', express.raw({ type: 'audio/wav', limit: '6mb' }));                      // voice notes
  server.use('/call-review/analyze', express.raw({ type: 'application/octet-stream', limit: '15mb' }));    // uploaded recordings
  server.use(express.static(join(ROOT, 'public'), { maxAge: '7d', index: false }));

  // ---- strict CSP: no inline scripts or styles, nothing loaded from other origins
  server.use(helmet({
    contentSecurityPolicy: {
      useDefaults: false,
      directives: {
        'default-src': ["'self'"], 'script-src': ["'self'"], 'style-src': ["'self'"], 'img-src': ["'self'", 'data:'], 'font-src': ["'self'"],
        'media-src': ["'self'", 'blob:'],      // the agents' neural voice is played from a blob made in the page
        'object-src': ["'none'"], 'base-uri': ["'self'"], 'form-action': ["'self'"], 'frame-ancestors': ["'none'"],
      },
    },
    frameguard: { action: 'deny' },
    referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
    strictTransportSecurity: { maxAge: 31_536_000, includeSubDomains: true },
  }));
  server.use((_req: express.Request, res: express.Response, next: express.NextFunction) => {
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(self), geolocation=(), payment=()');
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
