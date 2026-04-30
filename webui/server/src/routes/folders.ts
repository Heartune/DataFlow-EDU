import { Router } from 'express';
import crypto from 'crypto';
import { getDb } from '../db.js';
import type { Request, Response } from 'express';

export interface FolderNode {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  created_at: number;
  task_count: number;
  children: FolderNode[];
}

/**
 * 递归收集某文件夹及其所有后代的 id（含自身），用于递归删除。
 */
function collectDescendantIds(allFolders: Array<{ id: string; parent_id: string | null }>, rootId: string): string[] {
  const result: string[] = [rootId];
  for (const f of allFolders) {
    if (f.parent_id === rootId) {
      result.push(...collectDescendantIds(allFolders, f.id));
    }
  }
  return result;
}

/**
 * 把扁平文件夹列表组装成树。
 */
function buildTree(
  rows: Array<{ id: string; name: string; parent_id: string | null; sort_order: number; created_at: number }>,
  taskCounts: Record<string, number>,
  parentId: string | null = null
): FolderNode[] {
  return rows
    .filter((r) => r.parent_id === parentId)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((r) => {
      const children = buildTree(rows, taskCounts, r.id);
      const childTotal = children.reduce((sum, c) => sum + c.task_count, 0);
      return {
        id: r.id,
        name: r.name,
        parent_id: r.parent_id,
        sort_order: r.sort_order,
        created_at: r.created_at,
        task_count: (taskCounts[r.id] ?? 0) + childTotal,
        children,
      };
    });
}

export function foldersRoutes() {
  const router = Router();

  /** GET /api/folders — 返回当前用户完整文件夹树 */
  router.get('/', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const db = getDb();

    const rows = db
      .prepare('SELECT id, name, parent_id, sort_order, created_at FROM folders WHERE user_id = ?')
      .all(userId) as Array<{ id: string; name: string; parent_id: string | null; sort_order: number; created_at: number }>;

    // 每个文件夹直接关联的任务数
    const countRows = db
      .prepare(
        `SELECT tf.folder_id, COUNT(*) as cnt
         FROM task_folders tf
         JOIN tasks t ON t.id = tf.task_id AND t.user_id = ?
         GROUP BY tf.folder_id`
      )
      .all(userId) as Array<{ folder_id: string; cnt: number }>;

    const taskCounts: Record<string, number> = {};
    for (const r of countRows) taskCounts[r.folder_id] = r.cnt;

    res.json({ folders: buildTree(rows, taskCounts) });
  });

  /** POST /api/folders — 新建文件夹 */
  router.post('/', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const { name, parent_id } = req.body as { name?: string; parent_id?: string | null };

    if (!name || typeof name !== 'string' || name.trim().length === 0) {
      res.status(400).json({ error: 'name_required' });
      return;
    }
    if (name.trim().length > 64) {
      res.status(400).json({ error: 'name_too_long' });
      return;
    }

    const db = getDb();

    // 验证父文件夹归属
    if (parent_id) {
      const parent = db
        .prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?')
        .get(parent_id, userId);
      if (!parent) {
        res.status(404).json({ error: 'parent_not_found' });
        return;
      }
    }

    // 同一父节点下不允许重名
    const dup = db
      .prepare('SELECT id FROM folders WHERE user_id = ? AND parent_id IS ? AND name = ?')
      .get(userId, parent_id ?? null, name.trim());
    if (dup) {
      res.status(409).json({ error: 'duplicate_name' });
      return;
    }

    // sort_order = 同级最大值 + 1000
    const maxRow = db
      .prepare('SELECT MAX(sort_order) as m FROM folders WHERE user_id = ? AND parent_id IS ?')
      .get(userId, parent_id ?? null) as { m: number | null };
    const sortOrder = (maxRow.m ?? 0) + 1000;

    const id = crypto.randomUUID();
    const now = Date.now();
    db.prepare(
      'INSERT INTO folders (id, user_id, name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(id, userId, name.trim(), parent_id ?? null, sortOrder, now);

    res.status(201).json({ id, name: name.trim(), parent_id: parent_id ?? null, sort_order: sortOrder, created_at: now, task_count: 0, children: [] });
  });

  /** PATCH /api/folders/:id — 重命名 / 移动 / 调序 */
  router.patch('/:id', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const { id } = req.params;
    const { name, parent_id, sort_order } = req.body as { name?: string; parent_id?: string | null; sort_order?: number };

    const db = getDb();

    const folder = db
      .prepare('SELECT * FROM folders WHERE id = ? AND user_id = ?')
      .get(id, userId) as { id: string; name: string; parent_id: string | null; sort_order: number } | undefined;
    if (!folder) {
      res.status(404).json({ error: 'not_found' });
      return;
    }

    const newName = name !== undefined ? name.trim() : folder.name;
    const newParent = parent_id !== undefined ? (parent_id ?? null) : folder.parent_id;
    const newOrder = sort_order !== undefined ? sort_order : folder.sort_order;

    if (newName.length === 0 || newName.length > 64) {
      res.status(400).json({ error: 'invalid_name' });
      return;
    }

    // 防止把文件夹移动成自己的后代（循环引用）
    if (newParent && newParent !== folder.parent_id) {
      const allFolders = db
        .prepare('SELECT id, parent_id FROM folders WHERE user_id = ?')
        .all(userId) as Array<{ id: string; parent_id: string | null }>;
      const descendants = collectDescendantIds(allFolders, id);
      if (descendants.includes(newParent)) {
        res.status(400).json({ error: 'circular_reference' });
        return;
      }
      // 验证新父文件夹归属
      const parent = db.prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?').get(newParent, userId);
      if (!parent) {
        res.status(404).json({ error: 'parent_not_found' });
        return;
      }
    }

    // 同一父节点下重名检查（排除自身）
    const dup = db
      .prepare('SELECT id FROM folders WHERE user_id = ? AND parent_id IS ? AND name = ? AND id != ?')
      .get(userId, newParent, newName, id);
    if (dup) {
      res.status(409).json({ error: 'duplicate_name' });
      return;
    }

    db.prepare('UPDATE folders SET name = ?, parent_id = ?, sort_order = ? WHERE id = ?')
      .run(newName, newParent, newOrder, id);

    res.json({ id, name: newName, parent_id: newParent, sort_order: newOrder });
  });

  /** DELETE /api/folders/:id — 删除文件夹（及子文件夹），不删任务 */
  router.delete('/:id', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const { id } = req.params;

    const db = getDb();

    const folder = db
      .prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?')
      .get(id, userId);
    if (!folder) {
      res.status(404).json({ error: 'not_found' });
      return;
    }

    // 收集所有后代 id（外键 CASCADE 会自动清理 task_folders，但 SQLite 级联删除需要开启 foreign_keys=ON）
    const allFolders = db
      .prepare('SELECT id, parent_id FROM folders WHERE user_id = ?')
      .all(userId) as Array<{ id: string; parent_id: string | null }>;
    const toDelete = collectDescendantIds(allFolders, id);

    const placeholders = toDelete.map(() => '?').join(',');
    db.prepare(`DELETE FROM folders WHERE id IN (${placeholders})`).run(...toDelete);

    res.json({ deleted: toDelete.length });
  });

  /** POST /api/folders/:id/tasks/:taskId — 添加任务到文件夹（幂等） */
  router.post('/:id/tasks/:taskId', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const { id: folderId, taskId } = req.params;

    const db = getDb();

    // 验证文件夹归属
    const folder = db.prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?').get(folderId, userId);
    if (!folder) {
      res.status(404).json({ error: 'folder_not_found' });
      return;
    }

    // 验证任务归属
    const task = db.prepare('SELECT id FROM tasks WHERE id = ? AND user_id = ?').get(taskId, userId);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }

    db.prepare(
      'INSERT OR IGNORE INTO task_folders (task_id, folder_id, created_at) VALUES (?, ?, ?)'
    ).run(taskId, folderId, Date.now());

    res.json({ task_id: taskId, folder_id: folderId });
  });

  /** DELETE /api/folders/:id/tasks/:taskId — 从文件夹移除任务 */
  router.delete('/:id/tasks/:taskId', (req: Request, res: Response) => {
    const userId = (req as any).user.id as string;
    const { id: folderId, taskId } = req.params;

    const db = getDb();

    // 验证文件夹归属
    const folder = db.prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?').get(folderId, userId);
    if (!folder) {
      res.status(404).json({ error: 'folder_not_found' });
      return;
    }

    db.prepare('DELETE FROM task_folders WHERE task_id = ? AND folder_id = ?').run(taskId, folderId);

    res.json({ ok: true });
  });

  return router;
}
