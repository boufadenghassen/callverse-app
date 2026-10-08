import { Body, Controller, Get, HttpCode, Post, Query, Render, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { Public } from './access.guard';
import { AuthService } from './auth.service';

@Controller()
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Public() @Get('login') @Render('login')
  loginPage(@Query() q: Record<string, unknown>) {
    return { error: 'error' in q, loggedOut: 'logout' in q };
  }

  @Public() @Post('login') @HttpCode(302)
  async login(@Body() body: { username?: string; password?: string }, @Req() req: Request, @Res() res: Response) {
    const user = await this.auth.login(body.username ?? '', body.password ?? '');
    if (!user) return res.redirect('/login?error');
    req.session.regenerate((err) => { // new session id on sign-in (session fixation protection)
      if (err) return res.redirect('/login?error');
      req.session.user = user;
      req.session.save(() => res.redirect('/'));
    });
  }

  @Post('logout') @HttpCode(302)
  logout(@Req() req: Request, @Res() res: Response) {
    req.session.destroy(() => {
      res.clearCookie('CVSESSION');
      res.redirect('/login?logout');
    });
  }
}
