<script setup lang="ts">
import { computed } from 'vue';
import { useQuestionSidebar } from '@/stores/questionSidebar';
import { escapeHtml } from '@/utils/escapeHtml';

const sidebarStore = useQuestionSidebar();

const visible = computed(() => sidebarStore.openState);
const question = computed(() => sidebarStore.question);

const diffClass = computed(() => {
  const q = question.value;
  if (!q) return 'bg-slate-100 text-slate-600';
  if (q.difficulty === '难') return 'bg-red-100 text-red-700';
  if (q.difficulty === '易') return 'bg-green-100 text-green-700';
  return 'bg-slate-100 text-slate-600';
});

function close() {
  sidebarStore.close();
}
</script>

<template>
  <Transition name="overlay">
    <div
      v-if="visible"
      class="fixed inset-0 bg-black/30 z-50"
      @click="close"
    />
  </Transition>
  <Transition name="sidebar">
    <div
      v-if="visible"
      class="fixed top-0 right-0 w-full sm:w-[420px] h-full bg-white shadow-2xl z-50 overflow-y-auto"
    >
      <div
        class="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between"
      >
        <h3 class="text-base font-semibold text-slate-800">题目详情</h3>
        <button
          class="p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
          @click="close"
        >
          <svg
            class="w-5 h-5 text-slate-500"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div v-if="question" class="p-5 space-y-5">
        <div>
          <label class="text-xs font-medium text-slate-500 block mb-1.5"
            >题目</label
          >
          <div
            class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap bg-slate-50 rounded-lg p-3"
            v-html="escapeHtml(question.question || '-')"
          />
        </div>
        <div>
          <label class="text-xs font-medium text-slate-500 block mb-1.5"
            >标准答案</label
          >
          <div
            class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap bg-green-50 rounded-lg p-3 border border-green-100"
            v-html="escapeHtml(question.answer || '-')"
          />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-xs font-medium text-slate-500 block mb-1.5"
              >题型</label
            >
            <div class="text-sm text-slate-700">
              {{ question.type || '-' }}
            </div>
          </div>
          <div>
            <label class="text-xs font-medium text-slate-500 block mb-1.5"
              >知识小类</label
            >
            <div class="text-sm text-slate-700">
              {{ question.subcategory || '-' }}
            </div>
          </div>
          <div>
            <label class="text-xs font-medium text-slate-500 block mb-1.5"
              >能力层级</label
            >
            <div class="text-sm text-slate-700">
              {{ question.ability_level || '-' }}
            </div>
          </div>
          <div>
            <label class="text-xs font-medium text-slate-500 block mb-1.5"
              >难度</label
            >
            <span
              :class="['inline-block px-2 py-0.5 rounded text-xs', diffClass]"
            >
              {{ question.difficulty || '-' }}
            </span>
          </div>
          <div>
            <label class="text-xs font-medium text-slate-500 block mb-1.5"
              >来源页</label
            >
            <div class="text-sm text-slate-700">
              {{ question.source_page || '-' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.overlay-enter-active,
.overlay-leave-active {
  transition: opacity 0.3s;
}
.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}

.sidebar-enter-active,
.sidebar-leave-active {
  transition: transform 0.3s ease-out;
}
.sidebar-enter-from,
.sidebar-leave-to {
  transform: translateX(100%);
}
</style>
