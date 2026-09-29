import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  unit,
  sublabel,
  accentColor,
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  sublabel?: string;
  accentColor?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-panel p-4 sm:p-5 transition-all-fast hover:-translate-y-1 hover:shadow-lg hover:border-slate-400 dark:hover:border-slate-700">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted uppercase tracking-widest">{label}</span>
        {icon && (
          <span className="text-muted" style={accentColor ? { color: accentColor } : undefined}>
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2.5 flex items-baseline gap-1.5">
        <span
          className="font-mono text-[26px] font-bold leading-none font-tabular"
          style={accentColor ? { color: accentColor } : undefined}
        >
          {value}
        </span>
        {unit && <span className="text-sm font-mono text-muted">{unit}</span>}
      </div>
      {sublabel && <p className="mt-2 text-xs text-muted font-medium">{sublabel}</p>}
    </div>
  );
}
