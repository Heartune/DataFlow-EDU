import { Router, type Request, type Response } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { spawn, type ChildProcess } from 'child_process';
import chokidar from 'chokidar';
import { getDb, todayKey, type TaskRow } from '../db.js';

interface RunningProc {
  taskId: string;
  child: ChildProcess;
  startedAt: number;
}

// 单用户互斥锁：同一用户同时只允许一个 running 任务
const runningByUser = new Map<string, RunningProc>();

function userTaskRoot(projectRoot: string, uid: string, taskId: string): string {
  return path.join(projectRoot, 'dataflow_edu', 'data', 'users', uid, taskId);
}

function ensureDir(p: string) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function readProgress(taskDir: string): unknown {
  const p = path.join(taskDir, 'progress.json');
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return null;
  }
}

export function tasksRoutes(projectRoot: string): Router {
  const router = Router();

  const maxMb = Number(process.env.MAX_UPLOAD_MB || 50);
  const dailyLimit = Number(process.env.DAILY_UPLOAD_LIMIT || 20);

  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: maxMb * 1024 * 1024 },
    fileFilter: (_req, file, cb) => {
      const ok = /\.pdf$/i.test(file.originalname) || file.mimetype === 'application/pdf';
      if (ok) {
        cb(null, true);
      } else {
        cb(new Error('only_pdf_allowed') as unknown as null, false);
      }
    },
  });

  router.post('/upload-pdf', upload.single('pdf'), (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    if (!req.file) {
      res.status(400).json({ error: 'missing_file' });
      return;
    }
    const name = String((req.body && req.body.name) || req.file.originalname || '未命名教材').slice(0, 200);

    const db = getDb();
    const day = todayKey();
    const quota = db
      .prepare('SELECT count FROM upload_quota WHERE user_id = ? AND day = ?')
      .get(req.user.id, day) as { count: number } | undefined;
    const used = quota?.count ?? 0;
    if (used >= dailyLimit) {
      res.status(429).json({ error: 'daily_quota_exceeded', limit: dailyLimit });
      return;
    }

    const taskId = crypto.randomUUID();
    const taskDir = userTaskRoot(projectRoot, req.user.id, taskId);
    ensureDir(taskDir);
    const pdfPath = path.join(taskDir, 'input.pdf');
    fs.writeFileSync(pdfPath, req.file.buffer);

    const now = Date.now();
    db.prepare(
      'INSERT INTO tasks (id, user_id, name, status, current_stage, created_at, updated_at, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    ).run(
      taskId,
      req.user.id,
      name,
      'created',
      null,
      now,
      now,
      JSON.stringify({ pdf_size: req.file.size, original_name: req.file.originalname })
    );

    db.prepare(
      'INSERT INTO upload_quota (user_id, day, count) VALUES (?, ?, 1) ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1'
    ).run(req.user.id, day);

    res.json({ task_id: taskId, name, status: 'created' });
  });

  router.post('/:id/run', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const db = getDb();
    const task = db
      .prepare('SELECT * FROM tasks WHERE id = ? AND user_id = ?')
      .get(req.params.id, req.user.id) as TaskRow | undefined;
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    if (task.status === 'running') {
      res.status(409).json({ error: 'task_already_running' });
      return;
    }
    const existing = runningByUser.get(req.user.id);
    if (existing) {
      res.status(409).json({ error: 'user_has_running_task', running_task_id: existing.taskId });
      return;
    }

    const llmKey = String(req.headers['x-llm-key'] || '').trim();
    if (!llmKey) {
      res.status(400).json({ error: 'missing_llm_key', message: '请在 X-LLM-Key 头中携带 BYOK key' });
      return;
    }

    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const pdfPath = path.join(taskDir, 'input.pdf');
    if (!fs.existsSync(pdfPath)) {
      res.status(400).json({ error: 'pdf_missing' });
      return;
    }

    const pythonBin = process.env.PYTHON_BIN || 'python';
    const args = [
      '-m',
      'dataflow_edu.task_runner',
      '--task-id',
      task.id,
      '--uid',
      req.user.id,
      '--task-dir',
      taskDir,
      '--input-pdf',
      pdfPath,
      '--task-name',
      task.name,
    ];

    // 把本地 DataFlow/ 放到 PYTHONPATH 最前，避免 site-packages 同名包覆盖 get_logger 等导出
    const dataflowLocal = path.join(projectRoot, 'DataFlow');
    const pythonPath = [dataflowLocal, projectRoot, process.env.PYTHONPATH || '']
      .filter(Boolean)
      .join(path.delimiter);

    const child = spawn(pythonBin, args, {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
        DATAFLOW_NONINTERACTIVE: '1',
        DATAFLOW_TASK_ID: task.id,
        DATAFLOW_TASK_DIR: taskDir,
        DATAFLOW_TASK_INPUT_PDF: pdfPath,
        LLM_API_KEY: llmKey,
        DASHSCOPE_API_KEY: llmKey,
        OPENAI_API_KEY: llmKey,
        DEEPSEEK_API_KEY: llmKey,
        VOLCENGINE_API_KEY: llmKey,
        ARK_API_KEY: llmKey,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    runningByUser.set(req.user.id, { taskId: task.id, child, startedAt: Date.now() });

    const logPath = path.join(taskDir, 'runner.log');
    const logStream = fs.createWriteStream(logPath, { flags: 'a' });
    logStream.write(`\n===== run started at ${new Date().toISOString()} =====\n`);
    child.stdout?.pipe(logStream, { end: false });
    child.stderr?.pipe(logStream, { end: false });

    db.prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?').run(
      'running',
      Date.now(),
      task.id
    );

    const userId = req.user.id;
    child.on('exit', (code) => {
      const finalStatus = code === 0 ? 'succeeded' : 'failed';
      try {
        getDb()
          .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
          .run(finalStatus, Date.now(), task.id);
      } catch (err) {
        console.error('[tasks] update final status failed:', err);
      }
      runningByUser.delete(userId);
      logStream.write(`\n===== run exited code=${code} at ${new Date().toISOString()} =====\n`);
      logStream.end();
    });

    res.json({ task_id: task.id, status: 'running' });
  });

  router.get('/', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const all = req.query.all === '1' && req.user.role === 'admin';
    const rows = all
      ? (getDb().prepare('SELECT * FROM tasks ORDER BY created_at DESC').all() as TaskRow[])
      : (getDb()
          .prepare('SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC')
          .all(req.user.id) as TaskRow[]);
    res.json({
      tasks: rows.map((r) => ({
        id: r.id,
        user_id: r.user_id,
        name: r.name,
        status: r.status,
        current_stage: r.current_stage,
        created_at: r.created_at,
        updated_at: r.updated_at,
        meta: safeParse(r.meta_json),
      })),
    });
  });

  router.get('/:id', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getDb()
      .prepare('SELECT * FROM tasks WHERE id = ?')
      .get(req.params.id) as TaskRow | undefined;
    if (!task || (task.user_id !== req.user.id && req.user.role !== 'admin')) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const taskDir = userTaskRoot(projectRoot, task.user_id, task.id);
    res.json({
      task: {
        id: task.id,
        user_id: task.user_id,
        name: task.name,
        status: task.status,
        current_stage: task.current_stage,
        created_at: task.created_at,
        updated_at: task.updated_at,
        meta: safeParse(task.meta_json),
      },
      progress: readProgress(taskDir),
    });
  });

  router.get('/:id/events', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getDb()
      .prepare('SELECT * FROM tasks WHERE id = ?')
      .get(req.params.id) as TaskRow | undefined;
    if (!task || (task.user_id !== req.user.id && req.user.role !== 'admin')) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const taskDir = userTaskRoot(projectRoot, task.user_id, task.id);
    const progressPath = path.join(taskDir, 'progress.json');
    ensureDir(taskDir);

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders?.();

    const send = (event: string, payload: unknown) => {
      res.write(`event: ${event}\n`);
      res.write(`data: ${JSON.stringify(payload)}\n\n`);
    };

    // 立即推送一次当前快照
    send('snapshot', { task_id: task.id, status: task.status, progress: readProgress(taskDir) });

    const watcher = chokidar.watch(progressPath, {
      ignoreInitial: true,
      awaitWriteFinish: { stabilityThreshold: 100, pollInterval: 50 },
    });

    const pushProgress = () => {
      const progress = readProgress(taskDir);
      const fresh = getDb()
        .prepare('SELECT status FROM tasks WHERE id = ?')
        .get(task.id) as { status: string } | undefined;
      send('progress', { task_id: task.id, status: fresh?.status ?? task.status, progress });
    };
    watcher.on('add', pushProgress);
    watcher.on('change', pushProgress);

    // 心跳 + 检测任务终态
    const heartbeat = setInterval(() => {
      res.write(': ping\n\n');
      const fresh = getDb()
        .prepare('SELECT status FROM tasks WHERE id = ?')
        .get(task.id) as { status: string } | undefined;
      if (fresh && (fresh.status === 'succeeded' || fresh.status === 'failed')) {
        send('done', { task_id: task.id, status: fresh.status, progress: readProgress(taskDir) });
        cleanup();
      }
    }, 5000);

    let closed = false;
    const cleanup = () => {
      if (closed) return;
      closed = true;
      clearInterval(heartbeat);
      watcher.close().catch(() => undefined);
      res.end();
    };

    req.on('close', cleanup);
    req.on('aborted', cleanup);
  });

  return router;
}

function safeParse(s: string | null | undefined): unknown {
  if (!s) return {};
  try {
    return JSON.parse(s);
  } catch {
    return {};
  }
}
