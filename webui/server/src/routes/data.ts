import { Router, Request, Response } from 'express';
import fs from 'fs/promises';
import path from 'path';
import yaml from 'js-yaml';

export function dataRoutes(projectRoot: string): Router {
  const router = Router();

  const configPath = path.join(projectRoot, 'dataflow_edu', 'config', 'edu_config.yaml');
  const basePath = path.join(projectRoot, 'dataflow_edu', 'data', 'generation_and_balancing');

  router.get('/config', async (_: Request, res: Response) => {
    try {
      const content = await fs.readFile(configPath, 'utf-8');
      const config = yaml.load(content) || {};
      res.json(config);
    } catch (err) {
      res.status(404).json({ error: '配置文件加载失败' });
    }
  });

  router.get('/data/:book', async (req: Request, res: Response) => {
    const book = req.params.book?.trim();
    if (!book) {
      res.status(400).json({ error: '教材名称不能为空' });
      return;
    }

    const stage1Path = path.join(basePath, '2_1_generated_stage_1', `${book}_stage1_taxonomy.json`);
    const stage2Path = path.join(basePath, '2_1_generated_stage_2', `${book}_generated_questions.json`);
    const stage3Path = path.join(basePath, '2_2_balanced', `${book}_balanced_questions.json`);

    try {
      let config: Record<string, unknown> = {};
      try {
        const configContent = await fs.readFile(configPath, 'utf-8');
        config = (yaml.load(configContent) as Record<string, unknown>) || {};
      } catch {
        // config optional
      }

      const [r1, r2, r3] = await Promise.all([
        fs.readFile(stage1Path, 'utf-8').then(JSON.parse).catch(() => {
          throw new Error('阶段1 加载失败');
        }),
        fs.readFile(stage2Path, 'utf-8').then(JSON.parse).catch(() => {
          throw new Error('阶段2 加载失败');
        }),
        fs.readFile(stage3Path, 'utf-8').then(JSON.parse).catch(() => {
          throw new Error('阶段3 加载失败');
        }),
      ]);

      res.json({
        config,
        stage1: r1,
        stage2: r2,
        stage3: r3,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      res.status(404).json({ error: msg });
    }
  });

  return router;
}
