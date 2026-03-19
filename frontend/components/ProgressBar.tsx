interface Props {
  covered: number;
  total: number;
  missing: string[];
}

export default function ProgressBar({ covered, total, missing }: Props) {
  const pct = Math.round((covered / total) * 100);

  return (
    <div data-testid="progress-bar" className="px-6 py-2 bg-gray-900 border-b border-gray-800">
      <div className="flex items-center gap-3 max-w-4xl mx-auto">
        <span data-testid="progress-text" className="text-xs text-gray-400 whitespace-nowrap">
          商业画布 {covered}/{total}
        </span>
        <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs text-gray-400">{pct}%</span>
        {missing.length > 0 && (
          <span className="text-xs text-yellow-500 truncate max-w-xs">
            待完善: {missing.slice(0, 3).join("、")}
          </span>
        )}
      </div>
    </div>
  );
}
