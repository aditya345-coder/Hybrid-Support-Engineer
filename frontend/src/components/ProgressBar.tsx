interface Props {
  percent: number;
  message: string;
  etaSeconds?: number;
}

export function ProgressBar({ percent, message, etaSeconds }: Props) {
  return (
    <div className="w-full space-y-1">
      <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{message}</span>
        {etaSeconds !== undefined && etaSeconds > 0 && (
          <span>~{etaSeconds}s remaining</span>
        )}
      </div>
    </div>
  );
}
