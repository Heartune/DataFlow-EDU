/**
 * 任务列表 / 详情「当前阶段」与 ProgressView、ConfigView 卡片标题一致。
 * 旧版或日志衬底可能写入英文阶段名，在此归一为中文。
 */

const CANONICAL_STAGE_NAMES = new Set([
  '1.1 PDF转图片',
  '1.2 文字识别',
  '2.1 题目生成',
  '2.2 知识均衡检查与修正',
  '3.1 题意模糊检查',
  '3.2 题意模糊修正',
  '3.3 考察领域检查',
  '3.4 考察领域修正',
  '3.5 去除重复题目',
  '3.6 题库增强',
  '3.7 多语言翻译',
  '3.8 选择题格式检查',
]);

const ALIASES: Record<string, string> = (() => {
  const pairs: [string, string][] = [
    ['1.1 PDF→Images', '1.1 PDF转图片'],
    ['1.1 PDF->Images', '1.1 PDF转图片'],
    ['1.1 PDF to Images', '1.1 PDF转图片'],
    ['1.2 MinerU OCR', '1.2 文字识别'],
    ['1.2 MinerU OCR Operator', '1.2 文字识别'],
    ['2.1 Generation', '2.1 题目生成'],
    ['2.2 Balancing', '2.2 知识均衡检查与修正'],
    ['2.2 Knowledge Balancing', '2.2 知识均衡检查与修正'],
    ['2.2 知识均衡检查', '2.2 知识均衡检查与修正'],
    ['3.8 MCQ Verify', '3.8 选择题格式检查'],
    ['阶段2-题目生成', '2.1 题目生成'],
  ];
  const out: Record<string, string> = {};
  for (const [k, v] of pairs) {
    out[k] = v;
    out[k.toLowerCase()] = v;
  }
  return out;
})();

export function normalizeStageDisplayName(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const t = String(raw).trim();
  if (!t) return null;
  if (CANONICAL_STAGE_NAMES.has(t)) return t;
  const alias = ALIASES[t] ?? ALIASES[t.toLowerCase()];
  if (alias) return alias;
  const hasHan = /[\u4e00-\u9fff]/.test(t);
  if (!hasHan) {
    // 1.1：日志/tqdm 常见英文衬底（含 Unicode 箭头 →）
    if (/^1\.1\b/.test(t) && /pdf/i.test(t) && /images?/i.test(t)) return '1.1 PDF转图片';
    if (/^1\.2\b/.test(t) && /(mineru|\bocr\b)/i.test(t)) return '1.2 文字识别';
    if (/^2\.1\b/.test(t) && /generation/i.test(t)) return '2.1 题目生成';
    if (/^2\.2\b/.test(t) && /balanc/i.test(t)) return '2.2 知识均衡检查与修正';
    if (/^3\.8\b/.test(t) && /mcq/i.test(t)) return '3.8 选择题格式检查';
  }
  return t;
}

/** API / SSE 返回给前端的 progress：只改展示字段，不写回磁盘。 */
export function normalizeProgressPayload(progress: unknown): unknown {
  if (progress == null || typeof progress !== 'object') return progress;
  const p = progress as Record<string, unknown>;
  const stages = Array.isArray(p.stages)
    ? p.stages.map((item) => {
        if (!item || typeof item !== 'object') return item;
        const st = item as Record<string, unknown>;
        if (typeof st.name !== 'string') return { ...st };
        const name = normalizeStageDisplayName(st.name) ?? st.name;
        return { ...st, name };
      })
    : p.stages;
  let current_stage = p.current_stage;
  if (typeof current_stage === 'string') {
    current_stage = normalizeStageDisplayName(current_stage) ?? current_stage;
  }
  return { ...p, stages, current_stage };
}
