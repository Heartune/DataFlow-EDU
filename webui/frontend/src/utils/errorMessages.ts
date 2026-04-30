export interface ErrorInfo {
  /** 对教师展示的友好说明 */
  friendly: string;
  /** 可操作建议 */
  suggestion: string;
  /** 是否可以直接重新提交 */
  canRetry: boolean;
}

// 精确错误码映射
const CODE_MAP: Record<string, ErrorInfo> = {
  timeout: {
    friendly: '任务超时，AI 服务未能在规定时间内完成',
    suggestion: '建议将教材拆分为较少页数后重新提交，或稍后再试。',
    canRetry: true,
  },
  quota_exceeded: {
    friendly: 'AI 积分今日已全部用完',
    suggestion: '配额每天自动刷新，明天即可继续使用。如需提升配额请联系管理员。',
    canRetry: false,
  },
  daily_llm_quota_exceeded: {
    friendly: 'AI 积分今日已全部用完',
    suggestion: '配额每天自动刷新，明天即可继续使用。如需提升配额请联系管理员。',
    canRetry: false,
  },
  ppt_convert_failed: {
    friendly: 'PPT 文件转换失败',
    suggestion: '请将 PPT 另存为 PDF 后重新上传，或检查服务器是否已安装 LibreOffice。',
    canRetry: false,
  },
  pdf_missing: {
    friendly: '原始教材文件已丢失，无法继续',
    suggestion: '请重新上传教材文件并创建新任务。',
    canRetry: false,
  },
  missing_llm_key: {
    friendly: 'AI 服务密钥未配置',
    suggestion: '请联系管理员配置 LLM API Key 后再试。',
    canRetry: false,
  },
  ocr_failed: {
    friendly: '文字识别（OCR）失败',
    suggestion: '请确认教材 PDF 内容清晰，或尝试重新提交。如问题持续请联系管理员。',
    canRetry: true,
  },
  generation_failed: {
    friendly: 'AI 题目生成失败',
    suggestion: '可尝试重新提交；若多次失败，请联系管理员反馈。',
    canRetry: true,
  },
};

// 关键词匹配兜底（按优先级排序）
const KEYWORD_RULES: Array<{ keywords: string[]; info: ErrorInfo }> = [
  {
    keywords: ['non-interactive', 'interactive input', 'input loop'],
    info: {
      friendly: '后台进程遇到交互异常',
      suggestion: '请重新提交任务；如问题持续，请联系管理员并告知错误详情。',
      canRetry: true,
    },
  },
  {
    keywords: ['runtimeerror', 'runtime error'],
    info: {
      friendly: '后台运行时出现意外错误',
      suggestion: '请重新提交任务；如问题持续，请联系管理员并告知错误详情。',
      canRetry: true,
    },
  },
  {
    keywords: ['timeout', 'timed out', '超时'],
    info: {
      friendly: '任务超时，AI 服务响应过慢',
      suggestion: '建议将教材拆分为较少页数后重新提交，或稍后再试。',
      canRetry: true,
    },
  },
  {
    keywords: ['quota', '配额', '积分', 'rate limit', 'rate_limit'],
    info: {
      friendly: 'AI 接口调用超出配额限制',
      suggestion: '请稍等片刻后重新提交，或联系管理员提升配额。',
      canRetry: true,
    },
  },
  {
    keywords: ['connection', 'network', 'connect', '网络', 'econnreset', 'econnrefused'],
    info: {
      friendly: '网络连接出现问题',
      suggestion: '请检查网络后重新提交，或联系管理员确认 AI 服务是否正常。',
      canRetry: true,
    },
  },
  {
    keywords: ['memory', 'oom', 'out of memory', '内存'],
    info: {
      friendly: '处理时内存不足',
      suggestion: '建议将教材拆分为较小文件后重新提交。',
      canRetry: true,
    },
  },
  {
    keywords: ['json', 'parse', 'decode', 'format'],
    info: {
      friendly: 'AI 返回的结果格式异常',
      suggestion: '请重新提交；如问题持续，请联系管理员并告知错误详情。',
      canRetry: true,
    },
  },
];

const FALLBACK: ErrorInfo = {
  friendly: '生成过程中出现错误',
  suggestion: '请尝试重新提交任务；如问题持续，请联系管理员并提供错误详情。',
  canRetry: true,
};

/**
 * 根据原始错误字符串（可能是错误码或堆栈文本）返回对教师友好的错误信息。
 */
export function parseTaskError(rawError: string | null | undefined): ErrorInfo {
  if (!rawError) return FALLBACK;

  // 1. 精确码匹配
  const lower = rawError.toLowerCase().trim();
  if (CODE_MAP[lower]) return CODE_MAP[lower];
  if (CODE_MAP[rawError.trim()]) return CODE_MAP[rawError.trim()];

  // 2. 关键词匹配
  for (const rule of KEYWORD_RULES) {
    if (rule.keywords.some((kw) => lower.includes(kw))) {
      return rule.info;
    }
  }

  // 3. 通用兜底
  return FALLBACK;
}
