import React, { useEffect, useRef, useState } from 'react';

export type TableData = {
  columns: string[];
  rows: unknown[][];
} | null;

/** Heuristic: find a key column for row identity. Looks for _id or _number columns. */
const KEY_COLUMN_BY_TABLE: Record<string, string> = {};

export function getRowKey(row: unknown[], columns: string[], tableName: string): string {
  // Check explicit config first
  const keyCol = KEY_COLUMN_BY_TABLE[tableName];
  if (keyCol) {
    const idx = columns.findIndex((c) => c.toLowerCase() === keyCol.toLowerCase());
    if (idx >= 0 && row[idx] != null) return String(row[idx]);
  }
  // Heuristic: look for *_id or *_number column
  const idIdx = columns.findIndex((c) => c.toLowerCase().endsWith('_id') || c.toLowerCase().endsWith('_number'));
  if (idIdx >= 0 && row[idIdx] != null) return String(row[idIdx]);
  return JSON.stringify(row);
}

function diffRows(
  prevRows: unknown[][],
  newRows: unknown[][],
  columns: string[],
  tableName: string,
): Set<string> {
  const changed = new Set<string>();
  const prevByKey = new Map<string, unknown[]>();
  for (const row of prevRows) {
    const k = getRowKey(row, columns, tableName);
    prevByKey.set(k, row);
  }
  for (const row of newRows) {
    const k = getRowKey(row, columns, tableName);
    const prev = prevByKey.get(k);
    if (!prev || JSON.stringify(prev) !== JSON.stringify(row)) {
      changed.add(k);
    }
  }
  return changed;
}

export type TableState = {
  data: TableData;
  loading: boolean;
  error: string | null;
  changedRowKeys: Set<string>;
  setChangedRowKeys: React.Dispatch<React.SetStateAction<Set<string>>>;
};

export function useTableData(
  tableName: string,
  refreshTrigger: number,
): TableState {
  const [data, setData] = useState<TableData>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [changedRowKeys, setChangedRowKeys] = useState<Set<string>>(new Set());
  const prevDataRef = useRef<{ tableName: string; data: TableData } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/tables/${tableName}`, { credentials: 'include' })
      .then(async (res) => {
        const text = await res.text();
        let body: { error?: string; message?: string };
        try {
          body = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(res.ok ? 'Invalid response from server' : `HTTP ${res.status}: ${text.slice(0, 100)}`);
        }
        if (!res.ok) {
          throw new Error(body.error ?? body.message ?? `HTTP ${res.status}`);
        }
        return body as { columns: string[]; rows: unknown[][] };
      })
      .then((body: { columns: string[]; rows: unknown[][] }) => {
        if (!cancelled) {
          const newData = { columns: body.columns, rows: body.rows };
          const prev = prevDataRef.current;
          if (prev?.tableName === tableName && prev?.data?.rows && prev.data.columns.length === body.columns.length) {
            const changed = diffRows(prev.data.rows, body.rows, body.columns, tableName);
            setChangedRowKeys(changed);
          } else {
            setChangedRowKeys(new Set());
          }
          prevDataRef.current = { tableName, data: newData };
          setData(newData);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tableName, refreshTrigger]);

  return { data, loading, error, changedRowKeys, setChangedRowKeys };
}
