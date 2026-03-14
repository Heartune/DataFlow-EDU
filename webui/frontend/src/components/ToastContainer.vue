<script setup lang="ts">
import { useToastStore } from '@/stores/toast';

const toastStore = useToastStore();
</script>

<template>
  <div class="fixed top-4 right-4 z-[100] space-y-2 pointer-events-none flex flex-col items-end">
    <TransitionGroup name="toast">
      <div
        v-for="t in toastStore.items"
        :key="t.id"
        :class="[
          'flex items-center gap-2 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium animate-slide-in-right',
          t.type === 'success' && 'bg-green-50 border-green-200 text-green-800',
          t.type === 'warning' && 'bg-amber-50 border-amber-200 text-amber-800',
          t.type === 'info' && 'bg-blue-50 border-blue-200 text-blue-800',
        ]"
      >
        <svg
          v-if="t.type === 'success'"
          class="w-4 h-4 flex-shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M22 11.08V12a10 10 0 1 1-5.93-9.14"
          />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
        <svg
          v-else-if="t.type === 'warning'"
          class="w-4 h-4 flex-shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
          />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <svg
          v-else
          class="w-4 h-4 flex-shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        <span>{{ t.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
