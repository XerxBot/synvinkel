/**
 * FactCheckBlock — visar faktakontrollresultat + admin-trigger.
 * React island: client:load
 */
import { useState, useEffect } from 'react';

interface Claim {
  text: string;
  attributed: boolean;
  source_cited: string | null;
  verifiable: boolean;
}

interface FactCheck {
  id: string;
  model_used: string;
  claims: Claim[];
  sourcing_score: number | null;
  framing_notes: string | null;
  bias_indicators: string[];
  vs_source_profile: string | null;
  summary: string | null;
  created_at: string;
}

interface Props {
  apiBase: string;
  articleId: string;
}

function SourcingBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-700 w-8">{pct}%</span>
    </div>
  );
}

export default function FactCheckBlock({ apiBase, articleId }: Props) {
  const [fc, setFc] = useState<FactCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const u = localStorage.getItem('sv_user');
    const t = localStorage.getItem('sv_token');
    if (u) {
      const user = JSON.parse(u);
      if (user.role === 'admin') { setIsAdmin(true); setToken(t); }
    }
    fetchFC();
  }, []);

  const fetchFC = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/articles/${articleId}/factcheck`);
      if (res.ok) setFc(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const triggerFC = async () => {
    if (!token) return;
    setRunning(true);
    setError('');
    try {
      const res = await fetch(`${apiBase}/admin/articles/${articleId}/factcheck`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail ?? 'Faktakontroll misslyckades');
      setFc(json);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  if (loading) return null;

  return (
    <div className="mt-8 pt-8 border-t border-gray-200">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-base">🔍</span>
          <h2 className="text-lg font-semibold text-gray-900">Faktakontroll</h2>
          {fc && (
            <span className="text-xs text-gray-400 font-normal">
              {fc.model_used} · {new Date(fc.created_at).toLocaleDateString('sv-SE')}
            </span>
          )}
        </div>
        {isAdmin && (
          <button
            onClick={triggerFC}
            disabled={running}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {running ? 'Analyserar…' : fc ? 'Kör om' : 'Faktakontrollera'}
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      {running && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 text-center">
          <p className="text-sm text-gray-500">Claude analyserar artikeln… (10–30 sekunder)</p>
        </div>
      )}

      {!running && !fc && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-sm text-gray-400">Ingen faktakontroll genomförd ännu.</p>
          {isAdmin && (
            <p className="text-xs text-gray-400 mt-1">Klicka "Faktakontrollera" för att starta analysen.</p>
          )}
        </div>
      )}

      {!running && fc && (
        <div className="space-y-5">
          {/* Summary */}
          {fc.summary && (
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
              <p className="text-sm text-blue-900 leading-relaxed">{fc.summary}</p>
            </div>
          )}

          {/* Sourcing score */}
          {fc.sourcing_score !== null && (
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Källhänvisningsgrad</p>
              <SourcingBar score={fc.sourcing_score} />
              <p className="text-xs text-gray-400 mt-1">
                {Math.round(fc.sourcing_score * 100)}% av faktapåståendena är källhänvisade
              </p>
            </div>
          )}

          {/* Claims */}
          {fc.claims.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                Faktapåståenden ({fc.claims.length})
              </p>
              <div className="space-y-2">
                {fc.claims.map((c, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                    <span className="shrink-0 mt-0.5">
                      {c.attributed ? '✅' : '⚠️'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-800">{c.text}</p>
                      {c.source_cited && (
                        <p className="text-xs text-gray-400 mt-0.5">Källa: {c.source_cited}</p>
                      )}
                      {!c.verifiable && (
                        <span className="inline-block text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded mt-1">
                          värdering
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Framing + bias */}
          {(fc.framing_notes || fc.bias_indicators.length > 0) && (
            <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
              {fc.framing_notes && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Språklig vinkling</p>
                  <p className="text-sm text-gray-700">{fc.framing_notes}</p>
                </div>
              )}
              {fc.bias_indicators.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Indikatorer</p>
                  <div className="flex flex-wrap gap-1.5">
                    {fc.bias_indicators.map((b, i) => (
                      <span key={i} className="text-xs bg-orange-50 text-orange-700 border border-orange-100 px-2 py-0.5 rounded-full">
                        {b}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* vs source profile */}
          {fc.vs_source_profile && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
              <p className="text-xs text-amber-700 uppercase tracking-wide mb-1">Jämfört med källprofil</p>
              <p className="text-sm text-amber-900">{fc.vs_source_profile}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
