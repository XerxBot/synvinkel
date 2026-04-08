/**
 * SearchPage — interaktiv sökvy (React island).
 * Hämtar artiklar från /export/articles med live-filtrering.
 */
import { useState, useEffect, useCallback } from 'react';
import type { Article, Organization } from '../lib/api';
import { formatDate, formatSentiment, LEANING_LABELS } from '../lib/api';

interface Props {
  apiBase: string;
  sources: Organization[];
}

const TOPICS = [
  'ekonomi', 'klimat', 'migration', 'kriminalitet', 'arbetsmarknad',
  'skola', 'sjukvård', 'försvar', 'demokrati', 'bostäder',
];

function SentimentPill({ score }: { score: number | null }) {
  if (score === null) return null;
  const s = formatSentiment(score);
  const cls = score > 0.3 ? 'bg-green-100 text-green-700'
    : score < -0.3 ? 'bg-red-100 text-red-700'
    : 'bg-gray-100 text-gray-600';
  return <span className={`text-xs px-2 py-0.5 rounded-full ${cls}`}>{s}</span>;
}

function ArticleRow({ article }: { article: Article }) {
  return (
    <a href={`/articles/${article.id}`}
       className="flex flex-col sm:flex-row gap-3 p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-gray-300 transition-all group">
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-start gap-2 mb-1">
          <h3 className="font-medium text-gray-900 group-hover:text-blue-700 transition-colors line-clamp-2 leading-snug">
            {article.title}
          </h3>
          {article.article_type && (
            <span className="shrink-0 text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">
              {article.article_type.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
          {article.data_source && (
            <span className="text-blue-500 font-medium">{article.data_source}</span>
          )}
          <span>{formatDate(article.published_at)}</span>
          <SentimentPill score={article.sentiment_score} />
          {article.topics?.slice(0, 3).map(t => (
            <span key={t} className="bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{t}</span>
          ))}
        </div>
      </div>
    </a>
  );
}

export default function SearchPage({ apiBase, sources }: Props) {
  const [query, setQuery] = useState('');
  const [topicFilter, setTopicFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const LIMIT = 20;

  const fetchArticles = useCallback(async (off = 0) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(LIMIT), offset: String(off) });
      if (topicFilter) params.set('topic', topicFilter);
      if (sourceFilter) params.set('source_slug', sourceFilter);

      const res = await fetch(`${apiBase}/export/articles?${params}`);
      if (!res.ok) return;
      const data = await res.json();
      const fetched: Article[] = data.articles ?? [];

      // Client-side title filter if query entered
      const filtered = query
        ? fetched.filter(a => a.title.toLowerCase().includes(query.toLowerCase()))
        : fetched;

      setArticles(off === 0 ? filtered : prev => [...prev, ...filtered]);
      setTotal(data.meta.total_returned);
    } finally {
      setLoading(false);
    }
  }, [apiBase, topicFilter, sourceFilter, query]);

  useEffect(() => {
    setOffset(0);
    fetchArticles(0);
  }, [topicFilter, sourceFilter]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    fetchArticles(0);
  };

  return (
    <div>
      {/* Search form */}
      <form onSubmit={handleSearch} className="bg-white border border-gray-200 rounded-2xl p-5 mb-6 shadow-sm">
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Sök artiklar, rapporter, anföranden..."
            className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            type="submit"
            className="px-5 py-2.5 bg-navy-900 text-white rounded-xl text-sm font-medium hover:bg-navy-800 transition-colors"
            style={{ backgroundColor: '#1e293b' }}
          >
            Sök
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          <select
            value={topicFilter}
            onChange={e => setTopicFilter(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            <option value="">Alla ämnen</option>
            {TOPICS.map(t => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>

          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            <option value="">Alla källor</option>
            {sources.map(s => (
              <option key={s.slug} value={s.slug}>{s.name}</option>
            ))}
          </select>

          {(topicFilter || sourceFilter || query) && (
            <button
              type="button"
              onClick={() => { setTopicFilter(''); setSourceFilter(''); setQuery(''); }}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2 rounded-lg border border-gray-200"
            >
              Rensa filter
            </button>
          )}
        </div>
      </form>

      {/* Results */}
      {loading && articles.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <div className="animate-spin w-6 h-6 border-2 border-gray-300 border-t-blue-500 rounded-full mx-auto mb-3"></div>
          Laddar...
        </div>
      ) : articles.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-lg mb-2">Inga artiklar hittades</p>
          <p className="text-sm">Prova att justera filtren eller scrapa in mer data via Admin.</p>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-500 mb-4">
            {total !== null ? `${total} artiklar` : `${articles.length} artiklar`}
            {topicFilter && ` i ämnet "${topicFilter}"`}
            {sourceFilter && ` från "${sourceFilter}"`}
          </p>
          <div className="space-y-3">
            {articles.map(a => <ArticleRow key={a.id} article={a} />)}
          </div>
          {articles.length >= LIMIT && (
            <button
              onClick={() => { const next = offset + LIMIT; setOffset(next); fetchArticles(next); }}
              disabled={loading}
              className="w-full mt-4 py-3 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-xl hover:bg-white transition-all disabled:opacity-50"
            >
              {loading ? 'Laddar...' : 'Ladda fler'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
