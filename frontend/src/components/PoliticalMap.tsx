/**
 * PoliticalMap — interaktiv V-H × GAL-TAN scatter (React island).
 * X: vänster–höger, Y: GAL (top) → TAN (bottom)
 */
import { useState } from 'react';
import type { Organization } from '../lib/api';
import { leaningToPosition, TYPE_LABELS } from '../lib/api';

interface Props { orgs: Organization[]; }

const GAL_TAN_POS: Record<string, number> = {
  'gal': 8, 'center-left': 30, 'center-gal': 25,
  'center': 50, 'neutral': 50,
  'center-right': 70, 'center-tan': 75, 'tan': 92,
};

function galTanPosition(v: string | null): number {
  return GAL_TAN_POS[v ?? 'center'] ?? 50;
}

const TYPE_COLORS: Record<string, string> = {
  newspaper: '#3b82f6',
  public_broadcaster: '#8b5cf6',
  online_news: '#06b6d4',
  magazine: '#0ea5e9',
  think_tank: '#f59e0b',
  political_party: '#ef4444',
  interest_org: '#f97316',
  government: '#6b7280',
  social_media: '#84cc16',
};

export default function PoliticalMap({ orgs }: Props) {
  const [hovered, setHovered] = useState<Organization | null>(null);
  const [filterType, setFilterType] = useState('');

  const filtered = filterType ? orgs.filter(o => o.type === filterType) : orgs;
  const types = [...new Set(orgs.map(o => o.type))];

  return (
    <div>
      {/* Filter */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setFilterType('')}
          className={`text-xs px-3 py-1 rounded-full border transition-colors ${!filterType ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-300 text-gray-600 hover:border-gray-500'}`}
        >
          Alla ({orgs.length})
        </button>
        {types.map(t => (
          <button
            key={t}
            onClick={() => setFilterType(t === filterType ? '' : t)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${filterType === t ? 'text-white border-transparent' : 'border-gray-300 text-gray-600 hover:border-gray-500'}`}
            style={filterType === t ? { backgroundColor: TYPE_COLORS[t] ?? '#6b7280' } : {}}
          >
            {TYPE_LABELS[t] ?? t} ({orgs.filter(o => o.type === t).length})
          </button>
        ))}
      </div>

      {/* Map */}
      <div className="relative bg-white border border-gray-200 rounded-2xl overflow-hidden" style={{ paddingTop: '60%' }}>
        {/* Axis labels */}
        <div className="absolute inset-0 pointer-events-none">
          {/* X axis */}
          <div className="absolute bottom-2 left-0 right-0 flex justify-between px-6 text-xs text-gray-400">
            <span>Vänster</span>
            <span>Center</span>
            <span>Höger</span>
          </div>
          {/* Y axis */}
          <div className="absolute left-2 top-0 bottom-6 flex flex-col justify-between py-2 text-xs text-gray-400">
            <span>GAL</span>
            <span>TAN</span>
          </div>
          {/* Grid lines */}
          <div className="absolute inset-0" style={{ left: '5%', right: '3%', top: '3%', bottom: '18px' }}>
            <div className="absolute left-1/2 top-0 bottom-0 border-l border-dashed border-gray-100" />
            <div className="absolute top-1/2 left-0 right-0 border-t border-dashed border-gray-100" />
          </div>
        </div>

        {/* Org bubbles */}
        <div className="absolute inset-0" style={{ left: '5%', right: '3%', top: '3%', bottom: '18px' }}>
          {filtered.map(org => {
            const x = leaningToPosition(org.political_leaning);
            const y = galTanPosition(org.gal_tan_position);
            const color = TYPE_COLORS[org.type] ?? '#6b7280';
            const isHovered = hovered?.slug === org.slug;

            return (
              <a
                key={org.slug}
                href={`/sources/${org.slug}`}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 transition-all"
                style={{ left: `${x}%`, top: `${y}%`, zIndex: isHovered ? 10 : 1 }}
                onMouseEnter={() => setHovered(org)}
                onMouseLeave={() => setHovered(null)}
              >
                <div
                  className={`rounded-full border-2 border-white shadow transition-all cursor-pointer ${isHovered ? 'scale-150' : 'hover:scale-125'}`}
                  style={{
                    width: '12px', height: '12px',
                    backgroundColor: color,
                    opacity: filterType && org.type !== filterType ? 0.15 : 0.85,
                  }}
                />
                {isHovered && (
                  <div className="absolute left-1/2 bottom-full mb-2 -translate-x-1/2 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 whitespace-nowrap shadow-lg pointer-events-none z-20">
                    <div className="font-medium">{org.name}</div>
                    <div className="text-gray-400">{TYPE_LABELS[org.type] ?? org.type}</div>
                    <div className="text-gray-300">{org.political_leaning} · {org.gal_tan_position}</div>
                  </div>
                )}
              </a>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-3">
        {types.map(t => (
          <div key={t} className="flex items-center gap-1.5 text-xs text-gray-500">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: TYPE_COLORS[t] ?? '#6b7280' }} />
            {TYPE_LABELS[t] ?? t}
          </div>
        ))}
      </div>
    </div>
  );
}
