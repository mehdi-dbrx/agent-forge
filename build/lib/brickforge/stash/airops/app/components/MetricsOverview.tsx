import { useTableData } from '@/hooks/useTableData';
import { useTableRefresh } from '@/contexts/TableRefreshContext';

type CapsuleColor = 'amber' | 'blue';

function zoneCapsuleColor(zone: string): CapsuleColor {
  if (zone === 'B') return 'amber';
  if (zone === 'C') return 'blue';
  return 'amber';
}

function avgCheckinColor(mins: number): 'green' | 'amber' | 'red' {
  if (mins <= 5) return 'green';
  if (mins <= 20) return 'amber';
  return 'red';
}

function getColIndex(columns: string[], name: string): number {
  const lower = name.toLowerCase();
  return columns.findIndex((c) => c.toLowerCase() === lower);
}

function getCell(row: unknown[], colIndex: number): unknown {
  return colIndex >= 0 ? row[colIndex] : undefined;
}

const CAPSULE_CLASSES: Record<CapsuleColor, string> = {
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
};

function ZoneValueCard({
  zone,
  value,
  label,
  color,
  arcPercent,
  capsuleColor,
}: {
  zone: string;
  value: string;
  label: string;
  color: 'green' | 'amber' | 'red' | 'teal';
  arcPercent: number;
  capsuleColor: CapsuleColor;
}) {
  const colorClasses = {
    green: 'text-emerald-600 dark:text-emerald-400',
    amber: 'text-amber-600 dark:text-amber-400',
    red: 'text-red-600 dark:text-red-400',
    teal: 'text-teal-600 dark:text-teal-400',
  };
  const strokeClasses = {
    green: 'stroke-emerald-500 dark:stroke-emerald-400',
    amber: 'stroke-amber-500 dark:stroke-amber-400',
    red: 'stroke-red-500 dark:stroke-red-400',
    teal: 'stroke-teal-500 dark:stroke-teal-400',
  };
  const size = 86;
  const strokeWidth = 7;
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const dashOffset = circumference - (arcPercent / 100) * circumference;

  return (
    <div className="flex flex-col items-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
      <span className={`mb-1 inline-flex rounded-full px-2 py-0.5 font-medium text-xs ${CAPSULE_CLASSES[capsuleColor]}`}>
        Zone {zone}
      </span>
      <span className="mb-1.5 font-semibold text-muted-foreground text-xs">{label}</span>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-slate-200 dark:text-slate-700"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className={strokeClasses[color]}
          />
        </svg>
        <div
          className="absolute left-0 top-0 flex h-full w-full items-center justify-center"
          style={{ width: size, height: size }}
        >
          <span className={`whitespace-nowrap font-bold text-base leading-none ${colorClasses[color]}`}>{value}</span>
        </div>
      </div>
    </div>
  );
}

function ZoneMetricCard({
  zone,
  count,
  total,
  label,
  color,
  capsuleColor,
}: {
  zone: string;
  count: number;
  total: number;
  label: string;
  color: 'green' | 'amber' | 'red' | 'teal';
  capsuleColor: CapsuleColor;
}) {
  const colorClasses = {
    green: 'text-emerald-600 dark:text-emerald-400',
    amber: 'text-amber-600 dark:text-amber-400',
    red: 'text-red-600 dark:text-red-400',
    teal: 'text-teal-600 dark:text-teal-400',
  };
  const strokeClasses = {
    green: 'stroke-emerald-500 dark:stroke-emerald-400',
    amber: 'stroke-amber-500 dark:stroke-amber-400',
    red: 'stroke-red-500 dark:stroke-red-400',
    teal: 'stroke-teal-500 dark:stroke-teal-400',
  };
  const size = 86;
  const strokeWidth = 7;
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const arcPercent = total > 0 ? Math.min(100, (count / total) * 100) : 0;
  const dashOffset = circumference - (arcPercent / 100) * circumference;

  return (
    <div className="flex flex-col items-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
      <span className={`mb-1 inline-flex rounded-full px-2 py-0.5 font-medium text-xs ${CAPSULE_CLASSES[capsuleColor]}`}>
        Zone {zone}
      </span>
      <span className="mb-1.5 font-semibold text-muted-foreground text-xs">{label}</span>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-slate-200 dark:text-slate-700"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className={strokeClasses[color]}
          />
        </svg>
        <div
          className="absolute left-0 top-0 flex h-full w-full items-center justify-center"
          style={{ width: size, height: size }}
        >
          <span className={`whitespace-nowrap font-bold text-base leading-none ${colorClasses[color]}`}>
            {total > 0 ? `${count}/${total}` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}

export function MetricsOverview() {
  const { refreshKeys } = useTableRefresh();
  const metricsData = useTableData(`checkin_metrics`, refreshKeys[`checkin_metrics`] ?? 0);
  const flightsData = useTableData(`flights`, refreshKeys[`flights`] ?? 0);
  const agentsData = useTableData(`checkin_agents`, refreshKeys[`checkin_agents`] ?? 0);

  const loading = metricsData.loading || flightsData.loading || agentsData.loading;

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
        <h2 className="mb-2 font-medium text-foreground text-xs">Overview</h2>
        <p className="text-muted-foreground text-sm">Loading metrics...</p>
      </div>
    );
  }

  const metricsCols = metricsData.data?.columns ?? [];
  const flightsCols = flightsData.data?.columns ?? [];
  const agentsCols = agentsData.data?.columns ?? [];

  const avgColIdx = getColIndex(metricsCols, `avg_checkin_time_mins`);
  const zoneColIdx = getColIndex(metricsCols, `zone`);
  const flightZoneColIdx = getColIndex(flightsCols, `zone`);
  const delayRiskColIdx = getColIndex(flightsCols, `delay_risk`);
  const agentZoneColIdx = getColIndex(agentsCols, `zone`);
  const atCounterColIdx = getColIndex(agentsCols, `at_counter`);

  const allZones = new Set<string>();
  for (const row of metricsData.data?.rows ?? []) {
    const z = String(getCell(row as unknown[], zoneColIdx ?? -1)).trim();
    if (z) allZones.add(z);
  }
  for (const row of agentsData.data?.rows ?? []) {
    const z = String(getCell(row as unknown[], agentZoneColIdx ?? -1)).trim();
    if (z) allZones.add(z);
  }
  for (const row of flightsData.data?.rows ?? []) {
    const z = String(getCell(row as unknown[], flightZoneColIdx ?? -1)).trim();
    if (z) allZones.add(z);
  }
  const zones = [...allZones].sort();

  const avgCheckinByZone: Record<string, number> = {};
  for (const z of zones) avgCheckinByZone[z] = 0;
  for (const row of metricsData.data?.rows ?? []) {
    const z = String(getCell(row as unknown[], zoneColIdx ?? -1)).trim();
    const v = Number(getCell(row as unknown[], avgColIdx));
    if (z && !Number.isNaN(v)) avgCheckinByZone[z] = v;
  }

  const atRiskByZone: Record<string, number> = {};
  const totalFlightsByZone: Record<string, number> = {};
  for (const z of zones) {
    atRiskByZone[z] = 0;
    totalFlightsByZone[z] = 0;
  }
  for (const row of flightsData.data?.rows ?? []) {
    const z = String(getCell(row as unknown[], flightZoneColIdx ?? -1)).trim();
    const risk = String(getCell(row as unknown[], delayRiskColIdx ?? -1)).toLowerCase();
    if (!z) continue;
    totalFlightsByZone[z] = (totalFlightsByZone[z] ?? 0) + 1;
    if (risk === `at_risk`) atRiskByZone[z] = (atRiskByZone[z] ?? 0) + 1;
  }

  const totalByZone: Record<string, number> = {};
  const activeByZone: Record<string, number> = {};
  const breakAwayByZone: Record<string, number> = {};
  for (const z of zones) {
    totalByZone[z] = 0;
    activeByZone[z] = 0;
    breakAwayByZone[z] = 0;
  }
  for (const row of agentsData.data?.rows ?? []) {
    const zone = String(getCell(row as unknown[], agentZoneColIdx ?? -1)).trim();
    const status = String(getCell(row as unknown[], atCounterColIdx ?? -1)).toLowerCase();
    if (!zone) continue;
    totalByZone[zone] = (totalByZone[zone] ?? 0) + 1;
    if (status === `active`) {
      activeByZone[zone] = (activeByZone[zone] ?? 0) + 1;
    } else if (status === `break` || status === `away`) {
      breakAwayByZone[zone] = (breakAwayByZone[zone] ?? 0) + 1;
    }
  }

  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
      <h2 className="mb-2 font-medium text-foreground text-xs">Overview</h2>
      <div className="flex min-w-0 flex-nowrap gap-5 overflow-x-auto">
        {zones.map((zone) => {
          const capColor = zoneCapsuleColor(zone);
          const mins = avgCheckinByZone[zone] ?? 0;
          const valueColor = avgCheckinColor(mins);
          const arcPercent = Math.min(100, (mins / 20) * 100);
          const atRisk = atRiskByZone[zone] ?? 0;
          const totalFlights = totalFlightsByZone[zone] ?? 0;
          const atRiskColor = atRisk > 0 ? `red` : `teal`;
          return (
            <div
              key={zone}
              className="flex shrink-0 flex-wrap gap-3 rounded-lg border border-slate-200 p-2 dark:border-slate-600"
            >
              <ZoneValueCard
                zone={zone}
                value={mins > 0 ? `${mins.toFixed(1)} mn` : `—`}
                label="Av Checkin time"
                color={valueColor}
                arcPercent={arcPercent}
                capsuleColor={capColor}
              />
              <ZoneMetricCard
                zone={zone}
                count={atRisk}
                total={totalFlights}
                label="Flights at risk"
                color={atRiskColor}
                capsuleColor={capColor}
              />
              <ZoneMetricCard
                zone={zone}
                count={activeByZone[zone] ?? 0}
                total={totalByZone[zone] ?? 0}
                label="Active agents"
                color="green"
                capsuleColor={capColor}
              />
              <ZoneMetricCard
                zone={zone}
                count={breakAwayByZone[zone] ?? 0}
                total={totalByZone[zone] ?? 0}
                label="Off-counter agents"
                color="amber"
                capsuleColor={capColor}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
