<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
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
  token: string;
  status_url: string;
  download_url: string;
}

interface ActiveJob {
  jobId: string;
  format: Format;
  /** 创建导出时的参数，用于再次下载前刷新一次性 token */
  stage: string;
  lang: Lang;
  variant: Variant;
  status: ExportStatus;
  fileName: string;
  downloadUrl: string;
  token: string;
  errorMessage: string | null;
  startedAt: number;
}

// 流水线阶段名（progress.json 的 name 字段）→ { id: 导出目录名, label: 下拉显示名, hint: 一句话质量描述 }
// 顺序决定下拉列表中的优先级（越靠前越推荐）；只列有题目产物的阶段，纯检查阶段（3.1/3.3）不列入
const EXPORTABLE_STAGE_MAP: Record<string, { id: string; label: string; hint: string }> = {
  '3.8 选择题格式检查':   { id: '3_8_mcq_verified',                          label: '3.8 选择题格式检查',   hint: '推荐：选择题格式已规范，可直接导出' },
  '3.7 多语言翻译':      { id: '3_7_translated',                            label: '3.7 多语言翻译',     hint: '每道题附有英文/法文译文' },
  '3.6 题库增强':        { id: '3_6_synthesized',                            label: '3.6 题库增强',       hint: '已为每道题生成详细解析（explanation）' },
  '3.5 去除重复题目':    { id: '3_5_deduplicated',                           label: '3.5 去除重复题目',   hint: '已删除内容相似的重复题目' },
  '3.4 考察领域修正':    { id: '3_4_domain_refined',                         label: '3.4 考察领域修正',   hint: '题目考察的知识领域已经过校正' },
  '3.2 题意模糊修正':    { id: '3_2_ambiguity_refined',                      label: '3.2 题意模糊修正',   hint: '已删除或改写措辞模糊的题目' },
  '2.2 知识均衡检查与修正': { id: '2_1_generation/2_2_balanced',              label: '2.2 知识均衡检查与修正', hint: '针对知识分布不均章节已补充额外题目' },
  '2.2 知识均衡检查':      { id: '2_1_generation/2_2_balanced',                label: '2.2 知识均衡检查',   hint: '针对知识分布不均章节已补充额外题目' },
  '2.1 题目生成':        { id: '2_1_generation/2_1_generated_stage_2',     label: '2.1 题目生成',       hint: '直接由 AI 生成，未经任何质量优化' },
};

type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';

interface StageOption {
  id: string;
  label: string;
  hint: string;
  status: StageStatus;
}

// 从 progress 动态计算的可导出阶段列表（按 EXPORTABLE_STAGE_MAP 的键序排列）
const availableStages = ref<StageOption[]>([]);


async function loadAvailableStages() {
  try {
    const { data } = await api.get(`/tasks/${encodeURIComponent(props.id)}`);
    const progressStages: { name: string; status: StageStatus }[] = data?.progress?.stages ?? [];
    const statusByName = new Map(progressStages.map((s) => [s.name, s.status]));

    const result: StageOption[] = [];
    for (const [stageName, { id, label, hint }] of Object.entries(EXPORTABLE_STAGE_MAP)) {
      const status = statusByName.get(stageName);
      if (status === undefined) continue; // 该阶段不在此任务的流水线中（未启用）
      if (status === 'skipped') continue;  // 被跳过的阶段没有产物
      result.push({ id, label, hint, status });
    }
    availableStages.value = result;

    // 自动选中第一个已完成的阶段
    const firstSucceeded = result.find((s) => s.status === 'succeeded');
    if (firstSucceeded) stage.value = firstSucceeded.id;
    else if (result.length > 0) stage.value = result[0].id;
  } catch {
    // 拉取失败时降级：保持空列表，用户看到提示
  }
}

// 默认阶段（第一个 succeeded，或第一个可用阶段）
const defaultStageOption = computed(() =>
  availableStages.value.find((s) => s.status === 'succeeded') ?? availableStages.value[0] ?? null
);

const LANG_OPTIONS = [
  { value: 'zh' as const, label: '中文（原文）' },
  { value: 'en' as const, label: 'English（已翻译题需 stage ≥ 3.7）' },
  { value: 'fr' as const, label: 'Français（已翻译题需 stage ≥ 3.7）' },
];

const stage = ref('3_8_mcq_verified');
const lang = ref<Lang>('zh');
const variant = ref<Variant>('with_answer');
const activeFormat = ref<Format>('word');

/** 任务里 3.7 已成功完成时才可选英文 / 法文导出 */
const translationExportReady = computed(() =>
  availableStages.value.some((s) => s.id === '3_7_translated' && s.status === 'succeeded')
);

function langOptionEnabled(code: Lang): boolean {
  if (code === 'zh') return true;
  return translationExportReady.value;
}

watch(translationExportReady, (ready) => {
  if (!ready && lang.value !== 'zh') lang.value = 'zh';
});

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

onMounted(loadAvailableStages);

const isLegacyJsonZip = computed(() => false); // 保留：以后想区分 zip vs single json 时用

// 实际生效的阶段：timeline 中选中的 stage，兜底到默认阶段
const effectiveStage = computed(() =>
  stage.value || (defaultStageOption.value?.id ?? '')
);

async function startExport(format: Format) {
  error.value = '';
  info.value = '';
  clearTimer(format);

  try {
    const body: Record<string, unknown> = {
      format,
      stage: effectiveStage.value,
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
      stage: stage.value,
      lang: lang.value,
      variant: variant.value,
      status: data.status,
      fileName: data.file_name || `${props.taskName || 'task'}.${format === 'word' ? 'docx' : format}`,
      downloadUrl: data.download_url,
      token: data.token,
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

/** 一次性下载 token 用过后需重新走 export-jobs，服务端会去重并签发新 token */
async function refreshExportToken(format: Format): Promise<boolean> {
  const job = jobs.value[format];
  if (!job) return false;
  error.value = '';
  try {
    const body: Record<string, unknown> = {
      format,
      stage: job.stage,
      lang: job.lang,
    };
    if (format !== 'json') body.variant = job.variant;
    const resp = await api.post<CreateResponse>(
      `/tasks/${encodeURIComponent(props.id)}/export-jobs`,
      body
    );
    const data = resp.data;
    if (data.export_id !== job.jobId) {
      error.value = '刷新下载链接失败：与当前导出不一致，请重新生成';
      return false;
    }
    jobs.value[format] = {
      ...job,
      token: data.token,
      downloadUrl: data.download_url,
      fileName: data.file_name || job.fileName,
      status: (data.status as ExportStatus) || job.status,
    };
    return true;
  } catch (err: unknown) {
    error.value = `刷新下载链接失败：${extractErrorMessage(err)}`;
    return false;
  }
}

async function downloadAgain(format: Format) {
  if (!(await refreshExportToken(format))) return;
  triggerDownload(format);
}

const EXPORT_DOWNLOAD_ERR: Record<string, string> = {
  token_consumed: '下载链接为一次性，已失效。若已点「再次下载」仍失败，请重新生成导出',
  expired: '导出已过期，请重新生成',
  file_missing: '文件已丢失，请重新生成导出',
  invalid_token: '下载验证失败，请重新生成导出',
};

function triggerDownload(format: Format) {
  const job = jobs.value[format];
  if (!job) return;
  error.value = '';
  // POST body 传 download token，避免 token 出现在 URL / 日志中
  const jwtToken = localStorage.getItem(TOKEN_KEY);
  fetch(job.downloadUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {}),
    },
    body: JSON.stringify({ token: job.token }),
  })
    .then(async (resp) => {
      if (!resp.ok) {
        let msg = `下载失败 (${resp.status})`;
        try {
          const data = await resp.json();
          const code = typeof data.error === 'string' ? data.error : '';
          msg = EXPORT_DOWNLOAD_ERR[code] || data.message || code || msg;
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

function disabledOf(format: Format): boolean {
  const j = jobs.value[format];
  if (!j) return false;
  return j.status === 'pending' || j.status === 'running';
}

function stageStatusHint(status: StageStatus): string {
  const map: Record<StageStatus, string> = {
    pending: '尚未运行',
    running: '运行中',
    succeeded: '',
    failed: '运行失败',
    skipped: '已跳过',
    cancelled: '已取消',
  };
  return map[status] ?? status;
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

// ── 只读分享链接 ────────────────────────────────────────────────────────────────
interface ShareResult {
  token: string;
  share_url: string;
  expires_at: number | null;
}

const shareOpen = ref(false);
const shareExpires = ref<'1d' | '7d' | '30d' | 'never'>('7d');
const shareResult = ref<ShareResult | null>(null);
const shareLoading = ref(false);
const shareCopied = ref(false);

const EXPIRES_OPTIONS = [
  { value: '1d', label: '1 天' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: 'never', label: '永久' },
];

async function createShare() {
  shareLoading.value = true;
  shareResult.value = null;
  try {
    const { data } = await api.post<ShareResult>(
      `/tasks/${encodeURIComponent(props.id)}/share`,
      { expires: shareExpires.value }
    );
    shareResult.value = data;
  } catch (err: unknown) {
    error.value = `创建分享链接失败：${extractErrorMessage(err)}`;
  } finally {
    shareLoading.value = false;
  }
}

function fullShareUrl(token: string): string {
  return `${window.location.origin}/share/${encodeURIComponent(token)}`;
}

async function copyShareLink() {
  if (!shareResult.value) return;
  try {
    await navigator.clipboard.writeText(fullShareUrl(shareResult.value.token));
    shareCopied.value = true;
    setTimeout(() => (shareCopied.value = false), 2000);
  } catch {
    error.value = '复制失败，请手动复制链接';
  }
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

    <!-- 统一导出面板：与弹窗同款卡片风格 -->
    <div class="bg-white border border-slate-200 rounded-2xl overflow-hidden mb-4">

      <!-- 版本选择 -->
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">导出版本</h3>
        <div v-if="availableStages.length === 0" class="text-sm text-slate-400">（暂无可导出阶段）</div>
        <div v-else class="flex flex-col gap-3">
          <label
            v-for="(o, i) in availableStages"
            :key="o.id"
            class="grid grid-cols-[20px_1fr] gap-x-3 items-stretch"
            :class="o.status !== 'succeeded' ? 'cursor-not-allowed' : 'cursor-pointer'"
            @click="o.status === 'succeeded' && (stage = o.id)"
          >
            <!-- 时间轴：上下 flex-1 均分，圆点与右侧卡片垂直居中 -->
            <div class="flex flex-col items-center w-5 mx-auto h-full min-h-0 min-w-[20px]">
              <div v-if="i > 0" class="w-px flex-1 bg-slate-200 min-h-[6px] shrink-0" />
              <div v-else class="flex-1 min-h-0 shrink-0" />
              <div
                class="w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-all z-10"
                :class="effectiveStage === o.id
                  ? 'bg-emerald-600 border-emerald-600'
                  : o.status === 'succeeded'
                    ? 'bg-white border-slate-300'
                    : 'bg-white border-slate-200'"
              >
                <div v-if="effectiveStage === o.id" class="w-2 h-2 rounded-full bg-white" />
                <div v-else-if="o.status === 'succeeded'" class="w-1.5 h-1.5 rounded-full bg-slate-300" />
              </div>
              <div
                v-if="i < availableStages.length - 1"
                class="w-px flex-1 bg-slate-200 min-h-[6px] shrink-0"
              />
              <div v-else class="flex-1 min-h-0 shrink-0" />
            </div>

            <!-- 内容区 -->
            <input type="radio" :value="o.id" v-model="stage" class="sr-only" :disabled="o.status !== 'succeeded'" />
            <div
              class="flex-1 min-w-0 rounded-xl px-4 py-2.5 transition-all border"
              :class="[
                effectiveStage === o.id
                  ? 'bg-emerald-50 border-emerald-500 shadow-sm'
                  : 'border-slate-200 bg-white',
                o.status === 'succeeded' && effectiveStage !== o.id ? 'hover:bg-slate-50' : '',
                o.status !== 'succeeded' ? 'opacity-40' : '',
              ]"
            >
              <div class="flex items-center gap-2 flex-wrap">
                <span
                  class="text-sm font-medium"
                  :class="effectiveStage === o.id ? 'text-emerald-900' : 'text-slate-800'"
                >{{ o.label }}</span>
                <span
                  v-if="i === 0 && o.status === 'succeeded'"
                  class="text-[10px] font-medium px-1.5 py-0.5 rounded border"
                  :class="effectiveStage === o.id
                    ? 'bg-emerald-100 border-emerald-200 text-emerald-800'
                    : 'bg-slate-100 border-slate-200 text-slate-600'"
                >最新版</span>
                <span
                  v-if="o.status !== 'succeeded'"
                  class="text-[10px] font-medium text-slate-400 bg-slate-100 rounded px-1.5 py-0.5"
                >{{ stageStatusHint(o.status) }}</span>
              </div>
              <p
                class="text-xs mt-0.5"
                :class="effectiveStage === o.id ? 'text-emerald-800/80' : 'text-slate-400'"
              >{{ o.hint }}</p>
            </div>
          </label>
        </div>
      </div>

      <!-- 格式选择 -->
      <div class="px-6 py-4 border-t border-slate-100">
        <p class="text-xs font-semibold text-slate-500 mb-2">文件格式</p>
        <div class="grid grid-cols-3 gap-2">
          <label
            v-for="opt in [
              { value: 'word', label: 'Word（推荐）', icon: 'fa-file-word' },
              { value: 'pdf',  label: 'PDF（推荐）',  icon: 'fa-file-pdf' },
              { value: 'json', label: 'JSON', icon: 'fa-file-code' },
            ]"
            :key="opt.value"
            class="flex flex-col items-center gap-1.5 border rounded-xl py-3 cursor-pointer transition-all"
            :class="activeFormat === opt.value ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-400'"
          >
            <input type="radio" :value="opt.value" v-model="activeFormat" class="sr-only" />
            <i :class="['fa-solid text-xl', opt.icon, activeFormat === opt.value ? 'text-slate-800' : 'text-slate-400']" />
            <span class="text-xs font-medium" :class="activeFormat === opt.value ? 'text-slate-800' : 'text-slate-500'">{{ opt.label }}</span>
          </label>
        </div>
      </div>

      <!-- 试卷类型 + 语言（同一行，窄屏自动换行） -->
      <div class="px-6 py-4 border-t border-slate-100">
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
          <template v-if="activeFormat !== 'json'">
            <span class="text-xs font-semibold text-slate-500 shrink-0">试卷类型</span>
            <div class="flex gap-2 flex-wrap min-w-0">
              <label
                v-for="opt in [
                  { value: 'with_answer', label: '教师卷', sub: '含答案与解析' },
                  { value: 'blank',       label: '学生卷', sub: '空白答案栏' },
                ]"
                :key="opt.value"
                class="flex flex-col gap-0.5 border rounded-xl px-4 py-2.5 cursor-pointer transition-all min-w-[140px] flex-1 sm:flex-initial sm:min-w-[160px]"
                :class="variant === opt.value ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-400'"
              >
                <input type="radio" :value="opt.value" v-model="variant" class="sr-only" />
                <span class="text-sm font-medium" :class="variant === opt.value ? 'text-slate-900' : 'text-slate-600'">{{ opt.label }}</span>
                <span class="text-xs text-slate-400">{{ opt.sub }}</span>
              </label>
            </div>
          </template>
          <div
            :class="[
              'flex flex-wrap items-center gap-x-4 gap-y-2 min-w-0',
              activeFormat !== 'json' && 'sm:border-l sm:border-slate-200 sm:pl-6',
            ]"
          >
          <span class="text-xs font-semibold text-slate-500 shrink-0">语言选择</span>
          <div class="flex gap-2 flex-wrap">
            <label
              v-for="o in LANG_OPTIONS"
              :key="o.value"
              class="flex items-center gap-1.5 text-xs border rounded-lg px-2.5 py-1.5 transition-all"
              :class="[
                lang === o.value ? 'border-slate-900 bg-slate-50 text-slate-900 font-medium' : 'border-slate-200 text-slate-500',
                langOptionEnabled(o.value) ? 'cursor-pointer hover:border-slate-400' : 'opacity-40 cursor-not-allowed',
              ]"
            >
              <input type="radio" :value="o.value" v-model="lang" class="sr-only" :disabled="!langOptionEnabled(o.value)" />
              {{ o.label.split('（')[0] }}
            </label>
          </div>
          </div>
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="px-6 py-4 border-t border-slate-100 flex items-center justify-between gap-3">
        <!-- 状态反馈 -->
        <div class="text-xs min-w-0">
          <span v-if="jobs[activeFormat as Format]?.status === 'running' || jobs[activeFormat as Format]?.status === 'pending'" class="text-amber-600 flex items-center gap-1.5">
            <i class="fa-solid fa-circle-notch animate-spin text-[10px]" />生成中…
          </span>
          <span v-else-if="jobs[activeFormat as Format]?.status === 'succeeded'" class="text-emerald-600">✓ 已生成，可再次下载</span>
          <span v-else-if="jobs[activeFormat as Format]?.status === 'failed'" class="text-rose-600 truncate">{{ jobs[activeFormat as Format]?.errorMessage || '生成失败' }}</span>
          <span v-else class="text-slate-400">选好配置后点击生成</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button
            v-if="jobs[activeFormat as Format]?.status === 'succeeded'"
            class="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
            @click="downloadAgain(activeFormat as Format)"
          >
            再次下载
          </button>
          <button
            class="px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
            :class="jobs[activeFormat as Format]?.status === 'succeeded' ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-slate-900 text-white hover:bg-slate-700'"
            :disabled="disabledOf(activeFormat as Format)"
            @click="startExport(activeFormat as Format)"
          >
            <i v-if="disabledOf(activeFormat as Format)" class="fa-solid fa-circle-notch animate-spin text-xs" />
            <i v-else class="fa-solid fa-download text-xs" />
            <span>{{ disabledOf(activeFormat as Format) ? '生成中…' : jobs[activeFormat as Format]?.status === 'succeeded' ? '重新生成' : '生成并下载' }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="mt-6 bg-white border border-slate-200 rounded-2xl p-5">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 class="text-sm font-semibold text-slate-900">多文件 JSON（旧版 zip）</h3>
          <p class="text-xs text-slate-500 mt-0.5">
            需要原始多文件 zip？可走旧版接口直接下载所选 stage 下所有 <code>*.json</code>。
            <span v-if="isLegacyJsonZip">（已启用旧版）</span>
          </p>
        </div>
        <button
          class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900"
          @click="downloadLegacyZip"
        >
          下载 zip（旧版）
        </button>
      </div>
    </div>

    <!-- 只读分享链接 -->
    <div class="mt-6 bg-white border border-slate-200 rounded-2xl p-5">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold text-slate-900">只读分享链接</h3>
          <p class="text-xs text-slate-500 mt-0.5">生成链接后，同事无需登录即可浏览题库。</p>
        </div>
        <button
          class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900"
          @click="shareOpen = !shareOpen"
        >
          {{ shareOpen ? '收起' : '生成分享链接' }}
        </button>
      </div>

      <div v-if="shareOpen" class="mt-4 space-y-3">
        <div class="flex items-center gap-3">
          <label class="text-sm text-slate-600 whitespace-nowrap">链接有效期</label>
          <select
            v-model="shareExpires"
            class="text-sm border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
          >
            <option v-for="opt in EXPIRES_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
          <button
            class="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
            :disabled="shareLoading"
            @click="createShare"
          >
            {{ shareLoading ? '生成中...' : '生成' }}
          </button>
        </div>

        <div v-if="shareResult" class="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
          <div class="flex items-center gap-2">
            <input
              type="text"
              readonly
              :value="fullShareUrl(shareResult.token)"
              class="flex-1 text-xs bg-white border border-slate-300 rounded-lg px-3 py-1.5 font-mono text-slate-700 min-w-0"
            />
            <button
              class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg hover:bg-white whitespace-nowrap"
              :class="{ 'border-emerald-400 text-emerald-700': shareCopied }"
              @click="copyShareLink"
            >
              {{ shareCopied ? '已复制' : '复制' }}
            </button>
          </div>
          <p class="text-xs text-slate-400">
            <span v-if="shareResult.expires_at">
              有效至 {{ new Date(shareResult.expires_at).toLocaleString() }}
            </span>
            <span v-else>永久有效</span>
            · 题目数据为生成时最新阶段快照，只读不可编辑
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
