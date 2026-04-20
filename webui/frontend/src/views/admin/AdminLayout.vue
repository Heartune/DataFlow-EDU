<script setup lang="ts">
import { computed } from 'vue';
import LoadView from '@/views/LoadView.vue';
import DashboardView from '@/views/DashboardView.vue';
import QuestionSidebar from '@/components/QuestionSidebar.vue';
import ToastContainer from '@/components/ToastContainer.vue';
import { usePipelineStore } from '@/stores/pipeline';

const store = usePipelineStore();
const showLoad = computed(() => !store.bookName && !store.showConfigOnly);
</script>

<template>
  <div>
    <LoadView v-if="showLoad" />
    <DashboardView v-else :config-only="store.showConfigOnly" />
    <QuestionSidebar />
    <ToastContainer />
  </div>
</template>
