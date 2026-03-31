"use client";

type Props = {
  message: string;
  onRetry?: () => void;
};

export function ErrorMessage({ message, onRetry }: Props) {
  return (
    <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 flex items-center justify-between gap-4">
      <p className="text-sm text-destructive">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 text-sm font-medium text-destructive underline-offset-4 hover:underline"
        >
          Retry
        </button>
      )}
    </div>
  );
}
