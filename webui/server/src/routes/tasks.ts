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

// 被 /stop 主动杀掉的任务 id 集合：child.exit 时据此把最终状态记为 cancelled 而不是 failed
const stoppingTasks = new Set<string>();

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

  type SpawnGuardError =
    | 'task_already_running'
    | 'user_has_running_task'
    | 'missing_llm_key'
    | 'pdf_missing';

  interface SpawnFailure {
    error: SpawnGuardError;
    status: number;
    extra?: Record<string, unknown>;
  }

  function spawnRunner(
    req: Request,
    task: TaskRow,
    extraArgs: string[]
  ): SpawnFailure | { ok: true } {
    if (task.status === 'running') {
      return { error: 'task_already_running', status: 409 };
    }
    const existing = runningByUser.get(req.user!.id);
    if (existing) {
      return {
        error: 'user_has_running_task',
        status: 409,
        extra: { running_task_id: existing.taskId },
      };
    }
    const llmKey = String(req.headers['x-llm-key'] || '').trim();
    if (!llmKey) {
      return { error: 'missing_llm_key', status: 400 };
    }
    const taskDir = userTaskRoot(projectRoot, req.user!.id, task.id);
    const pdfPath = path.join(taskDir, 'input.pdf');
    if (!fs.existsSync(pdfPath)) {
      return { error: 'pdf_missing', status: 400 };
    }

    const pythonBin = process.env.PYTHON_BIN || 'python';
    const baseArgs = [
      '-m',
      'dataflow_edu.task_runner',
      '--task-id',
      task.id,
      '--uid',
      req.user!.id,
      '--task-dir',
      taskDir,
      '--input-pdf',
      pdfPath,
      '--task-name',
      task.name,
    ];
    const args = baseArgs.concat(extraArgs);

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
      // Windows 下让 child 进入独立进程组，方便后面 taskkill /T /F 杀整棵进程树
      windowsHide: true,
    });

    runningByUser.set(req.user!.id, { taskId: task.id, child, startedAt: Date.now() });

    const logPath = path.join(taskDir, 'runner.log');
    const logStream = fs.createWriteStream(logPath, { flags: 'a' });
    const argsTag = extraArgs.length ? ` args=${extraArgs.join(' ')}` : '';
    logStream.write(`\n===== run started at ${new Date().toISOString()}${argsTag} =====\n`);
    child.stdout?.pipe(logStream, { end: false });
    child.stderr?.pipe(logStream, { end: false });

    const db = getDb();
    db.prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?').run(
      'running',
      Date.now(),
      task.id
    );

    const userId = req.user!.id;
    const taskId = task.id;
    child.on('exit', (code, signal) => {
      const wasStopped = stoppingTasks.delete(taskId);
      let finalStatus: 'succeeded' | 'failed' | 'cancelled';
      if (wasStopped) {
        finalStatus = 'cancelled';
      } else if (code === 0) {
        finalStatus = 'succeeded';
      } else {
        finalStatus = 'failed';
      }
      try {
        getDb()
          .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
          .run(finalStatus, Date.now(), taskId);
      } catch (err) {
        console.error('[tasks] update final status failed:', err);
      }
      runningByUser.delete(userId);
      logStream.write(
        `\n===== run exited code=${code} signal=${signal ?? ''} status=${finalStatus} at ${new Date().toISOString()} =====\n`
      );
      logStream.end();
    });

    return { ok: true };
  }

  function getOwnedTask(req: Request, id: string): TaskRow | undefined {
    if (!req.user) return undefined;
    return getDb()
      .prepare('SELECT * FROM tasks WHERE id = ? AND user_id = ?')
      .get(id, req.user.id) as TaskRow | undefined;
  }

  router.post('/:id/run', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const result = spawnRunner(req, task, []);
    if ('ok' in result) {
      res.json({ task_id: task.id, status: 'running' });
      return;
    }
    res.status(result.status).json({ error: result.error, ...(result.extra || {}) });
  });

  router.post('/:id/restart', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const result = spawnRunner(req, task, ['--reset']);
    if ('ok' in result) {
      res.json({ task_id: task.id, status: 'running', mode: 'restart' });
      return;
    }
    res.status(result.status).json({ error: result.error, ...(result.extra || {}) });
  });

  router.post('/:id/resume', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const progress = readProgress(taskDir) as
      | { stages?: Array<{ name: string; status: string }> }
      | null;
    if (!progress || !Array.isArray(progress.stages) || progress.stages.length === 0) {
      res.status(409).json({
        error: 'no_progress_to_resume',
        message: '没有历史进度可续跑，请改用「从头重跑」',
      });
      return;
    }
    const resumable = progress.stages.find(
      (s) => s.status !== 'succeeded' && s.status !== 'skipped'
    );
    if (!resumable) {
      res
        .status(409)
        .json({ error: 'nothing_to_resume', message: '所有阶段都已完成，无需续跑' });
      return;
    }
    const result = spawnRunner(req, task, ['--resume-from', resumable.name]);
    if ('ok' in result) {
      res.json({
        task_id: task.id,
        status: 'running',
        mode: 'resume',
        resume_from: resumable.name,
      });
      return;
    }
    res.status(result.status).json({ error: result.error, ...(result.extra || {}) });
  });

  router.post('/:id/stop', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const proc = runningByUser.get(req.user.id);
    if (!proc || proc.taskId !== task.id) {
      res.status(409).json({ error: 'task_not_running' });
      return;
    }

    stoppingTasks.add(task.id);
    const child = proc.child;
    const pid = child.pid;

    try {
      if (process.platform === 'win32') {
        // Windows 下 child.kill 等价于 TerminateProcess，但不会杀子进程；
        // 用 taskkill /T /F 把整棵进程树（含 MinerU 上传线程等）一起干掉。
        if (pid) {
          spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
        } else {
          child.kill();
        }
      } else {
        child.kill('SIGTERM');
        setTimeout(() => {
          if (!child.killed) {
            try {
              child.kill('SIGKILL');
            } catch {
              /* ignore */
            }
          }
        }, 2000);
      }
    } catch (err) {
      console.error('[tasks] stop kill failed:', err);
      stoppingTasks.delete(task.id);
      res.status(500).json({ error: 'stop_failed' });
      return;
    }

    res.json({ task_id: task.id, status: 'stopping' });
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

  router.get('/:id/log', (req: Request, res: Response) => {
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
    const logPath = path.join(taskDir, 'runner.log');
    const requested = Number(req.query.offset || 0);
    let offset = Number.isFinite(requested) && requested >= 0 ? Math.floor(requested) : 0;

    if (!fs.existsSync(logPath)) {
      res.json({ size: 0, next_offset: 0, lines: [] });
      return;
    }
    let size = 0;
    try {
      size = fs.statSync(logPath).size;
    } catch {
      res.json({ size: 0, next_offset: 0, lines: [] });
      return;
    }
    // restart/重跑可能截短文件 → 从头再读
    if (offset > size) offset = 0;
    if (offset === size) {
      res.json({ size, next_offset: size, lines: [] });
      return;
    }

    let raw = '';
    try {
      const fd = fs.openSync(logPath, 'r');
      try {
        const len = size - offset;
        const buf = Buffer.alloc(len);
        fs.readSync(fd, buf, 0, len, offset);
        raw = buf.toString('utf-8');
      } finally {
        fs.closeSync(fd);
      }
    } catch (err) {
      console.error('[tasks] read log failed:', err);
      res.status(500).json({ error: 'read_log_failed' });
      return;
    }

    // 最后一行不完整就保留到下次
    let consumed = raw.length;
    let body = raw;
    const lastNl = raw.lastIndexOf('\n');
    if (lastNl < 0) {
      // 整段都没有换行：全留到下次
      res.json({ size, next_offset: offset, lines: [] });
      return;
    }
    if (lastNl < raw.length - 1) {
      body = raw.slice(0, lastNl + 1);
      // consumed 按字节数推进 next_offset
      consumed = Buffer.byteLength(body, 'utf-8');
    } else {
      consumed = Buffer.byteLength(body, 'utf-8');
    }

    // 去 ANSI 颜色 + 把 tqdm 用的 \r 当行分隔符
    const ansiRe = /\x1b\[[0-9;]*m/g;
    const stripped = body.replace(ansiRe, '');
    const rawLines = stripped.split(/\r\n|\r|\n/);

    // 信号行白名单
    const reStage = /^=+\s*\[stage (start|ok|FAIL|skip-preserved)\]\s+(.+?)\s*=+\s*$/;
    const rePdfImg = /^\[pdf->img\] (转换|完成)/;
    const reMineruPhase = /^\s*\[(1|2|3)\/3\] /;
    const reUpload = /^\s*✓ \[(\d+)\/(\d+)\] page_/;
    const reDownload = /^\s*⏳ page_\d+\.png:/;
    const reTqdm = /^([^:\s][^:]*?):\s*\d+%\|.*?\|\s*(\d+)\/(\d+)/;
    const reBalanceIter = /^\s*🔄 第 (\d+) 轮迭代/;
    const reBalanceMax = /^最大迭代:\s*(\d+)/;
    const TQDM_TITLES = new Set([
      '阶段1-内容分类',
      '阶段2-题目生成',
      '二义性评估',
      '领域评估',
      '领域清洗',
      '去重',
      '题目合成',
      '合成',
      '翻译',
      '验证',
      'MCQ验证',
      '模糊度',
      '改写',
      '精炼',
    ]);

    const out: string[] = [];
    let lastSig = '';
    for (const ln of rawLines) {
      if (!ln) continue;
      let sig: string | null = null;
      if (reStage.test(ln)) sig = ln.trim();
      else if (rePdfImg.test(ln)) sig = ln.trim();
      else if (reMineruPhase.test(ln)) sig = ln.trim();
      else if (reUpload.test(ln)) sig = ln.trim();
      else if (reDownload.test(ln)) sig = ln.trim();
      else if (reBalanceIter.test(ln)) sig = ln.trim();
      else if (reBalanceMax.test(ln)) sig = ln.trim();
      else {
        const m = reTqdm.exec(ln);
        if (m) {
          const title = m[1].trim();
          if (TQDM_TITLES.has(title)) {
            // 标准化 tqdm 行：只保留标题 + i/N，其余进度条字符忽略
            sig = `${title}: ${m[2]}/${m[3]}`;
          }
        }
      }
      if (!sig) continue;
      if (sig === lastSig) continue;
      lastSig = sig;
      out.push(sig);
    }

    res.json({ size, next_offset: offset + consumed, lines: out });
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
      if (
        fresh &&
        (fresh.status === 'succeeded' ||
          fresh.status === 'failed' ||
          fresh.status === 'cancelled')
      ) {
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
