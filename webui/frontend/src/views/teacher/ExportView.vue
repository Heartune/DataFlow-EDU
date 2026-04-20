<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { TOKEN_KEY, api } from '@/api/client';

const props = defineProps<{ id: string; taskName?: string }>();

type Format = 'json' | 'word' | 'pdf';
type Variant = 'with_answer' | 'blank';
type Lang = 'zh' | 'en' | 'fr';
type ExportStatus = 'pending' | 'running' | 'succeeded' | 'failed';

interface ExportJobPublic {
  id: string;
  task_id: string;
  format: Format;
  variant: string;
  lang: Lang;
  stage: string;
  status: ExportStatus;
  file_name: string | null;
  size_bytes: number | null;
  error_message: string | null;
  token_consumed: boolean;
  expires_at: number;
  created_at: number;
  updated_at: number;
}

interface CreateResponse extends ExportJobPublic {
  ok: true;
  export_id: string;
  status_url: string;
  download_url: string;
}

interface ActiveJob {
  jobId: string;
  format: Format;
  status: ExportStatus;
  fileName: string;
  downloadUrl: string;
  errorMessage: string | null;
  startedAt: number;
}

const STAGE_OPTIONS = [
  { value: '3_8_mcq_verified', label: '3.8 MCQ Verify (推荐：选择题已校验)' },
  { value: '3_7_translated', label: '3.7 Translated（已加多语言译文）' },
  { value: '3_4_domain_refined', label: '3.4 Domain Refined（学科精炼后）' },
] as const;

const LANG_OPTIONS = [
  { value: 'zh' as const, label: '中文（原文）' },
  { value: 'en' as const, label: 'English（已翻译题需 stage ≥ 3.7）' },
  { value: 'fr' as const, label: 'Français（已翻译题需 stage ≥ 3.7）' },
];

const VARIANT_OPTIONS = [
  { value: 'with_answer' as const, label: '教师卷（题干 + 答案 + 解析）' },
  { value: 'blank' as const, label: '学生卷（题干 + 选项；答案集中在末尾）' },
];

const stage = ref<(typeof STAGE_OPTIONS)[number]['value']>('3_8_mcq_verified');
const lang = ref<Lang>('zh');
const variant = ref<Variant>('with_answer');

const error = ref('');
const info = ref('');

// 三种格式各自维护一个 active job，避免互相覆盖
const jobs = ref<Record<Format, ActiveJob | null>>({
  json: null,
  word: null,
  pdf: null,
});

const polling = ref<Record<Format, boolean>>({ json: false, word: false, pdf: false });
const pollTimers: Record<Format, ReturnType<typeof setTimeout> | null> = {
  json: null,
  word: null,
  pdf: null,
};

function clearTimer(format: Format) {
  if (pollTimers[format]) {
    clearTimeout(pollTimers[format]!);
    pollTimers[format] = null;
  }
  polling.value[format] = false;
}

onBeforeUnmount(() => {
  (Object.keys(pollTimers) as Format[]).forEach(clearTimer);
});

const isLegacyJsonZip = computed(() => false); // 保留：以后想区分 zip vs single json 时用

async function startExport(format: Format) {
  error.value = '';
  info.value = '';
  clearTimer(format);

  try {
    const body: Record<string, unknown> = {
      format,
      stage: stage.value,
      lang: lang.value,
    };
    if (format !== 'json') body.variant = variant.value;
    const resp = await api.post<CreateResponse>(
      `/tasks/${encodeURIComponent(props.id)}/export-jobs`,
      body
    );
    const data = resp.data;
    jobs.value[format] = {
      jobId: data.export_id,
      format,
      status: data.status,
      fileName: data.file_name || `${props.taskName || 'task'}.${format === 'word' ? 'docx' : format}`,
      downloadUrl: data.download_url,
      errorMessage: null,
      startedAt: Date.now(),
    };
    schedulePoll(format);
  } catch (err: unknown) {
    const msg = extractErrorMessage(err);
    error.value = `创建导出任务失败：${msg}`;
  }
}

function schedulePoll(format: Format) {
  polling.value[format] = true;
  const tick = async () => {
    const current = jobs.value[format];
    if (!current) {
      polling.value[format] = false;
      return;
    }
    try {
      const resp = await api.get<ExportJobPublic>(
        `/tasks/${encodeURIComponent(props.id)}/export-jobs/${encodeURIComponent(current.jobId)}`
      );
      const next = resp.data;
      jobs.value[format] = {
        ...current,
        status: next.status,
        fileName: next.file_name || current.fileName,
        errorMessage: next.error_message,
      };
      if (next.status === 'succeeded') {
        polling.value[format] = false;
        info.value = `${labelOf(format)} 已生成，可点击下载。`;
        triggerDownload(format);
        return;
      }
      if (next.status === 'failed') {
        polling.value[format] = false;
        error.value = `${labelOf(format)} 导出失败：${next.error_message || '未知错误'}`;
        return;
      }
    } catch (err) {
      // 网络抖动：再试一次再放弃
      console.warn('[export] poll error:', err);
    }
    pollTimers[format] = setTimeout(tick, 2000);
  };
  pollTimers[format] = setTimeout(tick, 1500);
}

function triggerDownload(format: Format) {
  const job = jobs.value[format];
  if (!job) return;
  // download 路由会校验 JWT；fetch 带 Authorization 头转 Blob 再下载，避免 token 泄漏到 URL 之外
  const token = localStorage.getItem(TOKEN_KEY);
  fetch(job.downloadUrl, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
    .then(async (resp) => {
      if (!resp.ok) {
        let msg = `下载失败 (${resp.status})`;
        try {
          const data = await resp.json();
          msg = data.message || data.error || msg;
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      let filename = job.fileName;
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      if (m) {
        try {
          filename = decodeURIComponent(m[1]);
        } catch {
          /* ignore */
        }
      }
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
      info.value = `已下载 ${filename}`;
    })
    .catch((err: Error) => {
      error.value = err.message || '下载失败';
    });
}

function labelOf(format: Format): string {
  if (format === 'json') return 'JSON 数据包';
  if (format === 'word') return 'Word 试卷';
  return 'PDF 试卷';
}

function statusText(format: Format): string {
  const j = jobs.value[format];
  if (!j) return '';
  if (j.status === 'pending' || j.status === 'running') return '生成中…';
  if (j.status === 'succeeded') return '已生成（点击下方再次下载）';
  if (j.status === 'failed') return `失败：${j.errorMessage || '未知错误'}`;
  return '';
}

function disabledOf(format: Format): boolean {
  const j = jobs.value[format];
  if (!j) return false;
  return j.status === 'pending' || j.status === 'running';
}

function extractErrorMessage(err: unknown): string {
  type AxiosLike = { response?: { data?: { message?: string; error?: string } }; message?: string };
  const e = err as AxiosLike;
  return (
    e?.response?.data?.message ||
    e?.response?.data?.error ||
    e?.message ||
    '请求失败'
  );
}

// 兼容旧版 GET zip 包（多文件原始 JSON），单独按钮
async function downloadLegacyZip() {
  error.value = '';
  info.value = '';
  const token = localStorage.getItem(TOKEN_KEY);
  const url = `/api/tasks/${encodeURIComponent(props.id)}/export?format=json&stage=${encodeURIComponent(stage.value)}`;
  try {
    const resp = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!resp.ok) {
      let msg = `下载失败 (${resp.status})`;
      try {
        const data = await resp.json();
        msg = data.message || data.error || msg;
      } catch {
        /* ignore */
      }
      error.value = msg;
      return;
    }
    const blob = await resp.blob();
    const cd = resp.headers.get('Content-Disposition') || '';
    let filename = `${props.taskName || 'task'}_${stage.value}.zip`;
    const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
    if (m) {
      try {
        filename = decodeURIComponent(m[1]);
      } catch {
        /* ignore */
      }
    }
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objectUrl);
    info.value = `已下载 ${filename}`;
  } catch (err: unknown) {
    error.value = extractErrorMessage(err);
  }
}
</script>

<template>
  <div>
    <p v-if="error" class="text-sm text-rose-600 mb-3">{{ error }}</p>
    <p v-if="info" class="text-sm text-emerald-600 mb-3">{{ info }}</p>

    <div class="bg-white border border-slate-200 rounded-2xl p-5 mb-4 grid sm:grid-cols-3 gap-4">
      <label class="text-sm text-slate-600 flex flex-col gap-1">
        <span>导出阶段</span>
        <select v-model="stage" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option v-for="o in STAGE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="text-sm text-slate-600 flex flex-col gap-1">
        <span>语言</span>
        <select v-model="lang" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option v-for="o in LANG_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <label class="text-sm text-slate-600 flex flex-col gap-1">
        <span>试卷变体（仅 Word/PDF 生效）</span>
        <select v-model="variant" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option v-for="o in VARIANT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
    </div>

    <div class="grid sm:grid-cols-3 gap-4">
      <!-- JSON -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col">
        <div class="text-3xl mb-3">📦</div>
        <h3 class="text-base font-semibold text-slate-900">JSON 数据包</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          按所选阶段 + 语言生成单个 <code>.json</code> 文件（含每题完整字段），适合模型微调或脚本处理。
        </p>
        <p v-if="jobs.json" class="text-xs text-slate-500 mt-2">{{ statusText('json') }}</p>
        <button
          class="mt-4 w-full px-3 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
          :disabled="disabledOf('json')"
          @click="startExport('json')"
        >
          {{ disabledOf('json') ? '生成中…' : '生成 JSON' }}
        </button>
        <button
          v-if="jobs.json && jobs.json.status === 'succeeded'"
          class="mt-2 w-full px-3 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm hover:bg-slate-50"
          @click="triggerDownload('json')"
        >
          再次下载
        </button>
      </div>

      <!-- Word -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col">
        <div class="text-3xl mb-3">📄</div>
        <h3 class="text-base font-semibold text-slate-900">Word 试卷</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          按 category → subcategory → 题型分章节排版，支持教师卷/学生卷两种变体。
        </p>
        <p v-if="jobs.word" class="text-xs text-slate-500 mt-2">{{ statusText('word') }}</p>
        <button
          class="mt-4 w-full px-3 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
          :disabled="disabledOf('word')"
          @click="startExport('word')"
        >
          {{ disabledOf('word') ? '生成中…' : '生成 Word' }}
        </button>
        <button
          v-if="jobs.word && jobs.word.status === 'succeeded'"
          class="mt-2 w-full px-3 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm hover:bg-slate-50"
          @click="triggerDownload('word')"
        >
          再次下载
        </button>
      </div>

      <!-- PDF -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col">
        <div class="text-3xl mb-3">📕</div>
        <h3 class="text-base font-semibold text-slate-900">PDF 试卷</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          复用 Word 排版，调用 LibreOffice headless 转换；服务端需安装 LibreOffice。
        </p>
        <p v-if="jobs.pdf" class="text-xs text-slate-500 mt-2">{{ statusText('pdf') }}</p>
        <button
          class="mt-4 w-full px-3 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
          :disabled="disabledOf('pdf')"
          @click="startExport('pdf')"
        >
          {{ disabledOf('pdf') ? '生成中…' : '生成 PDF' }}
        </button>
        <button
          v-if="jobs.pdf && jobs.pdf.status === 'succeeded'"
          class="mt-2 w-full px-3 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm hover:bg-slate-50"
          @click="triggerDownload('pdf')"
        >
          再次下载
        </button>
      </div>
    </div>

    <div class="mt-6 bg-slate-50 border border-slate-200 rounded-2xl p-4 text-xs text-slate-500">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <span>
          需要原始多文件 zip？可走旧版接口直接下载所选 stage 下所有 <code>*.json</code>。
          <span v-if="isLegacyJsonZip">（已启用旧版）</span>
        </span>
        <button
          class="px-3 py-1.5 border border-slate-300 rounded-lg hover:bg-white"
          @click="downloadLegacyZip"
        >
          下载 zip（旧版）
        </button>
      </div>
      <p class="mt-2 text-slate-400">
        生成的 Word/PDF/JSON 24 小时内有效，下载链接为一次性 token；过期后请重新生成。
      </p>
    </div>
  </div>
</template>
