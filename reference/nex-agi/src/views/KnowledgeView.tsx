import { useState } from 'react';
import { motion } from 'motion/react';
import { 
  HardDrive, Search, Filter, ShieldAlert, CheckCircle2, 
  RotateCw, Plus, FileCode, Database, RefreshCw, AlertTriangle 
} from 'lucide-react';

interface KnowledgeSource {
  id: string;
  name: string;
  type: string;
  size: string;
  status: 'indexed' | 'syncing' | 'failed';
  team: string;
  lastUpdated: string;
}

export function KnowledgeView() {
  const [sources, setSources] = useState<KnowledgeSource[]>([
    { id: 'k1', name: 'rate_limiting_algorithms.pdf', type: 'PDF Document', size: '1.2 MB', status: 'indexed', team: 'Elite Infrastructure', lastUpdated: '1 hour ago' },
    { id: 'k2', name: 'gossip_mesh_topology.docs', type: 'Google Doc', size: '18 KB', status: 'indexed', team: 'Elite Infrastructure', lastUpdated: '3 hours ago' },
    { id: 'k3', name: 'cache_eviction_strategy.json', type: 'JSON Array', size: '124 KB', status: 'indexed', team: 'Elite Infrastructure', lastUpdated: 'Yesterday' },
    { id: 'k4', name: 'client_api_handshake_specs.md', type: 'Markdown File', size: '42 KB', status: 'syncing', team: 'Client Experience', lastUpdated: 'Syncing now' },
    { id: 'k5', name: 'legacy_v1_obsolete.txt', type: 'Text Log', size: '512 KB', status: 'failed', team: 'Client Experience', lastUpdated: '2 days ago' }
  ]);

  const [searchQuery, setSearchQuery] = useState('');

  const filtered = sources.filter(s => 
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.team.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-8 space-y-6 text-stone-300">
      
      {/* HEADER SUMMARY */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-white/10 pb-4 gap-4">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981]">VECTOR DATABASES</p>
          <h2 className="text-xl font-sans font-black text-white tracking-tight mt-1">Global Knowledge Rollup</h2>
        </div>

        <div className="flex items-center gap-2">
          <button className="px-4 py-2 bg-white/5 hover:bg-white/10 pr-4 text-xs font-bold uppercase tracking-wider rounded-xl border border-white/10 flex items-center gap-2 cursor-pointer">
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Sync Sources</span>
          </button>
        </div>
      </div>

      {/* WARNING NOTIFICATION REGARDING EMBEDDING DIMENSIONS (pgvector warning) */}
      <div className="p-4 rounded-xl bg-orange-500/5 border border-orange-500/20 flex gap-3 text-xs leading-normal">
        <AlertTriangle className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-bold text-white">RATIONALE FOR INDEX REINDEXING (pgvector / Dimension Limit Lock)</p>
          <p className="text-zinc-400 font-mono text-[10px]">
            WARNING: Changing the active team embedding models (e.g. from text-embedding-3 to gemini-embed) alters the vector outputs (e.g., 1536 vs 768 dimensions). This mismatch violates spatial constraints and will render pgvector query indexes unsearchable. A complete reindex sequence is required upon any profile updates.
          </p>
        </div>
      </div>

      {/* SEARCH AND FILTERS */}
      <div className="flex items-center gap-3 bg-neutral-900 border border-white/10 rounded-xl px-4 py-2">
        <Search className="w-4 h-4 text-zinc-500 shrink-0" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filter documents across scopes or specialist files..."
          className="flex-1 bg-transparent text-xs text-stone-200 placeholder-zinc-500 focus:outline-none focus:ring-0"
        />
      </div>

      {/* SOURCES GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((src) => (
          <div
            key={src.id}
            className="p-5 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between h-40 relative overflow-hidden group hover:border-[#10b981]/30 transition-all"
          >
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <span className="text-[8.5px] px-2 py-0.5 bg-white/5 border border-white/5 rounded font-mono text-zinc-500 uppercase">{src.type}</span>
                <h4 className="text-white font-bold text-xs truncate max-w-[180px] pt-1">{src.name}</h4>
              </div>

              {src.status === 'indexed' && <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 text-[8.5px] font-bold font-mono rounded">INDEXED</span>}
              {src.status === 'syncing' && <span className="px-2 py-0.5 bg-teal-500/10 border border-teal-500/25 text-teal-400 text-[8.5px] font-bold font-mono rounded animate-pulse">SYNCING</span>}
              {src.status === 'failed' && <span className="px-2 py-0.5 bg-red-500/10 border border-red-500/25 text-red-400 text-[8.5px] font-bold font-mono rounded">FAILED</span>}
            </div>

            <div className="pt-4 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-zinc-500">
              <div>
                <p className="tracking-wider uppercase text-[8.5px] text-zinc-650">Scope Team</p>
                <p className="text-zinc-400 mt-0.5">{src.team}</p>
              </div>
              <div className="text-right">
                <p className="tracking-wider uppercase text-[8.5px] text-zinc-650">Storage Vol</p>
                <p className="text-zinc-400 mt-0.5">{src.size}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
