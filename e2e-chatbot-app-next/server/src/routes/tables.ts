import { Router, type Request, type Response } from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';

const ALLOWED_TABLES = ['checkin_metrics', 'flights', 'checkin_agents', 'border_officers', 'border_terminals'] as const;
const EMPTY_TABLES = new Set(['checkin_metrics', 'checkin_agents', 'border_officers', 'border_terminals']);

export const tablesRouter = Router();
tablesRouter.use(authMiddleware);

/**
 * GET /api/tables/:tableName - Proxy to backend /tables/:tableName
 * Backend has Databricks auth; avoids DATABRICKS_* env in Node (not available when deployed).
 * Returns { columns: string[], rows: any[][] }
 */
tablesRouter.get('/:tableName', requireAuth, async (req: Request, res: Response) => {
  const tableName = req.params.tableName;
  if (!ALLOWED_TABLES.includes(tableName as (typeof ALLOWED_TABLES)[number])) {
    return res.status(400).json({ error: 'Table not allowed', allowed: [...ALLOWED_TABLES] });
  }

  if (EMPTY_TABLES.has(tableName)) {
    return res.json({ columns: [], rows: [] });
  }

  const apiProxy = process.env.API_PROXY || '';
  let base = apiProxy.replace(/\/invocations\/?$/, '') || 'http://127.0.0.1:8000';
  if (base.startsWith('http://localhost:') || base.startsWith('https://localhost:')) {
    base = base.replace('localhost', '127.0.0.1');
  }
  const url = `${base}/tables/${tableName}`;

  try {
    const response = await fetch(url);
    const data = (await response.json()) as { columns?: string[]; rows?: unknown[][]; detail?: string };
    if (!response.ok) {
      const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data);
      console.error('[tables] backend error', response.status, msg.slice(0, 200));
      return res.status(response.status).json({
        error: 'Backend tables error',
        details: msg.slice(0, 200),
      });
    }
    return res.json({ columns: data.columns ?? [], rows: data.rows ?? [] });
  } catch (err) {
    console.error('[tables] fetch error', url, err);
    return res.status(502).json({
      error: 'Backend unavailable',
      message: err instanceof Error ? err.message : 'Unknown error',
    });
  }
});
