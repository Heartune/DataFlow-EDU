import { api } from '@/api/client';
import type { EduConfig } from '@/types/config';

function unwrapEduConfig(raw: any): EduConfig {
  return {
    taxonomy: raw?.taxonomy || [],
    question_types: raw?.question_types || [],
    ability_levels: raw?.ability_levels || [],
    operators: raw?.operators || {},
  };
}

function extractError(err: any, fallback: string): Error {
  const data = err?.response?.data;
  const msg = data?.error || data?.errors?.[0] || err?.message || fallback;
  return new Error(msg);
}

export async function getConfig(): Promise<EduConfig> {
  try {
    const { data } = await api.get('/admin/config');
    return unwrapEduConfig(data);
  } catch (err) {
    throw extractError(err, '配置加载失败');
  }
}

export async function saveConfig(
  config: EduConfig
): Promise<{ ok: boolean; errors?: string[] }> {
  try {
    const { data } = await api.put('/admin/config', config);
    if (data?.ok) return { ok: true };
    return { ok: false, errors: data?.errors || ['保存失败'] };
  } catch (err: any) {
    const data = err?.response?.data;
    if (data?.errors) return { ok: false, errors: data.errors };
    return { ok: false, errors: [data?.error || err?.message || '保存失败'] };
  }
}

export async function listPresets(): Promise<string[]> {
  try {
    const { data } = await api.get('/config/presets');
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export async function loadPreset(name: string): Promise<EduConfig> {
  try {
    const { data } = await api.post(`/admin/config/presets/${encodeURIComponent(name)}`);
    return unwrapEduConfig(data);
  } catch (err) {
    throw extractError(err, '加载预设失败');
  }
}
