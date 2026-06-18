import { memo, useState } from 'react';

export interface SelectorItem {
  key: string;
  label: string;
  description: string;
  default?: boolean;
  ready?: boolean;
}

export interface DynamicCardProps {
  type: 'confirmation' | 'info' | 'list' | 'error' | 'warning' | 'selector';
  title: string;
  fields?: { label: string; value: string }[];
  columns?: string[];
  rows?: (string | number | null)[][];
  items?: SelectorItem[];
  sendMessage?: (text: string, extra?: Record<string, unknown>) => void;
  theme?: 'default' | 'dbx';
}

// Neutral palette per theme — semantic colors (green/blue/red/amber) are shared
const NEUTRAL = {
  default: {
    border: 'border-gray-200 dark:border-gray-700',
    bg: 'bg-white dark:bg-gray-800/60',
    header: 'text-gray-700 dark:text-gray-300',
    label: 'text-gray-500 dark:text-gray-400',
    value: 'text-gray-800 dark:text-gray-200',
    muted: 'text-gray-400 dark:text-gray-500',
    toggleOff: 'bg-gray-300 dark:bg-gray-600',
    confirm: 'bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-800',
  },
  dbx: {
    border: 'border-dbx-gray-200 dark:border-dbx-gray-700',
    bg: 'bg-white dark:bg-dbx-gray-800/60',
    header: 'text-dbx-gray-700 dark:text-dbx-gray-300',
    label: 'text-dbx-gray-500 dark:text-dbx-gray-400',
    value: 'text-dbx-gray-800 dark:text-dbx-gray-200',
    muted: 'text-dbx-gray-400 dark:text-dbx-gray-500',
    toggleOff: 'bg-dbx-gray-300 dark:bg-dbx-gray-600',
    confirm: 'bg-dbx-orange text-white hover:bg-dbx-orange/90',
  },
} as const;

const SEMANTIC = {
  confirmation: {
    border: 'border-green-200 dark:border-green-800',
    bg: 'bg-green-50 dark:bg-green-900/20',
    header: 'text-green-700 dark:text-green-400',
    icon: '\u2713',
  },
  info: {
    border: 'border-blue-200 dark:border-blue-800',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    header: 'text-blue-700 dark:text-blue-400',
    icon: '\u2139',
  },
  error: {
    border: 'border-red-200 dark:border-red-800',
    bg: 'bg-red-50 dark:bg-red-900/20',
    header: 'text-red-700 dark:text-red-400',
    icon: '\u2717',
  },
  warning: {
    border: 'border-amber-200 dark:border-amber-800',
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    header: 'text-amber-700 dark:text-amber-400',
    icon: '\u26A0',
  },
} as const;

export const DynamicCard = memo(function DynamicCard(props: DynamicCardProps) {
  const { type, title, fields, columns, rows, items, sendMessage, theme = 'default' } = props;
  const n = NEUTRAL[theme];
  const sem = SEMANTIC[type as keyof typeof SEMANTIC];
  const colors = sem
    ? { border: sem.border, bg: sem.bg, header: sem.header, icon: sem.icon }
    : { border: n.border, bg: n.bg, header: n.header, icon: '' };

  const [selections, setSelections] = useState<Record<string, boolean>>(() => {
    if (!items) return {};
    return Object.fromEntries(items.map(i => [i.key, i.default ?? false]));
  });
  const [confirmed, setConfirmed] = useState(false);

  const handleToggle = (key: string) => {
    if (confirmed) return;
    setSelections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleConfirm = () => {
    if (confirmed || !sendMessage) return;
    setConfirmed(true);
    const selected = Object.entries(selections)
      .filter(([, v]) => v)
      .map(([k]) => k);
    const labels = (items || [])
      .filter(i => selected.includes(i.key))
      .map(i => i.label);
    const text = labels.length > 0
      ? `Selected: ${labels.join(', ')}`
      : 'No extras selected';
    sendMessage(text, { type: 'card_action', selections: selected });
  };

  return (
    <div
      className={`my-2 rounded-lg border ${colors.border} ${colors.bg} shadow-sm`}
      data-response-type="card"
    >
      {/* Header */}
      <div className={`px-4 py-2.5 text-sm font-semibold ${colors.header}`}>
        {colors.icon && <span className="mr-1.5">{colors.icon}</span>}
        {title}
      </div>

      {/* Key-value layout */}
      {fields && fields.length > 0 && (
        <div className="border-t border-inherit px-4 py-2">
          {fields.map((f, i) => (
            <div key={i} className="flex justify-between py-1 text-xs">
              <span className={n.label}>{f.label}</span>
              <span className={`font-medium ${n.value}`}>{f.value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Table layout */}
      {columns && columns.length > 0 && (
        <div className="overflow-x-auto border-t border-inherit">
          {rows && rows.length > 0 ? (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-inherit">
                  {columns.map((col, i) => (
                    <th key={i} className={`px-3 py-1.5 text-left font-medium ${n.label}`}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-inherit last:border-b-0">
                    {row.map((cell, j) => (
                      <td key={j} className={`px-3 py-1.5 ${n.value}`}>
                        {cell ?? ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className={`px-4 py-3 text-xs ${n.muted}`}>
              No results found
            </div>
          )}
        </div>
      )}

      {/* Selector layout */}
      {type === 'selector' && items && items.length > 0 && (
        <div className="border-t border-inherit">
          {items.map((item) => (
            <div
              key={item.key}
              className={`flex items-center justify-between px-4 py-2.5 border-b border-inherit last:border-b-0 ${confirmed ? 'opacity-60' : ''}`}
            >
              <div className="flex-1 min-w-0 mr-3">
                <div className={`text-xs font-medium ${n.value}`}>{item.label}</div>
                <div className={`text-[10px] ${n.muted}`}>{item.description}</div>
              </div>
              <button
                type="button"
                onClick={() => handleToggle(item.key)}
                disabled={confirmed}
                className={`relative w-8 h-4.5 rounded-full transition-colors ${
                  selections[item.key]
                    ? 'bg-purple-500'
                    : n.toggleOff
                } ${confirmed ? 'cursor-default' : 'cursor-pointer'}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white shadow transition-transform ${
                    selections[item.key] ? 'translate-x-3.5' : ''
                  }`}
                />
              </button>
            </div>
          ))}
          {!confirmed && sendMessage && (
            <div className="px-4 py-2.5 border-t border-inherit">
              <button
                type="button"
                onClick={handleConfirm}
                className={`w-full px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity ${n.confirm}`}
              >
                Confirm
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
