import Database from 'better-sqlite3';
import bcrypt from 'bcryptjs';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.resolve(__dirname, '../data');
const DB_PATH = path.join(DB_DIR, 'app.db');

/** 每用户每日 LLM token 上限默认值（与 DB 列默认、注册 INSERT、配额校验回退一致） */
export const DEFAULT_DAILY_LLM_QUOTA = 999999;

export interface UserRow {
  id: string;
  email: string;
  password_hash: string;
  role: 'admin' | 'user';
  created_at: number;
  approved: number; // 0 = pending_approval, 1 = approved
  onboarding_done: number; // 0 = not done, 1 = done
}

export interface TaskRow {
  id: string;
  user_id: string;
  name: string;
  status: 'created' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
  meta_json: string;
}

export interface AuditLogRow {
  id: string;
  ts: number;
  user_id: string | null;
  ip: string | null;
  action: string;
  target: string | null;
  status: string;
  meta_json: string | null;
}

export interface InviteCodeRow {
  code: string;
  created_by: string;
  used_by: string | null;
  used_at: number | null;
  expires_at: number | null;
  created_at: number;
}

export interface TaskShareRow {
  id: string;
  task_id: string;
  user_id: string;
  token_hash: string;
  expires_at: number | null; // NULL = 永不过期
  created_at: number;
}

export interface FolderRow {
  id: string;
  user_id: string;
  name: string;
  parent_id: string | null; // NULL = 根文件夹
  sort_order: number;
  created_at: number;
}

export interface TaskFolderRow {
  task_id: string;
  folder_id: string;
  created_at: number;
}

export type TaskExportStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface TaskExportRow {
  id: string;
  task_id: string;
  user_id: string;
  format: 'json' | 'word' | 'pdf';
  variant: string; // with_answer | blank | ''（json 时空）
  lang: string;    // zh | en | fr
  stage: string;   // 来源 stage 名
  status: TaskExportStatus;
  file_path: string | null;       // 绝对路径，下载时校验存在
  file_name: string | null;       // 给浏览器看的下载名
  size_bytes: number | null;
  error_message: string | null;
  token_hash: string;             // 一次性下载 token 的 SHA-256，下载后清空
  token_consumed: 0 | 1;
  expires_at: number;             // 过期时间戳（ms）；24h
  created_at: number;
  updated_at: number;
}

let db: Database.Database | null = null;

function ensureDir(p: string) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function initSchema(database: Database.Database) {
  database.pragma('journal_mode = WAL');
  database.pragma('foreign_keys = ON');

  database.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user',
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tasks (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'created',
      current_stage TEXT,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL,
      meta_json TEXT NOT NULL DEFAULT '{}',
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_tasks_queued ON tasks(status, created_at ASC);

    CREATE TABLE IF NOT EXISTS upload_quota (
      user_id TEXT NOT NULL,
      day TEXT NOT NULL,
      count INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (user_id, day)
    );

    CREATE TABLE IF NOT EXISTS task_exports (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      format TEXT NOT NULL,
      variant TEXT NOT NULL DEFAULT '',
      lang TEXT NOT NULL DEFAULT 'zh',
      stage TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'pending',
      file_path TEXT,
      file_name TEXT,
      size_bytes INTEGER,
      error_message TEXT,
      token_hash TEXT NOT NULL,
      token_consumed INTEGER NOT NULL DEFAULT 0,
      expires_at INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL,
      FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_task_exports_task ON task_exports(task_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_task_exports_expire ON task_exports(expires_at);
    CREATE INDEX IF NOT EXISTS idx_task_exports_dedup ON task_exports(task_id, format, variant, lang, stage, status, expires_at);

    CREATE TABLE IF NOT EXISTS rate_limit_hits (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      route TEXT NOT NULL,
      ts_ms INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_rate_limit_hits ON rate_limit_hits(user_id, route, ts_ms);

    CREATE TABLE IF NOT EXISTS audit_log (
      id TEXT PRIMARY KEY,
      ts INTEGER NOT NULL,
      user_id TEXT,
      ip TEXT,
      action TEXT NOT NULL,
      target TEXT,
      status TEXT NOT NULL,
      meta_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, ts DESC);

    CREATE TABLE IF NOT EXISTS invite_codes (
      code TEXT PRIMARY KEY,
      created_by TEXT NOT NULL,
      used_by TEXT,
      used_at INTEGER,
      expires_at INTEGER,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS task_shares (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      token_hash TEXT NOT NULL,
      expires_at INTEGER,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_task_shares_task ON task_shares(task_id);
    CREATE INDEX IF NOT EXISTS idx_task_shares_hash ON task_shares(token_hash);

    CREATE TABLE IF NOT EXISTS llm_usage (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      tokens INTEGER NOT NULL DEFAULT 0,
      day TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_llm_usage_user_day ON llm_usage(user_id, day);

    CREATE TABLE IF NOT EXISTS folders (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      parent_id TEXT,
      sort_order INTEGER NOT NULL DEFAULT 1000,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id, parent_id, sort_order);

    CREATE TABLE IF NOT EXISTS task_folders (
      task_id TEXT NOT NULL,
      folder_id TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY(task_id, folder_id),
      FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
      FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_task_folders_folder ON task_folders(folder_id);
    CREATE INDEX IF NOT EXISTS idx_task_folders_task ON task_folders(task_id);
  `);

  // 迁移：为已存在的 users 表补 approved 列（SQLite 不支持 ADD COLUMN IF NOT EXISTS）
  try {
    database.exec('ALTER TABLE users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1');
  } catch {
    // 列已存在，忽略
  }

  // 迁移：每用户每日 LLM token 配额上限
  try {
    database.exec(
      `ALTER TABLE users ADD COLUMN daily_llm_quota INTEGER NOT NULL DEFAULT ${DEFAULT_DAILY_LLM_QUOTA}`
    );
  } catch {
    // 列已存在，忽略
  }

  // 迁移：首次登录引导完成标记
  try {
    database.exec('ALTER TABLE users ADD COLUMN onboarding_done INTEGER NOT NULL DEFAULT 0');
  } catch {
    // 列已存在，忽略
  }

  // 将仍为旧默认 100000 的用户提升到新默认（列已存在的老库不会重跑 ALTER）
  try {
    database
      .prepare('UPDATE users SET daily_llm_quota = ? WHERE daily_llm_quota = 100000')
      .run(DEFAULT_DAILY_LLM_QUOTA);
  } catch {
    // 忽略
  }
}

/**
 * 清理已过期的导出记录与磁盘文件。
 *
 * 触发时机：
 * - 进程启动后立即跑一次（见 `index.ts`）；
 * - 每 30 分钟跑一次（setInterval）；
 * - 用户主动新建/查询导出时也可顺手调用。
 *
 * 清理规则：`expires_at < now` 的全部行删除，并尝试 unlink 对应文件；
 * 文件不存在或 unlink 失败都吞掉（只记 warn），不阻塞主流程。
 */
export function cleanupExpiredExports(): { removed: number } {
  const database = getDb();
  const now = Date.now();
  const rows = database
    .prepare('SELECT id, file_path FROM task_exports WHERE expires_at < ?')
    .all(now) as Array<{ id: string; file_path: string | null }>;

  for (const r of rows) {
    if (r.file_path) {
      try {
        if (fs.existsSync(r.file_path)) fs.unlinkSync(r.file_path);
      } catch (err) {
        console.warn(`[db] cleanup export file failed: ${r.file_path}`, err);
      }
    }
  }

  if (rows.length > 0) {
    const placeholders = rows.map(() => '?').join(',');
    database
      .prepare(`DELETE FROM task_exports WHERE id IN (${placeholders})`)
      .run(...rows.map((r) => r.id));
  }
  return { removed: rows.length };
}

function seedAdmin(database: Database.Database) {
  const email = (process.env.ADMIN_EMAIL || '').trim().toLowerCase();
  const password = process.env.ADMIN_PASSWORD || '';
  if (!email || !password) return;

  const existing = database
    .prepare('SELECT id, password_hash FROM users WHERE email = ?')
    .get(email) as Pick<UserRow, 'id' | 'password_hash'> | undefined;

  const hash = bcrypt.hashSync(password, 10);
  if (!existing) {
    database
      .prepare(
        'INSERT INTO users (id, email, password_hash, role, created_at, approved, daily_llm_quota) VALUES (?, ?, ?, ?, ?, 1, ?)'
      )
      .run(crypto.randomUUID(), email, hash, 'admin', Date.now(), DEFAULT_DAILY_LLM_QUOTA);
    console.log(`[db] seeded admin user: ${email}`);
  } else {
    // 若 .env 中密码与 DB 不一致，则更新（便于改密重启即生效）
    if (!bcrypt.compareSync(password, existing.password_hash)) {
      database
        .prepare('UPDATE users SET password_hash = ?, role = ? WHERE id = ?')
        .run(hash, 'admin', existing.id);
      console.log(`[db] updated admin password from .env: ${email}`);
    }
  }
}

export function getDb(): Database.Database {
  if (db) return db;
  ensureDir(DB_DIR);
  db = new Database(DB_PATH);
  initSchema(db);
  seedAdmin(db);
  return db;
}

/**
 * 写审计日志：覆盖注册/登录/任务启停/导出/删除等关键事件。
 * 失败只记 warn，不阻塞主流程。
 */
export function writeAuditLog(opts: {
  userId?: string | null;
  ip?: string | null;
  action: string;
  target?: string | null;
  status: string;
  meta?: Record<string, unknown> | null;
}): void {
  try {
    getDb()
      .prepare(
        'INSERT INTO audit_log (id, ts, user_id, ip, action, target, status, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
      )
      .run(
        crypto.randomUUID(),
        Date.now(),
        opts.userId ?? null,
        opts.ip ?? null,
        opts.action,
        opts.target ?? null,
        opts.status,
        opts.meta ? JSON.stringify(opts.meta) : null
      );
  } catch (err) {
    console.warn('[audit] writeAuditLog failed:', err);
  }
}

export function todayKey(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}
