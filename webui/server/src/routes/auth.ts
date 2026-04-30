import { Router, type Request, type Response } from 'express';
import bcrypt from 'bcryptjs';
import crypto from 'crypto';
import rateLimit from 'express-rate-limit';
import zxcvbn from 'zxcvbn';
import { getDb, writeAuditLog, DEFAULT_DAILY_LLM_QUOTA, type UserRow } from '../db.js';
import { requireAuth, signToken, type AuthUser } from '../middleware/auth.js';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// 注册/登录接口：5 次/min/IP
const authLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'too_many_requests', message: '请求过于频繁，请稍后再试' },
});

export function authRoutes(): Router {
  const router = Router();

  router.post('/register', authLimiter, (req: Request, res: Response) => {
    const { email, password, invite_code } = (req.body || {}) as {
      email?: string;
      password?: string;
      invite_code?: string;
    };
    const e = (email || '').trim().toLowerCase();
    if (!EMAIL_RE.test(e)) {
      res.status(400).json({ error: 'invalid_email' });
      return;
    }
    if (!password || password.length < 8) {
      res.status(400).json({ error: 'password_too_short', message: '密码至少 8 位' });
      return;
    }
    const result = zxcvbn(password);
    if (result.score < 2) {
      res.status(400).json({
        error: 'password_too_weak',
        message: '密码强度不足，请使用更复杂的密码',
        suggestions: result.feedback.suggestions,
        warning: result.feedback.warning,
      });
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
    const code = (invite_code || '').trim().toUpperCase();
    const now = Date.now();

    // 校验邀请码
    let approved = 0;
    if (code) {
      const inviteRow = db
        .prepare(
          "SELECT code, used_by, expires_at FROM invite_codes WHERE code = ?"
        )
        .get(code) as { code: string; used_by: string | null; expires_at: number | null } | undefined;

      if (!inviteRow) {
        writeAuditLog({ userId: null, ip: req.ip ?? null, action: 'register_fail', target: e, status: 'invalid_invite', meta: { code } });
        res.status(400).json({ error: 'invalid_invite_code', message: '邀请码无效' });
        return;
      }
      if (inviteRow.used_by) {
        writeAuditLog({ userId: null, ip: req.ip ?? null, action: 'register_fail', target: e, status: 'invite_used', meta: { code } });
        res.status(400).json({ error: 'invite_code_used', message: '邀请码已被使用' });
        return;
      }
      if (inviteRow.expires_at && inviteRow.expires_at < now) {
        writeAuditLog({ userId: null, ip: req.ip ?? null, action: 'register_fail', target: e, status: 'invite_expired', meta: { code } });
        res.status(400).json({ error: 'invite_code_expired', message: '邀请码已过期' });
        return;
      }
      // 核销邀请码
      db.prepare('UPDATE invite_codes SET used_by=?, used_at=? WHERE code=?').run(id, now, code);
      approved = 1;
    }

    db.prepare(
      'INSERT INTO users (id, email, password_hash, role, created_at, approved, daily_llm_quota) VALUES (?, ?, ?, ?, ?, ?, ?)'
    ).run(id, e, hash, 'user', now, approved, DEFAULT_DAILY_LLM_QUOTA);

    writeAuditLog({ userId: id, ip: req.ip ?? null, action: 'register_ok', target: e, status: approved === 1 ? 'activated' : 'pending_approval', meta: { invite_code: code || null } });

    if (approved === 0) {
      // 无邀请码：进入待审批状态，不签发 token
      res.status(202).json({
        status: 'pending_approval',
        message: '注册成功，请等待管理员审批后再登录',
      });
      return;
    }

    const token = signToken({ id, email: e, role: 'user' });
    res.json({ token, user: { id, email: e, role: 'user', onboarding_done: false } });
  });

  router.post('/login', authLimiter, (req: Request, res: Response) => {
    const { email, password } = (req.body || {}) as { email?: string; password?: string };
    const e = (email || '').trim().toLowerCase();
    if (!e || !password) {
      res.status(400).json({ error: 'missing_credentials' });
      return;
    }
    const row = getDb()
      .prepare('SELECT id, email, password_hash, role, approved, onboarding_done FROM users WHERE email = ?')
      .get(e) as Pick<UserRow, 'id' | 'email' | 'password_hash' | 'role' | 'approved' | 'onboarding_done'> | undefined;
    if (!row || !bcrypt.compareSync(password, row.password_hash)) {
      writeAuditLog({ userId: null, ip: req.ip ?? null, action: 'login_fail', target: e, status: 'fail' });
      res.status(401).json({ error: 'invalid_credentials' });
      return;
    }
    if (row.approved === 0) {
      writeAuditLog({ userId: row.id, ip: req.ip ?? null, action: 'login_fail', target: e, status: 'pending_approval' });
      res.status(403).json({ error: 'pending_approval', message: '账号正在等待管理员审批，请稍后再试' });
      return;
    }
    writeAuditLog({ userId: row.id, ip: req.ip ?? null, action: 'login_ok', target: e, status: 'ok' });
    const token = signToken({ id: row.id, email: row.email, role: row.role });
    res.json({
      token,
      user: { id: row.id, email: row.email, role: row.role, onboarding_done: row.onboarding_done === 1 },
    });
  });

  router.get('/me', requireAuth, (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const row = getDb()
      .prepare('SELECT onboarding_done FROM users WHERE id = ?')
      .get(req.user.id) as Pick<UserRow, 'onboarding_done'> | undefined;
    res.json({
      user: {
        ...req.user,
        onboarding_done: row?.onboarding_done === 1,
      },
    });
  });

  router.post('/me/onboarding-done', requireAuth, (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    getDb().prepare('UPDATE users SET onboarding_done = 1 WHERE id = ?').run(req.user.id);
    res.json({ ok: true });
  });

  return router;
}
