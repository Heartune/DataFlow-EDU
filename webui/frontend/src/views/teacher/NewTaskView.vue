<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api, LLM_KEY_KEY } from '@/api/client';

const router = useRouter();

const file = ref<File | null>(null);
const dragHover = ref(false);
const taskName = ref('');
const llmKey = ref(localStorage.getItem(LLM_KEY_KEY) || '');
const remember = ref(true);
const uploading = ref(false);
const error = ref('');
const progress = ref<string>('');

const sizeLabel = computed(() => {
  if (!file.value) return '';
  const mb = file.value.size / 1024 / 1024;
  return `${mb.toFixed(2)} MB`;
});

function pickFile(f: File | null | undefined) {
  if (!f) return;
  if (!/\.pdf$/i.test(f.name) && f.type !== 'application/pdf') {
    error.value = '只接受 PDF 文件';
    return;
  }
  if (f.size > 50 * 1024 * 1024) {
    error.value = `文件过大（${(f.size / 1024 / 1024).toFixed(1)}MB），上限 50MB`;
    return;
  }
  error.value = '';
  file.value = f;
  if (!taskName.value) {
    taskName.value = f.name.replace(/\.pdf$/i, '');
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

async function submit() {
  if (!file.value) {
    error.value = '请先选择 PDF';
    return;
  }
  if (!taskName.value.trim()) {
    error.value = '请填写任务名称';
    return;
  }
  if (!llmKey.value.trim()) {
    error.value = '请填写 LLM API Key（仅保存在本地浏览器）';
    return;
  }

  if (remember.value) {
    localStorage.setItem(LLM_KEY_KEY, llmKey.value.trim());
  } else {
    localStorage.removeItem(LLM_KEY_KEY);
  }

  uploading.value = true;
  error.value = '';
  progress.value = '正在上传 PDF...';

  try {
    const form = new FormData();
    form.append('pdf', file.value);
    form.append('name', taskName.value.trim());
    const { data: created } = await api.post('/tasks/upload-pdf', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    progress.value = '正在启动 pipeline...';
    await api.post(`/tasks/${created.task_id}/run`);

    router.replace(`/teacher/tasks/${created.task_id}`);
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'daily_quota_exceeded') {
      error.value = `已达每日上传上限（${err.response.data.limit} 次）`;
    } else if (code === 'user_has_running_task') {
      error.value = '你已有任务在跑，等它结束后再启动新任务';
    } else if (code === 'missing_llm_key') {
      error.value = 'LLM Key 缺失，请填写后重试';
    } else if (code === 'only_pdf_allowed') {
      error.value = '只接受 PDF 文件';
    } else {
      error.value = err?.response?.data?.message || err?.message || '提交失败';
    }
  } finally {
    uploading.value = false;
    progress.value = '';
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold text-slate-900 mb-1">新建任务</h1>
    <p class="text-sm text-slate-500 mb-6">
      上传一份教材 PDF，系统会跑完 OCR → 题目生成 → 清洗 → 翻译 → 选择题校验 全流程。
    </p>

    <div class="bg-white border border-slate-200 rounded-2xl p-6 space-y-5">
      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">教材 PDF</label>
        <div
          :class="[
            'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition',
            dragHover ? 'border-slate-900 bg-slate-50' : 'border-slate-300 hover:border-slate-500',
          ]"
          @dragover.prevent="dragHover = true"
          @dragleave="dragHover = false"
          @drop="onDrop"
          @click="($refs.fi as HTMLInputElement).click()"
        >
          <input ref="fi" type="file" accept="application/pdf,.pdf" class="hidden" @change="onFileChange" />
          <div v-if="!file" class="text-slate-500">
            <p class="text-base">将 PDF 拖到此处，或点击选择</p>
            <p class="text-xs mt-2">单文件 ≤ 50MB</p>
          </div>
          <div v-else class="text-slate-700">
            <p class="font-medium text-slate-900">{{ file.name }}</p>
            <p class="text-xs text-slate-500 mt-1">{{ sizeLabel }} · 点击重新选择</p>
          </div>
        </div>
      </div>

      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">任务名称（即教材名）</label>
        <input
          v-model="taskName"
          type="text"
          class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          placeholder="例如：生物学必修1"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-slate-700 mb-2">
          LLM API Key（BYOK · 仅存本地浏览器）
        </label>
        <input
          v-model="llmKey"
          type="password"
          class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900 font-mono text-sm"
          placeholder="sk-..."
          autocomplete="off"
        />
        <label class="flex items-center gap-2 text-xs text-slate-500 mt-2">
          <input v-model="remember" type="checkbox" />
          记住到本地浏览器（下次自动填充；后端不会落库）
        </label>
      </div>

      <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
      <p v-if="progress" class="text-sm text-slate-500">{{ progress }}</p>

      <div class="flex gap-3">
        <button
          class="px-4 py-2 border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900"
          :disabled="uploading"
          @click="router.back()"
        >
          取消
        </button>
        <button
          class="flex-1 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
          :disabled="uploading"
          @click="submit"
        >
          {{ uploading ? '提交中...' : '上传并开始运行' }}
        </button>
      </div>
    </div>
  </div>
</template>
