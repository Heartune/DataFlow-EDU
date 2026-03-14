<script setup lang="ts">
import DashboardHeader from '@/components/DashboardHeader.vue';
import ConfigView from '@/components/ConfigView.vue';
import Stage1View from '@/components/Stage1View.vue';
import Stage2View from '@/components/Stage2View.vue';
import Stage3View from '@/components/Stage3View.vue';
import { usePipelineStore } from '@/stores/pipeline';
import { computed } from 'vue';

defineProps<{ configOnly?: boolean }>();

const store = usePipelineStore();
const currentStage = computed(() => store.currentStage ?? 0);
</script>

<template>
  <div>
    <DashboardHeader />
    <div class="views-container">
      <ConfigView v-show="currentStage === 0" />
      <Stage1View v-show="currentStage === 1" />
      <Stage2View v-show="currentStage === 2" />
      <Stage3View v-show="currentStage === 3" />
    </div>
  </div>
</template>
