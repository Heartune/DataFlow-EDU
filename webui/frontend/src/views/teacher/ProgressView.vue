<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { api, TOKEN_KEY } from '@/api/client';
import { parseTaskError } from '@/utils/errorMessages';
import DoughnutChart from '@/components/charts/DoughnutChart.vue';

// ── 质量摘要 ──────────────────────────────────────────────────────────────────
interface TaskSummary {
  stage: string;
  total: number;
  typeDist: Record<string, number>;
  diffDist: Record<string, number>;
  categoryCount: number;
  subcategoryCount: number;
}

const summary = ref<TaskSummary | null>(null);

const props = defineProps<{ id: string }>();

const STAGE_DESCRIPTIONS: Record<string, string> = {
  '1.1 PDF转图片': '将所上传的文件拆分为逐页图片，为文字识别做准备',
  '1.2 文字识别': '使用 MinerU 对每页图片进行 OCR，提取正文与公式',
  '2.1 题目生成': '按学科素养与题型配置，调用大模型批量生成题目',
  '2.2 知识均衡检查与修正': '检查题目在各认知层级与知识领域的分布，并自动补题修正偏差',
  '2.2 知识均衡检查': '检查题目在各认知层级与知识领域的分布，并自动补题修正偏差',
  '3.1 题意模糊检查': '识别表述不清晰的题目并标记，为下一步修正做准备',
  '3.2 题意模糊修正': '对标记为模糊的题目重新润色，使题意清晰准确',
  '3.3 考察领域检查': '校验题目所考察的知识点是否与教材范围吻合',
  '3.4 考察领域修正': '修正与教材范围不符或跑题的题目',
  '3.5 去除重复题目': '检测并剔除语义高度相似的重复题目',
  '3.6 题库增强': '使用 AI 为每道题生成详细解题步骤（解析）',
  '3.7 多语言翻译': '将题目翻译为英文、法文等多语言版本',
  '3.8 选择题格式检查': '校验选择题的选项格式与答案标注是否规范',
};

interface StageInfo {
  name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';
  started_at?: string;
  finished_at?: string;
  error?: string;
  note?: string;
}
interface Progress {
  task_id: string;
  task_name: string;
  status: string;
  current_stage: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  stages: StageInfo[];
}
interface TaskMeta {
  pdf_size?: number;
  original_name?: string;
}
interface TaskDetail {
  id: string;
  name: string;
  status: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
  meta: TaskMeta;
}

interface StageProgress {
  current: number;
  total: number;
  unit: string;
  phase?: string;
  indeterminate?: boolean;
  failed?: boolean;
}

const task = ref<TaskDetail | null>(null);
const progress = ref<Progress | null>(null);
const error = ref('');
const actionMsg = ref('');
const actionBusy = ref<'resume' | 'restart' | 'stop' | ''>('');
let abortCtrl: AbortController | null = null;

const stageProgress = ref<Record<string, StageProgress>>({});
const selectedStageName = ref('');
const logOffset = ref(0);
let logTimer: ReturnType<typeof setInterval> | null = null;
let pollingInflight = false;

interface SampleQuestion {
  question?: string;
  answer?: string;
  type?: string;
  category?: string;
  subcategory?: string;
  ability_main?: string;
  ability_level?: string;
  difficulty?: string | number;
  options?: string[];
  explanation?: string;
}

const sample = ref<{ stage: string; data: SampleQuestion } | null>(null);
const sampleLoading = ref(false);
let sampleTimer: ReturnType<typeof setInterval> | null = null;

async function pollSample() {
  if (sampleLoading.value) return;
  sampleLoading.value = true;
  try {
    const resp = await api.get(`/tasks/${props.id}/sample-question`, {
      validateStatus: (s) => s === 200 || s === 204 || s === 404,
    });
    if (resp.status === 200 && resp.data?.sample) {
      sample.value = { stage: resp.data.stage, data: resp.data.sample };
    }
  } catch {
    // ignore
  } finally {
    sampleLoading.value = false;
  }
}

function ensureSamplePolling() {
  const running = isRunning();
  if (running && !sampleTimer) {
    void pollSample();
    sampleTimer = setInterval(() => void pollSample(), 8000);
  } else if (!running && sampleTimer) {
    clearInterval(sampleTimer);
    sampleTimer = null;
    void pollSample();
  } else if (!running && !sample.value) {
    void pollSample();
  }
}

// parser 跨调用的状态机（同一个任务的整个生命周期内累计）
const parserState = {
  currentStage: '' as string,
  // 1.2 OCR
  uploadedI: 0,
  uploadN: 0,
  downloadedI: 0,
  downloadN: 0,
  // 2.1 Generation
  stage1I: 0,
  stage1N: 0,
  stage2I: 0,
  stage2N: 0,
  // 2.2 Balancing
  iterMax: 0,
  iterCur: 0,
};

function resetParserState() {
  parserState.currentStage = '';
  parserState.uploadedI = 0;
  parserState.uploadN = 0;
  parserState.downloadedI = 0;
  parserState.downloadN = 0;
  parserState.stage1I = 0;
  parserState.stage1N = 0;
  parserState.stage2I = 0;
  parserState.stage2N = 0;
  parserState.iterMax = 0;
  parserState.iterCur = 0;
}

const overallStatus = computed(() => task.value?.status ?? 'created');
const stageList = computed(() => progress.value?.stages ?? []);
const selectedStage = computed(() => {
  return stageList.value.find((s) => s.name === selectedStageName.value) ?? stageList.value[0] ?? null;
});

const taskErrorInfo = computed(() => parseTaskError(progress.value?.error));

const copyErrorDone = ref(false);
async function copyErrorDetail() {
  const raw = progress.value?.error || '（无错误详情）';
  try {
    await navigator.clipboard.writeText(raw);
  } catch {
    // fallback：创建临时 textarea
    const el = document.createElement('textarea');
    el.value = raw;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  }
  copyErrorDone.value = true;
  setTimeout(() => { copyErrorDone.value = false; }, 2000);
}

const errorLabel: Record<string, string> = {
  no_progress_to_resume: '没有可恢复的历史进度，请改用「从头重新生成」',
  nothing_to_resume: '所有阶段都已完成，无需继续',
  user_has_running_task: '你已有任务正在生成，等它结束后再启动新任务',
  task_already_running: '任务已在运行中',
  task_not_running: '任务当前未在运行，无需停止',
  missing_llm_key: 'LLM Key 未配置，请联系管理员',
  pdf_missing: '原始 PDF 已丢失，无法继续',
  stop_failed: '停止失败，请检查后端日志',
};

const stageStatusClass: Record<StageInfo['status'], string> = {
  pending: 'bg-slate-50 text-slate-400 border-slate-200',
  running: 'bg-amber-50 text-amber-700 border-amber-300 ring-1 ring-amber-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  skipped: 'bg-slate-100 text-slate-500 border-slate-200',
  cancelled: 'bg-amber-50 text-amber-700 border-amber-200',
};

const stageDot: Record<StageInfo['status'], string> = {
  pending: '○',
  running: '◐',
  succeeded: '●',
  failed: '✕',
  skipped: '–',
  cancelled: '◯',
};

const timelineStatusLabel: Record<StageInfo['status'], string> = {
  pending: '待开始',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  skipped: '已跳过',
  cancelled: '已取消',
};

function timelineDotClass(status: StageInfo['status']) {
  const m: Record<StageInfo['status'], string> = {
    pending: 'bg-slate-200 ring-slate-300',
    running: 'bg-amber-400 ring-amber-200 animate-pulse',
    succeeded: 'bg-emerald-500 ring-emerald-200',
    failed: 'bg-rose-500 ring-rose-200',
    skipped: 'bg-slate-300 ring-slate-200',
    cancelled: 'bg-amber-300 ring-amber-200',
  };
  return m[status];
}

function timelineConnectorClass(prev: StageInfo) {
  if (prev.status === 'succeeded') return 'bg-emerald-400';
  if (prev.status === 'skipped') return 'bg-slate-300';
  if (prev.status === 'failed' || prev.status === 'cancelled') return 'bg-rose-200';
  return 'bg-slate-200';
}

function timelineTextClass(status: StageInfo['status']) {
  const m: Record<StageInfo['status'], string> = {
    pending: 'text-slate-400',
    running: 'text-amber-600',
    succeeded: 'text-emerald-600',
    failed: 'text-rose-600',
    skipped: 'text-slate-500',
    cancelled: 'text-amber-700',
  };
  return m[status];
}

/** 时间线节点标题：仅取「1.1」「2.1」等编号前缀 */
function stageTimelineCode(name: string) {
  const m = name.match(/^(\d+\.\d+)/);
  return m ? m[1] : name.split(/\s/)[0] || name;
}

function selectStage(name: string) {
  selectedStageName.value = name;
}

async function loadInitial() {
  try {
    const { data } = await api.get(`/tasks/${props.id}`);
    task.value = data.task;
    progress.value = data.progress;
    summary.value = data.summary ?? null;
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载失败';
  }
}

/** 任务从运行中结束为成功时，SSE 只更新状态不会带 summary，需与详情接口对齐 */
async function refreshTaskSummary() {
  try {
    const { data } = await api.get(`/tasks/${props.id}`);
    summary.value = data.summary ?? null;
  } catch {
    // ignore
  }
}

async function callAction(kind: 'resume' | 'restart' | 'stop') {
  if (actionBusy.value) return;
  actionBusy.value = kind;
  actionMsg.value = '';
  try {
    await api.post(`/tasks/${props.id}/${kind}`);
    // 重启 SSE 监听以快速接到新一轮 progress
    abortCtrl?.abort();
    if (kind === 'resume' || kind === 'restart') {
      logOffset.value = 0;
      stageProgress.value = {};
      resetParserState();
    }
    await loadInitial();
    startSse();
    ensureLogPolling();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    actionMsg.value =
      errorLabel[code] || err?.response?.data?.message || err?.message || '操作失败';
  } finally {
    actionBusy.value = '';
  }
}

function onResume() {
  void callAction('resume');
}
function onRestart() {
  if (!window.confirm('从头重新生成会清空所有已生成的数据，原始教材文件将保留。确认继续？')) return;
  void callAction('restart');
}
function onStop() {
  if (!window.confirm('停止后当前步骤将被中断，未完成的阶段会被标记为已取消。确认停止？'))
    return;
  void callAction('stop');
}

function startSse() {
  // EventSource 不支持自定义 header，把 token 作为 query 参数；
  // 后端 requireAuth 仅识别 Authorization 头，所以这里改用 ?token= 的兼容做法：直接用 fetch 流也行，
  // 但简单起见，我们让 SSE 共用 cookie/同源 + Authorization 头不可用，
  // 因此我们走「先短轮询」+ EventSource 提示信息读取的混合：实际上 EventSource 仍需要鉴权。
  //
  // 实现策略：通过 axios 拿到 progress 快照后，使用 EventSource 但带 withCredentials=false，
  // 后端 SSE 路由要求 Bearer，因此这里把 token 拼进 URL 头不可行；改为用 fetch + ReadableStream 自己实现 SSE。
  startSseViaFetch();
}

async function startSseViaFetch() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return;
  abortCtrl = new AbortController();
  try {
    const resp = await fetch(`/api/tasks/${props.id}/events`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: abortCtrl.signal,
    });
    if (!resp.ok || !resp.body) {
      console.warn('SSE 连接失败', resp.status);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buf = '';
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        handleSseBlock(block);
      }
    }
  } catch (err) {
    console.warn('SSE 中断', err);
  }
}

let pendingProgress: Progress | null = null;
let pendingStatus: string | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    if (pendingProgress) {
      progress.value = pendingProgress;
      pendingProgress = null;
    }
    if (pendingStatus && task.value) {
      task.value.status = pendingStatus as TaskDetail['status'];
      pendingStatus = null;
    }
  }, 200);
}

function handleSseBlock(block: string) {
  let event = 'message';
  let dataLine = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLine += line.slice(5).trim();
  }
  if (!dataLine) return;
  try {
    const payload = JSON.parse(dataLine);
    if (event === 'snapshot' || event === 'progress' || event === 'done') {
      if (payload.progress) pendingProgress = payload.progress;
      if (payload.status) pendingStatus = payload.status;
      // snapshot/done 立即生效，progress 走节流
      if (event === 'snapshot' || event === 'done') {
        if (flushTimer) {
          clearTimeout(flushTimer);
          flushTimer = null;
        }
        if (pendingProgress) {
          progress.value = pendingProgress;
          pendingProgress = null;
        }
        if (pendingStatus && task.value) {
          task.value.status = pendingStatus as TaskDetail['status'];
          pendingStatus = null;
        }
        ensureLogPolling();
      } else {
        scheduleFlush();
        ensureLogPolling();
      }
    }
  } catch {
    // ignore
  }
}

// ============ runner.log 增量轮询 + 阶段内进度解析 ============

function isRunning(): boolean {
  return task.value?.status === 'running';
}

async function pollLog(): Promise<void> {
  if (pollingInflight) return;
  pollingInflight = true;
  try {
    const { data } = await api.get(`/tasks/${props.id}/log`, {
      params: { offset: logOffset.value },
    });
    if (typeof data?.next_offset === 'number') {
      logOffset.value = data.next_offset;
    }
    if (Array.isArray(data?.lines) && data.lines.length) {
      parseLines(data.lines as string[]);
    }
  } catch {
    // 忽略：轮询失败下一轮再来
  } finally {
    pollingInflight = false;
  }
}

function ensureLogPolling(): void {
  const running = isRunning();
  if (running && !logTimer) {
    void pollLog();
    logTimer = setInterval(() => void pollLog(), 1500);
  } else if (!running && logTimer) {
    clearInterval(logTimer);
    logTimer = null;
    // 终态后再拉一次，把最后一段 log 吃完
    void pollLog();
  }
}

function setStageProgress(name: string, info: Partial<StageProgress>) {
  const cur = stageProgress.value[name] || { current: 0, total: 0, unit: '' };
  stageProgress.value = {
    ...stageProgress.value,
    [name]: { ...cur, ...info } as StageProgress,
  };
}

const _STAGE_RE = /^=+\s*\[stage (start|ok|FAIL|skip-preserved)\]\s+(.+?)\s*=+\s*$/;
const _PDF_DONE_RE = /^\[pdf->img\] 完成，共 (\d+) 页/;
const _MINERU_PHASE_RE = /^\s*\[(1|2|3)\/3\] /;
const _UPLOAD_RE = /^\s*✓ \[(\d+)\/(\d+)\] page_/;
const _DOWNLOAD_RE = /^\s*⏳ page_\d+\.png:/;
const _TQDM_RE = /^([^:\s][^:]*?):\s*(\d+)\/(\d+)\s*$/;
const _ITER_RE = /^\s*🔄 第 (\d+) 轮迭代/;
const _ITER_MAX_RE = /^最大迭代:\s*(\d+)/;

function commitFromState(stage: string) {
  if (stage === '1.2 文字识别') {
    const upPct = parserState.uploadN > 0 ? parserState.uploadedI / parserState.uploadN : 0;
    const dlPct =
      parserState.downloadN > 0 ? parserState.downloadedI / parserState.downloadN : 0;
    const merged = Math.round((upPct * 0.5 + dlPct * 0.5) * 100);
    let phase = '申请上传链接';
    if (parserState.downloadedI > 0 || parserState.downloadN > 0) {
      phase = `下载 ${parserState.downloadedI}/${parserState.downloadN || '?'}`;
    } else if (parserState.uploadedI > 0) {
      phase =
        parserState.uploadedI >= parserState.uploadN && parserState.uploadN > 0
          ? '解析中'
          : `上传 ${parserState.uploadedI}/${parserState.uploadN}`;
    }
    setStageProgress(stage, {
      current: merged,
      total: 100,
      unit: '%',
      phase,
      indeterminate: false,
    });
    return;
  }
  if (stage === '2.1 题目生成') {
    const p1 = parserState.stage1N > 0 ? parserState.stage1I / parserState.stage1N : 0;
    const p2 = parserState.stage2N > 0 ? parserState.stage2I / parserState.stage2N : 0;
    const merged = Math.round((p1 * 0.5 + p2 * 0.5) * 100);
    let phase = '阶段1 内容分类';
    if (parserState.stage2I > 0 || parserState.stage2N > 0) {
      phase = `阶段2 题目生成 ${parserState.stage2I}/${parserState.stage2N || '?'}`;
    } else {
      phase = `阶段1 内容分类 ${parserState.stage1I}/${parserState.stage1N || '?'}`;
    }
    setStageProgress(stage, {
      current: merged,
      total: 100,
      unit: '%',
      phase,
      indeterminate: false,
    });
    return;
  }
  if (stage === '2.2 知识均衡检查与修正') {
    if (parserState.iterMax > 0) {
      setStageProgress(stage, {
        current: parserState.iterCur,
        total: parserState.iterMax,
        unit: '轮',
        phase: undefined,
        indeterminate: false,
      });
    } else {
      setStageProgress(stage, {
        current: 0,
        total: 0,
        unit: '',
        indeterminate: true,
      });
    }
  }
}



function parseLines(lines: string[]) {
  for (const ln of lines) {
    // stage 切换 / 终态
    const sm = _STAGE_RE.exec(ln);
    if (sm) {
      const kind = sm[1];
      // sm[2] 形如 "1.2 MinerU OCR  (34.1s) [...]"，取第一个连续段作为 stage 名
      const rawName = sm[2].trim();
      // stage 名以两位编号开头，截到下一个多空格之前
      const nameMatch = rawName.match(/^(\d+\.\d+\s+[^\s].*?)(?:\s{2,}|$)/);
      const stageName = nameMatch ? nameMatch[1].trim() : rawName;
      if (kind === 'start') {
        parserState.currentStage = stageName;
        // 切换到新 stage 时，把跨 stage 共享的 OCR/Gen/Balance 局部状态重置
        parserState.uploadedI = 0;
        parserState.uploadN = 0;
        parserState.downloadedI = 0;
        parserState.downloadN = 0;
        parserState.stage1I = 0;
        parserState.stage1N = 0;
        parserState.stage2I = 0;
        parserState.stage2N = 0;
        parserState.iterMax = 0;
        parserState.iterCur = 0;
      } else if (kind === 'FAIL') {
        const cur = stageProgress.value[stageName];
        setStageProgress(stageName, { ...(cur || { current: 0, total: 0, unit: '' }), failed: true });
      }
      continue;
    }

    const stage = parserState.currentStage;
    if (!stage) continue;

    // 1.1 PDF→Images 完成行
    const pm = _PDF_DONE_RE.exec(ln);
    if (pm) {
      const n = Number(pm[1]);
      setStageProgress('1.1 PDF转图片', {
        current: n,
        total: n,
        unit: '页',
        indeterminate: false,
      });
      continue;
    }

    // 1.2 OCR 子阶段切换
    if (_MINERU_PHASE_RE.test(ln)) {
      commitFromState('1.2 文字识别');
      continue;
    }
    const um = _UPLOAD_RE.exec(ln);
    if (um) {
      parserState.uploadedI = Number(um[1]);
      parserState.uploadN = Number(um[2]);
      commitFromState('1.2 文字识别');
      continue;
    }
    if (_DOWNLOAD_RE.test(ln)) {
      if (parserState.downloadN === 0 && parserState.uploadN > 0) {
        parserState.downloadN = parserState.uploadN;
      }
      parserState.downloadedI += 1;
      commitFromState('1.2 文字识别');
      continue;
    }

    // 2.2 知识均衡检查与修正
    const imx = _ITER_MAX_RE.exec(ln);
    if (imx) {
      parserState.iterMax = Number(imx[1]);
      commitFromState('2.2 知识均衡检查与修正');
      continue;
    }
    const ic = _ITER_RE.exec(ln);
    if (ic) {
      parserState.iterCur = Number(ic[1]);
      commitFromState('2.2 知识均衡检查与修正');
      continue;
    }

    // tqdm 通用
    const tm = _TQDM_RE.exec(ln);
    if (tm) {
      const title = tm[1].trim();
      const i = Number(tm[2]);
      const n = Number(tm[3]);
      if (title === '阶段1-内容分类') {
        parserState.stage1I = i;
        parserState.stage1N = n;
        commitFromState('2.1 题目生成');
      } else if (title === '阶段2-题目生成') {
        parserState.stage2I = i;
        parserState.stage2N = n;
        commitFromState('2.1 题目生成');
      } else {
        // 3.x 阶段：直接喂给 currentStage
        if (stage.startsWith('3.')) {
          setStageProgress(stage, {
            current: i,
            total: n,
            unit: '题',
            phase: title,
            indeterminate: false,
          });
        }
      }
      continue;
    }
  }
}

// 历史回放：当 progress.json 显示某 stage 已 succeeded、但 stageProgress 缺失时补满条
function fillSucceededStages() {
  const stages = progress.value?.stages || [];
  const cur = stageProgress.value;
  let mutated = false;
  const next = { ...cur };
  for (const s of stages) {
    if (s.status === 'succeeded' && !next[s.name]) {
      next[s.name] = { current: 1, total: 1, unit: '' };
      mutated = true;
    }
  }
  if (mutated) stageProgress.value = next;
}

onMounted(async () => {
  await loadInitial();
  startSse();
  ensureLogPolling();
  ensureSamplePolling();
  if (task.value?.status === 'running') startEtaPolling();
});

onBeforeUnmount(() => {
  abortCtrl?.abort();
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  if (sampleTimer) {
    clearInterval(sampleTimer);
    sampleTimer = null;
  }
});

// ── 快捷导出面板 ──────────────────────────────────────────────────────────────
type QuickFormat = 'word' | 'pdf' | 'json';
type QuickVariant = 'with_answer' | 'blank';
type QuickLang = 'zh' | 'en' | 'fr';
type QuickExportStatus = 'idle' | 'pending' | 'running' | 'succeeded' | 'failed';

const QUICK_LANG_OPTIONS: { value: QuickLang; label: string }[] = [
  { value: 'zh', label: '中文（原文）' },
  { value: 'en', label: 'English（已翻译题需 stage ≥ 3.7）' },
  { value: 'fr', label: 'Français（已翻译题需 stage ≥ 3.7）' },
];

// 阶段名 → 导出 id 映射（与 ExportView 对齐）
const STAGE_NAME_TO_ID: Record<string, string> = {
  '3.8 选择题格式检查': '3_8_mcq_verified',
  '3.7 多语言翻译':     '3_7_translated',
  '3.6 题库增强':       '3_6_synthesized',
  '3.5 去除重复题目':   '3_5_deduplicated',
  '3.4 考察领域修正':   '3_4_domain_refined',
  '3.2 题意模糊修正':   '3_2_ambiguity_refined',
  '2.2 知识均衡检查与修正': '2_1_generation/2_2_balanced',
  '2.2 知识均衡检查':       '2_1_generation/2_2_balanced',
  '2.1 题目生成':       '2_1_generation/2_1_generated_stage_2',
};

const STAGE_ID_LABELS: Record<string, { label: string; hint: string }> = {
  '3_8_mcq_verified':                     { label: '3.8 选择题格式检查',           hint: '推荐：选择题格式已规范' },
  '3_7_translated':                       { label: '3.7 多语言翻译',            hint: '附有英/法译文' },
  '3_6_synthesized':                      { label: '3.6 题库增强',              hint: '补充了更多题型' },
  '3_5_deduplicated':                     { label: '3.5 去除重复题目',          hint: '已删除重复题目' },
  '3_4_domain_refined':                   { label: '3.4 考察领域修正',          hint: '知识领域已校正' },
  '3_2_ambiguity_refined':                { label: '3.2 题意模糊修正',          hint: '已改写模糊题目' },
  '2_1_generation/2_2_balanced':          { label: '2.2 知识均衡检查与修正',    hint: '知识分布更均衡' },
  '2_1_generation/2_1_generated_stage_2':  { label: '2.1 题目生成',              hint: '未经精炼的原始版本' },
};

const QUICK_STAGE_ORDER = [
  '3_8_mcq_verified',
  '3_7_translated',
  '3_6_synthesized',
  '3_5_deduplicated',
  '3_4_domain_refined',
  '3_2_ambiguity_refined',
  '2_1_generation/2_2_balanced',
  '2_1_generation/2_1_generated_stage_2',
];

// 可用的已完成阶段列表（按优先级排序）
const quickAvailableStages = computed(() => {
  const succeededIds = new Set(
    (progress.value?.stages || [])
      .filter((s) => s.status === 'succeeded')
      .map((s) => STAGE_NAME_TO_ID[s.name])
      .filter(Boolean)
  );
  return QUICK_STAGE_ORDER
    .filter((id) => succeededIds.has(id))
    .map((id) => ({ id, ...STAGE_ID_LABELS[id] }));
});

// 当前选中阶段（默认第一个 = 推荐最新版）
const quickStage = ref('');

// 当 progress 变化后自动选中默认阶段
watch(
  () => quickAvailableStages.value,
  (stages) => {
    if (stages.length > 0 && !stages.find((s) => s.id === quickStage.value)) {
      quickStage.value = stages[0].id;
    }
  },
  { immediate: true }
);

const quickFormat = ref<QuickFormat>('word');
const quickVariant = ref<QuickVariant>('with_answer');
const quickLang = ref<QuickLang>('zh');
const quickStatus = ref<QuickExportStatus>('idle');

/** 3.7 多语言翻译已成功完成时才可选英文 / 法文导出 */
const quickTranslationReady = computed(() =>
  (progress.value?.stages || []).some((s) => s.name === '3.7 多语言翻译' && s.status === 'succeeded')
);

function quickLangEnabled(code: QuickLang): boolean {
  if (code === 'zh') return true;
  return quickTranslationReady.value;
}

watch(quickTranslationReady, (ready) => {
  if (!ready && quickLang.value !== 'zh') quickLang.value = 'zh';
});
const quickError = ref('');
const quickJobId = ref('');
const quickToken = ref('');
const quickDownloadUrl = ref('');
const quickFileName = ref('');
let quickPollTimer: ReturnType<typeof setTimeout> | null = null;

function stopQuickPoll() {
  if (quickPollTimer) {
    clearTimeout(quickPollTimer);
    quickPollTimer = null;
  }
}

onBeforeUnmount(stopQuickPoll);

async function startQuickExport() {
  stopQuickPoll();
  quickError.value = '';
  quickStatus.value = 'pending';

  const bestStage = quickStage.value || quickAvailableStages.value[0]?.id || '';
  if (!bestStage) {
    quickError.value = '暂无可导出的阶段，请等待任务完成';
    quickStatus.value = 'idle';
    return;
  }

  try {
    const body: Record<string, unknown> = { format: quickFormat.value, stage: bestStage, lang: quickLang.value };
    if (quickFormat.value !== 'json') body.variant = quickVariant.value;
    const resp = await api.post(`/tasks/${props.id}/export-jobs`, body);
    const d = resp.data;
    quickJobId.value = d.export_id;
    quickToken.value = d.token;
    quickDownloadUrl.value = d.download_url;
    quickFileName.value = d.file_name || 'export';
    quickStatus.value = d.status === 'succeeded' ? 'succeeded' : 'running';
    if (quickStatus.value === 'succeeded') {
      triggerQuickDownload();
    } else {
      scheduleQuickPoll();
    }
  } catch (err: any) {
    quickStatus.value = 'failed';
    quickError.value = err?.response?.data?.message || err?.message || '创建导出失败';
  }
}

function scheduleQuickPoll() {
  const tick = async () => {
    try {
      const resp = await api.get(`/tasks/${props.id}/export-jobs/${quickJobId.value}`);
      const d = resp.data;
      if (d.status === 'succeeded') {
        quickStatus.value = 'succeeded';
        triggerQuickDownload();
        return;
      }
      if (d.status === 'failed') {
        quickStatus.value = 'failed';
        quickError.value = d.error_message || '导出失败';
        return;
      }
    } catch { /* 网络抖动，下轮再试 */ }
    quickPollTimer = setTimeout(tick, 2000);
  };
  quickPollTimer = setTimeout(tick, 1500);
}

function triggerQuickDownload() {
  const jwtToken = localStorage.getItem(TOKEN_KEY);
  fetch(quickDownloadUrl.value, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {}),
    },
    body: JSON.stringify({ token: quickToken.value }),
  })
    .then(async (resp) => {
      if (!resp.ok) {
        let msg = `下载失败 (${resp.status})`;
        try {
          const d = await resp.json();
          msg = d.message || d.error || msg;
        } catch { /* ignore */ }
        quickError.value = msg;
        quickStatus.value = 'failed';
        return;
      }
      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      let filename = quickFileName.value;
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      if (m) { try { filename = decodeURIComponent(m[1]); } catch { /* ignore */ } }
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    })
    .catch((err: Error) => {
      quickError.value = err.message || '下载失败';
      quickStatus.value = 'failed';
    });
}

function resetQuickExport() {
  stopQuickPoll();
  quickStatus.value = 'idle';
  quickError.value = '';
  quickJobId.value = '';
  quickToken.value = '';
}

// 导出 Modal
const showExportModal = ref(false);

function openExportModal() {
  resetQuickExport();
  showExportModal.value = true;
}
function closeExportModal() {
  showExportModal.value = false;
}

// 扇形图数据辅助
const TYPE_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16'];
const DIFF_COLORS: Record<string, string> = { '易': '#10B981', '中': '#F59E0B', '难': '#EF4444' };
const DIFF_LABELS: Record<string, string> = { '易': '基础', '中': '中等', '难': '拔高' };

function typeChartData(dist: Record<string, number>) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]).slice(0, 6);
  return {
    labels: entries.map(([k]) => k),
    data: entries.map(([, v]) => v),
    colors: entries.map((_, i) => TYPE_COLORS[i % TYPE_COLORS.length]),
  };
}

function diffChartData(dist: Record<string, number>) {
  const keys = ['易', '中', '难'].filter((k) => (dist[k] ?? 0) > 0);
  return {
    labels: keys.map((k) => DIFF_LABELS[k]),
    data: keys.map((k) => dist[k] ?? 0),
    colors: keys.map((k) => DIFF_COLORS[k]),
  };
}

const SUBJECTIVE_TYPES = new Set(['简答题', '论述题', '计算题', '综合题', '分析题', '解答题']);

function subjectivityChartData(dist: Record<string, number>) {
  let subj = 0;
  let obj = 0;
  for (const [t, n] of Object.entries(dist)) {
    if (SUBJECTIVE_TYPES.has(t)) subj += n;
    else obj += n;
  }
  const result: { labels: string[]; data: number[]; colors: string[] } = { labels: [], data: [], colors: [] };
  if (obj > 0) { result.labels.push('客观题'); result.data.push(obj); result.colors.push('#3B82F6'); }
  if (subj > 0) { result.labels.push('主观题'); result.data.push(subj); result.colors.push('#F59E0B'); }
  return result;
}

watch(
  () => progress.value?.stages?.map((s) => `${s.name}:${s.status}`).join('|'),
  () => fillSucceededStages(),
);

watch(
  () => progress.value?.stages?.map((s) => `${s.name}:${s.status}`).join('|'),
  () => {
    const stages = stageList.value;
    if (!stages.length) {
      selectedStageName.value = '';
      return;
    }
    if (stages.some((s) => s.name === selectedStageName.value)) return;
    const preferred =
      stages.find((s) => s.status === 'running') ??
      stages.find((s) => s.name === progress.value?.current_stage) ??
      stages.find((s) => s.status === 'failed' || s.status === 'cancelled') ??
      stages.find((s) => s.status === 'succeeded') ??
      stages[0];
    selectedStageName.value = preferred.name;
  },
  { immediate: true },
);

watch(
  () => task.value?.status,
  () => {
    ensureLogPolling();
    ensureSamplePolling();
  },
);

function fmtTime(s?: string | null) {
  if (!s) return '—';
  return s.replace('T', ' ').slice(0, 19);
}

// ── ETA banner ────────────────────────────────────────────────────────────────
interface EtaData {
  remaining_seconds: number;
  elapsed_seconds: number;
  method: 'history' | 'pdf_step_default';
  show_eta: boolean;
}

const eta = ref<EtaData | null>(null);
let etaTimer: ReturnType<typeof setInterval> | null = null;

async function loadEta() {
  if (task.value?.status !== 'running') return;
  try {
    const { data } = await api.get<EtaData>(`/tasks/${props.id}/eta`);
    eta.value = data;
  } catch {
    /* 加载失败静默忽略 */
  }
}

function fmtEta(seconds: number): string {
  if (seconds <= 0) return '即将完成';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m} 分钟`;
  return `${seconds} 秒`;
}

function fmtElapsed(seconds: number): string {
  if (seconds < 60) return '不到 1 分钟';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m} 分钟`;
}

function startEtaPolling() {
  if (etaTimer) return;
  void loadEta();
  etaTimer = setInterval(() => void loadEta(), 2 * 60 * 1000);
}

function stopEtaPolling() {
  if (etaTimer) {
    clearInterval(etaTimer);
    etaTimer = null;
  }
}

watch(
  () => task.value?.status,
  (status, prev) => {
    if (status === 'running') {
      startEtaPolling();
    } else {
      stopEtaPolling();
      eta.value = null;
    }
    if (status === 'succeeded' && prev === 'running') {
      void refreshTaskSummary();
    }
  }
);

onBeforeUnmount(() => {
  stopEtaPolling();
});

function barPercent(info: StageProgress | undefined, status: StageInfo['status']): number {
  if (status === 'succeeded') return 100;
  if (!info) return 0;
  if (info.indeterminate) return 100;
  if (info.total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((info.current / info.total) * 100)));
}

function barColorClass(info: StageProgress | undefined, status: StageInfo['status']): string {
  if (status === 'succeeded') return 'bg-emerald-300';
  if (status === 'failed' || info?.failed) return 'bg-rose-400';
  if (status === 'cancelled') return 'bg-amber-300';
  if (info?.indeterminate) return 'bg-amber-300 animate-pulse';
  return 'bg-amber-400';
}

function barLabel(info: StageProgress | undefined, status: StageInfo['status']): string {
  if (status === 'succeeded') {
    if (info && info.total > 0 && info.unit && info.unit !== '%') {
      return `${info.total}/${info.total} ${info.unit}`;
    }
    return '已完成';
  }
  if (!info) return '';
  if (info.indeterminate) return info.phase || '进行中…';
  if (info.unit === '%') {
    return info.phase ? `${info.phase} · ${info.current}%` : `${info.current}%`;
  }
  if (info.total <= 0) return info.phase || '';
  const head = info.phase ? `${info.phase} · ` : '';
  return `${head}${info.current}/${info.total} ${info.unit}`.trim();
}
</script>

<template>
  <div>
    <div v-if="error" class="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4">
      {{ error }}
    </div>

    <div v-if="task">
      <!-- ETA banner：仅在任务运行中时展示 -->
      <div
        v-if="eta && task.status === 'running'"
        class="mb-3 bg-sky-50 border border-sky-200 text-sky-800 rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm"
      >
        <span class="text-base">⏱</span>
        <span v-if="eta.show_eta">
          预计还需
          <span class="font-semibold">{{ fmtEta(eta.remaining_seconds) }}</span>
          <span class="text-sky-600 ml-1">
            （已运行 {{ fmtElapsed(eta.elapsed_seconds) }}，{{ eta.method === 'history' ? '基于历史数据' : '按页数和步骤估算' }}）
          </span>
        </span>
        <span v-else>
          已运行 <span class="font-semibold">{{ fmtElapsed(eta.elapsed_seconds) }}</span>
          <span class="text-sky-600 ml-1">（估算中）</span>
        </span>
      </div>

      <div class="bg-white border border-slate-200 rounded-2xl p-4 flex items-center justify-between gap-3 flex-wrap">
        <div class="text-sm text-slate-500">
          <span v-if="overallStatus === 'succeeded'" class="flex items-center gap-1.5 text-emerald-700 font-medium">
            <span>✅</span><span>生成完成</span>
          </span>
          <span v-else-if="progress?.current_stage">当前阶段：<span class="text-slate-900 font-medium">{{ progress.current_stage }}</span></span>
          <span v-else>—</span>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            v-if="overallStatus !== 'running' && overallStatus !== 'created' && overallStatus !== 'succeeded'"
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50"
            :disabled="!!actionBusy"
            @click="onResume"
          >
            {{ actionBusy === 'resume' ? '继续生成中...' : '继续生成' }}
          </button>
          <button
            v-if="overallStatus !== 'running' && overallStatus !== 'created'"
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50"
            :disabled="!!actionBusy"
            @click="onRestart"
          >
            {{ actionBusy === 'restart' ? '重新生成中...' : '从头重新生成' }}
          </button>
          <button
            v-if="overallStatus === 'running'"
            class="px-3 py-1.5 text-sm border border-rose-300 rounded-lg text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            :disabled="!!actionBusy"
            @click="onStop"
          >
            {{ actionBusy === 'stop' ? '停止中...' : '停止' }}
          </button>
        </div>
      </div>

      <div v-if="actionMsg" class="mt-3 text-sm text-rose-600">{{ actionMsg }}</div>

      <!-- 已取消：简单提示 -->
      <div
        v-if="progress?.error && overallStatus === 'cancelled'"
        class="mt-3 text-sm text-amber-700"
      >
        已停止：{{ progress.error }}
      </div>

      <!-- 失败：友好错误卡片 -->
      <div
        v-if="progress?.error && overallStatus === 'failed'"
        class="mt-4 bg-rose-50 border border-rose-200 rounded-xl p-4"
      >
        <div class="flex items-start gap-3">
          <svg class="w-5 h-5 text-rose-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-rose-800">{{ taskErrorInfo.friendly }}</p>
            <p class="text-sm text-rose-700 mt-1">{{ taskErrorInfo.suggestion }}</p>
            <div class="flex items-center gap-2 mt-3 flex-wrap">
              <button
                v-if="taskErrorInfo.canRetry"
                class="px-3 py-1.5 text-xs font-medium bg-rose-600 text-white rounded-lg hover:bg-rose-700 disabled:opacity-50 transition-colors"
                :disabled="!!actionBusy"
                @click="onRestart"
              >
                重新提交
              </button>
              <button
                class="px-3 py-1.5 text-xs font-medium border border-rose-300 text-rose-700 rounded-lg hover:bg-rose-100 transition-colors"
                @click="copyErrorDetail"
              >
                {{ copyErrorDone ? '已复制 ✓' : '复制错误详情' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 质量摘要卡片：仅任务全部完成时展示 -->
      <div
        v-if="overallStatus === 'succeeded' && summary"
        class="mt-4 bg-white border border-emerald-200 rounded-2xl p-5"
      >
        <!-- 核心数字 -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <div class="bg-slate-50 rounded-xl px-3 py-2.5 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ summary.total }}</div>
            <div class="text-xs text-slate-500 mt-0.5">题目总数</div>
          </div>
          <div class="bg-slate-50 rounded-xl px-3 py-2.5 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ summary.categoryCount }}</div>
            <div class="text-xs text-slate-500 mt-0.5">章节数</div>
          </div>
          <div class="bg-slate-50 rounded-xl px-3 py-2.5 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ summary.subcategoryCount }}</div>
            <div class="text-xs text-slate-500 mt-0.5">知识点数</div>
          </div>
          <div class="bg-slate-50 rounded-xl px-3 py-2.5 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ Object.keys(summary.typeDist).length }}</div>
            <div class="text-xs text-slate-500 mt-0.5">题型种数</div>
          </div>
        </div>

        <!-- 题型分布 + 难度分布 + 主客观比（扇形图） -->
        <div class="grid sm:grid-cols-3 gap-x-4 gap-y-7 mb-6">
          <!-- 题型 -->
          <div class="flex flex-col rounded-xl border border-sky-100 bg-sky-50/90 p-4 sm:p-5">
            <div class="text-sm font-semibold text-slate-700 mb-3 w-full text-center tracking-wide">题型分布</div>
            <div class="flex-1 flex items-center justify-center gap-3">
              <div class="w-20 h-20 flex-shrink-0">
                <DoughnutChart
                  :labels="typeChartData(summary.typeDist).labels"
                  :data="typeChartData(summary.typeDist).data"
                  :colors="typeChartData(summary.typeDist).colors"
                />
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="(entry, i) in typeChartData(summary.typeDist).labels"
                  :key="entry"
                  class="flex items-center gap-1.5 text-xs text-slate-600"
                >
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: typeChartData(summary.typeDist).colors[i] }" />
                  <span class="truncate max-w-[4rem]">{{ entry }}</span>
                  <span class="text-slate-400 ml-1">{{ typeChartData(summary.typeDist).data[i] }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 难度 -->
          <div class="flex flex-col rounded-xl border border-violet-100 bg-violet-50/90 p-4 sm:p-5">
            <div class="text-sm font-semibold text-slate-700 mb-3 w-full text-center tracking-wide">难度分布</div>
            <div class="flex-1 flex items-center justify-center gap-3">
              <div class="w-20 h-20 flex-shrink-0">
                <DoughnutChart
                  :labels="diffChartData(summary.diffDist).labels"
                  :data="diffChartData(summary.diffDist).data"
                  :colors="diffChartData(summary.diffDist).colors"
                />
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="(entry, i) in diffChartData(summary.diffDist).labels"
                  :key="entry"
                  class="flex items-center gap-1.5 text-xs text-slate-600"
                >
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: diffChartData(summary.diffDist).colors[i] }" />
                  <span>{{ entry }}</span>
                  <span class="text-slate-400 ml-1">{{ diffChartData(summary.diffDist).data[i] }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 主客观比 -->
          <div class="flex flex-col rounded-xl border border-amber-100 bg-amber-50/90 p-4 sm:p-5">
            <div class="text-sm font-semibold text-slate-700 mb-3 w-full text-center tracking-wide">主 / 客观比</div>
            <div class="flex-1 flex items-center justify-center gap-3">
              <div class="w-20 h-20 flex-shrink-0">
                <DoughnutChart
                  :labels="subjectivityChartData(summary.typeDist).labels"
                  :data="subjectivityChartData(summary.typeDist).data"
                  :colors="subjectivityChartData(summary.typeDist).colors"
                />
              </div>
              <div class="space-y-1.5">
                <div
                  v-for="(entry, i) in subjectivityChartData(summary.typeDist).labels"
                  :key="entry"
                  class="flex items-center gap-1.5 text-xs text-slate-600"
                >
                  <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: subjectivityChartData(summary.typeDist).colors[i] }" />
                  <span>{{ entry }}</span>
                  <span class="text-slate-400 ml-1">{{ subjectivityChartData(summary.typeDist).data[i] }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 快捷导出（单按钮） -->
        <div class="border-t border-slate-100 pt-3 flex items-center justify-between">
          <span class="text-xs text-slate-400">题目已生成，可下载试卷</span>
          <button
            class="px-4 py-2 text-sm font-medium rounded-lg bg-slate-900 text-white hover:bg-slate-700 transition-colors flex items-center gap-2"
            @click="openExportModal"
          >
            <i class="fa-solid fa-download text-xs" />
            导出
          </button>
        </div>
      </div>

      <div class="mt-6">
        <h2 class="text-sm font-semibold text-slate-700 mb-3">阶段进度</h2>

        <div
          v-if="stageList.length"
          class="rounded-xl border border-slate-200 bg-white/70 p-4 shadow-sm"
          aria-label="阶段时间线"
        >
          <div class="grid lg:grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)] gap-4">
            <div class="space-y-0">
              <button
                v-for="(s, idx) in stageList"
                :key="s.name"
                type="button"
                class="group flex w-full items-stretch text-left focus:outline-none"
                :aria-pressed="selectedStage?.name === s.name"
                @click="selectStage(s.name)"
              >
                <span class="flex w-8 shrink-0 flex-col items-center">
                  <span
                    v-if="idx > 0"
                    class="h-4 w-px transition-colors"
                    :class="timelineConnectorClass(stageList[idx - 1])"
                  />
                  <span
                    class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 border-white shadow-sm ring-2 transition-transform group-hover:scale-105"
                    :class="timelineDotClass(s.status)"
                  >
                    <span
                      v-if="selectedStage?.name === s.name"
                      class="h-1.5 w-1.5 rounded-full bg-white"
                    />
                  </span>
                  <span
                    v-if="idx < stageList.length - 1"
                    class="min-h-[48px] w-px flex-1 transition-colors"
                    :class="timelineConnectorClass(s)"
                  />
                </span>
                <span
                  class="mb-2 flex min-w-0 flex-1 items-start justify-between gap-3 rounded-lg border px-3 py-2.5 transition-colors"
                  :class="selectedStage?.name === s.name
                    ? ['border-slate-900 bg-white shadow-sm', stageStatusClass[s.status]]
                    : 'border-transparent hover:border-slate-200 hover:bg-white'"
                >
                  <span class="min-w-0">
                    <span class="flex items-center gap-2">
                      <span class="font-mono text-xs font-semibold text-slate-500 tabular-nums">
                        {{ stageTimelineCode(s.name) }}
                      </span>
                      <span class="truncate text-sm font-medium text-slate-900">{{ s.name }}</span>
                    </span>
                    <span
                      v-if="STAGE_DESCRIPTIONS[s.name]"
                      class="mt-1 block text-xs leading-snug text-slate-500"
                    >
                      {{ STAGE_DESCRIPTIONS[s.name] }}
                    </span>
                  </span>
                  <span
                    class="shrink-0 text-xs font-medium"
                    :class="timelineTextClass(s.status)"
                  >
                    {{ timelineStatusLabel[s.status] }}
                  </span>
                </span>
              </button>
            </div>

            <div v-if="selectedStage" class="lg:border-l lg:border-slate-200 lg:pl-4">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-xs text-slate-400">选中阶段</p>
                  <h3 class="mt-1 text-base font-semibold text-slate-900">
                    {{ selectedStage.name }}
                  </h3>
                </div>
                <span
                  :class="['inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium', stageStatusClass[selectedStage.status]]"
                >
                  <span
                    v-if="selectedStage.status === 'running'"
                    class="inline-block h-3 w-3 rounded-full border-2 border-amber-300 border-t-amber-600 animate-spin"
                    style="animation-duration: 1.1s"
                    aria-label="running"
                  />
                  <span v-else class="leading-none">{{ stageDot[selectedStage.status] }}</span>
                  {{ timelineStatusLabel[selectedStage.status] }}
                </span>
              </div>

              <p
                v-if="STAGE_DESCRIPTIONS[selectedStage.name]"
                class="mt-3 text-sm leading-6 text-slate-600"
              >
                {{ STAGE_DESCRIPTIONS[selectedStage.name] }}
              </p>

              <div class="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-500">
                <div class="rounded-lg bg-slate-50 px-3 py-2">
                  <div class="text-slate-400">开始</div>
                  <div class="mt-1 font-medium text-slate-700">{{ fmtTime(selectedStage.started_at) }}</div>
                </div>
                <div class="rounded-lg bg-slate-50 px-3 py-2">
                  <div class="text-slate-400">结束</div>
                  <div class="mt-1 font-medium text-slate-700">{{ fmtTime(selectedStage.finished_at) }}</div>
                </div>
              </div>

              <template v-if="['running', 'succeeded', 'failed', 'cancelled'].includes(selectedStage.status)">
                <div class="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    class="h-full transition-all duration-300"
                    :class="barColorClass(stageProgress[selectedStage.name], selectedStage.status)"
                    :style="{ width: barPercent(stageProgress[selectedStage.name], selectedStage.status) + '%' }"
                  />
                </div>
                <div
                  v-if="barLabel(stageProgress[selectedStage.name], selectedStage.status)"
                  class="mt-1 text-xs text-slate-500"
                >
                  {{ barLabel(stageProgress[selectedStage.name], selectedStage.status) }}
                </div>
              </template>

              <div
                v-if="selectedStage.error"
                class="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 break-words"
              >
                {{ selectedStage.error }}
              </div>
              <div
                v-if="selectedStage.note"
                class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600"
              >
                {{ selectedStage.note }}
              </div>
            </div>
          </div>
        </div>

        <div v-if="!stageList.length" class="text-sm text-slate-500">
          尚未开始或读取中...
        </div>
      </div>

      <div class="mt-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-slate-700">最新一题预览</h2>
          <span v-if="sample" class="text-xs text-slate-400 font-mono">{{ sample.stage }}</span>
        </div>
        <transition name="fade" mode="out-in">
          <div
            v-if="sample"
            :key="(sample.data.question || '') + (sample.data.answer || '')"
            class="bg-white border border-slate-200 rounded-2xl p-5"
          >
            <div class="flex items-center gap-2 flex-wrap text-xs mb-3">
              <span v-if="sample.data.type" class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                {{ sample.data.type }}
              </span>
              <span v-if="sample.data.category" class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                {{ sample.data.category }}<span v-if="sample.data.subcategory"> · {{ sample.data.subcategory }}</span>
              </span>
              <span v-if="sample.data.ability_main" class="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700">
                {{ sample.data.ability_main }}<span v-if="sample.data.ability_level"> · {{ sample.data.ability_level }}</span>
              </span>
              <span v-if="sample.data.difficulty" class="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
                难度 {{ sample.data.difficulty }}
              </span>
            </div>
            <p class="text-sm text-slate-900 whitespace-pre-wrap">{{ sample.data.question }}</p>
            <ul v-if="sample.data.options?.length" class="mt-2 text-sm text-slate-700 space-y-1">
              <li v-for="(o, i) in sample.data.options" :key="i" class="pl-2">{{ o }}</li>
            </ul>
            <div v-if="sample.data.answer" class="mt-3 text-sm">
              <span class="text-slate-500">答案：</span>
              <span class="text-emerald-700 font-medium whitespace-pre-wrap">{{ sample.data.answer }}</span>
            </div>
            <p v-if="sample.data.explanation" class="mt-2 text-xs text-slate-500 whitespace-pre-wrap">
              解析：{{ sample.data.explanation }}
            </p>
          </div>
          <div
            v-else
            class="bg-white border border-dashed border-slate-200 rounded-2xl p-5 text-sm text-slate-400 text-center"
          >
            等待第一批题目产出后将自动展示...
          </div>
        </transition>
      </div>
    </div>

    <!-- 导出 Modal -->
    <Teleport to="body">
      <div
        v-if="showExportModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @click.self="closeExportModal"
      >
        <div class="absolute inset-0 bg-black/40" @click="closeExportModal" />
        <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
          <!-- 顶栏 -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <h2 class="text-sm font-semibold text-slate-800">导出试卷</h2>
            <button class="text-slate-400 hover:text-slate-700 transition" @click="closeExportModal">
              <i class="fa-solid fa-xmark text-lg" />
            </button>
          </div>

          <!-- 内容 -->
          <div class="px-6 py-5 space-y-5">
            <!-- 版本选择 Timeline -->
            <div v-if="quickAvailableStages.length > 0">
              <p class="text-xs font-semibold text-slate-500 mb-3">导出版本</p>
              <div class="flex flex-col gap-3">
                <label
                  v-for="(opt, i) in quickAvailableStages"
                  :key="opt.id"
                  class="grid grid-cols-[20px_1fr] gap-x-3 items-stretch cursor-pointer"
                  @click="quickStage = opt.id; resetQuickExport()"
                >
                  <div class="flex flex-col items-center w-5 mx-auto h-full min-h-0 min-w-[20px]">
                    <div v-if="i > 0" class="w-px flex-1 bg-slate-200 min-h-[6px] shrink-0" />
                    <div v-else class="flex-1 min-h-0 shrink-0" />
                    <div
                      class="w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-all z-10"
                      :class="quickStage === opt.id
                        ? 'bg-emerald-600 border-emerald-600'
                        : 'bg-white border-slate-300'"
                    >
                      <div v-if="quickStage === opt.id" class="w-2 h-2 rounded-full bg-white" />
                      <div v-else class="w-1.5 h-1.5 rounded-full bg-slate-300" />
                    </div>
                    <div
                      v-if="i < quickAvailableStages.length - 1"
                      class="w-px flex-1 bg-slate-200 min-h-[6px] shrink-0"
                    />
                    <div v-else class="flex-1 min-h-0 shrink-0" />
                  </div>

                  <!-- 内容区 -->
                  <input type="radio" :value="opt.id" v-model="quickStage" class="sr-only" />
                  <div
                    class="flex-1 min-w-0 rounded-xl px-3 py-2 transition-all border"
                    :class="quickStage === opt.id
                      ? 'bg-emerald-50 border-emerald-500 shadow-sm'
                      : 'border-slate-200 bg-white hover:bg-slate-50'"
                  >
                    <div class="flex items-center gap-2 flex-wrap">
                      <span
                        class="text-sm font-medium"
                        :class="quickStage === opt.id ? 'text-emerald-900' : 'text-slate-800'"
                      >{{ opt.label }}</span>
                      <span
                        v-if="i === 0"
                        class="text-[10px] font-medium px-1.5 py-0.5 rounded border"
                        :class="quickStage === opt.id
                          ? 'bg-emerald-100 border-emerald-200 text-emerald-800'
                          : 'bg-slate-100 border-slate-200 text-slate-600'"
                      >最新版</span>
                    </div>
                    <p
                      class="text-xs mt-0.5"
                      :class="quickStage === opt.id ? 'text-emerald-800/80' : 'text-slate-400'"
                    >{{ opt.hint }}</p>
                  </div>
                </label>
              </div>
            </div>

            <!-- 格式选择 -->
            <div>
              <p class="text-xs font-semibold text-slate-500 mb-2">文件格式</p>
              <div class="grid grid-cols-3 gap-2">
                <label
                  v-for="opt in [{ value: 'word', label: 'Word（推荐）', icon: 'fa-file-word' }, { value: 'pdf', label: 'PDF（推荐）', icon: 'fa-file-pdf' }, { value: 'json', label: 'JSON', icon: 'fa-file-code' }]"
                  :key="opt.value"
                  class="flex flex-col items-center gap-1.5 border rounded-xl py-3 cursor-pointer transition-all"
                  :class="quickFormat === opt.value ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-400'"
                >
                  <input type="radio" :value="opt.value" v-model="quickFormat" class="sr-only" @change="resetQuickExport" />
                  <i :class="['fa-solid text-xl', opt.icon, quickFormat === opt.value ? 'text-slate-800' : 'text-slate-400']" />
                  <span class="text-xs font-medium" :class="quickFormat === opt.value ? 'text-slate-800' : 'text-slate-500'">{{ opt.label }}</span>
                </label>
              </div>
            </div>

            <!-- 试卷类型 + 语言（分两行，区块间距略大） -->
            <div class="flex flex-col gap-4">
              <div v-if="quickFormat !== 'json'" class="flex flex-wrap items-center gap-x-6 gap-y-3">
                <span class="text-xs font-semibold text-slate-500 shrink-0">试卷类型</span>
                <div class="flex gap-2 flex-wrap min-w-0">
                  <label
                    v-for="opt in [{ value: 'with_answer', label: '教师卷', sub: '含答案与解析' }, { value: 'blank', label: '学生卷', sub: '空白答案栏' }]"
                    :key="opt.value"
                    class="flex flex-col gap-0.5 border rounded-xl px-4 py-3 cursor-pointer transition-all min-w-[140px] flex-1 sm:flex-initial"
                    :class="quickVariant === opt.value ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-400'"
                  >
                    <input type="radio" :value="opt.value" v-model="quickVariant" class="sr-only" @change="resetQuickExport" />
                    <span class="text-sm font-medium" :class="quickVariant === opt.value ? 'text-slate-900' : 'text-slate-600'">{{ opt.label }}</span>
                    <span class="text-xs text-slate-400">{{ opt.sub }}</span>
                  </label>
                </div>
              </div>
              <div
                :class="quickFormat === 'json'
                  ? 'grid grid-cols-3 gap-2'
                  : 'flex flex-wrap items-center gap-x-6 gap-y-2'"
              >
                <div
                  v-if="quickFormat === 'json'"
                  class="col-span-2"
                  aria-hidden="true"
                />
                <div
                  :class="quickFormat === 'json'
                    ? 'flex flex-wrap items-center justify-end gap-x-4 gap-y-2 min-w-0 pl-0.5'
                    : 'contents'"
                >
                  <span class="text-xs font-semibold text-slate-500 shrink-0">语言选择</span>
                  <div
                    :class="quickFormat === 'json' ? 'flex gap-2 flex-wrap justify-end' : 'flex gap-2 flex-wrap'"
                  >
                    <label
                      v-for="o in QUICK_LANG_OPTIONS"
                      :key="o.value"
                      class="flex items-center gap-1.5 text-xs border rounded-lg px-2.5 py-1.5 transition-all"
                      :class="[
                        quickLang === o.value ? 'border-slate-900 bg-slate-50 text-slate-900 font-medium' : 'border-slate-200 text-slate-500',
                        quickLangEnabled(o.value) ? 'cursor-pointer hover:border-slate-400' : 'opacity-40 cursor-not-allowed',
                      ]"
                    >
                      <input
                        type="radio"
                        :value="o.value"
                        v-model="quickLang"
                        class="sr-only"
                        :disabled="!quickLangEnabled(o.value)"
                        @change="resetQuickExport"
                      />
                      {{ o.label.split('（')[0] }}
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <!-- 状态反馈 -->
            <p v-if="quickStatus === 'failed'" class="text-xs text-rose-600">{{ quickError }}</p>
            <p v-if="quickStatus === 'succeeded'" class="text-xs text-emerald-600">✓ 文件已开始下载</p>
          </div>

          <!-- 底栏 -->
          <div class="px-6 py-4 border-t border-slate-100 flex items-center justify-end gap-3">
            <button
              class="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
              @click="closeExportModal"
            >
              关闭
            </button>
            <button
              class="px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
              :class="quickStatus === 'succeeded' ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-slate-900 text-white hover:bg-slate-700'"
              :disabled="quickStatus === 'pending' || quickStatus === 'running'"
              @click="quickStatus === 'succeeded' ? triggerQuickDownload() : startQuickExport()"
            >
              <i v-if="quickStatus === 'pending' || quickStatus === 'running'" class="fa-solid fa-circle-notch animate-spin text-xs" />
              <i v-else class="fa-solid fa-download text-xs" />
              <span v-if="quickStatus === 'idle'">开始下载</span>
              <span v-else-if="quickStatus === 'pending' || quickStatus === 'running'">生成中…</span>
              <span v-else-if="quickStatus === 'succeeded'">再次下载</span>
              <span v-else>重试</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
