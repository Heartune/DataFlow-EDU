import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { dataRoutes } from './routes/data.js';
import { configRoutes } from './routes/config.js';
import { pipelineRoutes } from './routes/pipeline.js';
import { authRoutes } from './routes/auth.js';
import { tasksRoutes } from './routes/tasks.js';
import { requireAuth } from './middleware/auth.js';
import { getDb } from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '../../..');

// 初始化 SQLite + admin seed
getDb();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json({ limit: '10mb' }));

app.use('/api/auth', authRoutes());
app.use('/api/tasks', requireAuth, tasksRoutes(projectRoot));

app.use('/api', dataRoutes(projectRoot));
app.use('/api', configRoutes(projectRoot));
app.use('/api', pipelineRoutes());

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
