import { Router, type Request, type Response } from 'express';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { getDb, type TaskShareRow, type TaskRow } from '../db.js';

// 自顶向下选「最近」一阶段有题目的产物（与 task_runner 目录一致，含子目录如 2_1/2_2）
const STAGE_ORDER = [
  '3_8_mcq_verified',
  '3_7_translated',
  '3_6_synthesized',
  '3_5_deduplicated',
  '3_4_domain_refined',
  '3_3_domain_cleaned',
  '3_2_ambiguity_refined',
  '3_1_ambiguity_cleaned',
  '2_1_generation/2_2_balanced', // 2.2 优先于 2.1 原始 json
  '2_1_generation',
];

function userTaskRoot(projectRoot: string, userId: string, taskId: string): string {
  return path.join(projectRoot, 'dataflow_edu', 'data', 'users', userId, taskId);
}

/** 与管道产出一致：多数字段名为 questions，读分享 API 的 stats 也按此取 */
function extractItemArray(parsed: unknown): unknown[] {
  if (Array.isArray(parsed)) return parsed;
  if (!parsed || typeof parsed !== 'object') return [];
  const o = parsed as Record<string, unknown>;
  for (const key of ['questions', 'items', 'data'] as const) {
    const a = o[key];
    if (Array.isArray(a)) return a;
  }
  return [];
}

function* iterJsonFilesRecursive(dir: string): Generator<string> {
  if (!fs.existsSync(dir)) return;
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      yield* iterJsonFilesRecursive(full);
    } else if (
      ent.isFile() &&
      ent.name.endsWith('.json') &&
      !ent.name.includes('_progress')
    ) {
      yield full;
    }
  }
}

function loadLatestItems(
  taskDir: string
): { items: unknown[]; stage: string } | null {
  for (const stage of STAGE_ORDER) {
    const stageDir = path.join(taskDir, stage);
    for (const filePath of iterJsonFilesRecursive(stageDir)) {
      try {
        const raw = fs.readFileSync(filePath, 'utf-8');
        const parsed = JSON.parse(raw) as unknown;
        const items = extractItemArray(parsed);
        if (items.length > 0) {
          return { items, stage };
        }
      } catch {
        /* 解析失败跳过 */
      }
    }
  }
  return null;
}

export function shareRoutes(projectRoot: string): Router {
  const router = Router();

  // GET /api/share/:token — 公开只读，无需登录
  router.get('/:token', (req: Request, res: Response) => {
    const rawToken = String(req.params.token || '').trim();
    if (!rawToken) {
      res.status(400).json({ error: 'missing_token' });
      return;
    }

    const tokenHash = crypto.createHash('sha256').update(rawToken).digest('hex');

    const db = getDb();
    const share = db
      .prepare('SELECT * FROM task_shares WHERE token_hash = ?')
      .get(tokenHash) as TaskShareRow | undefined;

    if (!share) {
      res.status(404).json({ error: 'share_not_found' });
      return;
    }

    if (share.expires_at !== null && share.expires_at < Date.now()) {
      res.status(410).json({ error: 'share_expired' });
      return;
    }

    const task = db
      .prepare('SELECT * FROM tasks WHERE id = ?')
      .get(share.task_id) as TaskRow | undefined;

    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }

    const taskDir = userTaskRoot(projectRoot, share.user_id, share.task_id);
    const result = loadLatestItems(taskDir);

    if (!result) {
      res.json({
        task_name: task.name,
        stage: null,
        item_count: 0,
        items: [],
        generated_at: task.updated_at,
        expires_at: share.expires_at,
      });
      return;
    }

    res.json({
      task_name: task.name,
      stage: result.stage,
      item_count: result.items.length,
      items: result.items,
      generated_at: task.updated_at,
      expires_at: share.expires_at,
    });
  });

  return router;
}
