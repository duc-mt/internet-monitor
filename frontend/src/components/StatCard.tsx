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
    <div className="rounded-card border border-border bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted uppercase tracking-wide">{label}</span>
        {icon && (
          <span className="text-muted" style={accentColor ? { color: accentColor } : undefined}>
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span
          className="font-mono text-[26px] font-semibold leading-none font-tabular"
          style={accentColor ? { color: accentColor } : undefined}
        >
          {value}
        </span>
        {unit && <span className="text-sm text-muted">{unit}</span>}
      </div>
      {sublabel && <p className="mt-1.5 text-xs text-muted">{sublabel}</p>}
    </div>
  );
}
