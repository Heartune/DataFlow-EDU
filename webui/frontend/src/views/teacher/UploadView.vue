<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { isNavigationFailure, useRouter } from 'vue-router';
import { api } from '@/api/client';

const router = useRouter();

const file = ref<File | null>(null);
const dragHover = ref(false);
const taskName = ref('');

const llmKeyHint = ref('');
const uploading = ref(false);
const error = ref('');
const progress = ref<string>('');

interface Quota {
  used: number;
  limit: number;
  remaining: number;
}
interface LlmQuota {
  used: number;
  limit: number;
  remaining: number;
  platform_key_hint: string;
}

const quota = ref<Quota | null>(null);
const llmQuota = ref<LlmQuota | null>(null);

// ── 快速开始状态 ───────────────────────────────────────────────
const showQuickModal = ref(false);
const createdTaskId = ref('');
const quickGrade = ref<'senior' | 'junior'>('senior');
const quickSubject = ref('biology');
const quickSubmitting = ref(false);
const quickError = ref('');

const GRADE_OPTIONS = [
  { value: 'senior' as const, label: '高中' },
  { value: 'junior' as const, label: '初中' },
];

const SUBJECT_OPTIONS: { value: string; seniorLabel: string; juniorLabel: string }[] = [
  { value: 'chinese',   seniorLabel: '语文',       juniorLabel: '语文' },
  { value: 'math',      seniorLabel: '数学',       juniorLabel: '数学' },
  { value: 'english',   seniorLabel: '英语',       juniorLabel: '英语' },
  { value: 'physics',   seniorLabel: '物理',       juniorLabel: '物理' },
  { value: 'chemistry', seniorLabel: '化学',       juniorLabel: '化学' },
  { value: 'biology',   seniorLabel: '生物学',     juniorLabel: '生物学' },
  { value: 'politics',  seniorLabel: '思想政治',   juniorLabel: '道德与法治' },
  { value: 'history',   seniorLabel: '历史',       juniorLabel: '历史' },
  { value: 'geography', seniorLabel: '地理',       juniorLabel: '地理' },
];

function subjectLabel(s: typeof SUBJECT_OPTIONS[0]) {
  return quickGrade.value === 'senior' ? s.seniorLabel : s.juniorLabel;
}

async function loadQuota() {
  try {
    const [q, lq] = await Promise.all([
      api.get<Quota>('/tasks/quota'),
      api.get<LlmQuota>('/tasks/llm-quota'),
    ]);
    quota.value = q.data;
    llmQuota.value = lq.data;
    llmKeyHint.value = lq.data.platform_key_hint;
  } catch {
    /* 配额加载失败不阻塞主流程 */
  }
}

onMounted(loadQuota);

const sizeLabel = computed(() => {
  if (!file.value) return '';
  const mb = file.value.size / 1024 / 1024;
  return `${mb.toFixed(2)} MB`;
});

function pickFile(f: File | null | undefined) {
  if (!f) return;
  const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf';
  const isPpt =
    /\.(pptx|ppt)$/i.test(f.name) ||
    f.type === 'application/vnd.openxmlformats-officedocument.presentationml.presentation' ||
    f.type === 'application/vnd.ms-powerpoint';
  if (!isPdf && !isPpt) {
    error.value = '只接受 PDF 或 PPT/PPTX 格式的文件';
    return;
  }
  if (f.size > 50 * 1024 * 1024) {
    error.value = `文件过大（${(f.size / 1024 / 1024).toFixed(1)}MB），上限 50MB`;
    return;
  }
  error.value = '';
  file.value = f;
  if (!taskName.value) {
    taskName.value = f.name.replace(/\.(pdf|pptx|ppt)$/i, '');
  }
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  pickFile(input.files?.[0]);
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  dragHover.value = false;
  pickFile(e.dataTransfer?.files?.[0]);
}

async function submit(mode: 'wizard' | 'quick') {
  if (!file.value) {
    error.value = '请先选择文件';
    return;
  }
  if (!taskName.value.trim()) {
    error.value = '请填写任务名称';
    return;
  }

  uploading.value = true;
  error.value = '';
  const isPptFile = /\.(pptx|ppt)$/i.test(file.value.name);
  progress.value = isPptFile ? '正在上传课件（PPT 将自动转为 PDF）...' : '正在上传文件...';

  try {
    const form = new FormData();
    form.append('pdf', file.value);
    form.append('name', taskName.value.trim());
    // original: form.append('provider', 'zgca');
    form.append('provider', 'blt');
    const { data: created } = await api.post('/tasks/upload-pdf', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    if (mode === 'quick') {
      createdTaskId.value = created.task_id;
      showQuickModal.value = true;
    } else {
      progress.value = '上传完成，正在打开配置向导…';
      const taskId = created.task_id;
      const navTimeoutMs = 60_000;
      try {
        await new Promise<void>((resolve, reject) => {
          const t = window.setTimeout(() => {
            reject(
              new Error(
                `配置页加载超时（${Math.round(navTimeoutMs / 1000)} 秒）。请到「任务列表」打开该任务并进入「配置」。`,
              ),
            );
          }, navTimeoutMs);
          router
            .replace({ name: 'teacher-task-wizard', params: { id: taskId } })
            .then((failure) => {
              window.clearTimeout(t);
              if (failure && isNavigationFailure(failure)) {
                reject(new Error('暂时无法跳转，请从任务列表打开该任务的「配置」步骤。'));
              } else {
                resolve();
              }
            })
            .catch((e: unknown) => {
              window.clearTimeout(t);
              reject(e instanceof Error ? e : new Error(String(e)));
            });
        });
      } catch (e: unknown) {
        error.value = e instanceof Error ? e.message : '跳转失败';
      }
    }
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'daily_quota_exceeded') {
      error.value = `已达每日上传上限（${err.response.data.limit} 次）`;
    } else if (code === 'llm_quota_exceeded') {
      error.value = `今日 AI 大模型额度已耗尽（上限 ${err.response.data.limit?.toLocaleString()} 积分），请明日再试`;
    } else if (code === 'user_has_running_task') {
      error.value = '你已有任务在跑，等它结束后再启动新任务';
    } else if (code === 'missing_llm_key') {
      error.value = 'LLM Key 缺失，请联系管理员';
    } else if (code === 'only_pdf_or_ppt_allowed' || code === 'only_pdf_allowed') {
      error.value = '只接受 PDF 或 PPT/PPTX 格式的文件';
    } else if (code === 'ppt_convert_failed') {
      error.value = err?.response?.data?.message || 'PPT 转换失败，请联系管理员';
    } else {
      error.value = err?.response?.data?.message || err?.message || '提交失败';
    }
  } finally {
    uploading.value = false;
    progress.value = '';
  }
}

async function quickConfirm() {
  quickError.value = '';
  quickSubmitting.value = true;
  const preset = `${quickGrade.value}_${quickSubject.value}`;
  try {
    await api.post(`/tasks/${createdTaskId.value}/config`, { preset, overrides: {} });
    await api.post(`/tasks/${createdTaskId.value}/run`);
    router.replace(`/teacher/tasks/${createdTaskId.value}`);
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'user_has_running_task') {
      quickError.value = '你已有任务在跑，等它结束后再启动新任务';
    } else {
      quickError.value = err?.response?.data?.message || err?.message || '启动失败，请重试';
    }
    quickSubmitting.value = false;
  }
}

function closeQuickModal() {
  if (quickSubmitting.value) return;
  showQuickModal.value = false;
  // 上传已完成，跳进度页让用户自行决定
  if (createdTaskId.value) {
    router.replace(`/teacher/tasks/${createdTaskId.value}/wizard`);
  }
}

/** 关闭弹窗并留在上传页（任务已在服务端创建，可从任务列表继续处理） */
function backFromQuickModal() {
  if (quickSubmitting.value) return;
  showQuickModal.value = false;
  createdTaskId.value = '';
}
</script>

<template>
  <div class="max-w-2xl mx-auto min-w-0">
    <router-link
      to="/teacher/tasks"
      class="text-sm text-slate-500 hover:text-slate-900 mb-4 inline-block"
    >
      ← 返回任务列表
    </router-link>
    <h1 class="text-2xl font-bold text-slate-900 mb-1">新建任务</h1>
    <p class="text-sm text-slate-500 mb-3 leading-6">
      上传一份教科书、教辅书、课件等「任意」教学材料（PDF 或 PPT/PPTX 格式），<br>系统自动生成高质量习题与解析，并支持一键导出为试卷。<br>生成的习题将紧扣上传素材的内容。推荐上传课本，达到「回归课本」的效果。
    </p>

    <!-- 今日上传配额 -->
    <div
      v-if="quota !== null"
      :class="[
        'flex items-center gap-2 text-sm rounded-xl px-4 py-2 mb-3 border',
        quota.remaining === 0
          ? 'bg-rose-50 border-rose-200 text-rose-700'
          : 'bg-emerald-50 border-emerald-200 text-emerald-700',
      ]"
    >
      <span v-if="quota.remaining > 0">
        今天还能上传 <span class="font-semibold">{{ quota.remaining }}</span> 次（已用 {{ quota.used }} / 共 {{ quota.limit }} 次）
      </span>
      <span v-else class="font-medium">今日上传次数已用完（{{ quota.limit }} 次），请明日再试</span>
    </div>

    <!-- 今日 AI 大模型额度 -->
    <div
      v-if="llmQuota !== null"
      :class="[
        'flex items-center gap-2 text-sm rounded-xl px-4 py-2 mb-5 border',
        llmQuota.remaining === 0
          ? 'bg-rose-50 border-rose-200 text-rose-700'
          : 'bg-emerald-50 border-emerald-200 text-emerald-700',
      ]"
    >
      <span v-if="llmQuota.remaining > 0">
        今日 AI 大模型额度剩余
        <span class="font-semibold">{{ llmQuota.remaining.toLocaleString() }}</span> 积分
        （已用 {{ llmQuota.used.toLocaleString() }} / 共 {{ llmQuota.limit.toLocaleString() }}）
      </span>
      <span v-else class="font-medium">今日 AI 大模型额度已耗尽（{{ llmQuota.limit.toLocaleString() }} 积分），请明日再试</span>
    </div>

    <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-6 space-y-5">
      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">素材文件</label>
        <div
          :class="[
            'border-2 border-dashed rounded-xl p-5 sm:p-8 text-center cursor-pointer transition',
            dragHover ? 'border-slate-900 bg-slate-50' : 'border-slate-300 hover:border-slate-500',
          ]"
          @dragover.prevent="dragHover = true"
          @dragleave="dragHover = false"
          @drop="onDrop"
          @click="($refs.fi as HTMLInputElement).click()"
        >
          <input ref="fi" type="file" accept="application/pdf,.pdf,.pptx,.ppt" class="hidden" @change="onFileChange" />
          <div v-if="!file" class="text-slate-500">
            <p class="text-base">将素材拖到此处，或点击选择</p>
            <p class="text-xs mt-1">可上传教材、教辅、课件等任意教学资料（PDF 或 PPT/PPTX）</p>
            <p class="text-xs mt-1">单文件 ≤ 50MB · PPT/PPTX 将自动转为 PDF 后处理</p>
          </div>
          <div v-else class="text-slate-700">
            <p class="font-medium text-slate-900 break-all">{{ file.name }}</p>
            <p class="text-xs text-slate-500 mt-1">{{ sizeLabel }} · 点击重新选择</p>
          </div>
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">任务名称</label>
        <input
          v-model="taskName"
          type="text"
          class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          placeholder="例如：生物学必修1"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">AI 服务来源</label>
        <select
          disabled
          class="w-full px-3 py-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-500 text-sm cursor-not-allowed"
        >
          <!-- original: <option value="zgca" selected>ZGCA（平台）</option> -->
          <option value="blt" selected>BLT（平台）</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">
          API 密钥
        </label>
        <input
          value="已自动为您填入，您无需提供"
          type="text"
          readonly
          class="w-full px-3 py-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-400 text-sm cursor-not-allowed"
        />
        <p class="text-xs text-slate-400 mt-1.5">由平台统一管理，每日配额已在上方展示</p>
      </div>

      <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>

      <!-- 上传中进度条 -->
      <div v-if="uploading" class="space-y-1.5">
        <p class="text-sm text-slate-500">{{ progress }}</p>
        <div class="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div class="h-full bg-slate-900 rounded-full upload-indeterminate" />
        </div>
      </div>

      <div class="flex flex-col sm:flex-row gap-3">
        <button
          class="px-4 py-2 border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900"
          :disabled="uploading"
          @click="router.back()"
        >
          取消
        </button>
        <button
          class="flex-1 py-2 border border-slate-300 text-slate-700 rounded-lg hover:border-slate-900 hover:text-slate-900 disabled:opacity-50"
          :disabled="uploading || quota?.remaining === 0 || llmQuota?.remaining === 0"
          @click="submit('wizard')"
        >
          自定义配置
        </button>
        <button
          class="flex-1 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 flex items-center justify-center gap-1.5"
          :disabled="uploading || quota?.remaining === 0 || llmQuota?.remaining === 0"
          @click="submit('quick')"
        >
          <span>⚡</span>
          <span>{{ uploading ? '上传中...' : '快速开始' }}</span>
        </button>
      </div>
    </div>
  </div>

  <!-- 快速开始 Modal -->
  <Teleport to="body">
    <div
      v-if="showQuickModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="closeQuickModal"
    >
      <div class="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-sm mx-4">
        <button
          type="button"
          class="w-full text-left text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg px-2 py-2 -mx-2 mb-2 border border-transparent hover:border-slate-200 transition"
          :disabled="quickSubmitting"
          @click="backFromQuickModal"
        >
          ← 返回上传页
        </button>
        <h2 class="text-lg font-bold text-slate-900 mb-1">快速开始</h2>
        <p class="text-sm text-slate-500 mb-5">请指定学段和学科。<br>目前支持我国初高中九大学科，<br>如初中数学、高中语文、高中物理等。</p>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1.5">学段</label>
            <div class="flex gap-2">
              <button
                v-for="g in GRADE_OPTIONS"
                :key="g.value"
                type="button"
                :class="[
                  'flex-1 py-2 rounded-lg border text-sm font-medium transition',
                  quickGrade === g.value
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-300 text-slate-700 hover:border-slate-500',
                ]"
                @click="quickGrade = g.value"
              >
                {{ g.label }}
              </button>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1.5">学科</label>
            <select
              v-model="quickSubject"
              class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900 bg-white text-sm"
            >
              <option v-for="s in SUBJECT_OPTIONS" :key="s.value" :value="s.value">
                {{ subjectLabel(s) }}
              </option>
            </select>
          </div>

          <p v-if="quickError" class="text-sm text-rose-600">{{ quickError }}</p>
        </div>

        <div class="flex flex-col gap-3 mt-6">
          <button
            type="button"
            class="w-full py-2 px-3 border border-slate-300 rounded-lg text-slate-600 hover:border-slate-500 text-sm text-center leading-snug"
            :disabled="quickSubmitting"
            @click="closeQuickModal"
          >
            没找到对应学段或学科？改用自定义配置
          </button>
          <button
            type="button"
            class="w-full py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 text-sm font-medium"
            :disabled="quickSubmitting"
            @click="quickConfirm"
          >
            {{ quickSubmitting ? '正在启动...' : '确认，开始生成' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
@keyframes indeterminate {
  0%   { transform: translateX(-100%) scaleX(0.4); }
  50%  { transform: translateX(60%)   scaleX(0.6); }
  100% { transform: translateX(200%)  scaleX(0.4); }
}
.upload-indeterminate {
  animation: indeterminate 1.4s ease-in-out infinite !important;
  transition-duration: 0s !important;
}
</style>
