<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '@/api/client';

interface Task {
  id: string;
  name: string;
  status: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
}

const tasks = ref<Task[]>([]);
const loading = ref(false);
const error = ref('');
const actionMsg = ref('');
const actionBusy = ref<Record<string, boolean>>({});

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
  cancelled: '已取消',
};

const statusClass: Record<Task['status'], string> = {
  created: 'bg-slate-100 text-slate-600',
  running: 'bg-amber-100 text-amber-700',
  succeeded: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-slate-200 text-slate-600',
};

const errorLabel: Record<string, string> = {
  no_progress_to_resume: '没有历史进度可续跑，请改用「从头重跑」',
  nothing_to_resume: '所有阶段都已完成，无需续跑',
  user_has_running_task: '你已有任务在跑，等它结束后再启动新任务',
  task_already_running: '任务已在运行中',
  missing_llm_key: '缺少 LLM Key，请先在「新建任务」页填一次以保存到本地',
  pdf_missing: '原始 PDF 已丢失，无法继续',
};

async function resumeTask(t: Task) {
  if (actionBusy.value[t.id]) return;
  actionBusy.value = { ...actionBusy.value, [t.id]: true };
  actionMsg.value = '';
  try {
    await api.post(`/tasks/${t.id}/resume`);
    await load();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    actionMsg.value = errorLabel[code] || err?.response?.data?.message || err?.message || '续跑失败';
  } finally {
    actionBusy.value = { ...actionBusy.value, [t.id]: false };
  }
}

function canResume(t: Task) {
  return t.status === 'failed' || t.status === 'cancelled' || t.status === 'succeeded';
}

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

    <p v-if="actionMsg" class="text-sm text-rose-600 mb-3">{{ actionMsg }}</p>

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
            <td class="px-4 py-3 text-right whitespace-nowrap">
              <button
                v-if="canResume(t)"
                class="text-slate-700 hover:text-slate-900 underline mr-3 disabled:opacity-50"
                :disabled="!!actionBusy[t.id]"
                @click="resumeTask(t)"
              >
                {{ actionBusy[t.id] ? '续跑中...' : '续跑' }}
              </button>
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
