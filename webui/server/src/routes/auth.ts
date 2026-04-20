import { Router, type Request, type Response } from 'express';
import bcrypt from 'bcryptjs';
import crypto from 'crypto';
import { getDb, type UserRow } from '../db.js';
import { requireAuth, signToken } from '../middleware/auth.js';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function authRoutes(): Router {
  const router = Router();

  router.post('/register', (req: Request, res: Response) => {
    const { email, password } = (req.body || {}) as { email?: string; password?: string };
    const e = (email || '').trim().toLowerCase();
    if (!EMAIL_RE.test(e)) {
      res.status(400).json({ error: 'invalid_email' });
      return;
    }
    if (!password || password.length < 6) {
      res.status(400).json({ error: 'password_too_short', message: '密码至少 6 位' });
      return;
    }

    const db = getDb();
    const exists = db.prepare('SELECT id FROM users WHERE email = ?').get(e);
    if (exists) {
      res.status(409).json({ error: 'email_taken' });
      return;
    }

    const id = crypto.randomUUID();
    const hash = bcrypt.hashSync(password, 10);
    db.prepare(
      'INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)'
    ).run(id, e, hash, 'user', Date.now());

    const token = signToken({ id, email: e, role: 'user' });
    res.json({ token, user: { id, email: e, role: 'user' } });
  });

  router.post('/login', (req: Request, res: Response) => {
    const { email, password } = (req.body || {}) as { email?: string; password?: string };
    const e = (email || '').trim().toLowerCase();
    if (!e || !password) {
      res.status(400).json({ error: 'missing_credentials' });
      return;
    }
    const row = getDb()
      .prepare('SELECT id, email, password_hash, role FROM users WHERE email = ?')
      .get(e) as Pick<UserRow, 'id' | 'email' | 'password_hash' | 'role'> | undefined;
    if (!row || !bcrypt.compareSync(password, row.password_hash)) {
      res.status(401).json({ error: 'invalid_credentials' });
      return;
    }
    const token = signToken({ id: row.id, email: row.email, role: row.role });
    res.json({ token, user: { id: row.id, email: row.email, role: row.role } });
  });

  router.get('/me', requireAuth, (req: Request, res: Response) => {
    res.json({ user: req.user });
  });

  return router;
}
