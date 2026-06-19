import { useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTableRefresh } from '@/contexts/TableRefreshContext';
import { useTableData, getRowKey } from '@/hooks/useTableData';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { domainDashboardConfig } from '@/domain';

const TIMESTAMP_COLUMNS = ['recorded_at', 'last_checked', 'departure_time', 'scheduled_date', 'event_timestamp'];

// Color palette for auto-assigning dashboard table header colors
const PALETTE = [
  'bg-rose-100 dark:bg-rose-900/30',
  'bg-sky-100 dark:bg-sky-900/30',
  'bg-emerald-100 dark:bg-emerald-900/30',
  'bg-violet-100 dark:bg-violet-900/30',
  'bg-indigo-100 dark:bg-indigo-900/30',
  'bg-amber-100 dark:bg-amber-900/30',
  'bg-cyan-100 dark:bg-cyan-900/30',
  'bg-fuchsia-100 dark:bg-fuchsia-900/30',
];

const TABLE_PASTELS: Record<string, string> = domainDashboardConfig
  ? Object.fromEntries(domainDashboardConfig.tables.map(t => [t.name, t.color]))
  : {};

function displayName(name: string): string {
  return name.replace(/_/g, ' ');
}

function pctChangeCellClass(value: unknown): string {
  const n = Number(value);
  if (Number.isNaN(n)) return '';
  if (n >= 20) return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200 font-medium';
  if (n < 5) return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200';
  return '';
}


function formatCell(cell: unknown, columnName: string): string {
  if (cell == null) return '—';
  const s = String(cell);
  const col = columnName.toLowerCase();
  if (col.endsWith('_status') || col.endsWith('_risk') || col === 'status') return s.toLowerCase();
  const isTimestampColumn = TIMESTAMP_COLUMNS.some((c) =>
    columnName.toLowerCase().includes(c.toLowerCase()),
  );
  const looksLikeTimestamp =
    /^\d{4}-\d{2}-\d{2}(T|\s)\d{2}:\d{2}/.test(s) || /^\d{4}-\d{2}-\d{2}$/.test(s);
  if ((isTimestampColumn || looksLikeTimestamp) && s) {
    try {
      const d = new Date(s);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
        }).replace(/,/g, '');
      }
    } catch {
      /* fall through */
    }
  }
  return s;
}

function TableCard({ title, tableName, compact, id }: { title: string; tableName: string; compact?: boolean; id?: string }) {
  const { refreshKeys, refresh } = useTableRefresh();
  const refreshTrigger = refreshKeys[tableName] ?? 0;
  const { data, loading, error, changedRowKeys, setChangedRowKeys } = useTableData(tableName, refreshTrigger);

  useEffect(() => {
    if (changedRowKeys.size > 0) {
      const t = setTimeout(() => setChangedRowKeys(new Set()), 2000);
      return () => clearTimeout(t);
    }
  }, [changedRowKeys.size, setChangedRowKeys]);

  return (
    <div id={id} className="rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
      <div
        className={[
          'flex items-center justify-between border-b border-slate-200 px-3 py-1.5 dark:border-slate-700',
          TABLE_PASTELS[tableName] ?? 'bg-slate-50 dark:bg-slate-800/50',
        ].join(' ')}
      >
        <h2 className="font-medium text-foreground text-xs">{displayName(title)}</h2>
        <button
          type="button"
          onClick={() => refresh(tableName)}
          disabled={loading}
          aria-label="Refresh"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw
            className={`size-3.5 ${loading ? 'animate-spin' : ''}`}
          />
        </button>
      </div>
      <div className="overflow-x-auto p-[10px]">
        {error && (
          <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
        )}
        {!data && loading && (
          <p className="text-xs text-muted-foreground">Loading...</p>
        )}
        {data && (
          <table className={`w-full border-collapse text-xs ${compact ? 'min-w-[200px]' : 'min-w-[360px]'}`}>
            <thead>
              <tr>
                {data.columns.map((col) => (
                  <th
                    key={col}
                    className="border-b border-slate-200 px-2.5 py-1.5 text-left font-medium text-foreground dark:border-slate-700"
                  >
                    {displayName(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={data.columns.length}
                    className="px-2.5 py-2 text-center text-muted-foreground"
                  >
                    No rows
                  </td>
                </tr>
              ) : (
                data.rows.map((row, i) => {
                  const rowKey = getRowKey(row, data.columns, tableName);
                  const isChanged = changedRowKeys.has(rowKey);
                  return (
                  <tr
                    key={i}
                    className={[
                      'border-b border-slate-100 dark:border-slate-800',
                      isChanged ? 'animate-row-flash' : '',
                    ].filter(Boolean).join(' ')}
                  >
                    {row.map((cell, j) => {
                      const col = data.columns[j] ?? '';
                      const colLower = col.toLowerCase();
                      const display = formatCell(cell, col);
                      const isId = colLower.endsWith('_id') || colLower.endsWith('_number');
                      const isStatus = colLower.endsWith('_status') || colLower === 'status' || colLower.endsWith('_risk');
                      const isCapsule = isId || isStatus;
                      const isPctChange = colLower === 'pct_change';
                      const pctClass = isPctChange ? pctChangeCellClass(cell) : '';
                      return (
                        <td
                          key={j}
                          className="px-2.5 py-1.5 text-muted-foreground"
                        >
                          {isCapsule ? (
                            <span
                              className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300"
                            >
                              {display}
                            </span>
                          ) : isPctChange && pctClass ? (
                            <span className={['inline-flex rounded-full px-2 py-0.5 text-xs font-medium', pctClass].join(' ')}>
                              {display}
                            </span>
                          ) : (
                            display
                          )}
                        </td>
                      );
                    })}
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const { dashboardTables, featureEnabled } = useAppConfig();
  const domainTables = domainDashboardConfig?.tables ?? [];
  const tables = domainTables.length > 0
    ? domainTables
    : dashboardTables.map((name, i) => ({ name, color: PALETTE[i % PALETTE.length] }));

  if (!featureEnabled('dashboard') && domainTables.length === 0) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center overflow-auto px-4 py-3">
        <p className="text-muted-foreground text-sm">Welcome to your agent. Start a conversation in the chat.</p>
      </div>
    );
  }

  if (tables.length === 0) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center overflow-auto px-4 py-3">
        <p className="text-muted-foreground text-sm">Dashboard enabled but no tables selected. Select tables in the setup panel.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-auto px-4 py-3">
      <h1 className="mb-2 font-medium text-foreground text-sm">Dashboard</h1>
      <div className="flex flex-col gap-3">
        {tables.map(t => (
          <TableCard key={t.name} title={t.name} tableName={t.name} />
        ))}
      </div>
    </div>
  );
}
