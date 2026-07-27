"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase";
import { getAnalyticsSummary } from "@/lib/api";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

interface RecentQuestion {
  question: string;
  was_answered_confidently: boolean;
  created_at: string;
  latency_ms: number | null;
}

interface AnalyticsSummary {
  total_queries: number;
  confident_count: number;
  punted_count: number;
  confident_pct: number;
  recent_questions: RecentQuestion[];
}

const COLORS = {
  confident: "hsl(160, 70%, 45%)",
  punted: "hsl(25, 90%, 55%)",
};

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { name: string; value: number }[] }) => {
  if (active && payload?.length) {
    return (
      <div className="bg-surface-elevated border border-surface-border rounded-xl px-4 py-3 text-sm shadow-xl">
        <p className="font-semibold text-white">{payload[0].name}</p>
        <p className="text-gray-300">{payload[0].value} queries</p>
      </div>
    );
  }
  return null;
};

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: string }) {
  return (
    <div className="stat-card animate-slide-up">
      <p className="text-gray-500 text-xs font-medium uppercase tracking-wider">{label}</p>
      <p className={`text-3xl font-bold ${accent || "text-white"}`}>{value}</p>
      {sub && <p className="text-gray-500 text-xs">{sub}</p>}
    </div>
  );
}

// Group recent questions into hourly buckets for bar chart
function buildActivityData(questions: RecentQuestion[]) {
  const buckets: Record<string, number> = {};
  questions.forEach((q) => {
    const hour = new Date(q.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric" });
    buckets[hour] = (buckets[hour] ?? 0) + 1;
  });
  return Object.entries(buckets)
    .slice(-12)
    .map(([hour, count]) => ({ hour, count }));
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data: s }) => setToken(s.session?.access_token ?? null));
  }, []);

  useEffect(() => {
    if (!token) return;
    getAnalyticsSummary(token)
      .then(setData)
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return (
    <div className="flex items-center justify-center h-full text-gray-500 p-20">
      <svg className="w-6 h-6 animate-spin mr-3" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading analytics…
    </div>
  );

  if (!data) return null;

  const pieData = [
    { name: "Answered confidently", value: data.confident_count },
    { name: "Punted to HR/IT", value: data.punted_count },
  ];

  const activityData = buildActivityData(data.recent_questions);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-gray-400 mt-1 text-sm">
          Understand what your employees are asking — and where your documentation has gaps.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Queries" value={data.total_queries} />
        <StatCard
          label="Confident Answers"
          value={`${data.confident_pct}%`}
          sub={`${data.confident_count} queries`}
          accent="text-emerald-400"
        />
        <StatCard
          label="Punted to HR/IT"
          value={data.punted_count}
          sub="documentation gaps"
          accent="text-amber-400"
        />
        <StatCard
          label="Avg Latency"
          value={
            data.recent_questions.length
              ? `${Math.round(data.recent_questions.reduce((s, q) => s + (q.latency_ms ?? 0), 0) / data.recent_questions.length)}ms`
              : "—"
          }
          sub="end-to-end"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Confidence Pie */}
        <div className="card p-6">
          <h2 className="font-semibold text-white mb-1">Answer Confidence</h2>
          <p className="text-gray-500 text-xs mb-6">
            High "punted" rate = gaps in your documentation
          </p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? COLORS.confident : COLORS.punted} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Legend */}
          <div className="flex justify-center gap-6 mt-2">
            {pieData.map((entry, i) => (
              <div key={entry.name} className="flex items-center gap-2 text-sm">
                <span className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: i === 0 ? COLORS.confident : COLORS.punted }} />
                <span className="text-gray-400">{entry.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Activity Bar */}
        <div className="card p-6">
          <h2 className="font-semibold text-white mb-1">Query Activity</h2>
          <p className="text-gray-500 text-xs mb-6">Queries per hour (last 12 periods)</p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={activityData} margin={{ left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 14%, 22%)" />
                <XAxis dataKey="hour" tick={{ fill: "hsl(220, 9%, 46%)", fontSize: 10 }} />
                <YAxis tick={{ fill: "hsl(220, 9%, 46%)", fontSize: 10 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(222, 18%, 14%)",
                    border: "1px solid hsl(222, 14%, 22%)",
                    borderRadius: "12px",
                    color: "white",
                  }}
                />
                <Bar dataKey="count" fill="hsl(222, 68%, 50%)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Questions Table */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-surface-border">
          <h2 className="font-semibold text-white">Recent Questions</h2>
          <p className="text-gray-500 text-xs mt-0.5">Last 50 queries across your organization</p>
        </div>
        <div className="divide-y divide-surface-border">
          {data.recent_questions.length === 0 ? (
            <div className="text-center py-12 text-gray-500">No queries yet — share the chat with your team!</div>
          ) : (
            data.recent_questions.map((q, i) => (
              <div key={i} id={`query-row-${i}`}
                   className="flex items-start gap-4 px-6 py-4 hover:bg-surface-elevated/50 transition-colors">
                <div className="shrink-0 mt-0.5">
                  {q.was_answered_confidently ? (
                    <div className="w-6 h-6 rounded-full bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center">
                      <svg className="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  ) : (
                    <div className="w-6 h-6 rounded-full bg-amber-500/15 border border-amber-500/25 flex items-center justify-center">
                      <svg className="w-3 h-3 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M12 8v4m0 4h.01" />
                      </svg>
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm">{q.question}</p>
                  <p className="text-gray-500 text-xs mt-0.5">
                    {new Date(q.created_at).toLocaleString()}
                    {q.latency_ms ? ` · ${q.latency_ms}ms` : ""}
                  </p>
                </div>
                {!q.was_answered_confidently && (
                  <span className="badge-failed shrink-0">Gap</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
