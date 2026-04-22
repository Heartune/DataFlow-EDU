<script setup lang="ts">
import { computed } from 'vue';
import LoadView from '@/views/LoadView.vue';
import DashboardView from '@/views/DashboardView.vue';
import QuestionSidebar from '@/components/QuestionSidebar.vue';
import ToastContainer from '@/components/ToastContainer.vue';
import { usePipelineStore } from '@/stores/pipeline';
import { useAuthStore } from '@/stores/auth';

const store = usePipelineStore();
const auth = useAuthStore();
const showLoad = computed(() => !store.bookName && !store.showConfigOnly);
</script>

<template>
  <div class="relative">
    <div
      class="fixed top-3 right-3 z-50 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900 text-white text-xs font-medium shadow-lg"
      title="管理员模式：所有 /api/admin/* 接口已校验 role=admin"
    >
      <span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
      管理员模式 · {{ auth.user?.email || 'admin' }}
    </div>
    <LoadView v-if="showLoad" />
    <DashboardView v-else :config-only="store.showConfigOnly" />
    <QuestionSidebar />
    <ToastContainer />
  </div>
</template>
