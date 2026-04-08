/**
 * AdminDashboard — trigga scrape-jobb och se pipeline-status (React island).
 */
import { useState, useEffect } from 'react';
import type { DashboardData, ScrapeJob } from '../lib/api';

interface Props { apiBase: string; }

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-600 bg-green-50',
  running: 'text-blue-600 bg-blue-50 animate-pulse',
  queued: 'text-yellow-600 bg-yellow-50',
  failed: 'text-red-600 bg-red-50',
};

function JobRow({ job }: { job: ScrapeJob }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-3">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[job.status] ?? 'text-gray-500 bg-gray-100'}`}>
          {job.status}
        </span>
        <span className="text-sm font-medium text-gray-700">{job.source_name}</span>
      </div>
      <div className="text-xs text-gray-400 text-right">
        {job.articles_new > 0 && (
          <span className="text-green-600 font-medium mr-2">+{job.articles_new} nya</span>
        )}
        <span>{job.articles_found} hittade</span>
      </div>
    </div>
  );
}

export default function AdminDashboard({ apiBase }: Props) {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [activeJobs, setActiveJobs] = useState<ScrapeJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState<string | null>(null);
  const [limit, setLimit] = useState(20);

  const loadDashboard = async () => {
    try {
      const [dash, srcs] = await Promise.all([
        fetch(`${apiBase}/admin/dashboard`).then(r => r.json()),
        fetch(`${apiBase}/admin/scrape-jobs/sources`).then(r => r.json()),
      ]);
      setDashboard(dash);
      setSources(srcs.sources ?? []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDashboard(); }, []);

  // Poll running jobs
  useEffect(() => {
    if (activeJobs.some(j => j.status === 'running' || j.status === 'queued')) {
      const timer = setTimeout(async () => {
        const updated = await Promise.all(
          activeJobs.map(j =>
            fetch(`${apiBase}/admin/scrape-jobs/${j.id}`).then(r => r.json())
          )
        );
        setActiveJobs(updated);
        if (updated.some(j => j.status === 'completed' || j.status === 'failed')) {
          loadDashboard();
        }
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [activeJobs]);

  const triggerScrape = async (source: string) => {
    setScraping(source);
    try {
      const res = await fetch(`${apiBase}/admin/scrape-jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_slug: source, limit }),
      });
      const job = await res.json();
      setActiveJobs(prev => [job, ...prev]);
    } finally {
      setScraping(null);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">Laddar dashboard...</div>;
  }

  return (
    <div className="space-y-8">
      {/* Stats */}
      {dashboard && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Artiklar', value: dashboard.counts.articles.toLocaleString('sv-SE') },
            { label: 'Organisationer', value: dashboard.counts.organizations },
            { label: 'Ämnen', value: dashboard.counts.topics },
            { label: 'Väntande noter', value: dashboard.counts.pending_community_notes },
          ].map(stat => (
            <div key={stat.label} className="bg-white border border-gray-200 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Scrape triggers */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900">Trigga scraping</h2>
            <div className="flex items-center gap-2 text-sm">
              <label className="text-gray-500">Limit:</label>
              <select
                value={limit}
                onChange={e => setLimit(Number(e.target.value))}
                className="border border-gray-200 rounded px-2 py-1 text-sm"
              >
                {[10, 20, 50, 100].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-2">
            {sources.map(source => (
              <button
                key={source}
                onClick={() => triggerScrape(source)}
                disabled={scraping === source}
                className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 hover:bg-blue-50 border border-gray-200 hover:border-blue-300 rounded-lg text-sm transition-all disabled:opacity-50 group"
              >
                <span className="font-medium text-gray-700 group-hover:text-blue-700">{source}</span>
                {scraping === source ? (
                  <span className="text-xs text-blue-500">Startar...</span>
                ) : (
                  <span className="text-xs text-gray-400 group-hover:text-blue-500">Kör →</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Job status */}
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Senaste jobb</h2>

          {activeJobs.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Aktiva</p>
              {activeJobs.map(j => <JobRow key={j.id} job={j} />)}
            </div>
          )}

          {dashboard?.recent_scrape_jobs && dashboard.recent_scrape_jobs.length > 0 ? (
            <div>
              {activeJobs.length > 0 && (
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2 mt-4">Historik</p>
              )}
              {dashboard.recent_scrape_jobs.map(j => <JobRow key={j.id} job={j} />)}
            </div>
          ) : (
            <p className="text-sm text-gray-400">Inga jobb körda ännu.</p>
          )}
        </div>
      </div>
    </div>
  );
}
