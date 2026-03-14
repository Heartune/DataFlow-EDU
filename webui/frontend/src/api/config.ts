import type { EduConfig } from '@/types/config';

export async function getConfig(): Promise<EduConfig> {
  const res = await fetch('/api/config');
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || res.statusText || '配置加载失败');
  }
  const raw = await res.json();
  return {
    taxonomy: raw.taxonomy || [],
    question_types: raw.question_types || [],
    ability_levels: raw.ability_levels || [],
    operators: raw.operators || {},
  };
}

export async function saveConfig(
  config: EduConfig
): Promise<{ ok: boolean; errors?: string[] }> {
  const res = await fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.ok) return { ok: true };
  return { ok: false, errors: data.errors || [data.error || '保存失败'] };
}

export async function listPresets(): Promise<string[]> {
  const res = await fetch('/api/config/presets');
  if (!res.ok) return [];
  return res.json();
}

export async function loadPreset(name: string): Promise<EduConfig> {
  const res = await fetch(`/api/config/presets/${encodeURIComponent(name)}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || res.statusText || '加载预设失败');
  }
  const raw = await res.json();
  return {
    taxonomy: raw.taxonomy || [],
    question_types: raw.question_types || [],
    ability_levels: raw.ability_levels || [],
    operators: raw.operators || {},
  };
}
