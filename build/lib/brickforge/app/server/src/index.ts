// Load environment variables FIRST before any other imports
import './env';

import express, {
  type Request,
  type Response,
  type NextFunction,
  type Express,
} from 'express';
import cors from 'cors';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { chatRouter } from './routes/chat';
import { historyRouter } from './routes/history';
import { sessionRouter } from './routes/session';
import { messagesRouter } from './routes/messages';
import { configRouter } from './routes/config';
import { tablesRouter } from './routes/tables';
import multer from 'multer';
import { authMiddleware, requireAuth } from './middleware/auth';
import { ChatSDKError } from '@chat-template/core/errors';

const upload = multer({ storage: multer.memoryStorage() });

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app: Express = express();
const isDevelopment = process.env.NODE_ENV !== 'production';
// Either let PORT be set by env or use 3001 for development and 3000 for production
// The CHAT_APP_PORT can be used to override the port for the chat app.
const PORT =
  process.env.CHAT_APP_PORT ||
  process.env.PORT ||
  (isDevelopment ? 3001 : 3000);

// CORS configuration
app.use(
  cors({
    origin: isDevelopment ? 'http://localhost:3000' : true,
    credentials: true,
  }),
);

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Log every request (so you can see if /api/current-time hits this server)
app.use((req, _res, next) => {
  console.log('[req]', req.method, req.url);
  next();
});

// Health check endpoint (for Playwright tests)
app.get('/ping', (_req, res) => {
  res.status(200).send('pong');
});

// Dedicated route for stepping time back (register before /api/current-time so it matches first).
app.get('/api/current-time/backward', async (_req, res) => {
  const apiProxy = process.env.API_PROXY || '';
  let base = apiProxy.replace(/\/invocations\/?$/, '') || 'http://127.0.0.1:8000';
  if (base.startsWith('http://localhost:') || base.startsWith('https://localhost:')) {
    base = base.replace('localhost', '127.0.0.1');
  }
  const url = `${base}/current-time/backward`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const text = await response.text();
      console.error(`[current-time/backward] ${url} → ${response.status}`, text.slice(0, 200));
      return res.status(response.status).json({ error: 'Backend error', details: text.slice(0, 200) });
    }
    const data = (await response.json()) as { currentTime: string };
    return res.json(data);
  } catch (err) {
    console.error('[current-time/backward] fetch failed', url, err);
    return res.status(502).json({ error: 'Backend unavailable' });
  }
});

// Proxy to backend: simulated current time. ?advance=true moves queue; default peeks.
app.get('/api/current-time', async (req, res) => {
  const apiProxy = process.env.API_PROXY || '';
  let base = apiProxy.replace(/\/invocations\/?$/, '') || 'http://127.0.0.1:8000';
  // Use 127.0.0.1 for localhost so Node can reach the backend reliably
  if (base.startsWith('http://localhost:') || base.startsWith('https://localhost:')) {
    base = base.replace('localhost', '127.0.0.1');
  }
  const advance = req.query.advance === 'true' ? 'true' : 'false';
  const backward = req.query.backward === 'true' ? 'true' : 'false';
  const url = `${base}/current-time?advance=${advance}&backward=${backward}`;
  console.log('[current-time] proxy', advance, backward, '->', url);
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const text = await response.text();
      console.error(`[current-time] ${url} → ${response.status}`, text.slice(0, 200));
      return res.status(response.status).json({ error: 'Backend error', details: text.slice(0, 200) });
    }
    const data = (await response.json()) as { currentTime: string };
    return res.json(data);
  } catch (err) {
    console.error('[current-time] fetch failed', url, err);
    return res.status(502).json({ error: 'Backend unavailable' });
  }
});

// Reset demo state: runs scripts/reset_state.py (sequence of SQL scripts)
app.post('/api/reset-state', authMiddleware, requireAuth, (req, res) => {
  // Server lives at app/server; project root is two levels up
  const projectRoot = path.join(__dirname, '..', '..', '..');
  const scriptPath = path.join(projectRoot, 'scripts', 'reset_state.py');
  const proc = spawn('uv', ['run', 'python', scriptPath], {
    cwd: projectRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  proc.stdout?.on('data', (chunk) => { stdout += chunk.toString(); });
  proc.stderr?.on('data', (chunk) => { stderr += chunk.toString(); });
  proc.on('close', (code) => {
    if (code === 0) {
      res.json({ ok: true, message: 'State reset' });
    } else {
      console.error('[reset-state]', code, stderr);
      res.status(502).json({ error: 'Reset failed', details: stderr.slice(0, 500) });
    }
  });
  proc.on('error', (err) => {
    console.error('[reset-state] spawn error', err);
    res.status(502).json({ error: 'Reset failed', message: err.message });
  });
});

// SSE: staffing/task events (clients subscribe, receive task_created when Manager assigns)
const taskEventClients: Array<{ res: Response; assignedTo?: string }> = [];
app.get('/api/events/tasks', (req, res) => {
  const assignedTo = typeof req.query.assigned_to === 'string' ? req.query.assigned_to : undefined;
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();
  taskEventClients.push({ res, assignedTo });
  console.log(
    `[task-events] SSE client connected assigned_to=${assignedTo ?? 'any'} total=${taskEventClients.length}`,
  );
  res.write(`data: ${JSON.stringify({ type: 'connected' })}\n\n`);
  const heartbeat = setInterval(() => {
    res.write(': heartbeat\n\n');
  }, 30000);
  res.on('close', () => {
    clearInterval(heartbeat);
    const idx = taskEventClients.findIndex((c) => c.res === res);
    if (idx >= 0) taskEventClients.splice(idx, 1);
    console.log(`[task-events] SSE client disconnected total=${taskEventClients.length}`);
  });
});
app.post('/api/events/task-created', (req, res) => {
  const body = req.body as {
    assigned_to_id?: string;
    agent_name?: string;
    manager_name?: string;
  };
  const assignedToId = body?.assigned_to_id;
  if (!assignedToId || typeof assignedToId !== 'string') {
    return res.status(400).json({ error: 'assigned_to_id required' });
  }
  const payload = JSON.stringify({
    type: 'task_created',
    assigned_to_id: assignedToId,
    agent_name: body.agent_name ?? assignedToId,
    manager_name: body.manager_name ?? 'Manager',
  });
  let sent = 0;
  for (const { res: clientRes, assignedTo } of taskEventClients) {
    if (!assignedTo || assignedTo === assignedToId) {
      try {
        clientRes.write(`data: ${payload}\n\n`);
        sent++;
      } catch (e) {
        console.warn('[task-events] Failed to write to client:', e);
      }
    }
  }
  console.log(
    `[task-events] task_created assigned_to_id=${assignedToId} clients=${taskEventClients.length} sent=${sent}`,
  );
  res.status(204).send();
});

// Image upload: convert to data URL for AI SDK consumption (gated by PROJECT_TOOL_IMAGE)
app.post('/api/files/upload', upload.single('file'), (req, res) => {
  const file = req.file;
  if (!file) {
    return res.status(400).json({ error: 'file required' });
  }
  if (!file.mimetype.startsWith('image/')) {
    return res.status(400).json({ error: 'only image files are accepted' });
  }
  if (file.size > 10 * 1024 * 1024) {
    return res.status(413).json({ error: 'image must be under 10 MB' });
  }
  const base64 = file.buffer.toString('base64');
  const url = `data:${file.mimetype};base64,${base64}`;
  console.log(`[files/upload] ${file.originalname} ${file.mimetype} ${file.size} bytes`);
  res.json({ url, pathname: file.originalname || 'upload', contentType: file.mimetype });
});

// Audio transcription via OpenAI Whisper (proxies to keep API key server-side)
app.post('/api/audio/transcribe', upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) {
    return res.status(400).json({ error: 'file required' });
  }
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return res.status(503).json({ error: 'OPENAI_API_KEY not configured' });
  }
  const formData = new FormData();
  formData.append(
    'file',
    new Blob([file.buffer], { type: file.mimetype || 'audio/webm' }),
    file.originalname || 'recording.webm',
  );
  formData.append('model', 'whisper-1');
  try {
    console.log('[audio/transcribe] request received, size=', file.size, 'bytes');
    const response = await fetch('https://api.openai.com/v1/audio/transcriptions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}` },
      body: formData,
    });
    if (!response.ok) {
      const err = await response.text();
      console.error('[audio/transcribe] OpenAI error', response.status, err.slice(0, 200));
      return res.status(response.status).json({ error: err });
    }
    const { text } = (await response.json()) as { text: string };
    console.log('[audio/transcribe] success, text length=', text.length);
    res.json({ text });
  } catch (err) {
    console.error('[audio/transcribe]', err);
    res.status(502).json({ error: 'Transcription failed' });
  }
});

// API routes
app.use('/api/chat', chatRouter);
app.use('/api/history', historyRouter);
app.use('/api/session', sessionRouter);
app.use('/api/messages', messagesRouter);
app.use('/api/config', configRouter);
app.use('/api/tables', tablesRouter);

// 404 for unmatched API routes (return JSON, not HTML)
app.use('/api', (_req, res) => {
  res.status(404).json({ error: 'Not found', path: _req.path });
});

// In development, root is not served here — frontend runs on port 3000. Redirect so "Cannot GET /" doesn't happen.
if (isDevelopment) {
  app.get('/', (_req, res) => {
    res.redirect(302, 'http://localhost:3000');
  });
}

// Serve static files in production
if (!isDevelopment) {
  const clientBuildPath = path.join(__dirname, '../../client/dist');
  app.use(express.static(clientBuildPath));

  // SPA fallback - serve index.html for all non-API routes
  app.get(/^\/(?!api).*/, (_req, res) => {
    res.sendFile(path.join(clientBuildPath, 'index.html'));
  });
}

// Error handling middleware
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error('Error:', err);

  if (err instanceof ChatSDKError) {
    const response = err.toResponse();
    return res.status(response.status).json(response.json);
  }

  res.status(500).json({
    error: 'Internal Server Error',
    message: isDevelopment ? err.message : 'An unexpected error occurred',
  });
});

// Start MSW mock server in test mode
async function startServer() {
  if (process.env.PLAYWRIGHT === 'True') {
    console.log('[Test Mode] Starting MSW mock server for API mocking...');
    try {
      // Dynamically import MSW setup from tests directory (using relative path from server root)
      const modulePath = path.join(
        dirname(dirname(__dirname)),
        'tests',
        'api-mocking',
        'api-mock-server.ts',
      );
      console.log('[Test Mode] Attempting to load MSW from:', modulePath);

      const { mockServer } = await import(modulePath);

      mockServer.listen({
        onUnhandledRequest: (request: Request) => {
          console.warn(
            `[MSW] Unhandled ${request.method} request to ${request.url}`,
          );
        },
      });

      console.log('[Test Mode] MSW mock server started successfully');
      console.log(
        '[Test Mode] Registered handlers:',
        mockServer.listHandlers().length,
      );

      // Import captured request utilities for testing context injection
      const handlersPath = path.join(
        dirname(dirname(__dirname)),
        'tests',
        'api-mocking',
        'api-mock-handlers.ts',
      );
      const {
        getCapturedRequests,
        resetCapturedRequests,
        getLastCapturedRequest,
      } = await import(handlersPath);

      // Test-only endpoint to get captured requests (for context injection testing)
      app.get('/api/test/captured-requests', (_req, res) => {
        res.json(getCapturedRequests());
      });

      // Test-only endpoint to get the last captured request
      app.get('/api/test/last-captured-request', (_req, res) => {
        const lastRequest = getLastCapturedRequest();
        if (lastRequest) {
          res.json(lastRequest);
        } else {
          res.status(404).json({ error: 'No captured requests' });
        }
      });

      // Test-only endpoint to reset captured requests
      app.post('/api/test/reset-captured-requests', (_req, res) => {
        resetCapturedRequests();
        res.json({ success: true });
      });

      console.log('[Test Mode] Test endpoints for context injection registered');
    } catch (error) {
      console.error('[Test Mode] Failed to start MSW:', error);
      console.error(
        '[Test Mode] Error details:',
        error instanceof Error ? error.stack : error,
      );
    }
  }

  app.listen(PORT, () => {
    console.log(`Backend server is running on http://localhost:${PORT}`);
    console.log(`Environment: ${isDevelopment ? 'development' : 'production'}`);
  });
}

startServer();

export default app;
