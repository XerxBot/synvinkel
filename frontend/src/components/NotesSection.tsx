/**
 * NotesSection — Community Notes per artikel (React island).
 * Hämtar noter, visar dem, låter inloggade användare skriva + rösta.
 */
import { useState, useEffect } from 'react';

interface Note {
  id: string;
  article_id: string;
  note_type: string;
  content: string;
  evidence_urls: string[];
  verdict: string | null;
  status: string;
  upvotes: number;
  downvotes: number;
  helpful_score: number | null;
  user_vote: boolean | null;
  created_at: string;
}

interface User { id: string; display_name: string; role: string; }

interface Props { apiBase: string; articleId: string; }

const NOTE_TYPE_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  misleading:      { label: 'Vilseledande',    color: 'bg-red-100 text-red-700 border-red-200',    icon: '⚠️' },
  missing_context: { label: 'Saknar kontext',  color: 'bg-yellow-100 text-yellow-700 border-yellow-200', icon: '📋' },
  factual_error:   { label: 'Faktafel',        color: 'bg-orange-100 text-orange-700 border-orange-200', icon: '❌' },
  praise:          { label: 'Värt att lyfta',  color: 'bg-green-100 text-green-700 border-green-200',   icon: '✅' },
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('sv-SE', { year: 'numeric', month: 'short', day: 'numeric' });
}

function NoteCard({ note, onVote, currentUserId }: {
  note: Note;
  onVote: (noteId: string, up: boolean) => void;
  currentUserId: string | null;
}) {
  const type = NOTE_TYPE_LABELS[note.note_type] ?? { label: note.note_type, color: 'bg-gray-100 text-gray-700 border-gray-200', icon: '💬' };
  const isOwn = currentUserId === note.article_id; // can't self-vote anyway

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${type.color}`}>
          <span>{type.icon}</span> {type.label}
        </span>
        <span className="text-xs text-gray-400">{formatDate(note.created_at)}</span>
      </div>

      <p className="text-sm text-gray-800 leading-relaxed">{note.content}</p>

      {note.evidence_urls.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium">Källor:</p>
          {note.evidence_urls.map((url, i) => (
            <a key={i} href={url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-blue-600 hover:underline block truncate">
              {url}
            </a>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 pt-1 border-t border-gray-100">
        {currentUserId ? (
          <>
            <button
              onClick={() => onVote(note.id, true)}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                note.user_vote === true
                  ? 'bg-green-100 text-green-700 border-green-200'
                  : 'text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}
            >
              👍 {note.upvotes}
            </button>
            <button
              onClick={() => onVote(note.id, false)}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                note.user_vote === false
                  ? 'bg-red-100 text-red-700 border-red-200'
                  : 'text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}
            >
              👎 {note.downvotes}
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>👍 {note.upvotes}</span>
            <span>👎 {note.downvotes}</span>
          </div>
        )}
        {note.helpful_score !== null && (
          <span className="text-xs text-gray-400 ml-auto">
            {(note.helpful_score * 100).toFixed(0)}% hjälpsam
          </span>
        )}
      </div>
    </div>
  );
}

export default function NotesSection({ apiBase, articleId }: Props) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [form, setForm] = useState({ note_type: 'missing_context', content: '', evidence_url: '' });

  useEffect(() => {
    const t = localStorage.getItem('sv_token');
    const u = localStorage.getItem('sv_user');
    if (t && u) { setToken(t); setUser(JSON.parse(u)); }
    loadNotes();
  }, []);

  const loadNotes = async () => {
    setLoading(true);
    try {
      const headers: Record<string, string> = {};
      const t = localStorage.getItem('sv_token');
      if (t) headers['Authorization'] = `Bearer ${t}`;
      const res = await fetch(`${apiBase}/notes?article_id=${articleId}&status=approved`, { headers });
      if (res.ok) setNotes(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const handleVote = async (noteId: string, isUpvote: boolean) => {
    if (!token) return;
    const res = await fetch(`${apiBase}/notes/${noteId}/vote?is_upvote=${isUpvote}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const updated = await res.json();
      setNotes(prev => prev.map(n => n.id === noteId
        ? { ...n, ...updated, user_vote: n.user_vote === isUpvote ? null : isUpvote }
        : n
      ));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError('');
    try {
      const evidence_urls = form.evidence_url.trim() ? [form.evidence_url.trim()] : [];
      const res = await fetch(`${apiBase}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ article_id: articleId, note_type: form.note_type, content: form.content, evidence_urls }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(Array.isArray(json.detail) ? json.detail.map((d: any) => d.msg).join(', ') : json.detail);
      setShowForm(false);
      setForm({ note_type: 'missing_context', content: '', evidence_url: '' });
      // Visa pending-meddelande istället för att ladda om (noten är pending)
      alert('Din note är inskickad och granskas av moderatorer.');
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('sv_token');
    localStorage.removeItem('sv_user');
    setUser(null); setToken(null);
  };

  return (
    <section className="mt-8 pt-8 border-t border-gray-200">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Community Notes
          {notes.length > 0 && <span className="text-sm font-normal text-gray-400 ml-1">({notes.length})</span>}
        </h2>
        {user ? (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">{user.display_name}</span>
            <button onClick={() => setShowForm(!showForm)}
              className="text-xs px-3 py-1.5 bg-navy-900 text-white rounded-lg hover:opacity-90"
              style={{ backgroundColor: '#1e293b' }}>
              + Lägg till note
            </button>
            <button onClick={logout} className="text-xs text-gray-400 hover:text-gray-600">Logga ut</button>
          </div>
        ) : (
          <a href="/login" className="text-xs text-blue-600 hover:underline">
            Logga in för att bidra →
          </a>
        )}
      </div>

      {/* Create form */}
      {showForm && user && (
        <form onSubmit={handleSubmit} className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5 space-y-3">
          <div className="flex gap-2 flex-wrap">
            {Object.entries(NOTE_TYPE_LABELS).map(([key, val]) => (
              <button type="button" key={key}
                onClick={() => setForm(f => ({ ...f, note_type: key }))}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  form.note_type === key ? val.color : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                }`}>
                {val.icon} {val.label}
              </button>
            ))}
          </div>
          <textarea
            value={form.content}
            onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
            placeholder="Beskriv problemet eller tillägget. Var konkret och källhänvisa om möjligt. (min 20 tecken)"
            rows={4}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            required
          />
          <input
            type="url"
            value={form.evidence_url}
            onChange={e => setForm(f => ({ ...f, evidence_url: e.target.value }))}
            placeholder="Källlänk (valfritt)"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {formError && <p className="text-xs text-red-600">{formError}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={submitting}
              className="text-sm px-4 py-2 text-white rounded-lg disabled:opacity-50"
              style={{ backgroundColor: '#1e293b' }}>
              {submitting ? 'Skickar...' : 'Skicka note'}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="text-sm px-4 py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
              Avbryt
            </button>
          </div>
        </form>
      )}

      {/* Notes list */}
      {loading ? (
        <p className="text-sm text-gray-400 py-4">Laddar noter...</p>
      ) : notes.length > 0 ? (
        <div className="space-y-3">
          {notes.map(note => (
            <NoteCard key={note.id} note={note} onVote={handleVote} currentUserId={user?.id ?? null} />
          ))}
        </div>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 text-center">
          <p className="text-sm text-gray-400 mb-1">Inga godkända noter ännu för den här artikeln.</p>
          {!user && (
            <a href="/login" className="text-sm text-blue-600 hover:underline">
              Logga in och bidra →
            </a>
          )}
        </div>
      )}
    </section>
  );
}
