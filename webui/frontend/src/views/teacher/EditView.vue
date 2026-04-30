<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { AgGridVue } from 'ag-grid-vue3';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type CellValueChangedEvent,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type SelectionChangedEvent,
} from 'ag-grid-community';
import { api } from '@/api/client';

ModuleRegistry.registerModules([AllCommunityModule]);

const props = defineProps<{ id: string }>();

interface ItemRow {
  _id: string;
  question?: string;
  answer?: string;
  type?: string;
  options?: string[];
  category?: string;
  subcategory?: string;
  ability_main?: string;
  ability_level?: string;
  difficulty?: string | number;
  explanation?: string;
  [k: string]: unknown;
}

// 与 ExportView 保持一致的阶段映射（只列有题目产物的阶段，纯检查阶段不列入）
const EXPORTABLE_STAGE_MAP: Record<string, { id: string; label: string }> = {
  '3.8 选择题格式检查':   { id: '3_8_mcq_verified',                        label: '3.8 选择题格式检查' },
  '3.7 多语言翻译':      { id: '3_7_translated',                          label: '3.7 多语言翻译' },
  '3.6 题库增强':        { id: '3_6_synthesized',                          label: '3.6 题库增强' },
  '3.5 去除重复题目':    { id: '3_5_deduplicated',                        label: '3.5 去除重复题目' },
  '3.4 考察领域修正':    { id: '3_4_domain_refined',                      label: '3.4 考察领域修正' },
  '3.2 题意模糊修正':    { id: '3_2_ambiguity_refined',                   label: '3.2 题意模糊修正' },
  '2.2 知识均衡检查与修正': { id: '2_1_generation/2_2_balanced',            label: '2.2 知识均衡检查与修正' },
  '2.2 知识均衡检查':      { id: '2_1_generation/2_2_balanced',            label: '2.2 知识均衡检查' },
  '2.1 题目生成':        { id: '2_1_generation/2_1_generated_stage_2',     label: '2.1 题目生成' },
};

type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';

interface StageOption {
  id: string;
  label: string;
  status: StageStatus;
}

const availableStages = ref<StageOption[]>([]);

async function loadAvailableStages() {
  try {
    const { data } = await api.get(`/tasks/${encodeURIComponent(props.id)}`);
    const progressStages: { name: string; status: StageStatus }[] = data?.progress?.stages ?? [];
    const statusByName = new Map(progressStages.map((s) => [s.name, s.status]));

    const result: StageOption[] = [];
    for (const [stageName, { id, label }] of Object.entries(EXPORTABLE_STAGE_MAP)) {
      const status = statusByName.get(stageName);
      if (status === undefined) continue;
      if (status === 'skipped') continue;
      result.push({ id, label, status });
    }
    availableStages.value = result;

    const firstSucceeded = result.find((s) => s.status === 'succeeded');
    if (firstSucceeded) stage.value = firstSucceeded.id;
    else if (result.length > 0) stage.value = result[0].id;
  } catch {
    // 降级：保持默认值
  }
}

const stage = ref('3_8_mcq_verified');
const files = ref<string[]>([]);
const file = ref('');
const rows = ref<ItemRow[]>([]);
const total = ref(0);
const offset = ref(0);
const pageSize = 50;
const loading = ref(false);
const error = ref('');
const info = ref('');
const selectedIds = ref<Set<string>>(new Set());

let gridApi: GridApi<ItemRow> | null = null;

interface UndoEntry {
  kind: 'patch' | 'delete';
  stage: string;
  file: string;
  id: string;
  before: Partial<ItemRow>;
}
const undoStack = ref<UndoEntry[]>([]);
const UNDO_LIMIT = 20;

function pushUndo(entry: UndoEntry) {
  undoStack.value.push(entry);
  if (undoStack.value.length > UNDO_LIMIT) {
    undoStack.value.shift();
  }
}

const columnDefs = computed<ColDef<ItemRow>[]>(() => {
  const isMcq = stage.value === '3_8_mcq_verified';
  return [
    {
      headerCheckboxSelection: true,
      checkboxSelection: true,
      width: 44,
      pinned: 'left',
      resizable: false,
      sortable: false,
      filter: false,
      suppressMovable: true,
    },
    {
      headerName: '#',
      valueGetter: (p) => (p.node?.rowIndex ?? 0) + 1 + offset.value,
      width: 70,
      pinned: 'left',
    },
    { field: 'type', headerName: '题型', width: 90, editable: true },
    {
      field: 'question',
      headerName: '题干',
      flex: 2,
      minWidth: 240,
      editable: true,
      cellEditor: 'agLargeTextCellEditor',
      cellEditorPopup: true,
      cellEditorParams: { rows: 6, cols: 60 },
      autoHeight: true,
      wrapText: true,
    },
    ...(isMcq
      ? [
          {
            field: 'options',
            headerName: '选项',
            flex: 1.2,
            minWidth: 180,
            editable: true,
            valueFormatter: (p) =>
              Array.isArray(p.value) ? (p.value as string[]).join(' | ') : String(p.value ?? ''),
            valueParser: (p) => {
              const v = String(p.newValue ?? '').trim();
              if (!v) return [];
              return v.split('|').map((s) => s.trim()).filter(Boolean);
            },
            wrapText: true,
            autoHeight: true,
          } as ColDef<ItemRow>,
        ]
      : []),
    {
      field: 'answer',
      headerName: '答案',
      flex: 0.8,
      minWidth: 100,
      editable: true,
      wrapText: true,
      autoHeight: true,
    },
    {
      field: 'explanation',
      headerName: '解析',
      flex: 1.5,
      minWidth: 200,
      editable: true,
      cellEditor: 'agLargeTextCellEditor',
      cellEditorPopup: true,
      wrapText: true,
      autoHeight: true,
    },
    {
      headerName: '知识点',
      width: 200,
      valueGetter: (p) => {
        const c = p.data?.category || '';
        const s = p.data?.subcategory || '';
        return s ? `${c} › ${s}` : c;
      },
    },
    {
      field: 'difficulty',
      headerName: '难度',
      width: 80,
      editable: true,
    },
    {
      headerName: '认知',
      width: 200,
      valueGetter: (p) => {
        const m = p.data?.ability_main || '';
        const l = p.data?.ability_level || '';
        return l ? `${m} · ${l}` : m;
      },
    },
    {
      headerName: '操作',
      width: 90,
      pinned: 'right',
      sortable: false,
      filter: false,
      cellRenderer: (p: { data?: ItemRow }) => {
        const id = p.data?._id || '';
        return `<button data-id="${id}" class="row-del-btn text-rose-600 text-xs hover:underline">删除</button>`;
      },
      onCellClicked: (p) => {
        const id = p.data?._id;
        if (id) deleteItem(id);
      },
    },
  ];
});

const defaultColDef: ColDef = {
  resizable: true,
  sortable: true,
  filter: true,
  suppressHeaderMenuButton: true,
};

const theme = themeQuartz.withParams({
  fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  fontSize: 13,
  borderRadius: 12,
});

async function loadFiles() {
  files.value = [];
  file.value = '';
  try {
    const { data } = await api.get(`/tasks/${props.id}/files`, { params: { stage: stage.value } });
    files.value = data.files || [];
    if (files.value.length) {
      file.value = files.value[0];
    }
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载文件列表失败';
  }
}

async function loadItems(reset = true) {
  if (!file.value) {
    rows.value = [];
    total.value = 0;
    return;
  }
  loading.value = true;
  if (reset) {
    offset.value = 0;
  }
  error.value = '';
  try {
    const { data } = await api.get(`/tasks/${props.id}/items`, {
      params: { stage: stage.value, file: file.value, offset: offset.value, limit: pageSize },
    });
    if (reset) {
      rows.value = data.items || [];
    } else {
      rows.value = [...rows.value, ...(data.items || [])];
    }
    total.value = data.total || 0;
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载题目失败';
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  if (loading.value) return;
  if (rows.value.length >= total.value) return;
  offset.value += pageSize;
  await loadItems(false);
}

function onGridReady(p: GridReadyEvent<ItemRow>) {
  gridApi = p.api;
}

function onSelectionChanged(_e: SelectionChangedEvent<ItemRow>) {
  const sel = gridApi?.getSelectedRows() || [];
  selectedIds.value = new Set(sel.map((r) => r._id));
}

async function onCellValueChanged(e: CellValueChangedEvent<ItemRow>) {
  const data = e.data;
  if (!data?._id) return;
  const field = e.colDef.field;
  if (!field) return;
  const before: Partial<ItemRow> = { [field]: e.oldValue } as Partial<ItemRow>;
  const patch: Record<string, unknown> = { [field]: e.newValue };
  try {
    const { data: resp } = await api.patch(`/tasks/${props.id}/items/${data._id}`, patch, {
      params: { stage: stage.value, file: file.value },
    });
    pushUndo({ kind: 'patch', stage: stage.value, file: file.value, id: data._id, before });
    if (resp?.item?._id && resp.item._id !== data._id) {
      data._id = resp.item._id;
      gridApi?.applyTransaction({ update: [data] });
    }
    info.value = `已保存（已写入 .bak 备份）`;
    setTimeout(() => (info.value = ''), 2000);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '保存失败';
    if (e.node && field) {
      e.node.setDataValue(field, e.oldValue);
    }
  }
}

async function deleteItem(id: string) {
  const idx = rows.value.findIndex((r) => r._id === id);
  if (idx < 0) return;
  if (!window.confirm('确认删除此题？后台会先备份原文件再写入')) return;
  const before = { ...rows.value[idx] };
  try {
    await api.delete(`/tasks/${props.id}/items/${id}`, {
      params: { stage: stage.value, file: file.value },
    });
    rows.value.splice(idx, 1);
    total.value = Math.max(0, total.value - 1);
    pushUndo({ kind: 'delete', stage: stage.value, file: file.value, id, before });
    info.value = '已删除';
    setTimeout(() => (info.value = ''), 2000);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '删除失败';
  }
}

async function deleteSelected() {
  const ids = Array.from(selectedIds.value);
  if (ids.length === 0) return;
  if (!window.confirm(`确认删除选中的 ${ids.length} 条题目？后台会先备份原文件`)) return;
  let okCnt = 0;
  for (const id of ids) {
    const idx = rows.value.findIndex((r) => r._id === id);
    if (idx < 0) continue;
    const before = { ...rows.value[idx] };
    try {
      await api.delete(`/tasks/${props.id}/items/${id}`, {
        params: { stage: stage.value, file: file.value },
      });
      rows.value = rows.value.filter((r) => r._id !== id);
      total.value = Math.max(0, total.value - 1);
      pushUndo({ kind: 'delete', stage: stage.value, file: file.value, id, before });
      okCnt += 1;
    } catch {
      // 单条失败不打断其它
    }
  }
  selectedIds.value = new Set();
  info.value = `已删除 ${okCnt}/${ids.length} 条`;
  setTimeout(() => (info.value = ''), 2500);
}

async function undo() {
  const entry = undoStack.value.pop();
  if (!entry) return;
  if (entry.stage !== stage.value || entry.file !== file.value) {
    info.value = '撤销条目属于其它阶段/文件，已跳过';
    setTimeout(() => (info.value = ''), 2500);
    return;
  }
  if (entry.kind === 'patch') {
    try {
      await api.patch(`/tasks/${props.id}/items/${entry.id}`, entry.before, {
        params: { stage: entry.stage, file: entry.file },
      });
      const idx = rows.value.findIndex((r) => r._id === entry.id);
      if (idx >= 0) {
        rows.value[idx] = { ...rows.value[idx], ...entry.before };
        gridApi?.applyTransaction({ update: [rows.value[idx]] });
      }
      info.value = '已撤销修改';
    } catch (err: any) {
      error.value = err?.response?.data?.error || err?.message || '撤销失败';
    }
  } else if (entry.kind === 'delete') {
    rows.value.unshift(entry.before as ItemRow);
    total.value += 1;
    info.value = '⚠ 仅在前端恢复显示；后台数据已删除，刷新后将丢失';
    setTimeout(() => (info.value = ''), 4000);
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    e.preventDefault();
    void undo();
  }
}

onMounted(async () => {
  await loadAvailableStages();
  await loadFiles();
  await loadItems();
  window.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
});

watch(stage, async () => {
  await loadFiles();
  await loadItems();
});
watch(file, async () => {
  await loadItems();
});
</script>

<template>
  <div>
    <div class="flex items-center gap-3 flex-wrap mb-4">
      <label class="text-sm text-slate-600 flex items-center gap-2">
        阶段
        <select
          v-model="stage"
          class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm"
          :disabled="availableStages.length === 0"
        >
          <option v-if="availableStages.length === 0" value="">（暂无可编辑阶段）</option>
          <option
            v-for="s in availableStages"
            :key="s.id"
            :value="s.id"
            :disabled="s.status !== 'succeeded'"
          >
            {{ s.label }}{{ s.status !== 'succeeded' ? `（${s.status === 'pending' ? '尚未运行' : s.status === 'running' ? '运行中' : s.status === 'failed' ? '运行失败' : s.status}）` : '' }}
          </option>
        </select>
      </label>
      <label class="text-sm text-slate-600 flex items-center gap-2 flex-1 min-w-[14rem]">
        文件
        <select v-model="file" class="flex-1 px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option v-if="!files.length" value="">(此阶段尚无产物)</option>
          <option v-for="f in files" :key="f" :value="f">{{ f }}</option>
        </select>
      </label>
      <span class="text-xs text-slate-500">共 {{ total }} 题，已加载 {{ rows.length }}</span>
      <button
        class="text-sm px-3 py-1.5 border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900 disabled:opacity-50"
        :disabled="!undoStack.length"
        @click="undo"
        title="Ctrl+Z"
      >
        撤销 ({{ undoStack.length }})
      </button>
      <button
        class="text-sm px-3 py-1.5 border border-rose-300 rounded-lg text-rose-600 hover:bg-rose-50 disabled:opacity-50"
        :disabled="!selectedIds.size"
        @click="deleteSelected"
      >
        删除选中 ({{ selectedIds.size }})
      </button>
    </div>

    <p v-if="error" class="text-sm text-rose-600 mb-2">{{ error }}</p>
    <p v-if="info" class="text-sm text-emerald-600 mb-2">{{ info }}</p>

    <div v-if="!files.length" class="bg-white border border-dashed border-slate-200 rounded-2xl p-8 text-center text-sm text-slate-500">
      此阶段尚未产生任何文件。请等待 pipeline 跑到对应阶段，或切换其它阶段。
    </div>

    <div v-else class="bg-white border border-slate-200 rounded-2xl overflow-hidden" style="height: calc(100vh - 280px); min-height: 420px;">
      <AgGridVue
        style="width: 100%; height: 100%;"
        :theme="theme"
        :columnDefs="columnDefs"
        :rowData="rows"
        :defaultColDef="defaultColDef"
        rowSelection="multiple"
        :suppressRowClickSelection="true"
        :singleClickEdit="false"
        :stopEditingWhenCellsLoseFocus="true"
        :animateRows="true"
        @grid-ready="onGridReady"
        @selection-changed="onSelectionChanged"
        @cell-value-changed="onCellValueChanged"
      />
    </div>

    <div v-if="files.length" class="mt-3 flex items-center justify-between text-xs text-slate-500">
      <span>每次编辑/删除自动写 <code>.bak</code> 备份；首次另存 <code>.original.bak</code></span>
      <button
        v-if="rows.length < total"
        class="px-3 py-1 border border-slate-300 rounded-lg hover:border-slate-900"
        :disabled="loading"
        @click="loadMore"
      >
        {{ loading ? '加载中...' : `加载下一页 (${rows.length}/${total})` }}
      </button>
    </div>
  </div>
</template>
