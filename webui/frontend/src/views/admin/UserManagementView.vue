<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '@/api/client';

// ── 类型 ─────────────────────────────────────────────────────────────────────
interface InviteCode {
  code: string;
  created_by: string;
  used_by: string | null;
  used_by_email: string | null;
  used_at: number | null;
  expires_at: number | null;
  created_at: number;
}
interface PendingUser {
  id: string;
  email: string;
  role: string;
  created_at: number;
}
interface LlmBalance {
  hard_limit_usd: number | null;
  used_usd: number | null;
  remaining_usd: number | null;
  error?: string;
}
interface LlmUserUsage {
  id: string;
  email: string;
  role: string;
  daily_llm_quota: number;
  used: number;
}

// ── State ─────────────────────────────────────────────────────────────────────
const tab = ref<'pending' | 'invites' | 'audit' | 'llm_quota'>('pending');
const loading = ref(false);
const error = ref('');

const pendingUsers = ref<PendingUser[]>([]);
const inviteCodes = ref<InviteCode[]>([]);
const auditLog = ref<unknown[]>([]);
const auditTotal = ref(0);
const auditOffset = ref(0);
const auditLimit = 50;

const genCount = ref(1);
const genDays = ref<number | ''>('');
const genLoading = ref(false);
const genNewCodes = ref<string[]>([]);
const genError = ref('');

const actionMsg = ref('');

// LLM 配额相关
const llmBalance = ref<LlmBalance | null>(null);
const llmUsage = ref<LlmUserUsage[]>([]);
const llmDay = ref('');
const llmBalanceLoading = ref(false);
const llmUsageLoading = ref(false);
const editingQuota = ref<Record<string, number>>({});
const savingQuota = ref<Record<string, boolean>>({});
const quotaMsg = ref('');

function apiErrorMessage(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { message?: string } } };
  const msg = e?.response?.data?.message;
  if (msg) return String(msg);
  if (!e?.response) {
    return '无法连接后端，请在 webui/server 目录执行 npm run dev（默认监听 3001，与 Vite 代理一致）';
  }
  return fallback;
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function loadPending() {
  loading.value = true;
  error.value = '';
  try {
    const { data } = await api.get('/admin/users/pending');
    pendingUsers.value = data.items;
  } catch (e: unknown) {
    error.value = apiErrorMessage(e, '加载失败');
  } finally {
    loading.value = false;
  }
}

async function loadInvites() {
  loading.value = true;
  error.value = '';
  try {
    const { data } = await api.get('/admin/invite-codes');
    inviteCodes.value = data.items;
  } catch (e: unknown) {
    error.value = apiErrorMessage(e, '加载失败');
  } finally {
    loading.value = false;
  }
}

async function loadAudit() {
  loading.value = true;
  error.value = '';
  try {
    const { data } = await api.get('/admin/audit-log', { params: { limit: auditLimit, offset: auditOffset.value } });
    auditLog.value = data.items;
    auditTotal.value = data.total;
  } catch (e: unknown) {
    error.value = apiErrorMessage(e, '加载失败');
  } finally {
    loading.value = false;
  }
}

async function loadLlmBalance() {
  llmBalanceLoading.value = true;
  try {
    const { data } = await api.get<LlmBalance>('/admin/llm-balance');
    llmBalance.value = data;
  } catch (e: unknown) {
    llmBalance.value = { hard_limit_usd: null, used_usd: null, remaining_usd: null, error: apiErrorMessage(e, '查询失败') };
  } finally {
    llmBalanceLoading.value = false;
  }
}

async function loadLlmUsage() {
  llmUsageLoading.value = true;
  try {
    const { data } = await api.get<{ items: LlmUserUsage[]; day: string }>('/admin/llm-usage');
    llmUsage.value = data.items;
    llmDay.value = data.day;
    // 初始化编辑值
    for (const u of data.items) {
      if (!(u.id in editingQuota.value)) {
        editingQuota.value[u.id] = u.daily_llm_quota;
      }
    }
  } catch (e: unknown) {
    error.value = apiErrorMessage(e, '加载失败');
  } finally {
    llmUsageLoading.value = false;
  }
}

async function saveQuota(userId: string) {
  savingQuota.value[userId] = true;
  quotaMsg.value = '';
  try {
    await api.patch(`/admin/users/${userId}/quota`, { daily_llm_quota: editingQuota.value[userId] });
    quotaMsg.value = '配额已更新';
    await loadLlmUsage();
  } catch (e: unknown) {
    quotaMsg.value = apiErrorMessage(e, '保存失败');
  } finally {
    savingQuota.value[userId] = false;
  }
}

async function approveUser(userId: string) {
  try {
    await api.post(`/admin/users/${userId}/approve`);
    actionMsg.value = '已通过审批';
    await loadPending();
  } catch (e: unknown) {
    actionMsg.value = apiErrorMessage(e, '操作失败');
  }
}

async function rejectUser(userId: string, email: string) {
  if (!confirm(`确认拒绝并删除用户 ${email}？`)) return;
  try {
    await api.post(`/admin/users/${userId}/reject`);
    actionMsg.value = '已拒绝并删除';
    await loadPending();
  } catch (e: unknown) {
    actionMsg.value = apiErrorMessage(e, '操作失败');
  }
}

async function generateCodes() {
  genLoading.value = true;
  genError.value = '';
  genNewCodes.value = [];
  try {
    const body: Record<string, unknown> = { count: genCount.value };
    if (genDays.value !== '') body.expires_in_days = genDays.value;
    const { data } = await api.post('/admin/invite-codes', body);
    genNewCodes.value = data.codes;
    await loadInvites();
  } catch (e: unknown) {
    genError.value = apiErrorMessage(e, '生成失败');
  } finally {
    genLoading.value = false;
  }
}

async function revokeCode(code: string) {
  if (!confirm(`确认作废邀请码 ${code}？`)) return;
  try {
    await api.delete(`/admin/invite-codes/${code}`);
    actionMsg.value = '已作废';
    await loadInvites();
  } catch (e: unknown) {
    actionMsg.value = apiErrorMessage(e, '操作失败');
  }
}

function copyCode(code: string) {
  navigator.clipboard?.writeText(code).then(() => {
    actionMsg.value = `已复制：${code}`;
  });
}

function formatDate(ts: number | null) {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('zh-CN');
}

function switchTab(t: 'pending' | 'invites' | 'audit' | 'llm_quota') {
  tab.value = t;
  actionMsg.value = '';
  error.value = '';
  quotaMsg.value = '';
  if (t === 'pending') loadPending();
  else if (t === 'invites') loadInvites();
  else if (t === 'audit') loadAudit();
  else if (t === 'llm_quota') { loadLlmBalance(); loadLlmUsage(); }
}

onMounted(() => loadPending());
</script>

<template>
  <div class="max-w-5xl mx-auto p-6">
    <h1 class="text-2xl font-bold text-slate-900 mb-6">用户管理</h1>

    <!-- Tab 切换 -->
    <div class="flex gap-1 mb-6 border-b border-slate-200">
      <button
        v-for="t in [
          { key: 'pending', label: '待审批用户' },
          { key: 'invites', label: '邀请码管理' },
          { key: 'audit', label: '审计日志' },
          { key: 'llm_quota', label: 'LLM 配额' },
        ]"
        :key="t.key"
        :class="['px-4 py-2 text-sm font-medium rounded-t-lg -mb-px border-b-2 transition',
          tab === t.key ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700']"
        @click="switchTab(t.key as 'pending' | 'invites' | 'audit' | 'llm_quota')"
      >
        {{ t.label }}
        <span v-if="t.key === 'pending' && pendingUsers.length > 0"
          class="ml-1.5 px-1.5 py-0.5 bg-rose-100 text-rose-700 text-xs rounded-full">
          {{ pendingUsers.length }}
        </span>
      </button>
    </div>

    <!-- 全局消息 -->
    <p v-if="actionMsg" class="mb-4 text-sm text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">{{ actionMsg }}</p>
    <p v-if="error" class="mb-4 text-sm text-rose-700 bg-rose-50 rounded-lg px-3 py-2">{{ error }}</p>

    <!-- ── 待审批用户 ── -->
    <div v-if="tab === 'pending'">
      <p v-if="loading" class="text-sm text-slate-400">加载中...</p>
      <p v-else-if="pendingUsers.length === 0" class="text-sm text-slate-400">暂无待审批用户</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-slate-200">
              <th class="py-2 pr-4 font-medium text-slate-600">邮箱</th>
              <th class="py-2 pr-4 font-medium text-slate-600">注册时间</th>
              <th class="py-2 font-medium text-slate-600">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in pendingUsers" :key="u.id" class="border-b border-slate-100">
              <td class="py-2.5 pr-4 text-slate-800">{{ u.email }}</td>
              <td class="py-2.5 pr-4 text-slate-500">{{ formatDate(u.created_at) }}</td>
              <td class="py-2.5 flex gap-2">
                <button
                  class="px-3 py-1 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-700"
                  @click="approveUser(u.id)"
                >通过</button>
                <button
                  class="px-3 py-1 bg-rose-600 text-white text-xs rounded-lg hover:bg-rose-700"
                  @click="rejectUser(u.id, u.email)"
                >拒绝</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── 邀请码管理 ── -->
    <div v-if="tab === 'invites'" class="space-y-6">
      <!-- 生成区 -->
      <div class="bg-slate-50 rounded-xl p-4 border border-slate-200">
        <h3 class="text-sm font-semibold text-slate-800 mb-3">生成邀请码</h3>
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs text-slate-500 mb-1">数量</label>
            <input v-model.number="genCount" type="number" min="1" max="100"
              class="w-20 px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-slate-900" />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">有效天数（留空=永不过期）</label>
            <input v-model.number="genDays" type="number" min="1"
              class="w-28 px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-slate-900"
              placeholder="不限" />
          </div>
          <button
            class="px-4 py-1.5 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-800 disabled:opacity-50"
            :disabled="genLoading"
            @click="generateCodes"
          >{{ genLoading ? '生成中...' : '生成' }}</button>
        </div>
        <p v-if="genError" class="mt-2 text-xs text-rose-600">{{ genError }}</p>
        <div v-if="genNewCodes.length > 0" class="mt-3">
          <p class="text-xs text-slate-500 mb-1">新生成的码（点击复制）：</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="c in genNewCodes" :key="c"
              class="px-3 py-1 bg-white border border-slate-300 rounded-lg font-mono text-sm cursor-pointer hover:bg-slate-100 select-all"
              @click="copyCode(c)"
            >{{ c }}</span>
          </div>
        </div>
      </div>

      <!-- 码列表 -->
      <div>
        <p v-if="loading" class="text-sm text-slate-400">加载中...</p>
        <p v-else-if="inviteCodes.length === 0" class="text-sm text-slate-400">暂无邀请码</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left border-b border-slate-200">
                <th class="py-2 pr-4 font-medium text-slate-600">码</th>
                <th class="py-2 pr-4 font-medium text-slate-600">状态</th>
                <th class="py-2 pr-4 font-medium text-slate-600">使用者</th>
                <th class="py-2 pr-4 font-medium text-slate-600">过期时间</th>
                <th class="py-2 font-medium text-slate-600">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in inviteCodes" :key="c.code" class="border-b border-slate-100">
                <td class="py-2.5 pr-4 font-mono text-slate-800">{{ c.code }}</td>
                <td class="py-2.5 pr-4">
                  <span :class="c.used_by ? 'text-slate-400' : 'text-emerald-600 font-medium'">
                    {{ c.used_by ? '已使用' : '未使用' }}
                  </span>
                </td>
                <td class="py-2.5 pr-4 text-slate-500">{{ c.used_by_email || '—' }}</td>
                <td class="py-2.5 pr-4 text-slate-500">{{ formatDate(c.expires_at) }}</td>
                <td class="py-2.5 flex gap-2">
                  <button
                    class="px-2 py-1 border border-slate-300 text-slate-600 text-xs rounded hover:border-slate-900"
                    @click="copyCode(c.code)"
                  >复制</button>
                  <button
                    v-if="!c.used_by"
                    class="px-2 py-1 border border-rose-300 text-rose-600 text-xs rounded hover:bg-rose-50"
                    @click="revokeCode(c.code)"
                  >作废</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── 审计日志 ── -->
    <div v-if="tab === 'audit'">
      <p v-if="loading" class="text-sm text-slate-400">加载中...</p>
      <div v-else>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left border-b border-slate-200">
                <th class="py-2 pr-3 font-medium text-slate-600 whitespace-nowrap">时间</th>
                <th class="py-2 pr-3 font-medium text-slate-600">用户</th>
                <th class="py-2 pr-3 font-medium text-slate-600">事件</th>
                <th class="py-2 pr-3 font-medium text-slate-600">目标</th>
                <th class="py-2 font-medium text-slate-600">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in (auditLog as any[])" :key="i" class="border-b border-slate-100">
                <td class="py-2 pr-3 text-slate-500 whitespace-nowrap">{{ formatDate(row.ts) }}</td>
                <td class="py-2 pr-3 text-slate-600 max-w-[140px] truncate" :title="row.user_email || row.user_id">{{ row.user_email || row.user_id || '—' }}</td>
                <td class="py-2 pr-3 font-mono text-xs text-slate-800">{{ row.action }}</td>
                <td class="py-2 pr-3 text-slate-500 max-w-[160px] truncate" :title="row.target">{{ row.target || '—' }}</td>
                <td class="py-2 text-xs">
                  <span :class="['px-1.5 py-0.5 rounded', row.status === 'ok' || row.status === 'activated' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700']">{{ row.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 翻页 -->
        <div class="flex items-center gap-3 mt-4 text-sm text-slate-500">
          <button :disabled="auditOffset === 0"
            class="px-3 py-1 border rounded disabled:opacity-40 hover:border-slate-900"
            @click="auditOffset = Math.max(0, auditOffset - auditLimit); loadAudit()">上一页</button>
          <span>共 {{ auditTotal }} 条</span>
          <button :disabled="auditOffset + auditLimit >= auditTotal"
            class="px-3 py-1 border rounded disabled:opacity-40 hover:border-slate-900"
            @click="auditOffset += auditLimit; loadAudit()">下一页</button>
        </div>
      </div>
    </div>

    <!-- ── LLM 配额 ── -->
    <div v-if="tab === 'llm_quota'" class="space-y-6">

      <!-- ZGCA 余额卡片 -->
      <div class="bg-slate-50 rounded-xl p-5 border border-slate-200">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-slate-800">ZGCA API Key 余额</h3>
          <button
            class="text-xs text-slate-500 border border-slate-300 px-2 py-1 rounded hover:border-slate-700"
            :disabled="llmBalanceLoading"
            @click="loadLlmBalance"
          >{{ llmBalanceLoading ? '刷新中...' : '刷新' }}</button>
        </div>
        <div v-if="llmBalanceLoading" class="text-sm text-slate-400">查询中...</div>
        <div v-else-if="llmBalance">
          <div v-if="llmBalance.error" class="text-sm text-rose-600">查询失败：{{ llmBalance.error }}</div>
          <div v-else class="grid grid-cols-3 gap-4">
            <div class="text-center">
              <p class="text-xs text-slate-500 mb-1">总额度</p>
              <p class="text-lg font-bold text-slate-900">${{ llmBalance.hard_limit_usd?.toFixed(2) ?? '—' }}</p>
            </div>
            <div class="text-center">
              <p class="text-xs text-slate-500 mb-1">已用</p>
              <p class="text-lg font-bold text-amber-600">${{ llmBalance.used_usd?.toFixed(2) ?? '—' }}</p>
            </div>
            <div class="text-center">
              <p class="text-xs text-slate-500 mb-1">剩余</p>
              <p :class="['text-lg font-bold', (llmBalance.remaining_usd ?? 0) > 10 ? 'text-emerald-600' : 'text-rose-600']">
                ${{ llmBalance.remaining_usd?.toFixed(2) ?? '—' }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- 用户配额表格 -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-slate-800">
            用户当日 Token 用量
            <span v-if="llmDay" class="ml-2 text-slate-400 font-normal">（{{ llmDay }}）</span>
          </h3>
          <button
            class="text-xs text-slate-500 border border-slate-300 px-2 py-1 rounded hover:border-slate-700"
            :disabled="llmUsageLoading"
            @click="loadLlmUsage"
          >{{ llmUsageLoading ? '刷新中...' : '刷新' }}</button>
        </div>
        <p v-if="quotaMsg" class="mb-3 text-sm text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">{{ quotaMsg }}</p>
        <p v-if="llmUsageLoading" class="text-sm text-slate-400">加载中...</p>
        <div v-else-if="llmUsage.length === 0" class="text-sm text-slate-400">暂无用户数据</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left border-b border-slate-200">
                <th class="py-2 pr-4 font-medium text-slate-600">邮箱</th>
                <th class="py-2 pr-4 font-medium text-slate-600">今日已用</th>
                <th class="py-2 pr-4 font-medium text-slate-600">剩余</th>
                <th class="py-2 pr-4 font-medium text-slate-600">每日上限</th>
                <th class="py-2 font-medium text-slate-600">修改上限</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in llmUsage" :key="u.id" class="border-b border-slate-100">
                <td class="py-2.5 pr-4 text-slate-800">
                  {{ u.email }}
                  <span v-if="u.role === 'admin'" class="ml-1 text-xs text-slate-400">(admin)</span>
                </td>
                <td class="py-2.5 pr-4">
                  <span :class="['font-mono text-xs', u.used > u.daily_llm_quota * 0.8 ? 'text-rose-600 font-semibold' : 'text-slate-700']">
                    {{ u.used.toLocaleString() }}
                  </span>
                </td>
                <td class="py-2.5 pr-4 font-mono text-xs text-slate-500">
                  {{ Math.max(0, u.daily_llm_quota - u.used).toLocaleString() }}
                </td>
                <td class="py-2.5 pr-4 font-mono text-xs text-slate-600">
                  {{ u.daily_llm_quota.toLocaleString() }}
                </td>
                <td class="py-2.5">
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="editingQuota[u.id]"
                      type="number"
                      min="0"
                      step="10000"
                      class="w-28 px-2 py-1 border border-slate-300 rounded text-xs font-mono focus:outline-none focus:border-slate-700"
                    />
                    <button
                      class="px-2 py-1 bg-slate-800 text-white text-xs rounded hover:bg-slate-700 disabled:opacity-50"
                      :disabled="savingQuota[u.id] || editingQuota[u.id] === u.daily_llm_quota"
                      @click="saveQuota(u.id)"
                    >{{ savingQuota[u.id] ? '保存中' : '保存' }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
