import { Router, type Request, type Response } from 'express';
import path from 'path';
import crypto from 'crypto';
import { spawn } from 'child_process';
import { getDb, writeAuditLog } from '../db.js';

const NEEDS_MAX_CHARS = 500;
const RATE_LIMIT_PER_MIN = 5;
const RATE_LIMIT_WINDOW_MS = 60 * 1000;
const SPAWN_TIMEOUT_MS = 30 * 1000;

interface SuggestItem {
  name: string;
  dimension?: string;
  description?: string;
  source_url?: string;
}

type SuggestTarget = 'competencies' | 'taxonomy' | 'ability_levels' | 'question_types';

const ROUTE_SUGGEST = '/api/competency/suggest';

/** 持久化滑动窗口限流（存 DB，重启不丢失）。 */
function checkRateLimit(userId: string): { ok: true } | { ok: false; retryAfterMs: number } {
  const db = getDb();
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW_MS;

  const row = db
    .prepare(
      'SELECT COUNT(*) as n, MIN(ts_ms) as earliest FROM rate_limit_hits WHERE user_id=? AND route=? AND ts_ms>?'
    )
    .get(userId, ROUTE_SUGGEST, windowStart) as { n: number; earliest: number | null };

  if (row.n >= RATE_LIMIT_PER_MIN) {
    const earliest = row.earliest ?? now;
    return { ok: false, retryAfterMs: RATE_LIMIT_WINDOW_MS - (now - earliest) };
  }
  db.prepare('INSERT INTO rate_limit_hits(id,user_id,route,ts_ms) VALUES(?,?,?,?)').run(
    crypto.randomUUID(), userId, ROUTE_SUGGEST, now
  );
  return { ok: true };
}

// 每 10 分钟清理 2 个窗口期以前的旧记录，避免表无限增长
setInterval(() => {
  try {
    getDb()
      .prepare('DELETE FROM rate_limit_hits WHERE ts_ms < ?')
      .run(Date.now() - 2 * RATE_LIMIT_WINDOW_MS);
  } catch { /* ignore */ }
}, 10 * 60 * 1000).unref();

interface SubprocessResult {
  ok: boolean;
  competencies?: SuggestItem[];
  target?: SuggestTarget;
  items?: unknown[];
  error?: string;
  message?: string;
  exitCode: number | null;
  rawStdout: string;
  rawStderr: string;
  timedOut: boolean;
}

// 与 dataflow_edu/serving/llm_client.py LLM_PROVIDERS 对齐
// web_search_llm 默认走 BLT provider，但 BYOK key 通过 LLM_API_KEY / provider env 传入
// original default provider: zgca
const DEFAULT_COMPETENCY_PROVIDER = (process.env.DATAFLOW_LLM_PROVIDER || 'blt').toLowerCase();
const COMPETENCY_PROVIDER_KEY_MAP: Record<string, string> = {
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
  dashscope:          'DASHSCOPE_API_KEY',
  deepseek:           'DEEPSEEK_API_KEY',
  volcengine:         'ARK_API_KEY',
};

function runSuggestProcess(
  projectRoot: string,
  payload: { subject: string; grade?: string; book: string; needs: string; provider?: string; target?: SuggestTarget },
  llmKey: string
): Promise<SubprocessResult> {
  return new Promise((resolve) => {
    const pythonBin = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const dataflowLocal = path.join(projectRoot, 'DataFlow');
    const pythonPath = [dataflowLocal, projectRoot, process.env.PYTHONPATH || '']
      .filter(Boolean)
      .join(path.delimiter);

    const args = [
      '-m',
      'dataflow_edu.competency_suggest',
      '--subject',
      payload.subject,
      '--grade',
      payload.grade || '',
      '--book',
      payload.book,
      '--needs',
      payload.needs,
      '--target',
      payload.target || 'competencies',
    ];

    const provider = (payload.provider ?? DEFAULT_COMPETENCY_PROVIDER).toLowerCase();
    const providerEnvKey = COMPETENCY_PROVIDER_KEY_MAP[provider] ?? COMPETENCY_PROVIDER_KEY_MAP[DEFAULT_COMPETENCY_PROVIDER] ?? 'LLM_BLT_API_KEY';
    const spawnEnv: Record<string, string> = {
      ...process.env as Record<string, string>,
      PYTHONPATH: pythonPath,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      DATAFLOW_NONINTERACTIVE: '1',
      LLM_API_KEY: llmKey,
    };
    spawnEnv[providerEnvKey] = llmKey;

    const child = spawn(pythonBin, args, {
      cwd: projectRoot,
      env: spawnEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout?.on('data', (chunk: Buffer) => {
      stdoutBuf += chunk.toString('utf-8');
      if (stdoutBuf.length > 256 * 1024) stdoutBuf = stdoutBuf.slice(-256 * 1024);
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      stderrBuf += chunk.toString('utf-8');
      if (stderrBuf.length > 64 * 1024) stderrBuf = stderrBuf.slice(-64 * 1024);
    });

    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try {
        if (process.platform === 'win32' && child.pid) {
          spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
        } else {
          child.kill('SIGKILL');
        }
      } catch {
        /* ignore */
      }
    }, SPAWN_TIMEOUT_MS);

    child.on('error', (err) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        error: 'spawn_failed',
        message: err.message,
        exitCode: null,
        rawStdout: stdoutBuf,
        rawStderr: stderrBuf,
        timedOut,
      });
    });

    child.on('exit', (code) => {
      clearTimeout(timer);
      // 子进程协议：成功时 stdout 单行 JSON，失败时 stderr 单行 JSON
      if (code === 0) {
        try {
          const parsed = JSON.parse(stdoutBuf.trim().split(/\r?\n/).filter(Boolean).pop() || '{}');
          const target = (payload.target || 'competencies') as SuggestTarget;
          const key = target === 'competencies' ? 'competencies' : target;
          if (parsed && parsed.ok && Array.isArray(parsed[key])) {
            const items = parsed[key] as unknown[];
            resolve({
              ok: true,
              target,
              competencies: target === 'competencies' ? (items as SuggestItem[]) : undefined,
              items,
              exitCode: code,
              rawStdout: stdoutBuf,
              rawStderr: stderrBuf,
              timedOut,
            });
            return;
          }
          if (parsed && parsed.ok && Array.isArray(parsed.competencies)) {
            resolve({
              ok: true,
              competencies: parsed.competencies as SuggestItem[],
              exitCode: code,
              rawStdout: stdoutBuf,
              rawStderr: stderrBuf,
              timedOut,
            });
            return;
          }
        } catch {
          /* fallthrough */
        }
        resolve({
          ok: false,
          error: 'invalid_stdout',
          message: '子进程退出码 0 但 stdout 非合法 JSON',
          exitCode: code,
          rawStdout: stdoutBuf,
          rawStderr: stderrBuf,
          timedOut,
        });
        return;
      }
      // 失败：尝试从 stderr 解析最后一行 JSON
      let errCode = timedOut ? 'timeout' : 'subprocess_failed';
      let errMsg: string | undefined = timedOut ? '联网 LLM 调用超时（30s）' : undefined;
      try {
        const lastLine = stderrBuf.trim().split(/\r?\n/).filter(Boolean).pop() || '';
        const parsed = JSON.parse(lastLine);
        if (parsed && typeof parsed === 'object') {
          if (typeof parsed.error === 'string') errCode = parsed.error;
          if (typeof parsed.message === 'string') errMsg = parsed.message;
        }
      } catch {
        if (!errMsg) errMsg = stderrBuf.trim().slice(-300) || `exit code ${code ?? 'null'}`;
      }
      resolve({
        ok: false,
        error: errCode,
        message: errMsg,
        exitCode: code,
        rawStdout: stdoutBuf,
        rawStderr: stderrBuf,
        timedOut,
      });
    });
  });
}

export function competencyRoutes(projectRoot: string): Router {
  const router = Router();

  router.post('/suggest', async (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const body = (req.body || {}) as {
      subject?: unknown;
      book?: unknown;
      needs?: unknown;
      provider?: unknown;
    };
    const subject = String(body.subject ?? '').trim();
    const book = String(body.book ?? '').trim();
    const needs = String(body.needs ?? '').trim();
    const provider = String(body.provider ?? DEFAULT_COMPETENCY_PROVIDER).toLowerCase().trim();
    if (!subject) {
      res.status(400).json({ error: 'missing_subject' });
      return;
    }
    if (!book) {
      res.status(400).json({ error: 'missing_book' });
      return;
    }
    if (needs.length > NEEDS_MAX_CHARS) {
      res.status(400).json({
        error: 'needs_too_long',
        message: `个性化需求最长 ${NEEDS_MAX_CHARS} 字，当前 ${needs.length} 字`,
      });
      return;
    }

    const providerEnvKey =
      COMPETENCY_PROVIDER_KEY_MAP[provider] ??
      COMPETENCY_PROVIDER_KEY_MAP[DEFAULT_COMPETENCY_PROVIDER] ??
      'LLM_BLT_API_KEY';
    const envLlmKey = (process.env[providerEnvKey] || '').trim();
    const headerLlmKey = String(req.headers['x-llm-key'] || '').trim();
    const llmKey = envLlmKey || headerLlmKey;
    if (!llmKey) {
      res.status(400).json({ error: 'missing_llm_key', message: '服务端未配置 LLM API Key，且请求缺少 X-LLM-Key 请求头' });
      return;
    }

    const limit = checkRateLimit(req.user.id);
    if (!limit.ok) {
      res
        .status(429)
        .set('Retry-After', String(Math.ceil(limit.retryAfterMs / 1000)))
        .json({
          error: 'rate_limited',
          message: `每分钟最多 ${RATE_LIMIT_PER_MIN} 次，请 ${Math.ceil(
            limit.retryAfterMs / 1000
          )}s 后重试`,
        });
      return;
    }

    const result = await runSuggestProcess(projectRoot, { subject, book, needs, provider }, llmKey);
    if (result.ok) {
      res.json({ ok: true, competencies: result.competencies });
      return;
    }
    const status =
      result.error === 'timeout'
        ? 504
        : result.error === 'missing_api_key'
          ? 400
          : result.error === 'needs_too_long'
            ? 400
            : 502;
    res.status(status).json({
      ok: false,
      error: result.error || 'subprocess_failed',
      message: result.message || '联网素养建议失败',
    });
  });

  return router;
}

export function configSuggestRoutes(projectRoot: string): Router {
  const router = Router();

  router.post('/suggest', async (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'unauthorized' });
      return;
    }
    const body = (req.body || {}) as {
      grade?: unknown;
      subject?: unknown;
      book?: unknown;
      needs?: unknown;
      target?: unknown;
      provider?: unknown;
    };
    const grade = String(body.grade ?? '').trim();
    const subject = String(body.subject ?? '').trim();
    const book = String(body.book ?? '未指定教材').trim() || '未指定教材';
    const needs = String(body.needs ?? '').trim();
    const targetRaw = String(body.target ?? '').trim();
    const target = ['taxonomy', 'ability_levels', 'question_types'].includes(targetRaw)
      ? (targetRaw as SuggestTarget)
      : null;
    const provider = String(body.provider ?? DEFAULT_COMPETENCY_PROVIDER).toLowerCase().trim();
    if (!grade) {
      res.status(400).json({ error: 'missing_grade' });
      return;
    }
    if (!subject) {
      res.status(400).json({ error: 'missing_subject' });
      return;
    }
    if (!target) {
      res.status(400).json({ error: 'invalid_target' });
      return;
    }
    if (needs.length > NEEDS_MAX_CHARS) {
      res.status(400).json({
        error: 'needs_too_long',
        message: `个性化需求最长 ${NEEDS_MAX_CHARS} 字，当前 ${needs.length} 字`,
      });
      return;
    }

    const providerEnvKey =
      COMPETENCY_PROVIDER_KEY_MAP[provider] ??
      COMPETENCY_PROVIDER_KEY_MAP[DEFAULT_COMPETENCY_PROVIDER] ??
      'LLM_BLT_API_KEY';
    const envLlmKey = (process.env[providerEnvKey] || '').trim();
    const headerLlmKey = String(req.headers['x-llm-key'] || '').trim();
    const llmKey = envLlmKey || headerLlmKey;
    if (!llmKey) {
      res.status(400).json({ error: 'missing_llm_key', message: '服务端未配置 LLM API Key，且请求缺少 X-LLM-Key 请求头' });
      return;
    }

    const limit = checkRateLimit(req.user.id);
    if (!limit.ok) {
      res
        .status(429)
        .set('Retry-After', String(Math.ceil(limit.retryAfterMs / 1000)))
        .json({
          error: 'rate_limited',
          message: `每分钟最多 ${RATE_LIMIT_PER_MIN} 次，请 ${Math.ceil(
            limit.retryAfterMs / 1000
          )}s 后重试`,
        });
      return;
    }

    const result = await runSuggestProcess(
      projectRoot,
      { grade, subject, book, needs, provider, target },
      llmKey
    );
    if (result.ok) {
      res.json({ ok: true, target, items: result.items || [] });
      return;
    }
    const status =
      result.error === 'timeout'
        ? 504
        : result.error === 'missing_api_key'
          ? 400
          : result.error === 'needs_too_long' || result.error === 'invalid_target' || result.error === 'invalid_input'
            ? 400
            : 502;
    res.status(status).json({
      ok: false,
      error: result.error || 'subprocess_failed',
      message: result.message || '联网配置建议失败',
    });
  });

  return router;
}
