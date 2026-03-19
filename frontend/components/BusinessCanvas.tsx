interface CanvasItem {
  content: string[];
  is_inferred: boolean;
}

interface CanvasData {
  project_name: string;
  tagline: string;
  canvas: Record<string, CanvasItem>;
  next_steps: string[];
}

interface Props {
  data: CanvasData;
  onClose: () => void;
}

const CANVAS_LABELS: Record<string, string> = {
  key_partnerships: "🤝 重要伙伴",
  key_activities: "⚙️ 关键业务",
  value_propositions: "✨ 价值主张",
  customer_relationships: "💬 客户关系",
  customer_segments: "👥 客户细分",
  key_resources: "🔑 核心资源",
  channels: "📡 渠道通路",
  cost_structure: "💸 成本结构",
  revenue_streams: "💰 收入来源",
};

// Standard Business Model Canvas layout order
const CANVAS_LAYOUT = [
  ["key_partnerships", "key_activities", "value_propositions", "customer_relationships", "customer_segments"],
  ["key_resources", null, null, "channels", null],
  ["cost_structure", null, null, "revenue_streams", null],
];

export default function BusinessCanvas({ data, onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 overflow-auto">
      <div className="bg-gray-900 rounded-2xl w-full max-w-5xl max-h-full overflow-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 px-6 py-4 border-b border-gray-700 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">{data.project_name}</h2>
            <p className="text-sm text-gray-400 mt-0.5">{data.tagline}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg ml-4"
          >
            ✕
          </button>
        </div>

        {/* Canvas Grid */}
        <div className="p-6">
          <div className="grid grid-cols-5 gap-3 mb-4">
            {Object.entries(CANVAS_LABELS).map(([key, label]) => {
              const item = data.canvas[key];
              if (!item) return null;
              return (
                <CanvasCell key={key} label={label} item={item} />
              );
            })}
          </div>

          {/* Next Steps */}
          {data.next_steps.length > 0 && (
            <div className="mt-4 p-4 bg-blue-950 rounded-xl border border-blue-800">
              <h3 className="text-sm font-semibold text-blue-300 mb-2">🚀 建议下一步</h3>
              <ul className="space-y-1">
                {data.next_steps.map((step, i) => (
                  <li key={i} className="text-sm text-gray-300 flex gap-2">
                    <span className="text-blue-500">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CanvasCell({ label, item }: { label: string; item: CanvasItem }) {
  return (
    <div
      className={`rounded-xl p-3 border text-xs
        ${item.is_inferred
          ? "bg-yellow-950/30 border-yellow-800/50"
          : "bg-gray-800 border-gray-700"
        }`}
    >
      <div className="font-semibold text-gray-300 mb-2">{label}</div>
      <ul className="space-y-1">
        {item.content.map((point, i) => (
          <li key={i} className="text-gray-400 flex gap-1">
            <span className="text-gray-600">·</span>
            {point}
          </li>
        ))}
      </ul>
      {item.is_inferred && (
        <span className="text-yellow-600 text-xs mt-2 block">* 推断补全</span>
      )}
    </div>
  );
}
