<script setup lang="ts">
import { ref } from 'vue';
import { usePipelineStore } from '@/stores/pipeline';
import { useToastStore } from '@/stores/toast';

const store = usePipelineStore();
const toastStore = useToastStore();
const bookInput = ref('生物学必修1');
const loadError = ref('');
const loading = ref(false);

async function handleLoad() {
  const book = bookInput.value.trim();
  if (!book) {
    loadError.value = '请输入教材名称';
    return;
  }
  loadError.value = '';
  loading.value = true;
  try {
    await store.load(book);
    toastStore.show(`已加载 ${book}`, 'success');
  } catch (err) {
    loadError.value = (err instanceof Error ? err.message : '加载失败') + '，请确保后端服务已启动';
  } finally {
    loading.value = false;
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') handleLoad();
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-4">
    <div class="max-w-lg w-full">
      <div class="text-center mb-8">
        <div
          class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-50 mb-4"
        >
          <svg
            class="w-7 h-7 text-brand-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
            />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-slate-900 tracking-tight">
          DataFlow-EDU Pipeline
        </h1>
        <p class="mt-2 text-sm text-slate-500">
          从固定路径加载知识分类、题目生成、题目均衡三阶段数据
        </p>
      </div>

      <div class="bg-white rounded-2xl shadow-sm border border-slate-200/60 p-6 space-y-4">
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-2">教材名称</label>
          <input
            v-model="bookInput"
            type="text"
            placeholder="生物学必修1"
            class="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400"
            @keydown="onKeydown"
          />
          <p class="mt-1.5 text-xs text-slate-400">
            将加载 dataflow_edu/data/generation_and_balancing/ 下对应 JSON
          </p>
        </div>
        <button
          :disabled="loading"
          class="w-full py-3 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors cursor-pointer disabled:opacity-70"
          @click="handleLoad"
        >
          {{ loading ? '加载中...' : '加载' }}
        </button>
      </div>

      <div
        v-if="loadError"
        class="mt-4 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700"
      >
        {{ loadError }}
      </div>
    </div>
  </div>
</template>
