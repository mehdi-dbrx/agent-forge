import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { isDatabaseAvailable } from '@chat-template/db';

export const configRouter: RouterType = Router();

/**
 * GET /api/config - Get application configuration
 * Returns feature flags based on environment configuration
 */
configRouter.get('/', (_req: Request, res: Response) => {
  const features: Record<string, boolean> = {
    chatHistory: isDatabaseAvailable(),
  };

  // Auto-discover PROJECT_TOOL_* feature toggles from env
  for (const [key, val] of Object.entries(process.env)) {
    if (key.startsWith('PROJECT_TOOL_')) {
      const slug = key.replace('PROJECT_TOOL_', '').toLowerCase();
      features[slug] = !!val?.trim() && val.trim().toLowerCase() !== 'false';
    }
  }

  // Voice also requires OPENAI_API_KEY to be set
  if (features.voice && !process.env.OPENAI_API_KEY?.trim()) {
    features.voice = false;
  }

  // Custom logo URL (string, not boolean — sent as separate field)
  const logoUrl = process.env.PROJECT_LOGO_URL?.trim() || null;

  // Derive human-friendly app title from DBX_APP_NAME env var
  const appName = process.env.DBX_APP_NAME?.trim() || '';
  const appTitle = appName
    ? appName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : 'Agent Forge';

  // Dashboard tables from PROJECT_TABLES env var (comma-separated)
  const dashboardTables = (process.env.PROJECT_TABLES || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  res.json({ features, logoUrl, appTitle, dashboardTables });
});
