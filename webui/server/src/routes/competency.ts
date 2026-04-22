import { Router, type Request, type Response } from 'express';
import path from 'path';
import { spawn } from 'child_process';

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

// userId -> 最近请求时间戳数组（滑动窗口限流，仅进程内内存）
const userHits = new Map<string, number[]>();

function checkRateLimit(userId: string): { ok: true } | { ok: false; retryAfterMs: number } {
  const now = Date.now();
  const arr = (userHits.get(userId) || []).filter((t) => now - t < RATE_LIMIT_WINDOW_MS);
  if (arr.length >= RATE_LIMIT_PER_MIN) {
    const earliest = arr[0];
    return { ok: false, retryAfterMs: RATE_LIMIT_WINDOW_MS - (now - earliest) };
  }
  arr.push(now);
  userHits.set(userId, arr);
  return { ok: true };
}

interface SubprocessResult {
  ok: boolean;
  competencies?: SuggestItem[];
  error?: string;
  message?: string;
  exitCode: number | null;
  rawStdout: string;
  rawStderr: string;
  timedOut: boolean;
}

function runSuggestProcess(
  projectRoot: string,
  payload: { subject: string; book: string; needs: string },
  llmKey: string
): Promise<SubprocessResult> {
  return new Promise((resolve) => {
    const pythonBin = process.env.PYTHON_BIN || 'python';
    const dataflowLocal = path.join(projectRoot, 'DataFlow');
    const pythonPath = [dataflowLocal, projectRoot, process.env.PYTHONPATH || '']
      .filter(Boolean)
      .join(path.delimiter);

    const args = [
      '-m',
      'dataflow_edu.competency_suggest',
      '--subject',
      payload.subject,
      '--book',
      payload.book,
      '--needs',
      payload.needs,
    ];

    const child = spawn(pythonBin, args, {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        DATAFLOW_NONINTERACTIVE: '1',
        LLM_API_KEY: llmKey,
        LLM_ZGCA_API_KEY: llmKey,
        OPENAI_API_KEY: llmKey,
      },
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
    };
    const subject = String(body.subject ?? '').trim();
    const book = String(body.book ?? '').trim();
    const needs = String(body.needs ?? '').trim();
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

    const llmKey = String(req.headers['x-llm-key'] || '').trim();
    if (!llmKey) {
      res.status(400).json({ error: 'missing_llm_key', message: '请求缺少 X-LLM-Key 请求头' });
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

    const result = await runSuggestProcess(projectRoot, { subject, book, needs }, llmKey);
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
