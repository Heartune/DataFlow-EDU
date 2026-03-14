<script setup lang="ts">
import { computed } from 'vue';
import { usePipelineStore } from '@/stores/pipeline';

const store = usePipelineStore();

const hasStage1 = computed(() => !!store.stage1Data);
const hasStage2 = computed(() => !!store.stage2Data);
const hasStage3 = computed(() => !!store.stage3Data);

function hasStage(i: number) {
  if (i === 1) return hasStage1.value;
  if (i === 2) return hasStage2.value;
  return hasStage3.value;
}

function switchStage(stage: number) {
  if (hasStage(stage)) store.currentStage = stage;
}

function showLoadSection() {
  store.reset();
}
</script>

<template>
  <header
    class="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-50"
  >
    <div class="max-w-7xl mx-auto px-4 sm:px-6">
      <div class="py-3 flex items-center justify-between border-b border-slate-100">
        <div class="min-w-0">
          <h1 class="text-base font-bold text-slate-900 truncate">
            DataFlow-EDU Pipeline
          </h1>
          <p class="text-xs text-slate-500 mt-0.5 truncate">
            阶段1 · 阶段2 · 阶段3 · {{ store.bookName }}
          </p>
        </div>
        <button
          class="flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
          @click="showLoadSection"
        >
          <svg
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="23 4 23 10 17 10" />
            <path
              d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"
            />
          </svg>
          更换教材
        </button>
      </div>
      <div class="flex items-center gap-1 py-2">
        <button
          v-for="i in 3"
          :key="i"
          :disabled="!hasStage(i)"
          :class="[
            'tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            !hasStage(i)
              ? 'text-slate-400 cursor-not-allowed'
              : store.currentStage === i
                ? 'bg-brand-500 text-white'
                : 'text-slate-600 hover:bg-slate-100',
          ]"
          :data-stage="i"
          @click="switchStage(i)"
        >
          {{ i === 1 ? '阶段1 · 知识分类' : i === 2 ? '阶段2 · 题目生成' : '阶段3 · 题目均衡' }}
        </button>
      </div>
    </div>
  </header>
</template>
