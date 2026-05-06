import 'dotenv/config';
import express, { type Request } from 'express';
import cors from 'cors';
import type { CorsOptions } from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { fileURLToPath } from 'url';
import { dataRoutes } from './routes/data.js';
import { configRoutes, presetReaderRoutes } from './routes/config.js';
import { pipelineRoutes } from './routes/pipeline.js';
import { authRoutes } from './routes/auth.js';
import { tasksRoutes, reconcileOrphanedRunningTasks, killAllChildren, broadcastShutdownSSE } from './routes/tasks.js';
import { shareRoutes } from './routes/share.js';
import { competencyRoutes, configSuggestRoutes } from './routes/competency.js';
import { adminUserRoutes } from './routes/admin.js';
import { foldersRoutes } from './routes/folders.js';
import { userConfigRoutes } from './routes/userConfig.js';
import { requireAuth, requireAdmin } from './middleware/auth.js';
import { getDb, cleanupExpiredExports } from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '../../..');

// 初始化 SQLite + admin seed
getDb();
// 回收上次进程残留的"running"任务（tsx watch 重启 / crash 等场景），
// 否则其 DB 状态会永远卡在 running，对应内存里又没有 child，
// 用户既无法停止也无法重跑。
reconcileOrphanedRunningTasks(projectRoot);

// M3：导出文件 24h 后过期；启动时清一遍，并按 30min 节奏轮训。
try {
  const r = cleanupExpiredExports();
  if (r.removed > 0) console.log(`[db] cleaned ${r.removed} expired exports on boot`);
} catch (err) {
  console.warn('[db] cleanupExpiredExports on boot failed', err);
}
setInterval(() => {
  try {
    cleanupExpiredExports();
  } catch (err) {
    console.warn('[db] cleanupExpiredExports interval failed', err);
  }
}, 30 * 60 * 1000).unref();

const app = express();
const PORT = process.env.PORT || 3000;

// Docker 生产部署中 API 位于 Nginx 反代之后，开启后 req.ip / 限流才能使用真实客户端 IP。
app.set('trust proxy', 1);

// CORS：dev 允许 localhost:5173，生产走 CORS_ORIGINS 环境变量（逗号分隔）
const rawOrigins = process.env.CORS_ORIGINS?.split(',').map((s) => s.trim()).filter(Boolean) ?? [];
const devOrigins =
  process.env.NODE_ENV !== 'production'
    ? [
        'http://localhost:5173',
        'http://localhost:3001',
        'http://127.0.0.1:5173',
        'http://127.0.0.1:3001',
      ]
    : [];
const allowedOrigins = [...new Set([...rawOrigins, ...devOrigins])];

/** 开发模式下放行本机任意端口（Vite 5173 被占用时会自动换端口等） */
function isDevLoopbackOrigin(origin: string): boolean {
  try {
    const { protocol, hostname } = new URL(origin);
    if (protocol !== 'http:' && protocol !== 'https:') return false;
    return (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '[::1]' ||
      hostname === '::1'
    );
  } catch {
    return false;
  }
}

function normalizeForwardedHost(value: string | undefined): string | null {
  const first = value?.split(',')[0]?.trim().toLowerCase();
  return first || null;
}

function isReverseProxySameOrigin(origin: string, req: Request): boolean {
  try {
    const originUrl = new URL(origin);
    if (originUrl.protocol !== 'http:' && originUrl.protocol !== 'https:') return false;
    const forwardedHost = normalizeForwardedHost(req.get('x-forwarded-host'));
    const host = normalizeForwardedHost(req.get('host'));
    return [forwardedHost, host].filter(Boolean).includes(originUrl.host.toLowerCase());
  } catch {
    return false;
  }
}

function isAllowedCorsOrigin(origin: string | undefined, req: Request): boolean {
  // 允许无 Origin 请求（服务端直接调用 / curl / healthcheck 等）
  if (!origin) return true;
  if (allowedOrigins.includes(origin)) return true;
  if (process.env.NODE_ENV !== 'production' && isDevLoopbackOrigin(origin)) return true;
  // Docker 生产部署下，浏览器访问 web:80，由 Nginx 同源反代 /api 到 worker:3000。
  // 此时后端应允许与反代入口 Host 完全一致的 Origin，避免 IP:PORT 部署必须手工改 CORS_ORIGINS。
  return isReverseProxySameOrigin(origin, req);
}

app.use(
  cors((req, cb) => {
    const origin = req.get('origin');
    const options: CorsOptions = {
      origin: isAllowedCorsOrigin(origin, req) ? true : false,
      credentials: true,
    };
    cb(null, options);
  })
);

// HTTP 安全头（使用 helmet 默认配置）
app.use(helmet());

app.use(express.json({ limit: '10mb' }));

// 全局兜底限流：200 次/min/IP
const globalLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 200,
  standardHeaders: true,
  legacyHeaders: false,
});
app.use('/api', globalLimiter);

// 健康检查：检查 DB 可读 + 磁盘可写
app.get('/api/healthz', (_, res) => {
  try {
    getDb().prepare('SELECT 1 FROM users LIMIT 1').get();
  } catch (err) {
    console.error('[healthz] DB check failed:', err);
    res.status(503).json({ status: 'error', detail: 'db_unreachable' });
    return;
  }
  const tmpFile = path.join(os.tmpdir(), `.healthz-${Date.now()}`);
  try {
    fs.writeFileSync(tmpFile, '1');
    fs.unlinkSync(tmpFile);
  } catch (err) {
    console.error('[healthz] disk check failed:', err);
    res.status(503).json({ status: 'error', detail: 'disk_unwritable' });
    return;
  }
  res.json({ status: 'ok' });
});

app.use('/api/auth', authRoutes());
app.use('/api/tasks', requireAuth, tasksRoutes(projectRoot));
app.use('/api/folders', requireAuth, foldersRoutes());
app.use('/api/user-config', requireAuth, userConfigRoutes());
// 只读分享：公开接口，无需登录
app.use('/api/share', shareRoutes(projectRoot));

// 教师端 / 通用：preset 只读接口（WizardView 第 1 步必用）
app.use('/api', requireAuth, presetReaderRoutes(projectRoot));

// 联网素养建议：BYOK + 滑动窗口限流
app.use('/api/competency', requireAuth, competencyRoutes(projectRoot));
app.use('/api/config', requireAuth, configSuggestRoutes(projectRoot));

// 管理员看板专用：写全局配置 / 读历史 stage 数据 / pipeline 控制
app.use('/api/admin', requireAuth, requireAdmin, dataRoutes(projectRoot));
app.use('/api/admin', requireAuth, requireAdmin, configRoutes(projectRoot));
app.use('/api/admin', requireAuth, requireAdmin, pipelineRoutes());
// 用户管理：邀请码 + 待审批用户 + 审计日志
app.use('/api/admin', requireAuth, requireAdmin, adminUserRoutes());

if (process.env.NODE_ENV !== 'production') {
  app.get('/', (_, res) => {
    res.type('html').send(`<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DataFlow-EDU WebUI（开发）</title>
<style>
body{font-family:system-ui,sans-serif;max-width:36rem;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#1a1a1a}
code{background:#f3f3f3;padding:0 .25rem;border-radius:4px}
a{color:#0b57d0}
</style>
</head>
<body>
<h1>这是 API 服务（开发模式）</h1>
<p>根路径不托管前端页面。请在项目 <code>webui</code> 目录运行 <code>npm run dev</code>，在终端里查看 Vite 给出的地址（一般为 <a href="http://localhost:5173/">http://localhost:5173/</a>，若占用会自动换端口）。</p>
<p>本服务仅提供 <code>/api/*</code>，当前监听端口：<strong>${PORT}</strong>。</p>
</body>
</html>`);
  });
}

if (process.env.NODE_ENV === 'production') {
  const frontendDist = path.resolve(__dirname, '../frontend/dist');
  app.use(express.static(frontendDist));
  app.get('*', (_, res) => {
    res.sendFile(path.join(frontendDist, 'index.html'));
  });
}

const server = app.listen(PORT, () => {
  console.log(`[edu-webui-server] running at http://localhost:${PORT}`);
});

// Graceful shutdown：SIGTERM（docker stop / systemd stop）/ SIGINT（Ctrl+C）
const doShutdown = async (sig: string) => {
  console.log(`[edu-webui-server] ${sig} received, shutting down...`);
  server.close();
  broadcastShutdownSSE();
  await killAllChildren();
  try { getDb().close(); } catch { /* ignore */ }
  process.exit(0);
};
process.on('SIGTERM', () => void doShutdown('SIGTERM'));
process.on('SIGINT',  () => void doShutdown('SIGINT'));
