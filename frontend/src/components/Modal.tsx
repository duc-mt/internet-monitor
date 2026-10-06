import { type ReactNode, useEffect } from "react";
import { X } from "lucide-react";

export function Modal({
  title,
  onClose,
  children,
  size = "md",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  size?: "md" | "xl";
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm transition-opacity" onClick={onClose} />
      <div
        className={`relative w-full ${
          size === "xl" ? "max-w-3xl" : "max-w-md"
        } rounded-card border border-border bg-panel shadow-2xl transition-all-fast`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-slate-100 dark:bg-slate-900 rounded-t-card">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-rose-500/90 border border-rose-600/50 shadow-inner"></div>
              <div className="w-3 h-3 rounded-full bg-amber-500/90 border border-amber-600/50 shadow-inner"></div>
              <div className="w-3 h-3 rounded-full bg-emerald-500/90 border border-emerald-600/50 shadow-inner"></div>
            </div>
            <h2 className="text-xs font-medium font-mono tracking-wider text-slate-500 uppercase">{title}</h2>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text p-1 rounded-control transition-all-fast" aria-label="Close modal">
            <X size={14} />
          </button>
        </div>
        <div className={`px-5 py-4 ${size === "xl" ? "max-h-[75vh] overflow-y-auto" : ""}`}>{children}</div>
      </div>
    </div>
  );
}
