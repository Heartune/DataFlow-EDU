<script setup lang="ts">
import { computed } from 'vue';
import { Doughnut } from 'vue-chartjs';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

const props = defineProps<{
  labels: string[];
  data: number[];
  colors?: string[];
}>();

const defaultColors = [
  '#3B82F6',
  '#F59E0B',
  '#10B981',
  '#8B5CF6',
  '#EC4899',
  '#06B6D4',
  '#84CC16',
  '#F97316',
  '#6366F1',
  '#94A3B8',
];

const chartData = computed(() => {
  const cols = props.colors || defaultColors;
  return {
    labels: props.labels,
    datasets: [
      {
        data: props.data,
        backgroundColor: props.labels.map((_, i) => cols[i % cols.length] + '22'),
        borderColor: props.labels.map((_, i) => cols[i % cols.length]),
        borderWidth: 2,
      },
    ],
  };
});

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '62%',
  plugins: { legend: { display: false } },
};
</script>

<template>
  <Doughnut :data="chartData" :options="chartOptions" />
</template>
