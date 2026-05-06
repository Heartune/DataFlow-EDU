import type { Request, Response, NextFunction, RequestHandler } from 'express';
import jwt from 'jsonwebtoken';
import { getDb } from '../db.js';

export interface AuthUser {
  id: string;
  email: string;
  role: 'admin' | 'user';
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

function getJwtSecret(): string {
  const secret = process.env.JWT_SECRET;
  const isProd = process.env.NODE_ENV === 'production';
  const minLen = isProd ? 32 : 8;
  if (!secret || secret.length < minLen) {
    const msg = isProd
      ? `[fatal] JWT_SECRET 未设置或过短（生产环境需 ≥32 字节），请在 webui/server/.env 中配置强随机串后重启`
      : 'JWT_SECRET 未设置或过短，请在 webui/server/.env 中配置一个长随机串';
    if (isProd) {
      console.error(msg);
      process.exit(1);
    }
    throw new Error(msg);
  }
  return secret;
}

export function signToken(user: AuthUser): string {
  return jwt.sign(user, getJwtSecret(), { expiresIn: '7d' });
}

export const requireAuth: RequestHandler = (req: Request, res: Response, next: NextFunction) => {
  const header = req.headers.authorization || '';
  const m = header.match(/^Bearer\s+(.+)$/i);
  if (!m) {
    res.status(401).json({ error: 'missing_token' });
    return;
  }
  try {
    const decoded = jwt.verify(m[1], getJwtSecret()) as AuthUser & { iat?: number; exp?: number };
    const row = getDb()
      .prepare('SELECT id, email, role FROM users WHERE id = ?')
      .get(decoded.id) as { id: string; email: string; role: string } | undefined;
    if (!row) {
      res.status(401).json({
        error: 'session_stale',
        message: '会话对应的用户不存在（例如数据库曾重置）。请退出后重新登录。',
      });
      return;
    }
    req.user = {
      id: row.id,
      email: row.email,
      role: row.role === 'admin' ? 'admin' : 'user',
    };
    next();
  } catch {
    res.status(401).json({ error: 'invalid_token' });
  }
};

export const requireAdmin: RequestHandler = (req: Request, res: Response, next: NextFunction) => {
  if (!req.user) {
    res.status(401).json({ error: 'missing_token' });
    return;
  }
  if (req.user.role !== 'admin') {
    res.status(403).json({ error: 'forbidden' });
    return;
  }
  next();
};
