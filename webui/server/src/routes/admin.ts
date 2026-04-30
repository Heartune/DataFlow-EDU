/**
 * Admin 路由：邀请码管理 + 待审批用户管理 + LLM 配额管理。
 * 挂载于 /api/admin，已被 requireAdmin 中间件保护。
 */
import { Router, type Request, type Response } from 'express';
import crypto from 'crypto';
import https from 'https';
import http from 'http';
import { getDb, writeAuditLog, todayKey, type InviteCodeRow, type UserRow } from '../db.js';

export function adminUserRoutes(): Router {
  const router = Router();

  // ── 邀请码 ────────────────────────────────────────────────────────────────

  /** 生成 N 张邀请码（可设过期时间）。*/
  router.post('/invite-codes', (req: Request, res: Response) => {
    const { count = 1, expires_in_days } = (req.body || {}) as {
      count?: number;
      expires_in_days?: number;
    };
    const n = Math.max(1, Math.min(100, Number(count) || 1));
    const expiresAt = expires_in_days
      ? Date.now() + Number(expires_in_days) * 24 * 60 * 60 * 1000
      : null;

    const db = getDb();
    const now = Date.now();
    const codes: string[] = [];
    const stmt = db.prepare(
      'INSERT INTO invite_codes(code, created_by, used_by, used_at, expires_at, created_at) VALUES(?,?,NULL,NULL,?,?)'
    );
    db.transaction(() => {
      for (let i = 0; i < n; i++) {
        const code = crypto.randomBytes(6).toString('hex').toUpperCase();
        stmt.run(code, req.user!.id, expiresAt, now);
        codes.push(code);
      }
    })();

    writeAuditLog({ userId: req.user!.id, ip: req.ip ?? null, action: 'invite_codes_created', target: null, status: 'ok', meta: { count: n, expires_in_days: expires_in_days ?? null } });
    res.json({ ok: true, codes });
  });

  /** 列出所有邀请码及使用状态。*/
  router.get('/invite-codes', (_req: Request, res: Response) => {
    const rows = getDb()
      .prepare(
        `SELECT ic.code, ic.created_by, ic.used_by, ic.used_at, ic.expires_at, ic.created_at,
                u.email AS used_by_email
         FROM invite_codes ic
         LEFT JOIN users u ON u.id = ic.used_by
         ORDER BY ic.created_at DESC`
      )
      .all() as Array<InviteCodeRow & { used_by_email: string | null }>;
    res.json({ items: rows });
  });

  /** 作废一张未使用的邀请码。*/
  router.delete('/invite-codes/:code', (req: Request, res: Response) => {
    const code = (req.params.code || '').trim().toUpperCase();
    const row = getDb()
      .prepare('SELECT code, used_by FROM invite_codes WHERE code = ?')
      .get(code) as Pick<InviteCodeRow, 'code' | 'used_by'> | undefined;
    if (!row) {
      res.status(404).json({ error: 'code_not_found' });
      return;
    }
    if (row.used_by) {
      res.status(409).json({ error: 'code_already_used', message: '邀请码已使用，无法作废' });
      return;
    }
    getDb().prepare('DELETE FROM invite_codes WHERE code = ?').run(code);
    writeAuditLog({ userId: req.user!.id, ip: req.ip ?? null, action: 'invite_code_revoked', target: code, status: 'ok' });
    res.json({ ok: true });
  });

  // ── 待审批用户 ────────────────────────────────────────────────────────────

  /** 列出 approved=0 的待审批用户。*/
  router.get('/users/pending', (_req: Request, res: Response) => {
    const rows = getDb()
      .prepare(
        "SELECT id, email, role, created_at FROM users WHERE approved = 0 ORDER BY created_at ASC"
      )
      .all() as Array<Pick<UserRow, 'id' | 'email' | 'role' | 'created_at'>>;
    res.json({ items: rows });
  });

  /** 列出所有用户（含审批状态）。*/
  router.get('/users', (_req: Request, res: Response) => {
    const rows = getDb()
      .prepare(
        "SELECT id, email, role, created_at, approved FROM users ORDER BY created_at DESC"
      )
      .all() as Array<Pick<UserRow, 'id' | 'email' | 'role' | 'created_at' | 'approved'>>;
    res.json({ items: rows });
  });

  /** 审批通过用户。*/
  router.post('/users/:id/approve', (req: Request, res: Response) => {
    const userId = req.params.id;
    const row = getDb()
      .prepare('SELECT id, email, approved FROM users WHERE id = ?')
      .get(userId) as Pick<UserRow, 'id' | 'email' | 'approved'> | undefined;
    if (!row) {
      res.status(404).json({ error: 'user_not_found' });
      return;
    }
    if (row.approved === 1) {
      res.status(409).json({ error: 'already_approved' });
      return;
    }
    getDb().prepare('UPDATE users SET approved = 1 WHERE id = ?').run(userId);
    writeAuditLog({ userId: req.user!.id, ip: req.ip ?? null, action: 'user_approved', target: userId, status: 'ok', meta: { email: row.email } });
    res.json({ ok: true });
  });

  /** 拒绝并删除待审批用户。*/
  router.post('/users/:id/reject', (req: Request, res: Response) => {
    const userId = req.params.id;
    const row = getDb()
      .prepare('SELECT id, email, approved FROM users WHERE id = ?')
      .get(userId) as Pick<UserRow, 'id' | 'email' | 'approved'> | undefined;
    if (!row) {
      res.status(404).json({ error: 'user_not_found' });
      return;
    }
    getDb().prepare('DELETE FROM users WHERE id = ?').run(userId);
    writeAuditLog({ userId: req.user!.id, ip: req.ip ?? null, action: 'user_rejected', target: userId, status: 'ok', meta: { email: row.email } });
    res.json({ ok: true });
  });

  // ── 审计日志查询 ──────────────────────────────────────────────────────────

  /** 查询审计日志（管理员可查，支持简单分页）。*/
  router.get('/audit-log', (req: Request, res: Response) => {
    const limit = Math.max(1, Math.min(200, Number(req.query.limit) || 50));
    const offset = Math.max(0, Number(req.query.offset) || 0);
    const rows = getDb()
      .prepare(
        `SELECT al.*, u.email AS user_email
         FROM audit_log al
         LEFT JOIN users u ON u.id = al.user_id
         ORDER BY al.ts DESC LIMIT ? OFFSET ?`
      )
      .all(limit, offset);
    const total = (getDb().prepare('SELECT COUNT(*) as n FROM audit_log').get() as { n: number }).n;
    res.json({ items: rows, total, limit, offset });
  });

  // ── LLM 配额管理 ──────────────────────────────────────────────────────────

  /**
   * 查询 ZGCA API Key 余额（OpenAI-compatible billing API）。
   * 返回 { hard_limit_usd, used_usd, remaining_usd } 或 { error }。
   */
  router.get('/llm-balance', async (_req: Request, res: Response) => {
    const zgcaKey = (process.env.LLM_ZGCA_API_KEY || '').trim();
    const zgcaBase = 'http://35.220.164.252:3888';

    if (!zgcaKey) {
      res.json({ hard_limit_usd: null, used_usd: null, remaining_usd: null, error: 'key_not_configured' });
      return;
    }

    const newApiUser = (process.env.LLM_ZGCA_NEW_API_USER || '').trim();

    function fetchJson(url: string, authKey: string): Promise<unknown> {
      return new Promise((resolve, reject) => {
        const parsed = new URL(url);
        const lib = parsed.protocol === 'https:' ? https : http;
        const headers: Record<string, string> = { Authorization: `Bearer ${authKey}` };
        if (newApiUser) headers['New-Api-User'] = newApiUser;
        const options = {
          hostname: parsed.hostname,
          port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
          path: parsed.pathname + parsed.search,
          method: 'GET',
          headers,
          timeout: 10000,
        };
        const req2 = lib.request(options, (r) => {
          let data = '';
          r.on('data', (chunk) => { data += chunk; });
          r.on('end', () => {
            try { resolve(JSON.parse(data)); } catch { reject(new Error(`parse error: ${data.slice(0, 200)}`)); }
          });
        });
        req2.on('error', reject);
        req2.on('timeout', () => { req2.destroy(); reject(new Error('timeout')); });
        req2.end();
      });
    }

    try {
      const [subData, usageData] = await Promise.all([
        fetchJson(`${zgcaBase}/v1/dashboard/billing/subscription`, zgcaKey),
        fetchJson(`${zgcaBase}/v1/dashboard/billing/usage`, zgcaKey),
      ]);
      const sub = subData as Record<string, unknown>;
      const usage = usageData as Record<string, unknown>;
      const hardLimit = Number(sub.hard_limit_usd ?? 0);
      const usedUsd = Number(usage.total_usage ?? 0) / 100;
      res.json({
        hard_limit_usd: hardLimit,
        used_usd: parseFloat(usedUsd.toFixed(4)),
        remaining_usd: parseFloat(Math.max(0, hardLimit - usedUsd).toFixed(4)),
      });
    } catch (err) {
      console.warn('[admin] llm-balance fetch failed:', err);
      res.json({ hard_limit_usd: null, used_usd: null, remaining_usd: null, error: String(err) });
    }
  });

  /** 查询所有用户当日 LLM token 用量汇总。*/
  router.get('/llm-usage', (_req: Request, res: Response) => {
    const day = todayKey();
    const rows = getDb()
      .prepare(
        `SELECT u.id, u.email, u.role, u.daily_llm_quota,
                COALESCE(SUM(lu.tokens), 0) AS used
         FROM users u
         LEFT JOIN llm_usage lu ON lu.user_id = u.id AND lu.day = ?
         GROUP BY u.id
         ORDER BY used DESC`
      )
      .all(day) as Array<{
        id: string;
        email: string;
        role: string;
        daily_llm_quota: number;
        used: number;
      }>;
    res.json({ items: rows, day });
  });

  /** 修改单个用户的每日 LLM token 配额上限。*/
  router.patch('/users/:id/quota', (req: Request, res: Response) => {
    const userId = req.params.id;
    const { daily_llm_quota } = (req.body || {}) as { daily_llm_quota?: number };
    if (daily_llm_quota == null || isNaN(Number(daily_llm_quota)) || Number(daily_llm_quota) < 0) {
      res.status(400).json({ error: 'invalid_quota', message: 'daily_llm_quota 必须为非负整数' });
      return;
    }
    const userRow = getDb()
      .prepare('SELECT id, email FROM users WHERE id = ?')
      .get(userId) as Pick<UserRow, 'id' | 'email'> | undefined;
    if (!userRow) {
      res.status(404).json({ error: 'user_not_found' });
      return;
    }
    getDb()
      .prepare('UPDATE users SET daily_llm_quota = ? WHERE id = ?')
      .run(Math.floor(Number(daily_llm_quota)), userId);
    writeAuditLog({
      userId: req.user!.id,
      ip: req.ip ?? null,
      action: 'user_quota_updated',
      target: userId,
      status: 'ok',
      meta: { email: userRow.email, daily_llm_quota: Math.floor(Number(daily_llm_quota)) },
    });
    res.json({ ok: true });
  });

  return router;
}
