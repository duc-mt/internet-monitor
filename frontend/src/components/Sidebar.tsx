import { NavLink } from "react-router-dom";
import { Activity, Gauge, History, MonitorDot, Settings as SettingsIcon, Moon, Sun, Laptop } from "lucide-react";
import { useStatus } from "../hooks/useStatus";
import { useTheme } from "../hooks/useTheme";
import { QUALITY_COLOR } from "./QualityBadge";
import type { Theme } from "../types";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/targets", label: "Targets", icon: MonitorDot, end: false },
  { to: "/history", label: "History", icon: History, end: false },
  { to: "/outages", label: "Outages", icon: Activity, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

export function Sidebar() {
  const { data: status } = useStatus();
  const { theme, setTheme } = useTheme();

  const dotColor = status ? QUALITY_COLOR[status.quality] : "var(--color-unknown)";

  return (
    <aside className="w-[220px] shrink-0 border-r border-border bg-panel flex flex-col h-full">
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-full transition-colors"
            style={{ backgroundColor: dotColor, boxShadow: `0 0 8px ${dotColor}` }}
          />
          <span className="font-semibold tracking-tight text-[15px]">Internet Monitor</span>
        </div>
        <p className="mt-1 text-[11px] text-muted font-mono">
          {status ? (status.online ? "ONLINE" : "OFFLINE") : "—"}
        </p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-control px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-accent-soft text-accent font-medium"
                  : "text-muted hover:text-text hover:bg-panel-alt"
              }`
            }
          >
            <Icon size={16} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-border">
        <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5">
          {(["light", "system", "dark"] as Theme[]).map((t) => {
            const Icon = t === "light" ? Sun : t === "dark" ? Moon : Laptop;
            return (
              <button
                key={t}
                onClick={() => setTheme(t)}
                aria-label={`${t} theme`}
                className={`flex-1 flex items-center justify-center py-1.5 rounded-[4px] transition-colors ${
                  theme === t ? "bg-accent-soft text-accent" : "text-muted hover:text-text"
                }`}
              >
                <Icon size={14} />
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
