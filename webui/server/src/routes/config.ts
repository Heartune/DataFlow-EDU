import { Router, Request, Response } from 'express';
import fs from 'fs/promises';
import path from 'path';
import yaml from 'js-yaml';
import { spawn } from 'child_process';

export function configRoutes(projectRoot: string): Router {
  const router = Router();
  const configPath = path.join(projectRoot, 'dataflow_edu', 'config', 'edu_config.yaml');
  const presetsDir = path.join(projectRoot, 'dataflow_edu', 'config', 'presets');
  const validateScript = path.join(
    projectRoot,
    'dataflow_edu',
    'config',
    'validate_and_save.py'
  );

  router.put('/config', async (req: Request, res: Response) => {
    const body = req.body;
    if (!body || typeof body !== 'object') {
      res.status(400).json({ ok: false, errors: ['请求体必须为 JSON 配置对象'] });
      return;
    }

    return new Promise<void>((resolve) => {
      const python = process.platform === 'win32' ? 'python' : 'python3';
      const proc = spawn(python, [validateScript], {
        cwd: projectRoot,
        env: { ...process.env, PYTHONPATH: projectRoot },
      });

      let stdout = '';
      let stderr = '';
      proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
      proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

      proc.on('error', (err) => {
        res.status(500).json({
          ok: false,
          errors: [`启动校验脚本失败: ${err.message}`],
        });
        resolve();
      });

      proc.on('close', (code) => {
        try {
          const result = JSON.parse(stdout.trim());
          if (result.ok) {
            res.json({ ok: true });
          } else {
            res.status(400).json({ ok: false, errors: result.errors || ['校验失败'] });
          }
        } catch {
          res.status(500).json({
            ok: false,
            errors: [`校验脚本异常: ${stderr || stdout || '无输出'}`],
          });
        }
        resolve();
      });

      proc.stdin.write(JSON.stringify(body), 'utf-8', () => {
        proc.stdin.end();
      });
    });
  });

  router.get('/config/presets', async (_: Request, res: Response) => {
    try {
      const files = await fs.readdir(presetsDir);
      const names = files
        .filter((f) => f.endsWith('.yaml') || f.endsWith('.yml'))
        .map((f) => path.basename(f, path.extname(f)));
      res.json(names);
    } catch {
      res.json([]);
    }
  });

  router.post('/config/presets/:name', async (req: Request, res: Response) => {
    const name = req.params.name?.trim();
    if (!name || /[.\\/]/.test(name)) {
      res.status(400).json({ error: '无效预设名称' });
      return;
    }
    const presetPath = path.join(presetsDir, `${name}.yaml`);
    const altPath = path.join(presetsDir, `${name}.yml`);
    let content: string;
    try {
      content = await fs.readFile(presetPath, 'utf-8');
    } catch {
      try {
        content = await fs.readFile(altPath, 'utf-8');
      } catch {
        res.status(404).json({ error: '预设不存在' });
        return;
      }
    }
    try {
      const parsed = yaml.load(content) as object;
      await fs.writeFile(configPath, content, 'utf-8');
      res.json(parsed);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存预设失败';
      res.status(500).json({ error: msg });
    }
  });

  return router;
}
