import { Router, type Request, type Response } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { spawn, type ChildProcess } from 'child_process';
import chokidar from 'chokidar';
import yaml from 'js-yaml';
import archiver from 'archiver';
import { getDb, todayKey, type TaskRow } from '../db.js';

// EditView 允许编辑的 stage 白名单（防止越权访问其它路径）
const EDITABLE_STAGES = new Set(['3_4_domain_refined', '3_7_translated', '3_8_mcq_verified']);

// sample-question 抽样按以下顺序找最后一个非空 stage（越靠前越优先）
const SAMPLE_STAGE_ORDER = [
  '3_8_mcq_verified',
  '3_7_translated',
  '3_6_synthesized',
  '3_5_deduplicated',
  '3_4_domain_refined',
  '3_2_ambiguity_refined',
  '2_1_generation/2_2_balanced',
];

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

// 与 task_runner.ProgressTracker._now_iso 同格式（YYYY-MM-DDTHH:mm:ss，无毫秒/时区）
function nowIsoForProgress(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/**
 * 把孤儿 progress.json 改写为终态：
 *   - 顶层 status: running → finalStatus
 *   - stages 中 status==='running' 的全部改为 finalStatus
 *   - 写入 error 字段方便用户看到原因
 * 仅在文件存在时操作。读写失败仅记日志，不抛异常。
 */
function markOrphanedProgress(
  taskDir: string,
  finalStatus: 'failed' | 'cancelled',
  errMsg: string
): void {
  const p = path.join(taskDir, 'progress.json');
  if (!fs.existsSync(p)) return;
  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return;
  }
  if (!raw || typeof raw !== 'object') return;
  const obj = raw as Record<string, unknown> & {
    status?: string;
    error?: string | null;
    finished_at?: string | null;
    stages?: Array<Record<string, unknown> & { status?: string }>;
  };
  const ts = nowIsoForProgress();
  let touched = false;
  if (Array.isArray(obj.stages)) {
    for (const s of obj.stages) {
      if (s && s.status === 'running') {
        s.status = finalStatus;
        (s as Record<string, unknown>).finished_at = ts;
        (s as Record<string, unknown>).error = errMsg;
        touched = true;
      }
    }
  }
  if (obj.status === 'running') {
    obj.status = finalStatus;
    obj.error = errMsg;
    obj.finished_at = ts;
    touched = true;
  }
  if (!touched) return;
  try {
    fs.writeFileSync(p, JSON.stringify(obj, null, 2), 'utf-8');
  } catch (err) {
    console.error('[tasks] markOrphanedProgress write failed:', err);
  }
}

/**
 * 服务端启动时的孤儿任务回收：
 *
 * `runningByUser` 是进程内内存表，`tsx watch` 重启 / 进程崩溃后会丢失。
 * 此时 DB 里仍可能有 status='running' 的任务，并且其 child Python 进程
 * 因为 stdio 管道断开多半已经死掉（即便没死也无法被新进程 kill）。
 * 我们在 server 启动时把它们一律判为 failed，并同步改写 progress.json，
 * 让 UI 能立即看到失败原因，避免用户被永久"假运行中"卡住。
 */
export function reconcileOrphanedRunningTasks(projectRoot: string): void {
  let rows: TaskRow[] = [];
  try {
    rows = getDb()
      .prepare("SELECT * FROM tasks WHERE status = 'running'")
      .all() as TaskRow[];
  } catch (err) {
    console.error('[tasks] reconcileOrphanedRunningTasks query failed:', err);
    return;
  }
  if (!rows.length) return;
  const now = Date.now();
  const errMsg = '服务端在该任务运行期间重启，子进程已丢失。请使用「续跑」从断点继续，或「从头重跑」。';
  for (const r of rows) {
    try {
      getDb()
        .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
        .run('failed', now, r.id);
    } catch (err) {
      console.error(`[tasks] reconcile DB update failed for ${r.id}:`, err);
      continue;
    }
    const taskDir = userTaskRoot(projectRoot, r.user_id, r.id);
    markOrphanedProgress(taskDir, 'failed', errMsg);
  }
  console.log(`[tasks] reconciled ${rows.length} orphan running task(s) on startup`);
}

function shortId(input: string): string {
  return crypto.createHash('sha1').update(input, 'utf-8').digest('hex').slice(0, 12);
}

function listStageFiles(taskDir: string, stage: string): string[] {
  const dir = path.join(taskDir, stage.replace(/\//g, path.sep));
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.toLowerCase().endsWith('.json'))
    .filter((f) => !f.endsWith('.bak'))
    .filter((f) => !/_progress\.json$/i.test(f))
    .sort();
}

function resolveStageFile(taskDir: string, stage: string, file: string): string | null {
  if (!EDITABLE_STAGES.has(stage)) return null;
  if (!file || /[\\/]/.test(file) || file.includes('..')) return null;
  if (!file.toLowerCase().endsWith('.json')) return null;
  const stageDir = path.resolve(taskDir, stage.replace(/\//g, path.sep));
  const full = path.resolve(stageDir, file);
  if (!full.startsWith(stageDir + path.sep) && full !== stageDir) return null;
  if (!fs.existsSync(full)) return null;
  return full;
}

function readJsonSafe(p: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return null;
  }
}

function extractQuestions(parsed: unknown): { questions: Array<Record<string, unknown>>; container: 'questions' | 'array' | 'unknown' } {
  if (Array.isArray(parsed)) {
    return { questions: parsed as Array<Record<string, unknown>>, container: 'array' };
  }
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>;
    if (Array.isArray(obj.questions)) {
      return { questions: obj.questions as Array<Record<string, unknown>>, container: 'questions' };
    }
  }
  return { questions: [], container: 'unknown' };
}

function attachIds(items: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return items.map((it) => {
    const q = String(it.question ?? '');
    const a = String(it.answer ?? '');
    return { ...it, _id: shortId(q + '\n' + a) };
  });
}

// 原子写：写到 .tmp 后 rename，失败时清理
function atomicWriteJson(target: string, data: unknown): void {
  const tmp = target + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf-8');
  fs.renameSync(tmp, target);
}

// 单层 .bak 备份；首次还额外保留 .original.bak
function backupBeforeWrite(filePath: string): void {
  const bak = filePath + '.bak';
  const original = filePath + '.original.bak';
  try {
    if (fs.existsSync(filePath)) {
      if (!fs.existsSync(original)) {
        fs.copyFileSync(filePath, original);
      }
      fs.copyFileSync(filePath, bak);
    }
  } catch (err) {
    console.error('[tasks] backupBeforeWrite failed:', err);
  }
}

function loadPresetYaml(projectRoot: string, presetName: string): Record<string, unknown> | null {
  if (!presetName || /[.\\/]/.test(presetName)) return null;
  const presetsDir = path.join(projectRoot, 'dataflow_edu', 'config', 'presets');
  for (const ext of ['.yaml', '.yml']) {
    const p = path.join(presetsDir, `${presetName}${ext}`);
    if (fs.existsSync(p)) {
      try {
        const parsed = yaml.load(fs.readFileSync(p, 'utf-8'));
        if (parsed && typeof parsed === 'object') {
          return parsed as Record<string, unknown>;
        }
      } catch {
        return null;
      }
    }
  }
  return null;
}

interface WizardOverrides {
  taxonomy?: unknown;
  ability_levels?: unknown;
  question_types?: unknown;
  difficulty_distribution?: unknown;
}

function buildTaskConfigYaml(
  preset: Record<string, unknown> | null,
  overrides: WizardOverrides
): string {
  const merged: Record<string, unknown> = preset ? { ...preset } : {};
  if (overrides.taxonomy !== undefined) merged.taxonomy = overrides.taxonomy;
  if (overrides.ability_levels !== undefined) merged.ability_levels = overrides.ability_levels;
  if (overrides.question_types !== undefined) merged.question_types = overrides.question_types;
  if (overrides.difficulty_distribution !== undefined) {
    merged.difficulty_distribution = overrides.difficulty_distribution;
  }
  return yaml.dump(merged, { lineWidth: 120, noRefs: true, sortKeys: false });
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
      // 兜底回收孤儿：DB 显示 running 但内存里没有对应 child（多半是上次 server 重启遗留）。
      // 此时直接标记为 failed 再继续 spawn，避免用户被永久挡住。
      const inMem = runningByUser.get(req.user!.id);
      if (!inMem || inMem.taskId !== task.id) {
        const now = Date.now();
        try {
          getDb()
            .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
            .run('failed', now, task.id);
        } catch (err) {
          console.error('[tasks] orphan recovery in spawnRunner failed:', err);
          return { error: 'task_already_running', status: 409 };
        }
        const taskDir = userTaskRoot(projectRoot, req.user!.id, task.id);
        markOrphanedProgress(
          taskDir,
          'failed',
          '检测到孤儿任务（服务端重启），已自动判为失败，准备重新启动'
        );
      } else {
        return { error: 'task_already_running', status: 409 };
      }
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
    const childTaskDir = taskDir;
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
      // Windows 下 taskkill /T /F 是强杀，Python 来不及把 progress.json 里
      // status==='running' 的 stage 改成终态，UI 上对应卡片会一直转圈。
      // 这里在子进程退出时统一兜底一次：把 progress.json 里残留 running 的
      // stage 与顶层 status 一并改成 cancelled / failed。
      if (finalStatus === 'cancelled' || finalStatus === 'failed') {
        const errMsg =
          finalStatus === 'cancelled'
            ? '任务已被用户停止，子进程被强制结束'
            : `子进程异常退出 (code=${code ?? 'null'}, signal=${signal ?? 'null'})`;
        markOrphanedProgress(childTaskDir, finalStatus, errMsg);
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
      // 孤儿任务恢复：DB 还显示 running 但内存里没有 child
      // （上次 server 重启时进程被丢失，对应 Python 多半也已死）。
      // 此时也允许"停止"——直接落库为 cancelled，让 UI 解卡。
      if (task.status === 'running') {
        const now = Date.now();
        try {
          getDb()
            .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
            .run('cancelled', now, task.id);
        } catch (err) {
          console.error('[tasks] stop orphan DB update failed:', err);
          res.status(500).json({ error: 'stop_failed' });
          return;
        }
        const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
        markOrphanedProgress(
          taskDir,
          'cancelled',
          '任务孤儿化（服务端重启），已强制标记为已取消'
        );
        res.json({ task_id: task.id, status: 'cancelled', mode: 'orphan_recovered' });
        return;
      }
      // 任务已在终态（succeeded / failed / cancelled），但 progress.json 里
      // 可能还残留 running 的 stage（强杀 Python 时来不及写入终态）。
      // 这里允许用户用「停止」当作"清理 UI 卡死"的兜底入口：把残留的
      // running stage 一并改成 task 当前的终态（succeeded 时则不改，避免覆盖正常完结的状态）。
      if (task.status === 'cancelled' || task.status === 'failed') {
        const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
        markOrphanedProgress(
          taskDir,
          task.status,
          task.status === 'cancelled'
            ? '任务已被停止，UI 残留状态已清理'
            : '任务已失败，UI 残留状态已清理'
        );
        res.json({ task_id: task.id, status: task.status, mode: 'progress_cleaned' });
        return;
      }
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
    // 兜底愈合：task 已在终态但 progress.json 里仍有 running 的 stage
    // （Windows 强杀 Python 时来不及写终态），读取详情时顺便清一次，
    // 让前端 UI 不再卡在转圈状态。succeeded 不动，避免覆盖正常完结。
    if (task.status === 'cancelled' || task.status === 'failed') {
      markOrphanedProgress(
        taskDir,
        task.status,
        task.status === 'cancelled'
          ? '任务已被停止，UI 残留状态已清理'
          : '任务已失败，UI 残留状态已清理'
      );
    }
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

  // ---------------------------------------------------------------
  // Wizard 配置：写入 task_dir/config.yaml；task_runner 优先读取
  // ---------------------------------------------------------------
  router.get('/:id/config', (req: Request, res: Response) => {
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
    const cfgPath = path.join(taskDir, 'config.yaml');
    if (!fs.existsSync(cfgPath)) {
      res.json({ exists: false, config: null });
      return;
    }
    try {
      const raw = fs.readFileSync(cfgPath, 'utf-8');
      const parsed = yaml.load(raw);
      res.json({ exists: true, config: parsed });
    } catch (err) {
      console.error('[tasks] read task config failed:', err);
      res.status(500).json({ error: 'read_config_failed' });
    }
  });

  router.post('/:id/config', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    if (task.status === 'running') {
      res.status(409).json({ error: 'task_already_running' });
      return;
    }
    const body = (req.body || {}) as {
      preset?: string;
      overrides?: WizardOverrides;
    };
    const presetName = String(body.preset || '').trim();
    let preset: Record<string, unknown> | null = null;
    if (presetName) {
      preset = loadPresetYaml(projectRoot, presetName);
      if (!preset) {
        res.status(400).json({ error: 'invalid_preset' });
        return;
      }
    }
    const overrides: WizardOverrides = body.overrides || {};
    const yamlText = buildTaskConfigYaml(preset, overrides);
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    ensureDir(taskDir);
    const cfgPath = path.join(taskDir, 'config.yaml');
    try {
      fs.writeFileSync(cfgPath, yamlText, 'utf-8');
    } catch (err) {
      console.error('[tasks] write task config failed:', err);
      res.status(500).json({ error: 'write_config_failed' });
      return;
    }
    res.json({ ok: true, preset: presetName || null });
  });

  // ---------------------------------------------------------------
  // 抽样：进度页"最新一题预览"
  // ---------------------------------------------------------------
  router.get('/:id/sample-question', (req: Request, res: Response) => {
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
    for (const stage of SAMPLE_STAGE_ORDER) {
      const files = listStageFiles(taskDir, stage);
      for (const f of files) {
        const full = path.join(taskDir, stage.replace(/\//g, path.sep), f);
        const parsed = readJsonSafe(full);
        const { questions } = extractQuestions(parsed);
        if (questions.length === 0) continue;
        const sample = questions[Math.floor(Math.random() * questions.length)];
        res.json({ stage, file: f, sample });
        return;
      }
    }
    res.status(204).end();
  });

  // ---------------------------------------------------------------
  // EditView 列文件
  // ---------------------------------------------------------------
  router.get('/:id/files', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const stage = String(req.query.stage || '').trim();
    if (!EDITABLE_STAGES.has(stage)) {
      res.status(400).json({ error: 'invalid_stage' });
      return;
    }
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const files = listStageFiles(taskDir, stage);
    res.json({ stage, files });
  });

  // 列题（带 sha1 id）
  router.get('/:id/items', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const stage = String(req.query.stage || '').trim();
    const file = String(req.query.file || '').trim();
    const offset = Math.max(0, Number(req.query.offset || 0));
    const limit = Math.max(1, Math.min(500, Number(req.query.limit || 50)));
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const target = resolveStageFile(taskDir, stage, file);
    if (!target) {
      res.status(400).json({ error: 'invalid_target' });
      return;
    }
    const parsed = readJsonSafe(target);
    const { questions } = extractQuestions(parsed);
    const withIds = attachIds(questions);
    const slice = withIds.slice(offset, offset + limit);
    res.json({
      stage,
      file,
      total: withIds.length,
      offset,
      limit,
      items: slice,
    });
  });

  // 修改某条
  router.patch('/:id/items/:itemId', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const stage = String(req.query.stage || '').trim();
    const file = String(req.query.file || '').trim();
    const itemId = String(req.params.itemId || '').trim();
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const target = resolveStageFile(taskDir, stage, file);
    if (!target || !itemId) {
      res.status(400).json({ error: 'invalid_target' });
      return;
    }
    const patch = (req.body || {}) as Record<string, unknown>;
    if (!patch || typeof patch !== 'object') {
      res.status(400).json({ error: 'invalid_body' });
      return;
    }
    delete patch._id;
    const parsed = readJsonSafe(target);
    const { questions, container } = extractQuestions(parsed);
    if (container === 'unknown') {
      res.status(400).json({ error: 'unrecognized_format' });
      return;
    }
    let foundIdx = -1;
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      const id = shortId(String(q.question ?? '') + '\n' + String(q.answer ?? ''));
      if (id === itemId) {
        foundIdx = i;
        break;
      }
    }
    if (foundIdx === -1) {
      res.status(404).json({ error: 'item_not_found' });
      return;
    }
    questions[foundIdx] = { ...questions[foundIdx], ...patch };
    backupBeforeWrite(target);
    try {
      const out = container === 'array' ? questions : { ...(parsed as Record<string, unknown>), questions };
      atomicWriteJson(target, out);
    } catch (err) {
      console.error('[tasks] patch item write failed:', err);
      res.status(500).json({ error: 'write_failed' });
      return;
    }
    const updated = questions[foundIdx];
    const newId = shortId(String(updated.question ?? '') + '\n' + String(updated.answer ?? ''));
    res.json({ ok: true, item: { ...updated, _id: newId } });
  });

  // 删除某条
  router.delete('/:id/items/:itemId', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const stage = String(req.query.stage || '').trim();
    const file = String(req.query.file || '').trim();
    const itemId = String(req.params.itemId || '').trim();
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const target = resolveStageFile(taskDir, stage, file);
    if (!target || !itemId) {
      res.status(400).json({ error: 'invalid_target' });
      return;
    }
    const parsed = readJsonSafe(target);
    const { questions, container } = extractQuestions(parsed);
    if (container === 'unknown') {
      res.status(400).json({ error: 'unrecognized_format' });
      return;
    }
    const before = questions.length;
    const kept = questions.filter((q) => {
      const id = shortId(String(q.question ?? '') + '\n' + String(q.answer ?? ''));
      return id !== itemId;
    });
    if (kept.length === before) {
      res.status(404).json({ error: 'item_not_found' });
      return;
    }
    backupBeforeWrite(target);
    try {
      const out = container === 'array' ? kept : { ...(parsed as Record<string, unknown>), questions: kept };
      atomicWriteJson(target, out);
    } catch (err) {
      console.error('[tasks] delete item write failed:', err);
      res.status(500).json({ error: 'write_failed' });
      return;
    }
    res.json({ ok: true, removed: before - kept.length });
  });

  // ---------------------------------------------------------------
  // 导出：JSON zip
  // ---------------------------------------------------------------
  router.get('/:id/export', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const format = String(req.query.format || 'json').toLowerCase();
    if (format !== 'json') {
      res.status(400).json({ error: 'unsupported_format', message: 'M2 仅支持 json 格式导出，Word/PDF 即将到来' });
      return;
    }
    const stage = String(req.query.stage || '3_8_mcq_verified').trim();
    if (!EDITABLE_STAGES.has(stage)) {
      res.status(400).json({ error: 'invalid_stage' });
      return;
    }
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const stageDir = path.join(taskDir, stage);
    if (!fs.existsSync(stageDir)) {
      res.status(404).json({ error: 'stage_not_ready' });
      return;
    }
    const files = listStageFiles(taskDir, stage);
    if (files.length === 0) {
      res.status(404).json({ error: 'empty_stage' });
      return;
    }
    const safeName = task.name.replace(/[^\w\u4e00-\u9fa5\-]+/g, '_').slice(0, 80) || 'task';
    const zipName = `${safeName}_${stage}.zip`;
    res.setHeader('Content-Type', 'application/zip');
    res.setHeader(
      'Content-Disposition',
      `attachment; filename*=UTF-8''${encodeURIComponent(zipName)}`
    );
    const archive = archiver('zip', { zlib: { level: 9 } });
    archive.on('error', (err) => {
      console.error('[tasks] export archive error:', err);
      try {
        res.status(500).end();
      } catch {
        /* ignore */
      }
    });
    archive.pipe(res);
    for (const f of files) {
      archive.file(path.join(stageDir, f), { name: f });
    }
    archive.finalize();
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
