<script setup lang="ts">
import { computed } from 'vue';
import LoadView from '@/views/LoadView.vue';
import DashboardView from '@/views/DashboardView.vue';
import QuestionSidebar from '@/components/QuestionSidebar.vue';
import ToastContainer from '@/components/ToastContainer.vue';
import { usePipelineStore } from '@/stores/pipeline';

const store = usePipelineStore();
const showLoad = computed(() => !store.bookName);
</script>

<template>
  <div class="bg-slate-50 min-h-screen font-sans text-slate-900 antialiased">
    <LoadView v-if="showLoad" />
    <DashboardView v-else />

    <QuestionSidebar />
    <ToastContainer />
  </div>
</template>
