<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { api, TOKEN_KEY } from '@/api/client';

const props = defineProps<{ id: string }>();

interface StageInfo {
  name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';
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
  status: 'created' | 'running' | 'succeeded' | 'failed';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
  meta: TaskMeta;
}

const task = ref<TaskDetail | null>(null);
const progress = ref<Progress | null>(null);
const error = ref('');
let abortCtrl: AbortController | null = null;

const overallStatus = computed(() => task.value?.status ?? 'created');

const statusLabel: Record<string, string> = {
  created: '待启动',
  running: '运行中',
  succeeded: '已完成',
  failed: '失败',
};

const stageStatusClass: Record<StageInfo['status'], string> = {
  pending: 'bg-slate-100 text-slate-400 border-slate-200',
  running: 'bg-amber-50 text-amber-700 border-amber-300 ring-1 ring-amber-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  skipped: 'bg-slate-50 text-slate-500 border-slate-200',
};

const stageDot: Record<StageInfo['status'], string> = {
  pending: '○',
  running: '◐',
  succeeded: '●',
  failed: '✕',
  skipped: '–',
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
      } else {
        scheduleFlush();
      }
    }
  } catch {
    // ignore
  }
}

onMounted(async () => {
  await loadInitial();
  startSse();
});

onBeforeUnmount(() => {
  abortCtrl?.abort();
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
});

function fmtTime(s?: string | null) {
  if (!s) return '—';
  return s.replace('T', ' ').slice(0, 19);
}
</script>

<template>
  <div>
    <router-link to="/teacher/tasks" class="text-sm text-slate-500 hover:text-slate-900">
      ← 返回任务列表
    </router-link>

    <div v-if="error" class="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4 mt-4">
      {{ error }}
    </div>

    <div v-if="task" class="mt-4">
      <div class="bg-white border border-slate-200 rounded-2xl p-6">
        <div class="flex items-start justify-between">
          <div>
            <h1 class="text-2xl font-bold text-slate-900">{{ task.name }}</h1>
            <p class="text-xs text-slate-500 mt-1 font-mono">{{ task.id }}</p>
          </div>
          <span
            :class="[
              'px-3 py-1 rounded-full text-sm border',
              overallStatus === 'running'
                ? 'bg-amber-50 text-amber-700 border-amber-200'
                : overallStatus === 'succeeded'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : overallStatus === 'failed'
                    ? 'bg-rose-50 text-rose-700 border-rose-200'
                    : 'bg-slate-50 text-slate-600 border-slate-200',
            ]"
          >
            {{ statusLabel[overallStatus] || overallStatus }}
          </span>
        </div>

        <div v-if="progress?.error" class="mt-3 text-sm text-rose-600">
          错误：{{ progress.error }}
        </div>
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
          </div>
          <div
            v-if="!progress?.stages?.length"
            class="text-sm text-slate-500 col-span-full"
          >
            尚未开始或读取中...
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
