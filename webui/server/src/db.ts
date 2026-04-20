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
  `);
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
