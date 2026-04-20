import type { Request, Response, NextFunction, RequestHandler } from 'express';
import jwt from 'jsonwebtoken';

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
  if (!secret || secret.length < 8) {
    throw new Error('JWT_SECRET 未设置或过短，请在 webui/server/.env 中配置一个长随机串');
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
    req.user = { id: decoded.id, email: decoded.email, role: decoded.role };
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
