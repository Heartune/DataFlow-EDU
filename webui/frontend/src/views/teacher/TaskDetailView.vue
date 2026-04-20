<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { api, TOKEN_KEY } from '@/api/client';

const props = defineProps<{ id: string }>();

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

const errorLabel: Record<string, string> = {
  no_progress_to_resume: '没有历史进度可续跑，请改用「从头重跑」',
  nothing_to_resume: '所有阶段都已完成，无需续跑',
  user_has_running_task: '你已有任务在跑，等它结束后再启动新任务',
  task_already_running: '任务已在运行中',
  task_not_running: '任务并未运行，无需停止',
  missing_llm_key: '缺少 LLM Key，请先在「新建任务」页填一次以保存到本地',
  pdf_missing: '原始 PDF 已丢失，无法继续',
  stop_failed: '停止失败，请检查后端日志',
};

const stageStatusClass: Record<StageInfo['status'], string> = {
  pending: 'bg-slate-100 text-slate-400 border-slate-200',
  running: 'bg-amber-50 text-amber-700 border-amber-300 ring-1 ring-amber-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  skipped: 'bg-slate-50 text-slate-500 border-slate-200',
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

async function loadInitial() {
  try {
    const { data } = await api.get(`/tasks/${props.id}`);
    task.value = data.task;
    progress.value = data.progress;
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载失败';
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
  if (!window.confirm('从头重跑会清空 task 目录下除原 PDF 外的所有中间产物，确认继续？')) return;
  void callAction('restart');
}
function onStop() {
  if (!window.confirm('停止后正在运行的子进程会被强制结束，未完成的阶段会被标记为已取消。确认停止？'))
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
  if (stage === '1.2 MinerU OCR') {
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
  if (stage === '2.1 Generation') {
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
  if (stage === '2.2 Balancing') {
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
      setStageProgress('1.1 PDF→Images', {
        current: n,
        total: n,
        unit: '页',
        indeterminate: false,
      });
      continue;
    }

    // 1.2 OCR 子阶段切换
    if (_MINERU_PHASE_RE.test(ln)) {
      commitFromState('1.2 MinerU OCR');
      continue;
    }
    const um = _UPLOAD_RE.exec(ln);
    if (um) {
      parserState.uploadedI = Number(um[1]);
      parserState.uploadN = Number(um[2]);
      commitFromState('1.2 MinerU OCR');
      continue;
    }
    if (_DOWNLOAD_RE.test(ln)) {
      if (parserState.downloadN === 0 && parserState.uploadN > 0) {
        parserState.downloadN = parserState.uploadN;
      }
      parserState.downloadedI += 1;
      commitFromState('1.2 MinerU OCR');
      continue;
    }

    // 2.2 Balancing
    const imx = _ITER_MAX_RE.exec(ln);
    if (imx) {
      parserState.iterMax = Number(imx[1]);
      commitFromState('2.2 Balancing');
      continue;
    }
    const ic = _ITER_RE.exec(ln);
    if (ic) {
      parserState.iterCur = Number(ic[1]);
      commitFromState('2.2 Balancing');
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
        commitFromState('2.1 Generation');
      } else if (title === '阶段2-题目生成') {
        parserState.stage2I = i;
        parserState.stage2N = n;
        commitFromState('2.1 Generation');
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

watch(
  () => progress.value?.stages?.map((s) => `${s.name}:${s.status}`).join('|'),
  () => fillSucceededStages(),
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
      <div class="bg-white border border-slate-200 rounded-2xl p-4 flex items-center justify-between gap-3 flex-wrap">
        <div class="text-sm text-slate-500">
          <span v-if="progress?.current_stage">当前阶段：<span class="text-slate-900 font-medium">{{ progress.current_stage }}</span></span>
          <span v-else>—</span>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            v-if="overallStatus !== 'running' && overallStatus !== 'created'"
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50"
            :disabled="!!actionBusy"
            @click="onResume"
          >
            {{ actionBusy === 'resume' ? '续跑中...' : '续跑' }}
          </button>
          <button
            v-if="overallStatus !== 'running' && overallStatus !== 'created'"
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50"
            :disabled="!!actionBusy"
            @click="onRestart"
          >
            {{ actionBusy === 'restart' ? '重启中...' : '从头重跑' }}
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
      <div
        v-if="progress?.error"
        :class="[
          'mt-3 text-sm',
          overallStatus === 'cancelled' ? 'text-amber-700' : 'text-rose-600',
        ]"
      >
        {{ overallStatus === 'cancelled' ? '已停止：' : '错误：' }}{{ progress.error }}
      </div>

      <div class="mt-6">
        <h2 class="text-sm font-semibold text-slate-700 mb-3">阶段进度</h2>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div
            v-for="s in progress?.stages || []"
            :key="s.name"
            :class="['border rounded-xl p-4', stageStatusClass[s.status]]"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ s.name }}</span>
              <span
                v-if="s.status === 'running'"
                class="inline-block w-3.5 h-3.5 rounded-full border-2 border-amber-300 border-t-amber-600 animate-spin"
                style="animation-duration: 1.1s"
                aria-label="running"
              />
              <span v-else class="text-lg leading-none">{{ stageDot[s.status] }}</span>
            </div>
            <div class="text-xs mt-2 opacity-80">
              <div v-if="s.started_at">起：{{ fmtTime(s.started_at) }}</div>
              <div v-if="s.finished_at">止：{{ fmtTime(s.finished_at) }}</div>
              <div v-if="s.error" class="mt-1 break-words">{{ s.error }}</div>
              <div v-if="s.note" class="mt-1">{{ s.note }}</div>
            </div>
            <template v-if="['running', 'succeeded', 'failed', 'cancelled'].includes(s.status)">
              <div class="mt-3 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                <div
                  class="h-full transition-all duration-300"
                  :class="barColorClass(stageProgress[s.name], s.status)"
                  :style="{ width: barPercent(stageProgress[s.name], s.status) + '%' }"
                />
              </div>
              <div
                v-if="barLabel(stageProgress[s.name], s.status)"
                class="text-[11px] mt-1 opacity-70"
              >
                {{ barLabel(stageProgress[s.name], s.status) }}
              </div>
            </template>
          </div>
          <div
            v-if="!progress?.stages?.length"
            class="text-sm text-slate-500 col-span-full"
          >
            尚未开始或读取中...
          </div>
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
