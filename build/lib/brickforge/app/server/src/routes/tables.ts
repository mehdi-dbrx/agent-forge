import { Router, type Request, type Response } from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';

export const tablesRouter = Router();
tablesRouter.use(authMiddleware);

/**
 * GET /api/tables/:tableName - Proxy to backend /tables/:tableName
 * Backend has Databricks auth; avoids DATABRICKS_* env in Node (not available when deployed).
 * Backend validates table access against UC schema. No hardcoded allowlist here.
 * Returns { columns: string[], rows: any[][] }
 */
tablesRouter.get('/:tableName', requireAuth, async (req: Request, res: Response) => {
  const tableName = req.params.tableName;
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(tableName)) {
    return res.status(400).json({ error: 'Invalid table name' });
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
