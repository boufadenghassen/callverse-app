process.env.CALLVERSE_DEMO_PASSWORD = 'test-password-123';
process.env.CALLVERSE_COOKIE_SECURE = 'false'; // supertest talks plain http

import { Test } from '@nestjs/testing';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { setup } from '../src/setup';

export const PASSWORD = 'test-password-123';
export type Agent = ReturnType<typeof request.agent>;

export async function startApp() {
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
  const app = moduleRef.createNestApplication<NestExpressApplication>();
  setup(app);
  await app.init();
  return app;
}

export const csrfOf = (html: string) => /name="_csrf" value="([^"]+)"/.exec(html)?.[1] ?? '';
export const count = (html: string, needle: string) => html.split(needle).length - 1;

/** A browser-like client: signs in as `username` (or stays anonymous) and keeps its cookie. */
export async function client(app: NestExpressApplication, username?: string): Promise<Agent> {
  const agent = request.agent(app.getHttpServer());
  if (username) {
    const page = await agent.get('/login');
    await agent.post('/login').type('form').send({ username, password: PASSWORD, _csrf: csrfOf(page.text) }).expect(302);
  }
  return agent;
}

/** Posts a form with the CSRF token taken from `fromPage`. */
export async function post(agent: Agent, path: string, fromPage: string, fields: Record<string, string>) {
  const page = await agent.get(fromPage);
  return agent.post(path).type('form').send({ ...fields, _csrf: csrfOf(page.text) });
}
