import { useEffect, useState } from "react";

interface Stats {
  total_queries: number;
  hallucination_rate: number;
  top_features: { feature: string; count: number }[];
}

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/stats/hallucination`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      {!stats ? (
        <p className="text-gray-500">Loading stats...</p>
      ) : (
        <div className="space-y-4">
          <div className="flex gap-8">
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-sm text-gray-500">Total Queries</p>
              <p className="text-2xl font-bold">{stats.total_queries}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-sm text-gray-500">Hallucination Rate</p>
              <p className="text-2xl font-bold">
                {(stats.hallucination_rate * 100).toFixed(1)}%
              </p>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-semibold mb-2">Top Hallucinated Features</h3>
            <ul className="space-y-1">
              {stats.top_features.map((f) => (
                <li key={f.feature} className="flex justify-between">
                  <span>{f.feature}</span>
                  <span className="text-gray-500">{f.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
