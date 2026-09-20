export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 justify-center text-muted text-sm">
      <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <div className="h-2.5 w-2.5 rounded-full bg-offline" />
      <p className="text-sm text-text max-w-sm">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs px-3 py-1.5 rounded-control border border-border text-muted hover:text-text hover:border-accent transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 py-10 text-center">
      <p className="text-sm text-text">{title}</p>
      {description && <p className="text-xs text-muted max-w-sm">{description}</p>}
    </div>
  );
}
