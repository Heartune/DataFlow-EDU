import { Router, type Request, type Response } from 'express';
import crypto from 'crypto';
import {
  getDb,
  type UserConfigRecentRow,
  type UserConfigTemplateRow,
} from '../db.js';

const MAX_NAME_CHARS = 80;
const MAX_CONFIG_JSON_BYTES = 256 * 1024;
const DEFAULT_RECENT_LIMIT = 5;
const MAX_RECENT_LIMIT = 20;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function parseConfigJson(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text);
    return asRecord(parsed) ?? {};
  } catch {
    return {};
  }
}

function serializeConfig(config: unknown): string | null {
  const obj = asRecord(config);
  if (!obj) return null;
  const text = JSON.stringify(obj);
  if (Buffer.byteLength(text, 'utf-8') > MAX_CONFIG_JSON_BYTES) return null;
  return text;
}

function cleanName(name: unknown, fallback: string): string {
  const n = String(name ?? '').trim().slice(0, MAX_NAME_CHARS);
  return n || fallback;
}

function templateDto(row: UserConfigTemplateRow) {
  return {
    id: row.id,
    name: row.name,
    config: parseConfigJson(row.config_json),
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function recentDto(row: UserConfigRecentRow) {
  return {
    id: row.id,
    source_type: row.source_type,
    source_id: row.source_id,
    name: row.name,
    config: parseConfigJson(row.config_json),
    used_at: row.used_at,
  };
}

export function recordUserConfigRecent(opts: {
  userId: string;
  sourceType?: unknown;
  sourceId?: unknown;
  name?: unknown;
  config: unknown;
}): void {
  const configJson = serializeConfig(opts.config);
  if (!configJson) return;
  const now = Date.now();
  const sourceType = String(opts.sourceType || 'custom').trim().slice(0, 40) || 'custom';
  const sourceIdRaw = String(opts.sourceId || '').trim().slice(0, 120);
  const sourceId = sourceIdRaw || null;
  const name = cleanName(opts.name, '未命名配置');
  const db = getDb();
  try {
    db.prepare(
      `INSERT INTO user_config_recents (id, user_id, source_type, source_id, name, config_json, used_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).run(crypto.randomUUID(), opts.userId, sourceType, sourceId, name, configJson, now);

    const stale = db
      .prepare(
        `SELECT id FROM user_config_recents
         WHERE user_id = ?
         ORDER BY used_at DESC
         LIMIT -1 OFFSET ?`
      )
      .all(opts.userId, MAX_RECENT_LIMIT) as Array<{ id: string }>;
    if (stale.length) {
      const placeholders = stale.map(() => '?').join(',');
      db.prepare(`DELETE FROM user_config_recents WHERE id IN (${placeholders})`).run(
        ...stale.map((r) => r.id)
      );
    }
  } catch (err) {
    console.warn('[user-config] record recent failed:', err);
  }
}

export function userConfigRoutes(): Router {
  const router = Router();

  router.get('/templates', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const rows = getDb()
      .prepare(
        `SELECT id, user_id, name, config_json, created_at, updated_at
         FROM user_config_templates
         WHERE user_id = ?
         ORDER BY updated_at DESC`
      )
      .all(req.user.id) as UserConfigTemplateRow[];
    res.json(rows.map(templateDto));
  });

  router.post('/templates', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const body = asRecord(req.body) ?? {};
    const configJson = serializeConfig(body.config);
    if (!configJson) {
      res.status(400).json({ error: 'invalid_config' });
      return;
    }
    const now = Date.now();
    const id = crypto.randomUUID();
    const name = cleanName(body.name, `我的配置 ${new Date(now).toLocaleDateString('zh-CN')}`);
    getDb()
      .prepare(
        `INSERT INTO user_config_templates (id, user_id, name, config_json, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
      .run(id, req.user.id, name, configJson, now, now);
    const row = getDb()
      .prepare(
        `SELECT id, user_id, name, config_json, created_at, updated_at
         FROM user_config_templates
         WHERE id = ? AND user_id = ?`
      )
      .get(id, req.user.id) as UserConfigTemplateRow;
    res.json(templateDto(row));
  });

  router.delete('/templates/:id', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const result = getDb()
      .prepare('DELETE FROM user_config_templates WHERE id = ? AND user_id = ?')
      .run(req.params.id, req.user.id);
    res.json({ ok: true, deleted: result.changes });
  });

  router.get('/recents', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const rawLimit = Number(req.query.limit ?? DEFAULT_RECENT_LIMIT);
    const limit = Math.max(1, Math.min(MAX_RECENT_LIMIT, Number.isFinite(rawLimit) ? rawLimit : DEFAULT_RECENT_LIMIT));
    const rows = getDb()
      .prepare(
        `SELECT id, user_id, source_type, source_id, name, config_json, used_at
         FROM user_config_recents
         WHERE user_id = ?
         ORDER BY used_at DESC
         LIMIT ?`
      )
      .all(req.user.id, limit) as UserConfigRecentRow[];
    res.json(rows.map(recentDto));
  });

  return router;
}
