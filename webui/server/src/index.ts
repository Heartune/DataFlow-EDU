import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { dataRoutes } from './routes/data.js';
import { configRoutes, presetReaderRoutes } from './routes/config.js';
import { pipelineRoutes } from './routes/pipeline.js';
import { authRoutes } from './routes/auth.js';
import { tasksRoutes, reconcileOrphanedRunningTasks } from './routes/tasks.js';
import { competencyRoutes } from './routes/competency.js';
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

app.use(cors());
app.use(express.json({ limit: '10mb' }));

app.use('/api/auth', authRoutes());
app.use('/api/tasks', requireAuth, tasksRoutes(projectRoot));

// 教师端 / 通用：preset 只读接口（WizardView 第 1 步必用）
app.use('/api', requireAuth, presetReaderRoutes(projectRoot));

// 联网素养建议：BYOK + 滑动窗口限流
app.use('/api/competency', requireAuth, competencyRoutes(projectRoot));

// 管理员看板专用：写全局配置 / 读历史 stage 数据 / pipeline 控制
app.use('/api/admin', requireAuth, requireAdmin, dataRoutes(projectRoot));
app.use('/api/admin', requireAuth, requireAdmin, configRoutes(projectRoot));
app.use('/api/admin', requireAuth, requireAdmin, pipelineRoutes());

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

app.listen(PORT, () => {
  console.log(`[edu-webui-server] running at http://localhost:${PORT}`);
});
