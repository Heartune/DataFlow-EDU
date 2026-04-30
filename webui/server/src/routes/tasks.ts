import { Router, type Request, type Response } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import os from 'os';
import crypto from 'crypto';
import { spawn, execFileSync, type ChildProcess } from 'child_process';
import { fileTypeFromFile } from 'file-type';
import chokidar from 'chokidar';
import yaml from 'js-yaml';
import archiver from 'archiver';
import {
  cleanupExpiredExports,
  DEFAULT_DAILY_LLM_QUOTA,
  getDb,
  todayKey,
  writeAuditLog,
  type TaskExportRow,
  type TaskExportStatus,
  type TaskRow,
} from '../db.js';
import { normalizeProgressPayload, normalizeStageDisplayName } from '../stageDisplayName.js';

// 允许编辑/导出的 stage 白名单（防止越权访问任意路径）
const EDITABLE_STAGES = new Set([
  '2_1_generation/2_1_generated_stage_2', // 2.1 原始生成
  '2_1_generation/2_2_balanced',           // 2.2 均衡补题
  '3_2_ambiguity_refined',                 // 3.2 题意修正
  '3_4_domain_refined',                    // 3.4 领域修正
  '3_5_deduplicated',                      // 3.5 去重
  '3_6_synthesized',                       // 3.6 题库增强
  '3_7_translated',                        // 3.7 翻译
  '3_8_mcq_verified',                      // 3.8 选择题校验
]);

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

// ── 全局并发控制 ──────────────────────────────────────────────────────────────
const MAX_CONCURRENT = parseInt(process.env.MAX_CONCURRENT_TASKS ?? '4', 10);
const TASK_TIMEOUT_MS = parseInt(process.env.TASK_TIMEOUT_HOURS ?? '4', 10) * 60 * 60 * 1000;
// original default provider/model/base URL were ZGCA / saved config / provider fallback.
const DEFAULT_LLM_PROVIDER = (process.env.DATAFLOW_LLM_PROVIDER || 'blt').toLowerCase();
const DEFAULT_LLM_MODEL = process.env.DATAFLOW_LLM_MODEL || 'gemini-3-flash-preview-nothinking';
const DEFAULT_LLM_BASE_URL = process.env.DATAFLOW_LLM_BASE_URL || 'https://api.bltcy.ai/v1';

const ETA_MS_PER_10_PAGES_PER_STEP = 2 * 60 * 1000;
const ETA_MANDATORY_STEP_COUNT = 3;
const ETA_OPTIONAL_STAGES = [
  '2.2 知识均衡检查与修正',
  '3.1 题意模糊检查',
  '3.2 题意模糊修正',
  '3.3 考察领域检查',
  '3.4 考察领域修正',
  '3.5 去除重复题目',
  '3.6 题库增强',
  '3.7 多语言翻译',
  '3.8 选择题格式检查',
];
const ETA_OPTIONAL_STAGE_SET = new Set(ETA_OPTIONAL_STAGES);

function estimateStepCountForEta(taskDir: string): number {
  const progressPath = path.join(taskDir, 'progress.json');
  try {
    if (fs.existsSync(progressPath)) {
      const progress = JSON.parse(fs.readFileSync(progressPath, 'utf-8')) as {
        stages?: Array<{ status?: unknown }>;
      };
      if (Array.isArray(progress.stages) && progress.stages.length > 0) {
        const active = progress.stages.filter((s) => s.status !== 'skipped').length;
        if (active > 0) return active;
      }
    }
  } catch {
    /* ignore and fall through */
  }

  const configPath = path.join(taskDir, 'config.yaml');
  try {
    if (fs.existsSync(configPath)) {
      const parsed = yaml.load(fs.readFileSync(configPath, 'utf-8')) as { enabled_stages?: unknown } | null;
      if (parsed && Array.isArray(parsed.enabled_stages)) {
        const enabledOptional = new Set(
          parsed.enabled_stages.filter((name): name is string => typeof name === 'string' && ETA_OPTIONAL_STAGE_SET.has(name))
        );
        return ETA_MANDATORY_STEP_COUNT + enabledOptional.size;
      }
    }
  } catch {
    /* ignore and fall through */
  }

  return ETA_MANDATORY_STEP_COUNT + ETA_OPTIONAL_STAGES.length;
}

function estimateDefaultTotalMsForEta(taskDir: string, currentPages: number | null): number {
  const pageCount = currentPages && currentPages > 0 ? currentPages : 10;
  const pageChunks = Math.max(1, Math.ceil(pageCount / 10));
  const stepCount = Math.max(1, estimateStepCountForEta(taskDir));
  return pageChunks * stepCount * ETA_MS_PER_10_PAGES_PER_STEP;
}

// 等待队列（进程内；重启后 queued 状态任务回退为 created）
interface QueuedTask {
  taskId: string;
  userId: string;
  llmKey: string;
  extraArgs: string[];
  ip: string | null;
}
const pendingQueue: QueuedTask[] = [];

// ── SSE：per-task-id 进程级 watcher + 订阅集 ──────────────────────────────────
interface WatchEntry {
  watcher: ReturnType<typeof chokidar.watch>;
  subs: Set<() => void>;
}
const taskWatchers = new Map<string, WatchEntry>();

// 追踪所有活跃 SSE response，用于 graceful shutdown
const activeSseConns = new Set<Response>();

// ── provider → env var 映射（与 dataflow_edu/serving/llm_client.py LLM_PROVIDERS 对齐）
const PROVIDER_KEY_MAP: Record<string, string> = {
  zaiwen:             'LLM_ZAIWEN_API_KEY',
  zgca:               'LLM_ZGCA_API_KEY',
  gptagent:           'LLM_GPTAGENT_API_KEY',
  aiping:             'LLM_AIPING_API_KEY',
  blt:                'LLM_BLT_API_KEY',
  openrouter_official:'LLM_OPENROUTER_OFFICIAL_API_KEY',
  openrouter:         'LLM_OPENROUTER_API_KEY',
  xiaoai:             'LLM_XIAOAI_API_KEY',
  qiniu:              'LLM_QINIU_API_KEY',
  iflytek:            'LLM_IFLYTEK_API_KEY',
  openai:             'OPENAI_API_KEY',
  // 兜容：部分公有云直连（admin 手动配时可能用到）
  dashscope:          'DASHSCOPE_API_KEY',
  deepseek:           'DEEPSEEK_API_KEY',
  volcengine:         'ARK_API_KEY',
  volcark:            'ARK_API_KEY',
};

// projectRoot 模块级缓存，由 tasksRoutes(projectRoot) 设置后供内部函数使用
let _projectRoot = '';

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

/**
 * 列表/详情里展示的 current_stage：DB 列目前不会被 Python 回写，始终以 progress.json 为准兜底。
 * 已成功任务在 finish_ok 后会清空 current_stage，则用最后一个 succeeded 阶段名作为停留点。
 */
function resolveTaskCurrentStage(
  projectRoot: string,
  userId: string,
  taskId: string,
  dbStage: string | null
): string | null {
  if (dbStage && String(dbStage).trim()) {
    return normalizeStageDisplayName(dbStage);
  }
  const raw = readProgress(userTaskRoot(projectRoot, userId, taskId));
  if (!raw || typeof raw !== 'object') return null;
  const prog = raw as {
    current_stage?: unknown;
    status?: string;
    stages?: Array<{ name?: string; status?: string }>;
  };
  if (typeof prog.current_stage === 'string' && prog.current_stage.trim()) {
    return normalizeStageDisplayName(prog.current_stage);
  }
  if (prog.status === 'succeeded' && Array.isArray(prog.stages)) {
    let lastSucceeded: string | null = null;
    for (const s of prog.stages) {
      if (s && s.status === 'succeeded' && typeof s.name === 'string') lastSucceeded = s.name;
    }
    return normalizeStageDisplayName(lastSucceeded);
  }
  return null;
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
  // 重启后 queued 任务的内存队列已丢失，回退为 created 让用户重新触发
  try {
    const queuedRows = getDb()
      .prepare("SELECT id FROM tasks WHERE status = 'queued'")
      .all() as Array<{ id: string }>;
    if (queuedRows.length > 0) {
      const resetNow = Date.now();
      for (const r of queuedRows) {
        getDb()
          .prepare("UPDATE tasks SET status = 'created', updated_at = ? WHERE id = ?")
          .run(resetNow, r.id);
      }
      console.log(`[tasks] reset ${queuedRows.length} queued task(s) to created on startup`);
    }
  } catch (err) {
    console.error('[tasks] reset queued tasks on startup failed:', err);
  }
  console.log(`[tasks] reconciled ${rows.length} orphan running task(s) on startup`);
}

/** 强杀所有正在运行的子进程（graceful shutdown 用）。返回 Promise，最多等 5 秒。 */
export function killAllChildren(): Promise<void> {
  const procs = [...runningByUser.values()];
  for (const p of procs) {
    try {
      if (process.platform === 'win32' && p.child.pid) {
        spawn('taskkill', ['/pid', String(p.child.pid), '/T', '/F'], { windowsHide: true });
      } else {
        p.child.kill('SIGTERM');
      }
    } catch {
      /* ignore */
    }
  }
  if (procs.length === 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, 5000));
}

/** 向所有活跃 SSE 连接广播 shutdown 事件（graceful shutdown 用）。 */
export function broadcastShutdownSSE(): void {
  for (const res of activeSseConns) {
    try {
      res.write('event: shutdown\ndata: {}\n\n');
      res.end();
    } catch {
      /* ignore */
    }
  }
  activeSseConns.clear();
}

/** 实际 spawn 逻辑（不依赖 Request，供 spawnRunner 和 scheduleNext 共用）。 */
function doSpawn(
  userId: string,
  task: TaskRow,
  llmKey: string,
  extraArgs: string[],
  ip: string | null
): void {
  const projectRoot = _projectRoot;
  const taskDir = userTaskRoot(projectRoot, userId, task.id);
  const pdfPath = path.join(taskDir, 'input.pdf');

  // 解析 provider
  let meta: Record<string, unknown> = {};
  try { meta = JSON.parse(task.meta_json || '{}'); } catch { /* ignore */ }
  // original: const provider = String(meta.provider ?? 'zaiwen').toLowerCase();
  const provider = String(meta.provider ?? DEFAULT_LLM_PROVIDER).toLowerCase();
  const providerEnvKey = PROVIDER_KEY_MAP[provider] ?? PROVIDER_KEY_MAP[DEFAULT_LLM_PROVIDER] ?? 'LLM_BLT_API_KEY';

  const pythonBin = process.env.PYTHON_BIN || 'python';
  const dataflowLocal = path.join(projectRoot, 'DataFlow');
  const pythonPath = [dataflowLocal, projectRoot, process.env.PYTHONPATH || '']
    .filter(Boolean)
    .join(path.delimiter);

  const baseArgs = [
    '-m', 'dataflow_edu.task_runner',
    '--task-id', task.id,
    '--uid', userId,
    '--task-dir', taskDir,
    '--input-pdf', pdfPath,
    '--task-name', task.name,
  ];
  const args = baseArgs.concat(extraArgs);

  const spawnEnv: Record<string, string> = {
    ...process.env as Record<string, string>,
    PYTHONPATH: pythonPath,
    DATAFLOW_NONINTERACTIVE: '1',
    DATAFLOW_TASK_ID: task.id,
    DATAFLOW_TASK_DIR: taskDir,
    DATAFLOW_TASK_INPUT_PDF: pdfPath,
    DATAFLOW_LLM_PROVIDER: provider,
    DATAFLOW_LLM_MODEL: DEFAULT_LLM_MODEL,
    DATAFLOW_LLM_BASE_URL: provider === DEFAULT_LLM_PROVIDER ? DEFAULT_LLM_BASE_URL : (process.env.DATAFLOW_LLM_BASE_URL || ''),
    LLM_API_KEY: llmKey,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
  };
  spawnEnv[providerEnvKey] = llmKey;

  const child = spawn(pythonBin, args, {
    cwd: projectRoot,
    env: spawnEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  runningByUser.set(userId, { taskId: task.id, child, startedAt: Date.now() });

  const logPath = path.join(taskDir, 'runner.log');
  const logStream = fs.createWriteStream(logPath, { flags: 'a' });
  const argsTag = extraArgs.length ? ` args=${extraArgs.join(' ')}` : '';
  logStream.write(`\n===== run started at ${new Date().toISOString()}${argsTag} =====\n`);
  child.stdout?.pipe(logStream, { end: false });
  child.stderr?.pipe(logStream, { end: false });

  meta.started_at = Date.now();
  const db = getDb();
  db.prepare('UPDATE tasks SET status = ?, updated_at = ?, meta_json = ? WHERE id = ?').run('running', meta.started_at, JSON.stringify(meta), task.id);

  writeAuditLog({ userId, ip, action: 'task_start', target: task.id, status: 'ok' });

  // 硬超时
  let timedOut = false;
  const timeoutTimer = setTimeout(() => {
    timedOut = true;
    try {
      if (process.platform === 'win32' && child.pid) {
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
      } else {
        child.kill('SIGTERM');
        setTimeout(() => {
          if (!child.killed) try { child.kill('SIGKILL'); } catch { /* ignore */ }
        }, 5000);
      }
    } catch { /* ignore */ }
  }, TASK_TIMEOUT_MS);

  const taskId = task.id;
  const childTaskDir = taskDir;

  child.on('exit', (code, signal) => {
    clearTimeout(timeoutTimer);
    const wasStopped = stoppingTasks.delete(taskId);
    let finalStatus: 'succeeded' | 'failed' | 'cancelled';
    if (wasStopped) {
      finalStatus = 'cancelled';
    } else if (timedOut) {
      finalStatus = 'failed';
    } else if (code === 0) {
      finalStatus = 'succeeded';
    } else {
      finalStatus = 'failed';
    }
    try {
      const metaUpdate: Record<string, unknown> = { ...meta };
      if (timedOut) metaUpdate.timeout = true;
      getDb()
        .prepare('UPDATE tasks SET status = ?, updated_at = ?, meta_json = ? WHERE id = ?')
        .run(finalStatus, Date.now(), JSON.stringify(metaUpdate), taskId);
    } catch (err) {
      console.error('[tasks] update final status failed:', err);
    }
    if (finalStatus === 'cancelled' || finalStatus === 'failed') {
      const errMsg = timedOut
        ? `任务执行超时（${Math.round(TASK_TIMEOUT_MS / 3600000)}h），已强制终止`
        : finalStatus === 'cancelled'
        ? '任务已被用户停止，子进程被强制结束'
        : `子进程异常退出 (code=${code ?? 'null'}, signal=${signal ?? 'null'})`;
      markOrphanedProgress(childTaskDir, finalStatus, errMsg);
    }

    const auditAction = timedOut ? 'task_timeout' : wasStopped ? 'task_cancel' : finalStatus === 'succeeded' ? 'task_done' : 'task_fail';
    writeAuditLog({ userId, ip, action: auditAction, target: taskId, status: finalStatus });

    runningByUser.delete(userId);
    logStream.write(
      `\n===== run exited code=${code} signal=${signal ?? ''} status=${finalStatus} timeout=${timedOut} at ${new Date().toISOString()} =====\n`
    );
    logStream.end();

    // 读取 task_usage.json 并写入 llm_usage 表
    try {
      const usagePath = path.join(childTaskDir, 'task_usage.json');
      if (fs.existsSync(usagePath)) {
        const usageRaw = JSON.parse(fs.readFileSync(usagePath, 'utf-8')) as { total_tokens?: number };
        const tokens = Number(usageRaw.total_tokens ?? 0);
        if (tokens > 0) {
          getDb()
            .prepare('INSERT INTO llm_usage (id, user_id, task_id, tokens, day, created_at) VALUES (?, ?, ?, ?, ?, ?)')
            .run(crypto.randomUUID(), userId, taskId, tokens, todayKey(), Date.now());
        }
      }
    } catch (err) {
      console.warn('[tasks] write llm_usage failed:', err);
    }

    // 调度下一个等待中的任务
    scheduleNext();
  });
}

/** 从等待队列取出下一个任务并 spawn。 */
function scheduleNext(): void {
  if (runningByUser.size >= MAX_CONCURRENT || pendingQueue.length === 0) return;
  const item = pendingQueue.shift();
  if (!item) return;
  const task = getDb()
    .prepare('SELECT * FROM tasks WHERE id = ?')
    .get(item.taskId) as TaskRow | undefined;
  if (!task || task.status === 'cancelled' || task.status === 'failed') {
    // 任务在队列中被取消或删除，跳过
    scheduleNext();
    return;
  }
  doSpawn(item.userId, task, item.llmKey, item.extraArgs, item.ip);
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
  enabled_stages?: string[];
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
  if (overrides.enabled_stages !== undefined) {
    merged.enabled_stages = overrides.enabled_stages;
  }
  return yaml.dump(merged, { lineWidth: 120, noRefs: true, sortKeys: false });
}

const PPT_MIMES = new Set([
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
  'application/zip', // PPTX 本质是 ZIP，file-type 有时返回此值
]);

function findLibreOffice(): string {
  const candidates =
    process.platform === 'win32'
      ? [
          'C:\\Program Files\\LibreOffice\\program\\soffice.exe',
          'C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe',
          'soffice',
        ]
      : ['libreoffice', 'soffice'];
  for (const cmd of candidates) {
    try {
      execFileSync(cmd, ['--version'], { stdio: 'ignore', timeout: 5000 });
      return cmd;
    } catch {
      // try next
    }
  }
  throw new Error('未找到 LibreOffice，请先安装后再上传 PPT/PPTX 课件');
}

function convertPptToPdf(srcPath: string, outDir: string): void {
  const soffice = findLibreOffice();
  execFileSync(soffice, ['--headless', '--convert-to', 'pdf', '--outdir', outDir, srcPath], {
    timeout: 120_000,
  });
}

export function tasksRoutes(projectRoot: string): Router {
  _projectRoot = projectRoot;
  const router = Router();

  const maxMb = Number(process.env.MAX_UPLOAD_MB || 50);
  const dailyLimit = Number(process.env.DAILY_UPLOAD_LIMIT || 20);

  // diskStorage：先落到 OS 临时目录，校验魔数后再 rename 到任务目录
  const upload = multer({
    storage: multer.diskStorage({
      destination: (_req, _file, cb) => cb(null, os.tmpdir()),
      filename: (_req, _file, cb) => cb(null, `pdf-upload-${crypto.randomUUID()}.tmp`),
    }),
    limits: { fileSize: maxMb * 1024 * 1024 },
    fileFilter: (_req, file, cb) => {
      const isPdf = /\.pdf$/i.test(file.originalname) || file.mimetype === 'application/pdf';
      const isPpt =
        /\.(pptx|ppt)$/i.test(file.originalname) ||
        file.mimetype === 'application/vnd.openxmlformats-officedocument.presentationml.presentation' ||
        file.mimetype === 'application/vnd.ms-powerpoint';
      if (isPdf || isPpt) {
        cb(null, true);
      } else {
        cb(new Error('only_pdf_or_ppt_allowed') as unknown as null, false);
      }
    },
  });

  router.post('/upload-pdf', upload.single('pdf'), async (req: Request, res: Response) => {
    if (!req.user) {
      if (req.file) fs.unlink(req.file.path, () => {});
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    if (!req.file) {
      res.status(400).json({ error: 'missing_file' });
      return;
    }

    // file-type 魔数校验：确认文件内容为 PDF 或 PPT/PPTX
    let ft: { mime: string } | undefined;
    try {
      ft = await fileTypeFromFile(req.file.path);
    } catch {
      fs.unlink(req.file.path, () => {});
      res.status(400).json({ error: 'invalid_file', message: '无法读取文件类型' });
      return;
    }
    const allowedMimes = new Set(['application/pdf', ...PPT_MIMES]);
    if (!ft || !allowedMimes.has(ft.mime)) {
      fs.unlink(req.file.path, () => {});
      res.status(400).json({ error: 'invalid_file', message: '文件内容不是合法的 PDF 或 PPT/PPTX' });
      return;
    }

    const name = String((req.body && req.body.name) || req.file.originalname || '未命名教材').slice(0, 200);
    const VALID_PROVIDERS = new Set(['blt', 'zgca', 'dashscope', 'openai', 'deepseek', 'volcengine', 'volcark']);
    // original fallback: 'zgca'
    const rawProvider = String((req.body && req.body.provider) || DEFAULT_LLM_PROVIDER).toLowerCase().trim();
    const provider = VALID_PROVIDERS.has(rawProvider) ? rawProvider : DEFAULT_LLM_PROVIDER;

    const db = getDb();
    const day = todayKey();
    const quota = db
      .prepare('SELECT count FROM upload_quota WHERE user_id = ? AND day = ?')
      .get(req.user.id, day) as { count: number } | undefined;
    const used = quota?.count ?? 0;
    if (used >= dailyLimit) {
      fs.unlink(req.file.path, () => {});
      res.status(429).json({ error: 'daily_quota_exceeded', limit: dailyLimit });
      return;
    }

    // LLM token 配额检查
    const llmQuotaRow = db
      .prepare('SELECT daily_llm_quota FROM users WHERE id = ?')
      .get(req.user.id) as { daily_llm_quota: number } | undefined;
    const llmDailyLimit = llmQuotaRow?.daily_llm_quota ?? DEFAULT_DAILY_LLM_QUOTA;
    const llmUsedRow = db
      .prepare("SELECT COALESCE(SUM(tokens),0) as used FROM llm_usage WHERE user_id = ? AND day = ?")
      .get(req.user.id, day) as { used: number };
    if (llmUsedRow.used >= llmDailyLimit) {
      fs.unlink(req.file.path, () => {});
      res.status(429).json({ error: 'llm_quota_exceeded', limit: llmDailyLimit });
      return;
    }

    const taskId = crypto.randomUUID();
    const taskDir = userTaskRoot(projectRoot, req.user.id, taskId);
    ensureDir(taskDir);

    const isPptUpload = PPT_MIMES.has(ft.mime);
    if (isPptUpload) {
      // PPT/PPTX：先存到任务目录，再调 LibreOffice 转为 input.pdf
      const ext = /\.(pptx|ppt)$/i.exec(req.file.originalname)?.[0]?.toLowerCase() ?? '.pptx';
      const pptInTask = path.join(taskDir, `input${ext}`);
      try {
        fs.renameSync(req.file.path, pptInTask);
      } catch {
        fs.copyFileSync(req.file.path, pptInTask);
        fs.unlink(req.file.path, () => {});
      }
      try {
        convertPptToPdf(pptInTask, taskDir);
      } catch (e) {
        fs.rmSync(taskDir, { recursive: true, force: true });
        res.status(500).json({
          error: 'ppt_convert_failed',
          message: `PPT 转换失败，请确认服务器已安装 LibreOffice：${(e as Error).message}`,
        });
        return;
      }
      fs.unlink(pptInTask, () => {});
    } else {
      // PDF：直接移动到 input.pdf
      const pdfPath = path.join(taskDir, 'input.pdf');
      try {
        fs.renameSync(req.file.path, pdfPath);
      } catch {
        fs.copyFileSync(req.file.path, pdfPath);
        fs.unlink(req.file.path, () => {});
      }
    }

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
      JSON.stringify({ pdf_size: req.file.size, original_name: req.file.originalname, provider })
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

  /** 请求时校验，然后直接 spawn 或入队（容量满时）。 */
  function spawnRunner(
    req: Request,
    task: TaskRow,
    extraArgs: string[]
  ): SpawnFailure | { ok: true } | { queued: true } {
    if (task.status === 'running') {
      const inMem = runningByUser.get(req.user!.id);
      if (!inMem || inMem.taskId !== task.id) {
        // 孤儿任务：标记失败后继续 spawn
        try {
          getDb()
            .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
            .run('failed', Date.now(), task.id);
        } catch (err) {
          console.error('[tasks] orphan recovery in spawnRunner failed:', err);
          return { error: 'task_already_running', status: 409 };
        }
        const taskDir = userTaskRoot(projectRoot, req.user!.id, task.id);
        markOrphanedProgress(taskDir, 'failed', '检测到孤儿任务（服务端重启），已自动判为失败，准备重新启动');
      } else {
        return { error: 'task_already_running', status: 409 };
      }
    }
    const existing = runningByUser.get(req.user!.id);
    if (existing) {
      return { error: 'user_has_running_task', status: 409, extra: { running_task_id: existing.taskId } };
    }
    // 平台密钥模式优先使用服务端 env。只有平台 key 缺失时才接受浏览器传入的 BYOK，
    // 避免用户浏览器 localStorage 中残留的旧 X-LLM-Key 覆盖生产平台 key。
    const headerLlmKey = String(req.headers['x-llm-key'] || '').trim();
    const taskMeta = (() => {
      try { return JSON.parse(task.meta_json || '{}') as Record<string, unknown>; } catch { return {}; }
    })();
    const provider = String(taskMeta.provider ?? DEFAULT_LLM_PROVIDER).toLowerCase();
    const providerEnvKey = PROVIDER_KEY_MAP[provider] ?? PROVIDER_KEY_MAP[DEFAULT_LLM_PROVIDER];
    const envLlmKey = providerEnvKey ? (process.env[providerEnvKey] || '').trim() : '';
    const llmKey = envLlmKey || headerLlmKey;
    if (!llmKey) {
      return { error: 'missing_llm_key', status: 400 };
    }
    const taskDir = userTaskRoot(projectRoot, req.user!.id, task.id);
    if (!fs.existsSync(path.join(taskDir, 'input.pdf'))) {
      return { error: 'pdf_missing', status: 400 };
    }

    const ip = req.ip ?? null;

    // 容量满：入队等待
    if (runningByUser.size >= MAX_CONCURRENT) {
      pendingQueue.push({ taskId: task.id, userId: req.user!.id, llmKey, extraArgs, ip });
      getDb()
        .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
        .run('queued', Date.now(), task.id);
      return { queued: true };
    }

    doSpawn(req.user!.id, task, llmKey, extraArgs, ip);
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
    if ('queued' in result) {
      res.status(202).json({ task_id: task.id, status: 'queued' });
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
    if ('queued' in result) {
      res.status(202).json({ task_id: task.id, status: 'queued', mode: 'restart' });
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
    const resumeLabel = normalizeStageDisplayName(resumable.name) ?? resumable.name;
    const result = spawnRunner(req, task, ['--resume-from', resumeLabel]);
    if ('ok' in result) {
      res.json({ task_id: task.id, status: 'running', mode: 'resume', resume_from: resumeLabel });
      return;
    }
    if ('queued' in result) {
      res.status(202).json({ task_id: task.id, status: 'queued', mode: 'resume' });
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
      // queued 任务：从内存队列移除并标记 cancelled
      if (task.status === 'queued') {
        const idx = pendingQueue.findIndex((q) => q.taskId === task.id);
        if (idx >= 0) pendingQueue.splice(idx, 1);
        try {
          getDb()
            .prepare('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?')
            .run('cancelled', Date.now(), task.id);
        } catch (err) {
          console.error('[tasks] cancel queued task failed:', err);
          res.status(500).json({ error: 'stop_failed' });
          return;
        }
        writeAuditLog({ userId: req.user.id, ip: req.ip ?? null, action: 'task_cancel', target: task.id, status: 'cancelled' });
        res.json({ task_id: task.id, status: 'cancelled', mode: 'dequeued' });
        return;
      }
      // 孤儿任务恢复：DB 还显示 running 但内存里没有 child
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

  // ── GET /quota ───────────────────────────────────────────────────────────────
  // 返回当前用户今日上传配额使用情况
  router.get('/quota', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const day = todayKey();
    const row = getDb()
      .prepare('SELECT count FROM upload_quota WHERE user_id = ? AND day = ?')
      .get(req.user.id, day) as { count: number } | undefined;
    const used = row?.count ?? 0;
    res.json({ used, limit: dailyLimit, remaining: Math.max(0, dailyLimit - used) });
  });

  // ── GET /llm-quota ───────────────────────────────────────────────────────────
  // 返回当前用户今日 LLM token 配额使用情况 + 平台密钥脱敏提示
  router.get('/llm-quota', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const db = getDb();
    const day = todayKey();
    const userRow = db
      .prepare('SELECT daily_llm_quota FROM users WHERE id = ?')
      .get(req.user.id) as { daily_llm_quota: number } | undefined;
      const limit = userRow?.daily_llm_quota ?? DEFAULT_DAILY_LLM_QUOTA;
    const usedRow = db
      .prepare("SELECT COALESCE(SUM(tokens),0) as used FROM llm_usage WHERE user_id = ? AND day = ?")
      .get(req.user.id, day) as { used: number };
    const used = Number(usedRow.used ?? 0);
    // 平台密钥脱敏：只返回前 8 位 + "..."
    // original: const rawKey = (process.env.LLM_ZGCA_API_KEY || '').trim();
    const quotaProviderEnvKey = PROVIDER_KEY_MAP[DEFAULT_LLM_PROVIDER] ?? 'LLM_BLT_API_KEY';
    const rawKey = (process.env[quotaProviderEnvKey] || '').trim();
    const platformKeyHint = rawKey.length > 8 ? rawKey.slice(0, 8) + '...' : rawKey ? '(已配置)' : '(未配置)';
    res.json({ used, limit, remaining: Math.max(0, limit - used), platform_key_hint: platformKeyHint });
  });

  router.get('/', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const db = getDb();
    const all = req.query.all === '1' && req.user.role === 'admin';
    const folderId = typeof req.query.folder_id === 'string' ? req.query.folder_id.trim() : '';

    let rows: TaskRow[];

    if (folderId === 'uncategorized') {
      // 未分类：不属于当前用户任何文件夹的任务
      rows = db
        .prepare(
          `SELECT t.* FROM tasks t
           WHERE t.user_id = ?
             AND NOT EXISTS (
               SELECT 1 FROM task_folders tf
               JOIN folders f ON f.id = tf.folder_id AND f.user_id = t.user_id
               WHERE tf.task_id = t.id
             )
           ORDER BY t.created_at DESC`
        )
        .all(req.user.id) as TaskRow[];
    } else if (folderId) {
      // 指定文件夹（递归包含所有后代文件夹）
      const folder = db
        .prepare('SELECT id FROM folders WHERE id = ? AND user_id = ?')
        .get(folderId, req.user.id);
      if (!folder) {
        res.status(404).json({ error: 'folder_not_found' });
        return;
      }
      // 收集该文件夹及其所有后代的 ID
      const allUserFolders = db
        .prepare('SELECT id, parent_id FROM folders WHERE user_id = ?')
        .all(req.user.id) as Array<{ id: string; parent_id: string | null }>;
      function collectIds(rootId: string): string[] {
        const ids: string[] = [rootId];
        for (const f of allUserFolders) {
          if (f.parent_id === rootId) ids.push(...collectIds(f.id));
        }
        return ids;
      }
      const folderIds = collectIds(folderId);
      const placeholders = folderIds.map(() => '?').join(',');
      rows = db
        .prepare(
          `SELECT DISTINCT t.* FROM tasks t
           JOIN task_folders tf ON tf.task_id = t.id
           WHERE t.user_id = ? AND tf.folder_id IN (${placeholders})
           ORDER BY t.created_at DESC`
        )
        .all(req.user.id, ...folderIds) as TaskRow[];
    } else if (all) {
      rows = db.prepare('SELECT * FROM tasks ORDER BY created_at DESC').all() as TaskRow[];
    } else {
      rows = db
        .prepare('SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC')
        .all(req.user.id) as TaskRow[];
    }

    // 为当前用户的所有任务批量读取文件夹关联
    const taskIds = rows.map((r) => r.id);
    const foldersByTask: Record<string, Array<{ id: string; name: string }>> = {};
    if (taskIds.length > 0 && !all) {
      const placeholders = taskIds.map(() => '?').join(',');
      const tfRows = db
        .prepare(
          `SELECT tf.task_id, f.id as folder_id, f.name as folder_name
           FROM task_folders tf
           JOIN folders f ON f.id = tf.folder_id AND f.user_id = ?
           WHERE tf.task_id IN (${placeholders})`
        )
        .all(req.user.id, ...taskIds) as Array<{ task_id: string; folder_id: string; folder_name: string }>;
      for (const row of tfRows) {
        if (!foldersByTask[row.task_id]) foldersByTask[row.task_id] = [];
        foldersByTask[row.task_id].push({ id: row.folder_id, name: row.folder_name });
      }
    }

    res.json({
      tasks: rows.map((r) => ({
        id: r.id,
        user_id: r.user_id,
        name: r.name,
        status: r.status,
        current_stage: resolveTaskCurrentStage(projectRoot, r.user_id, r.id, r.current_stage),
        created_at: r.created_at,
        updated_at: r.updated_at,
        meta: safeParse(r.meta_json),
        folders: foldersByTask[r.id] ?? [],
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

    // 当任务成功时附加题目质量摘要
    let summary: ReturnType<typeof computeTaskSummary> | null = null;
    if (task.status === 'succeeded') {
      summary = computeTaskSummary(taskDir);
    }

    res.json({
      task: {
        id: task.id,
        user_id: task.user_id,
        name: task.name,
        status: task.status,
        current_stage: resolveTaskCurrentStage(projectRoot, task.user_id, task.id, task.current_stage),
        created_at: task.created_at,
        updated_at: task.updated_at,
        meta: safeParse(task.meta_json),
      },
      progress: normalizeProgressPayload(readProgress(taskDir)),
      summary,
    });
  });

  /** PATCH /:id — 仅支持重命名（与上传时 name 长度一致） */
  router.patch('/:id', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const taskId = req.params.id;
    const row = getDb()
      .prepare('SELECT * FROM tasks WHERE id = ?')
      .get(taskId) as TaskRow | undefined;
    if (!row || (row.user_id !== req.user.id && req.user.role !== 'admin')) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const raw = (req.body as { name?: unknown })?.name;
    if (typeof raw !== 'string') {
      res.status(400).json({ error: 'name_required' });
      return;
    }
    const name = raw.trim();
    if (!name) {
      res.status(400).json({ error: 'name_empty' });
      return;
    }
    if (name.length > 200) {
      res.status(400).json({ error: 'name_too_long' });
      return;
    }
    const now = Date.now();
    getDb().prepare('UPDATE tasks SET name = ?, updated_at = ? WHERE id = ?').run(name, now, taskId);

    const taskDir = userTaskRoot(projectRoot, row.user_id, taskId);
    const progressPath = path.join(taskDir, 'progress.json');
    try {
      if (fs.existsSync(progressPath)) {
        const prog = JSON.parse(fs.readFileSync(progressPath, 'utf-8')) as Record<string, unknown>;
        if (prog && typeof prog === 'object') {
          prog.task_name = name;
          atomicWriteJson(progressPath, prog);
        }
      }
    } catch (e) {
      console.warn('[tasks] patch task name: progress.json sync failed', e);
    }

    res.json({ id: taskId, name, updated_at: now });
  });

  // ── GET /:id/eta ──────────────────────────────────────────────────────────────
  // 估算当前任务剩余完成时间（hybrid：有历史走历史均值，否则按 PDF 页数与 step 数估算）
  router.get('/:id/eta', (req: Request, res: Response) => {
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

    const now = Date.now();
    // pdf_pages 优先从 task_meta.json（task_runner 在启动时写入），其次从 meta_json
    const taskDir = userTaskRoot(projectRoot, task.user_id, task.id);
    const taskMetaPath = path.join(taskDir, 'task_meta.json');
    let currentPages: number | null = null;
    try {
      if (fs.existsSync(taskMetaPath)) {
        const raw = JSON.parse(fs.readFileSync(taskMetaPath, 'utf-8')) as Record<string, unknown>;
        if (typeof raw.pdf_pages === 'number') currentPages = raw.pdf_pages as number;
      }
    } catch {
      /* 读取失败忽略 */
    }
    const metaForEta = safeParse(task.meta_json) as Record<string, unknown>;
    if (currentPages === null) {
      if (typeof metaForEta.pdf_pages === 'number') currentPages = metaForEta.pdf_pages as number;
    }

    // elapsed 从任务实际启动时刻算起（doSpawn 写入 meta.started_at），fallback 到 created_at
    const startedAt = typeof metaForEta.started_at === 'number'
      ? metaForEta.started_at as number
      : task.created_at;
    const elapsedMs = now - startedAt;

    // 查历史已完成任务
    const history = getDb()
      .prepare(`SELECT created_at, updated_at, meta_json FROM tasks WHERE status = 'succeeded' AND id != ?`)
      .all(task.id) as Array<{ created_at: number; updated_at: number; meta_json: string }>;

    let totalMs = estimateDefaultTotalMsForEta(taskDir, currentPages);
    let method: 'history' | 'pdf_step_default' = 'pdf_step_default';

    if (history.length >= 2) {
      const durations = history.map((h) => h.updated_at - h.created_at).filter((d) => d > 0);
      if (durations.length >= 2) {
        const avgDuration = durations.reduce((a, b) => a + b, 0) / durations.length;
        if (currentPages !== null) {
          // pages 调整：用历史中有 pdf_pages 的任务做线性插值
          const withPages = history
            .map((h) => {
              const m = safeParse(h.meta_json) as Record<string, unknown>;
              return typeof m.pdf_pages === 'number'
                ? { pages: m.pdf_pages as number, duration: h.updated_at - h.created_at }
                : null;
            })
            .filter(Boolean) as Array<{ pages: number; duration: number }>;
          if (withPages.length >= 2) {
            const avgPages = withPages.reduce((a, b) => a + b.pages, 0) / withPages.length;
            if (avgPages > 0) {
              totalMs = avgDuration * (currentPages / avgPages);
            } else {
              totalMs = avgDuration;
            }
          } else {
            totalMs = avgDuration;
          }
        } else {
          totalMs = avgDuration;
        }
        method = 'history';
      }
    }

    const remainingMs = Math.max(0, totalMs - elapsedMs);
    res.json({
      remaining_seconds: Math.round(remainingMs / 1000),
      elapsed_seconds: Math.round(elapsedMs / 1000),
      method,
      show_eta: true,
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

    activeSseConns.add(res);

    const send = (event: string, payload: unknown) => {
      try {
        res.write(`event: ${event}\n`);
        res.write(`data: ${JSON.stringify(payload)}\n\n`);
      } catch { /* ignore */ }
    };

    send('snapshot', { task_id: task.id, status: task.status, progress: normalizeProgressPayload(readProgress(taskDir)) });

    // 共享进程级 watcher：同一个 task_id 的多个 SSE 连接共用同一个 chokidar 实例
    const pushProgress = () => {
      const progress = readProgress(taskDir);
      const fresh = getDb()
        .prepare('SELECT status FROM tasks WHERE id = ?')
        .get(task.id) as { status: string } | undefined;
      send('progress', { task_id: task.id, status: fresh?.status ?? task.status, progress: normalizeProgressPayload(progress) });
    };

    let watchEntry = taskWatchers.get(task.id);
    if (!watchEntry) {
      const watcher = chokidar.watch(progressPath, {
        ignoreInitial: true,
        awaitWriteFinish: { stabilityThreshold: 100, pollInterval: 50 },
      });
      watchEntry = { watcher, subs: new Set() };
      taskWatchers.set(task.id, watchEntry);
      watcher.on('add', () => {
        const entry = taskWatchers.get(task.id);
        entry?.subs.forEach((fn) => fn());
      });
      watcher.on('change', () => {
        const entry = taskWatchers.get(task.id);
        entry?.subs.forEach((fn) => fn());
      });
    }
    watchEntry.subs.add(pushProgress);

    // 心跳 + 检测任务终态
    const heartbeat = setInterval(() => {
      try { res.write(': ping\n\n'); } catch { /* ignore */ }
      const fresh = getDb()
        .prepare('SELECT status FROM tasks WHERE id = ?')
        .get(task.id) as { status: string } | undefined;
      if (
        fresh &&
        (fresh.status === 'succeeded' ||
          fresh.status === 'failed' ||
          fresh.status === 'cancelled')
      ) {
        send('done', { task_id: task.id, status: fresh.status, progress: normalizeProgressPayload(readProgress(taskDir)) });
        cleanup();
      }
    }, 5000);

    let closed = false;
    const cleanup = () => {
      if (closed) return;
      closed = true;
      clearInterval(heartbeat);
      activeSseConns.delete(res);
      // 退订，引用计数归零时销毁 watcher
      const entry = taskWatchers.get(task.id);
      if (entry) {
        entry.subs.delete(pushProgress);
        if (entry.subs.size === 0) {
          entry.watcher.close().catch(() => undefined);
          taskWatchers.delete(task.id);
        }
      }
      try { res.end(); } catch { /* ignore */ }
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
  // 题目统计（统计 Tab）
  // ---------------------------------------------------------------
  router.get('/:id/stats', (req: Request, res: Response) => {
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
    const requestedStage = String(req.query.stage || '').trim();

    // 按 SAMPLE_STAGE_ORDER 找第一个有数据的阶段，汇总所有文件的题目
    // 若请求了特定阶段则优先使用该阶段（不存在数据时降级到自动选择）
    let usedStage = '';
    let stageFiles: string[] = [];
    let allQuestions: Array<Record<string, unknown>> = [];
    const stagesToTry = requestedStage
      ? [requestedStage, ...SAMPLE_STAGE_ORDER.filter((s) => s !== requestedStage)]
      : SAMPLE_STAGE_ORDER;
    for (const stage of stagesToTry) {
      const files = listStageFiles(taskDir, stage);
      const stageQs: Array<Record<string, unknown>> = [];
      for (const f of files) {
        const full = path.join(taskDir, stage.replace(/\//g, path.sep), f);
        const parsed = readJsonSafe(full);
        const { questions } = extractQuestions(parsed);
        stageQs.push(...questions.map((q) => ({
          ...q,
          _id: shortId(String(q.question ?? '') + '\n' + String(q.answer ?? '')),
          _file: f,
        })));
      }
      if (stageQs.length > 0) {
        usedStage = stage;
        stageFiles = files;
        allQuestions = stageQs;
        break;
      }
    }

    if (allQuestions.length === 0) {
      res.status(204).end();
      return;
    }

    // 计算统计（与前端 computeQuestionStats 逻辑保持一致）
    const total = allQuestions.length;
    const levelDist: Record<string, number> = {};
    const typeDist: Record<string, number> = {};
    const diffDist: Record<string, number> = { 易: 0, 中: 0, 难: 0 };
    const categoryDist: Record<string, number> = {};
    const subcategoryDist: Record<string, number> = {};
    const abilityMainDist: Record<string, number> = {};

    for (const q of allQuestions) {
      const l = String(q.ability_level || '未分类');
      levelDist[l] = (levelDist[l] || 0) + 1;

      const t = String(q.type || '未知');
      typeDist[t] = (typeDist[t] || 0) + 1;

      const d = String(q.difficulty || '中');
      if (d in diffDist) diffDist[d]++;

      const cat = String(q.category || '未分类');
      categoryDist[cat] = (categoryDist[cat] || 0) + 1;

      const subcat = String(q.subcategory || '未分类');
      subcategoryDist[subcat] = (subcategoryDist[subcat] || 0) + 1;

      const main = String(q.ability_main || '未分类');
      abilityMainDist[main] = (abilityMainDist[main] || 0) + 1;
    }

    const subjective = ['简答题', '论述题', '计算题', '综合题'];
    const subjCount = subjective.reduce((s, f) => s + (typeDist[f] || 0), 0);
    const subjectiveRatio = total ? String(Math.round((subjCount / total) * 100)) : '0';

    res.json({
      stage: usedStage,
      files: stageFiles,
      total,
      levelDist,
      typeDist,
      diffDist,
      categoryDist,
      subcategoryDist,
      abilityMainDist,
      subjectiveRatio,
      items: allQuestions,
    });
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

  // 新增一条题目
  router.post('/:id/items', (req: Request, res: Response) => {
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
    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    const target = resolveStageFile(taskDir, stage, file);
    if (!target) {
      res.status(400).json({ error: 'invalid_target' });
      return;
    }
    const body = (req.body || {}) as Record<string, unknown>;
    delete body._id;
    delete body._file;
    if (!body.question || typeof body.question !== 'string' || !String(body.question).trim()) {
      res.status(400).json({ error: 'question_required' });
      return;
    }
    const parsed = readJsonSafe(target);
    const { questions, container } = extractQuestions(parsed);
    if (container === 'unknown') {
      res.status(400).json({ error: 'unrecognized_format' });
      return;
    }
    const newItem: Record<string, unknown> = {
      question: '',
      type: '选择题',
      options: [],
      answer: '',
      explanation: '',
      difficulty: '中',
      ...body,
    };
    questions.push(newItem);
    backupBeforeWrite(target);
    try {
      const out = container === 'array' ? questions : { ...(parsed as Record<string, unknown>), questions };
      atomicWriteJson(target, out);
    } catch (err) {
      console.error('[tasks] add item write failed:', err);
      res.status(500).json({ error: 'write_failed' });
      return;
    }
    const newId = shortId(String(newItem.question ?? '') + '\n' + String(newItem.answer ?? ''));
    res.status(201).json({ ok: true, item: { ...newItem, _id: newId, _file: file } });
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

  // ---------------------------------------------------------------
  // M3 异步导出：Word / PDF / JSON 三件套
  //   - POST /:id/export-jobs：创建导出作业，spawn 子进程，返回 download_url（一次性 token）
  //   - GET  /:id/export-jobs：列出当前 task 的导出历史（含状态）
  //   - GET  /:id/export-jobs/:exportId：单个导出状态轮询
  //   - GET  /:id/export-jobs/:exportId/download?token=xxx：一次性 token 下载
  //
  // 安全约束：
  //   - 三个写/查接口都走 requireAuth + getOwnedTask 双重校验；
  //   - 下载接口除 JWT 外还要求 query.token 命中 SHA256(token_hash)；
  //   - token 单次有效，下载完成立即把 token_consumed=1，再次下载需要重新创建作业；
  //   - 24h 后行 + 文件双双过期（cleanupExpiredExports 在 index.ts 启动 + 每 30min 执行）。
  // ---------------------------------------------------------------

  const SUPPORTED_EXPORT_FORMATS = new Set(['json', 'word', 'pdf']);
  const SUPPORTED_EXPORT_VARIANTS = new Set(['with_answer', 'blank']);
  const SUPPORTED_EXPORT_LANGS = new Set(['zh', 'en', 'fr']);
  const EXPORT_TTL_MS = 24 * 60 * 60 * 1000;

  function exportFileExt(format: string): string {
    if (format === 'json') return 'json';
    if (format === 'word') return 'docx';
    if (format === 'pdf') return 'pdf';
    return 'bin';
  }

  function safeFileBase(name: string): string {
    return name.replace(/[^\w\u4e00-\u9fa5\-]+/g, '_').slice(0, 80) || 'task';
  }

  function exportRowToPublic(row: TaskExportRow): Record<string, unknown> {
    // 不暴露 token_hash / file_path 等内部字段
    return {
      id: row.id,
      task_id: row.task_id,
      format: row.format,
      variant: row.variant,
      lang: row.lang,
      stage: row.stage,
      status: row.status,
      file_name: row.file_name,
      size_bytes: row.size_bytes,
      error_message: row.error_message,
      token_consumed: row.token_consumed === 1,
      expires_at: row.expires_at,
      created_at: row.created_at,
      updated_at: row.updated_at,
    };
  }

  function buildDownloadUrl(taskId: string, exportId: string): string {
    return `/api/tasks/${encodeURIComponent(taskId)}/export-jobs/${encodeURIComponent(
      exportId
    )}/download`;
  }

  function spawnExportChild(
    exportId: string,
    task: TaskRow,
    uid: string,
    args: {
      format: string;
      variant: string;
      lang: string;
      stage: string;
      taskDir: string;
      outputPath: string;
    }
  ): void {
    const pythonBin = process.env.PYTHON_BIN || 'python';
    const dataflowLocal = path.join(projectRoot, 'DataFlow');
    const pythonPath = [dataflowLocal, projectRoot, process.env.PYTHONPATH || '']
      .filter(Boolean)
      .join(path.delimiter);

    const childArgs = [
      '-m',
      'dataflow_edu.export',
      '--task-dir',
      args.taskDir,
      '--output',
      args.outputPath,
      '--format',
      args.format,
      '--lang',
      args.lang,
      '--stage',
      args.stage,
      '--task-name',
      task.name,
    ];
    if (args.format !== 'json') {
      childArgs.push('--variant', args.variant);
    }
    if (args.format === 'json') {
      childArgs.push('--keep-raw');
    }

    const child = spawn(pythonBin, childArgs, {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        DATAFLOW_EDU_CONFIG_ONLY: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    const db = getDb();
    db.prepare(
      "UPDATE task_exports SET status = ?, updated_at = ? WHERE id = ?"
    ).run('running', Date.now(), exportId);

    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout?.on('data', (chunk: Buffer) => {
      stdoutBuf += chunk.toString('utf-8');
      if (stdoutBuf.length > 64 * 1024) stdoutBuf = stdoutBuf.slice(-64 * 1024);
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      stderrBuf += chunk.toString('utf-8');
      if (stderrBuf.length > 64 * 1024) stderrBuf = stderrBuf.slice(-64 * 1024);
    });

    child.on('error', (err) => {
      console.error(`[exports] spawn error for ${exportId}:`, err);
      try {
        getDb()
          .prepare(
            'UPDATE task_exports SET status = ?, error_message = ?, updated_at = ? WHERE id = ?'
          )
          .run('failed', `spawn_failed: ${err.message}`, Date.now(), exportId);
      } catch (dbErr) {
        console.error('[exports] update failed status failed:', dbErr);
      }
    });

    child.on('exit', (code) => {
      const now = Date.now();
      if (code === 0 && fs.existsSync(args.outputPath)) {
        let sizeBytes = 0;
        try {
          sizeBytes = fs.statSync(args.outputPath).size;
        } catch {
          /* ignore */
        }
        try {
          getDb()
            .prepare(
              'UPDATE task_exports SET status = ?, file_path = ?, size_bytes = ?, updated_at = ? WHERE id = ?'
            )
            .run('succeeded', args.outputPath, sizeBytes, now, exportId);
        } catch (err) {
          console.error('[exports] mark succeeded failed:', err);
        }
        return;
      }
      // 失败：尝试从 stderr 解析 JSON 错误，否则降级为字符串
      let msg = stderrBuf.trim().slice(-500);
      try {
        const lastLine = stderrBuf.trim().split(/\r?\n/).pop() || '';
        const parsed = JSON.parse(lastLine);
        if (parsed && typeof parsed === 'object' && parsed.message) {
          msg = String(parsed.message).slice(0, 500);
        }
      } catch {
        /* ignore */
      }
      if (!msg) msg = `子进程异常退出 (code=${code ?? 'null'})`;
      try {
        getDb()
          .prepare(
            'UPDATE task_exports SET status = ?, error_message = ?, updated_at = ? WHERE id = ?'
          )
          .run('failed', msg, now, exportId);
      } catch (err) {
        console.error('[exports] mark failed failed:', err);
      }
      // 删除残留的不完整文件
      if (fs.existsSync(args.outputPath)) {
        try {
          fs.unlinkSync(args.outputPath);
        } catch {
          /* ignore */
        }
      }
      void uid;
    });
  }

  router.post('/:id/export-jobs', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }

    const format = String(req.query.format || req.body?.format || '').toLowerCase();
    const variant = String(req.query.variant || req.body?.variant || 'with_answer').toLowerCase();
    const lang = String(req.query.lang || req.body?.lang || 'zh').toLowerCase();
    const stage = String(req.query.stage || req.body?.stage || '3_8_mcq_verified').trim();

    if (!SUPPORTED_EXPORT_FORMATS.has(format)) {
      res.status(400).json({ error: 'invalid_format', message: '仅支持 json/word/pdf' });
      return;
    }
    if (format !== 'json' && !SUPPORTED_EXPORT_VARIANTS.has(variant)) {
      res.status(400).json({ error: 'invalid_variant', message: '仅支持 with_answer/blank' });
      return;
    }
    if (!SUPPORTED_EXPORT_LANGS.has(lang)) {
      res.status(400).json({ error: 'invalid_lang', message: '仅支持 zh/en/fr' });
      return;
    }
    if (!EDITABLE_STAGES.has(stage)) {
      res.status(400).json({ error: 'invalid_stage' });
      return;
    }

    const taskDir = userTaskRoot(projectRoot, req.user.id, task.id);
    if (!fs.existsSync(taskDir)) {
      res.status(404).json({ error: 'task_dir_missing' });
      return;
    }
    const stageDir = path.join(taskDir, stage);
    if (!fs.existsSync(stageDir)) {
      res.status(404).json({
        error: 'stage_not_ready',
        message: '该阶段尚未产出任何文件，无法导出',
      });
      return;
    }

    // 顺手清一遍过期数据
    try {
      cleanupExpiredExports();
    } catch (err) {
      console.warn('[exports] cleanup before create failed:', err);
    }

    // 去重：24h 内相同参数的 pending/running/succeeded 记录直接复用
    const existing = getDb()
      .prepare(
        `SELECT id, token_hash, file_name, expires_at FROM task_exports
         WHERE task_id=? AND format=? AND variant=? AND lang=? AND stage=?
           AND status IN ('pending','running','succeeded') AND expires_at > ?
         ORDER BY created_at DESC LIMIT 1`
      )
      .get(
        task.id,
        format,
        format === 'json' ? '' : variant,
        lang,
        stage,
        Date.now()
      ) as Pick<TaskExportRow, 'id' | 'token_hash' | 'file_name' | 'expires_at'> | undefined;
    if (existing) {
      const exportRow = getDb()
        .prepare('SELECT * FROM task_exports WHERE id = ?')
        .get(existing.id) as TaskExportRow;
      // 重新生成一次性 token 并更新 DB（覆盖旧 token）
      const newToken = crypto.randomBytes(32).toString('base64url');
      const newTokenHash = crypto.createHash('sha256').update(newToken).digest('hex');
      getDb()
        .prepare('UPDATE task_exports SET token_hash=?, token_consumed=0, updated_at=? WHERE id=?')
        .run(newTokenHash, Date.now(), existing.id);
      res.json({
        ok: true,
        export_id: existing.id,
        status: exportRow?.status ?? 'pending',
        file_name: existing.file_name,
        expires_at: existing.expires_at,
        deduped: true,
        token: newToken,
        status_url: `/api/tasks/${encodeURIComponent(task.id)}/export-jobs/${encodeURIComponent(existing.id)}`,
        download_url: buildDownloadUrl(task.id, existing.id),
      });
      return;
    }

    const exportId = crypto.randomUUID();
    const ext = exportFileExt(format);
    const safeBase = safeFileBase(task.name);
    const variantSuffix = format === 'json' ? '' : `_${variant}`;
    const fileName = `${safeBase}_${stage}_${lang}${variantSuffix}.${ext}`;
    const exportDir = path.join(taskDir, '_exports');
    ensureDir(exportDir);
    const outputPath = path.join(exportDir, `${exportId}.${ext}`);

    // 一次性 token：原文 32 字节 base64，DB 只存 SHA-256
    const token = crypto.randomBytes(32).toString('base64url');
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const now = Date.now();
    const expiresAt = now + EXPORT_TTL_MS;

    try {
      getDb()
        .prepare(
          `INSERT INTO task_exports (
            id, task_id, user_id, format, variant, lang, stage,
            status, file_path, file_name, size_bytes, error_message,
            token_hash, token_consumed, expires_at, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL, NULL, ?, 0, ?, ?, ?)`
        )
        .run(
          exportId,
          task.id,
          req.user.id,
          format,
          format === 'json' ? '' : variant,
          lang,
          stage,
          fileName,
          tokenHash,
          expiresAt,
          now,
          now
        );
    } catch (err) {
      console.error('[exports] insert row failed:', err);
      res.status(500).json({ error: 'db_insert_failed' });
      return;
    }

    spawnExportChild(exportId, task, req.user.id, {
      format,
      variant,
      lang,
      stage,
      taskDir,
      outputPath,
    });

    writeAuditLog({ userId: req.user.id, ip: req.ip ?? null, action: 'export_create', target: exportId, status: 'ok', meta: { format, variant, lang, stage, task_id: task.id } });

    res.status(202).json({
      ok: true,
      export_id: exportId,
      status: 'pending' as TaskExportStatus,
      file_name: fileName,
      expires_at: expiresAt,
      token,
      status_url: `/api/tasks/${encodeURIComponent(task.id)}/export-jobs/${encodeURIComponent(
        exportId
      )}`,
      download_url: buildDownloadUrl(task.id, exportId),
    });
  });

  router.get('/:id/export-jobs', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    try {
      cleanupExpiredExports();
    } catch {
      /* ignore */
    }
    const rows = getDb()
      .prepare(
        'SELECT * FROM task_exports WHERE task_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 50'
      )
      .all(task.id, req.user.id) as TaskExportRow[];
    res.json({ items: rows.map(exportRowToPublic) });
  });

  router.get('/:id/export-jobs/:exportId', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    const row = getDb()
      .prepare(
        'SELECT * FROM task_exports WHERE id = ? AND task_id = ? AND user_id = ?'
      )
      .get(req.params.exportId, task.id, req.user.id) as TaskExportRow | undefined;
    if (!row) {
      res.status(404).json({ error: 'export_not_found' });
      return;
    }
    res.json(exportRowToPublic(row));
  });

  // 共用下载逻辑：从 token（string）读取、校验、流式发送
  function handleExportDownload(req: Request, res: Response, token: string): void {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    if (!token) {
      res.status(400).json({ error: 'missing_token' });
      return;
    }

    const db = getDb();
    const row = db
      .prepare('SELECT * FROM task_exports WHERE id = ? AND task_id = ? AND user_id = ?')
      .get(req.params.exportId, task.id, req.user.id) as TaskExportRow | undefined;
    if (!row) {
      res.status(404).json({ error: 'export_not_found' });
      return;
    }
    if (row.expires_at < Date.now()) {
      res.status(410).json({ error: 'expired' });
      return;
    }
    if (row.status !== 'succeeded') {
      res.status(409).json({ error: 'not_ready', status: row.status });
      return;
    }
    if (row.token_consumed === 1) {
      res.status(410).json({ error: 'token_consumed' });
      return;
    }
    const provided = crypto.createHash('sha256').update(token).digest('hex');
    const a = Buffer.from(provided, 'hex');
    const b = Buffer.from(row.token_hash, 'hex');
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
      res.status(403).json({ error: 'invalid_token' });
      return;
    }
    if (!row.file_path || !fs.existsSync(row.file_path)) {
      res.status(410).json({ error: 'file_missing' });
      return;
    }

    try {
      db.prepare('UPDATE task_exports SET token_consumed = 1, updated_at = ? WHERE id = ?').run(
        Date.now(),
        row.id
      );
    } catch (err) {
      console.error('[exports] mark token consumed failed:', err);
    }

    const filename = row.file_name || path.basename(row.file_path);
    const mime =
      row.format === 'pdf'
        ? 'application/pdf'
        : row.format === 'word'
          ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
          : 'application/json; charset=utf-8';
    res.setHeader('Content-Type', mime);
    res.setHeader(
      'Content-Disposition',
      `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`
    );
    const stream = fs.createReadStream(row.file_path);
    stream.on('error', (err) => {
      console.error('[exports] stream error:', err);
      try {
        res.status(500).end();
      } catch {
        /* ignore */
      }
    });
    stream.pipe(res);
  }

  // POST 下载（推荐）：token 在 request body，不出现在 URL / 日志中
  router.post(
    '/:id/export-jobs/:exportId/download',
    (req: Request, res: Response) => {
      const token = String(req.body?.token || '').trim();
      handleExportDownload(req, res, token);
    }
  );

  // GET 下载（已废弃，兼容旧前端）：token 在 query 参数中
  // @deprecated 改用 POST /:id/export-jobs/:exportId/download，body 传 token
  router.get(
    '/:id/export-jobs/:exportId/download',
    (req: Request, res: Response) => {
      const token = String(req.query.token || '').trim();
      handleExportDownload(req, res, token);
    }
  );

  // ── POST /:id/share ───────────────────────────────────────────────────────────
  // 教师为任务生成只读分享链接，可选过期时间
  router.post('/:id/share', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const task = getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }

    const expires: string = String(req.body?.expires || '7d').trim();
    const validExpires = new Set(['1d', '7d', '30d', 'never']);
    if (!validExpires.has(expires)) {
      res.status(400).json({ error: 'invalid_expires', message: '仅支持 1d/7d/30d/never' });
      return;
    }

    const expireMs: Record<string, number | null> = {
      '1d': 24 * 60 * 60 * 1000,
      '7d': 7 * 24 * 60 * 60 * 1000,
      '30d': 30 * 24 * 60 * 60 * 1000,
      never: 0,
    };
    const ttl = expireMs[expires];
    const expiresAt = ttl ? Date.now() + ttl : null;

    const token = crypto.randomBytes(32).toString('base64url');
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const shareId = crypto.randomUUID();

    try {
      getDb()
        .prepare(
          'INSERT INTO task_shares (id, task_id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)'
        )
        .run(shareId, task.id, req.user.id, tokenHash, expiresAt, Date.now());
    } catch (err) {
      console.error('[share] insert failed:', err);
      res.status(500).json({ error: 'db_insert_failed' });
      return;
    }

    writeAuditLog({
      userId: req.user.id,
      ip: req.ip ?? null,
      action: 'share_create',
      target: shareId,
      status: 'ok',
      meta: { task_id: task.id, expires },
    });

    res.json({
      ok: true,
      share_id: shareId,
      token,
      expires_at: expiresAt,
      share_url: `/share/${encodeURIComponent(token)}`,
    });
  });

  // ── DELETE /:id ──────────────────────────────────────────────────────────────
  router.delete('/:id', (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const isAdmin = req.user.role === 'admin';
    const task = isAdmin
      ? (getDb().prepare('SELECT * FROM tasks WHERE id = ?').get(req.params.id) as TaskRow | undefined)
      : getOwnedTask(req, req.params.id);
    if (!task) {
      res.status(404).json({ error: 'task_not_found' });
      return;
    }
    if (task.status === 'running' || task.status === 'queued') {
      res.status(409).json({
        error: 'task_running',
        message: '请先停止任务再删除',
        status: task.status,
      });
      return;
    }
    // 级联删 DB（外键 ON DELETE CASCADE 会自动清 task_exports / upload_quota）
    try {
      getDb().prepare('DELETE FROM tasks WHERE id = ?').run(task.id);
    } catch (err) {
      console.error('[tasks] delete task DB failed:', err);
      res.status(500).json({ error: 'db_delete_failed' });
      return;
    }
    // 异步删文件目录
    const taskDir = userTaskRoot(projectRoot, task.user_id, task.id);
    fs.rm(taskDir, { recursive: true, force: true }, (err) => {
      if (err) console.warn('[tasks] delete task dir failed:', taskDir, err);
    });
    const auditAction = isAdmin && task.user_id !== req.user!.id ? 'admin_task_delete' : 'task_delete';
    writeAuditLog({ userId: req.user!.id, ip: req.ip ?? null, action: auditAction, target: task.id, status: 'ok', meta: { owner: task.user_id } });
    res.json({ ok: true, task_id: task.id });
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

/**
 * 计算任务最终阶段的题目质量摘要（题型/难度/覆盖），与 /stats 接口共享逻辑。
 * 按 SAMPLE_STAGE_ORDER 找第一个有数据的阶段并汇总。
 */
function computeTaskSummary(taskDir: string): {
  stage: string;
  total: number;
  typeDist: Record<string, number>;
  diffDist: Record<string, number>;
  categoryCount: number;
  subcategoryCount: number;
} | null {
  let usedStage = '';
  let allQuestions: Array<Record<string, unknown>> = [];
  for (const stage of SAMPLE_STAGE_ORDER) {
    const files = listStageFiles(taskDir, stage);
    const stageQs: Array<Record<string, unknown>> = [];
    for (const f of files) {
      const full = path.join(taskDir, stage.replace(/\//g, path.sep), f);
      const parsed = readJsonSafe(full);
      const { questions } = extractQuestions(parsed);
      stageQs.push(...questions);
    }
    if (stageQs.length > 0) {
      usedStage = stage;
      allQuestions = stageQs;
      break;
    }
  }
  if (allQuestions.length === 0) return null;

  const typeDist: Record<string, number> = {};
  const diffDist: Record<string, number> = { 易: 0, 中: 0, 难: 0 };
  const categories = new Set<string>();
  const subcategories = new Set<string>();

  for (const q of allQuestions) {
    const t = String(q.type || '未知');
    typeDist[t] = (typeDist[t] || 0) + 1;

    const d = String(q.difficulty || '中');
    if (d in diffDist) diffDist[d]++;

    const cat = String(q.category || '');
    if (cat) categories.add(cat);

    const sub = String(q.subcategory || '');
    if (sub) subcategories.add(sub);
  }

  return {
    stage: usedStage,
    total: allQuestions.length,
    typeDist,
    diffDist,
    categoryCount: categories.size,
    subcategoryCount: subcategories.size,
  };
}
