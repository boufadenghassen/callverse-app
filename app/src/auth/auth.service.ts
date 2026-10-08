import { Injectable } from '@nestjs/common';
import * as bcrypt from 'bcryptjs';

/** One demo account per persona. */
const ROLES: Record<string, string> = {
  yasmine: 'CLIENT', karim: 'ADVISOR', sana: 'WORKFORCE', nour: 'QUALITY',
  amine: 'COMPLAINT', rim: 'TRAINER', leila: 'SALES', admin: 'ADMIN',
};
const MAX_ATTEMPTS = 5, LOCK_MS = 15 * 60_000;

/**
 * Demo accounts that share the password in CALLVERSE_DEMO_PASSWORD (never stored in code), plus a lock after
 * repeated failures (brute-force protection). Replace with a database or Keycloak for production.
 */
@Injectable()
export class AuthService {
  private readonly hash: string;
  private readonly attempts = new Map<string, { count: number; lockedUntil: number }>();

  constructor() {
    const pw = process.env.CALLVERSE_DEMO_PASSWORD ?? '';
    if (pw.length < 12) throw new Error('Set CALLVERSE_DEMO_PASSWORD (at least 12 characters) before starting.');
    this.hash = bcrypt.hashSync(pw, 10);
  }

  async login(username: string, password: string): Promise<{ name: string; role: string } | null> {
    const key = String(username).trim().toLowerCase().slice(0, 64);
    if (this.isLocked(key)) return null;
    const ok = await bcrypt.compare(String(password).slice(0, 128), this.hash); // always compare, so timing does not reveal valid names
    const role = Object.hasOwn(ROLES, key) ? ROLES[key] : undefined;
    if (ok && role) {
      this.attempts.delete(key);
      return { name: key, role };
    }
    const count = (this.attempts.get(key)?.count ?? 0) + 1;
    this.attempts.set(key, { count, lockedUntil: count >= MAX_ATTEMPTS ? Date.now() + LOCK_MS : 0 });
    return null;
  }

  private isLocked(key: string): boolean {
    const a = this.attempts.get(key);
    if (!a || !a.lockedUntil) return false;
    if (Date.now() > a.lockedUntil) { this.attempts.delete(key); return false; }
    return true;
  }
}
