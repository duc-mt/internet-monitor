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
    <aside className="w-[230px] shrink-0 border-r border-border bg-panel flex flex-col h-full">
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-control bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-sm shrink-0">
            <Activity size={16} strokeWidth={2.5} />
          </div>
          <div className="overflow-hidden">
            <span className="font-extrabold tracking-tight text-[15px] block truncate leading-tight">Internet Monitor</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className="h-1.5 w-1.5 rounded-full transition-colors shrink-0"
                style={{ backgroundColor: dotColor, boxShadow: `0 0 6px ${dotColor}` }}
              />
              <span className="text-[10px] text-muted font-mono uppercase tracking-widest font-semibold">
                {status ? (status.online ? "ONLINE" : "OFFLINE") : "—"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-control px-3 py-2 text-sm transition-all-fast font-medium ${
                isActive
                  ? "bg-gradient-to-r from-blue-500/10 to-indigo-500/15 border-l-2 border-indigo-500 text-indigo-400 font-semibold"
                  : "text-muted hover:text-text hover:bg-panel-alt hover:translate-x-0.5"
              }`
            }
          >
            <Icon size={16} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-border">
        <div className="flex items-center rounded-control border border-border p-0.5 gap-0.5 bg-panel-alt">
          {(["light", "system", "dark"] as Theme[]).map((t) => {
            const Icon = t === "light" ? Sun : t === "dark" ? Moon : Laptop;
            return (
              <button
                key={t}
                onClick={() => setTheme(t)}
                aria-label={`${t} theme`}
                className={`flex-1 flex items-center justify-center py-1.5 rounded-[4px] transition-all-fast ${
                  theme === t ? "bg-accent-soft text-accent font-semibold shadow-sm" : "text-muted hover:text-text"
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
