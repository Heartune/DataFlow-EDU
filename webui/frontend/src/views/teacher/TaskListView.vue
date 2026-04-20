<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '@/api/client';

interface Task {
  id: string;
  name: string;
  status: 'created' | 'running' | 'succeeded' | 'failed';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
}

const tasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref('');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const { data } = await api.get('/tasks');
    tasks.value = data.tasks;
  } catch (err: any) {
    error.value = err?.message || '加载失败';
  } finally {
    loading.value = false;
  }
}

function fmtDate(ts: number) {
  return new Date(ts).toLocaleString();
}

const statusLabel: Record<Task['status'], string> = {
  created: '待启动',
  running: '运行中',
  succeeded: '已完成',
  failed: '失败',
};

const statusClass: Record<Task['status'], string> = {
  created: 'bg-slate-100 text-slate-600',
  running: 'bg-amber-100 text-amber-700',
  succeeded: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
};

onMounted(load);
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">我的任务</h1>
        <p class="text-sm text-slate-500 mt-1">上传一份教材 PDF，自动生成结构化题库与解析。</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900"
          @click="load"
        >
          刷新
        </button>
        <router-link
          to="/teacher/tasks/new"
          class="px-3 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800"
        >
          + 新建任务
        </router-link>
      </div>
    </div>

    <div v-if="loading" class="text-slate-500 py-12 text-center">加载中...</div>
    <div v-else-if="error" class="text-rose-600 py-12 text-center">{{ error }}</div>
    <div v-else-if="!tasks.length" class="bg-white rounded-2xl border border-slate-200 p-12 text-center">
      <p class="text-slate-500 mb-4">还没有任务，先去创建一个吧。</p>
      <router-link
        to="/teacher/tasks/new"
        class="inline-block px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800"
      >
        创建第一个任务
      </router-link>
    </div>

    <div v-else class="bg-white rounded-2xl border border-slate-200 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="text-left px-4 py-3 font-medium">名称</th>
            <th class="text-left px-4 py-3 font-medium">状态</th>
            <th class="text-left px-4 py-3 font-medium">当前阶段</th>
            <th class="text-left px-4 py-3 font-medium">创建时间</th>
            <th class="text-left px-4 py-3 font-medium">更新时间</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="t in tasks" :key="t.id" class="hover:bg-slate-50">
            <td class="px-4 py-3 font-medium text-slate-900">{{ t.name }}</td>
            <td class="px-4 py-3">
              <span :class="['px-2 py-0.5 rounded-full text-xs', statusClass[t.status]]">
                {{ statusLabel[t.status] }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-600">{{ t.current_stage || '—' }}</td>
            <td class="px-4 py-3 text-slate-500">{{ fmtDate(t.created_at) }}</td>
            <td class="px-4 py-3 text-slate-500">{{ fmtDate(t.updated_at) }}</td>
            <td class="px-4 py-3 text-right">
              <router-link
                :to="`/teacher/tasks/${t.id}`"
                class="text-slate-700 hover:text-slate-900 underline"
              >
                查看
              </router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
