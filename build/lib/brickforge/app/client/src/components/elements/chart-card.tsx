import { memo, useId, useState } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export interface ChartConfig {
  type: 'bar' | 'line' | 'area' | 'pie';
  title: string;
  headers: string[];
  rows: (string | number)[][];
  x_column: number;
  y_column: number;
}

const CHART_TYPES = ['area', 'line', 'bar', 'pie'] as const;

const PIE_COLORS = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
];

function formatYAxis(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function formatXAxis(value: string): string {
  if (!value) return '';
  // Truncate long labels
  if (value.length > 12) return `${value.slice(0, 12)}...`;
  // Format date-like strings
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  }
  return value;
}

export const ChartCard = memo(function ChartCard({ data }: { data: ChartConfig }) {
  const gradientId = useId();
  const [chartType, setChartType] = useState<typeof CHART_TYPES[number]>(
    CHART_TYPES.includes(data.type as typeof CHART_TYPES[number]) ? data.type as typeof CHART_TYPES[number] : 'bar',
  );

  const { headers, rows, x_column, y_column, title } = data;

  if (!headers || !rows || x_column == null || y_column == null) {
    return <div className="text-sm text-red-500">Invalid chart data</div>;
  }

  const xKey = headers[x_column];
  const yKey = headers[y_column];

  const chartData = rows.map((row) => ({
    [xKey]: String(row[x_column] ?? ''),
    [yKey]: typeof row[y_column] === 'number' ? row[y_column] : Number.parseFloat(String(row[y_column])) || 0,
  }));

  const renderChart = () => {
    const commonAxisProps = {
      tickLine: false,
      axisLine: false,
      fontSize: 11,
      tick: { fill: '#9ca3af' },
    };

    if (chartType === 'pie') {
      return (
        <PieChart>
          <Pie
            data={chartData}
            dataKey={yKey}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={80}
            innerRadius={40}
            paddingAngle={2}
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {chartData.map((_, i) => (
              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#e5e7eb',
            }}
          />
        </PieChart>
      );
    }

    const xAxisProps = { ...commonAxisProps, dataKey: xKey, tickFormatter: formatXAxis };
    const yAxisProps = { ...commonAxisProps, tickFormatter: formatYAxis, width: 50 };
    const gridProps = { strokeDasharray: '3 3', stroke: '#374151', opacity: 0.5 };
    const tooltipProps = {
      contentStyle: {
        backgroundColor: '#1f2937',
        border: '1px solid #374151',
        borderRadius: '8px',
        fontSize: '12px',
        color: '#e5e7eb',
      },
    };

    if (chartType === 'area') {
      return (
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id={`area-grad-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.7} />
              <stop offset="40%" stopColor="#60a5fa" stopOpacity={0.5} />
              <stop offset="80%" stopColor="#93c5fd" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#bfdbfe" stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid {...gridProps} />
          <XAxis {...xAxisProps} />
          <YAxis {...yAxisProps} />
          <Tooltip {...tooltipProps} />
          <Area
            type="monotone"
            dataKey={yKey}
            stroke="#3b82f6"
            strokeWidth={2}
            fill={`url(#area-grad-${gradientId})`}
          />
        </AreaChart>
      );
    }

    if (chartType === 'line') {
      return (
        <LineChart data={chartData}>
          <CartesianGrid {...gridProps} />
          <XAxis {...xAxisProps} />
          <YAxis {...yAxisProps} />
          <Tooltip {...tooltipProps} />
          <Line
            type="monotone"
            dataKey={yKey}
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      );
    }

    // Bar chart (default)
    return (
      <BarChart data={chartData}>
        <CartesianGrid {...gridProps} />
        <XAxis {...xAxisProps} />
        <YAxis {...yAxisProps} />
        <Tooltip {...tooltipProps} />
        <Bar dataKey={yKey} fill="#3b82f6" radius={[4, 4, 0, 0]} />
      </BarChart>
    );
  };

  return (
    <div
      className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/60"
      data-response-type="chart"
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <div className="flex gap-1">
          {CHART_TYPES.map((ct) => (
            <button
              key={ct}
              type="button"
              onClick={() => setChartType(ct)}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                chartType === ct
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                  : 'text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300'
              }`}
            >
              {ct}
            </button>
          ))}
        </div>
      </div>
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </div>
    </div>
  );
});
