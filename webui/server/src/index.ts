import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { dataRoutes } from './routes/data.js';
import { configRoutes } from './routes/config.js';
import { pipelineRoutes } from './routes/pipeline.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '../../..');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.use('/api', dataRoutes(projectRoot));
app.use('/api', configRoutes(projectRoot));
app.use('/api', pipelineRoutes());

if (process.env.NODE_ENV === 'production') {
  const frontendDist = path.resolve(__dirname, '../frontend/dist');
  app.use(express.static(frontendDist));
  app.get('*', (_, res) => {
    res.sendFile(path.join(frontendDist, 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`[edu-webui-server] running at http://localhost:${PORT}`);
});
