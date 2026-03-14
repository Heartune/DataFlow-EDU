<script setup lang="ts">
import { Bar } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const props = defineProps<{
  labels: string[];
  data: number[];
  backgroundColor?: string;
  borderColor?: string;
}>();

const chartData = {
  labels: props.labels,
  datasets: [
    {
      data: props.data,
      backgroundColor: props.backgroundColor || '#10B98120',
      borderColor: props.borderColor || '#10B981',
      borderWidth: 1.5,
      borderRadius: 4,
    },
  ],
};

const chartOptions = {
  indexAxis: 'y' as const,
  responsive: true,
  maintainAspectRatio: false,
  layout: { padding: { top: 30, bottom: 30 } },
  plugins: { legend: { display: false } },
  scales: {
    x: { beginAtZero: true, grid: { color: '#F1F5F9' } },
    y: { grid: { display: false } },
  },
};
</script>

<template>
  <Bar :data="chartData" :options="chartOptions" />
</template>
