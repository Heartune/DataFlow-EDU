import Database from 'better-sqlite3';
import bcrypt from 'bcryptjs';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_DIR = path.resolve(__dirname, '../data');
const DB_PATH = path.join(DB_DIR, 'app.db');

export interface UserRow {
  id: string;
  email: string;
  password_hash: string;
  role: 'admin' | 'user';
  created_at: number;
}

export interface TaskRow {
  id: string;
  user_id: string;
  name: string;
  status: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
  meta_json: string;
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
  `);
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
        'INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)'
      )
      .run(crypto.randomUUID(), email, hash, 'admin', Date.now());
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

export function todayKey(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}
