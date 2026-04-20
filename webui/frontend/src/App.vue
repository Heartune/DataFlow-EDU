<script setup lang="ts">
import { onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
onMounted(() => {
  if (!auth.initialized) auth.fetchMe();
});
</script>

<template>
  <div class="bg-slate-50 min-h-screen font-sans text-slate-900 antialiased">
    <router-view />
  </div>
</template>
