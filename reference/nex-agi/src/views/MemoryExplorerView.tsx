import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  HardDrive, Search, SearchCode, FolderKanban, Bookmark, 
  Trash2, Pin, ShieldCheck, Eye, EyeOff, Bot, Sliders, LayoutGrid 
} from 'lucide-react';

interface Memory {
  id: string;
  agentId: string;
  category: 'fact' | 'experience' | 'learning' | 'summary';
  text: string;
  isPrivate: boolean;
  isPinned: boolean;
  timestamp: string;
}

export function MemoryExplorerView() {
  const [selectedAgent, setSelectedAgent] = useState<string>('architect');
  const [activeCategory, setActiveCategory] = useState<'all' | 'fact' | 'experience' | 'learning' | 'summary'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const [memories, setMemories] = useState<Memory[]>([
    { id: 'm1', agentId: 'architect', category: 'fact', text: 'Prefer pn-counters over central locks for 10M RPS workloads', isPrivate: false, isPinned: true, timestamp: '1 hour ago' },
    { id: 'm2', agentId: 'architect', category: 'experience', text: 'Encountered Redis cluster division timeout under 85% concurrent test runs', isPrivate: true, isPinned: false, timestamp: '3 hours ago' },
    { id: 'm3', agentId: 'reviewer', category: 'learning', text: 'Single Point of Failure risks always emerge in distributed design drafts within multi-master configurations', isPrivate: false, isPinned: true, timestamp: '1 day ago' },
    { id: 'm4', agentId: 'reviewer', category: 'summary', text: 'Reviewer session 18 checklist: prioritize robust cache eviction keys over database disk persists', isPrivate: false, isPinned: false, timestamp: 'Yesterday' },
    { id: 'm5', agentId: 'qa', category: 'fact', text: 'Strict type safety checks reduce boundary failures by 40% across heterogenous channels', isPrivate: true, isPinned: false, timestamp: '2 days ago' }
  ]);

  // Filters
  const filtered = memories.filter(m => {
    const matchesAgent = m.agentId === selectedAgent;
    const matchesCat = activeCategory === 'all' || m.category === activeCategory;
    const matchesQuery = m.text.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesAgent && matchesCat && matchesQuery;
  });

  const togglePin = (id: string) => {
    setMemories(prev => prev.map(m => m.id === id ? { ...m, isPinned: !m.isPinned } : m));
  };

  const deleteMemory = (id: string) => {
    setMemories(prev => prev.filter(m => m.id !== id));
  };

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-8 space-y-6 text-stone-300">
      
      {/* HEADER OVERVIEW */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-white/10 pb-4 gap-4">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981]">EPISODIC LOGS</p>
          <h2 className="text-xl font-sans font-black text-white tracking-tight mt-1">Multi-Agent Cognitive Memory Explorer</h2>
        </div>
      </div>

      {/* AGENT DRILL DOWN CONTROL RAIL */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between bg-neutral-900 border border-white/10 p-3 rounded-2xl">
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          {[
            { id: 'architect', label: 'Architect Cognition' },
            { id: 'reviewer', label: 'Strict Auditor' },
            { id: 'qa', label: 'Pedantic QA' }
          ].map((agent) => (
            <button
              key={agent.id}
              onClick={() => setSelectedAgent(agent.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all cursor-pointer whitespace-nowrap ${
                selectedAgent === agent.id ? 'bg-white/5 text-white' : 'text-zinc-500'
              }`}
            >
              {agent.label}
            </button>
          ))}
        </div>

        {/* Categories toggler */}
        <div className="flex items-center gap-1">
          {[
            { id: 'all', label: 'All Logged' },
            { id: 'fact', label: 'Facts' },
            { id: 'experience', label: 'Experiences' },
            { id: 'summary', label: 'Summaries' }
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id as any)}
              className={`px-2.5 py-1 text-[9.5px] font-bold uppercase rounded-md transition-all cursor-pointer ${
                activeCategory === cat.id ? 'text-[#10b981]' : 'text-zinc-550'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* SEARCH AND DRILL MEMORIES FIELD */}
      <div className="flex items-center gap-3 bg-neutral-900/60 border border-white/10 rounded-xl px-4 py-2">
        <Search className="w-4 h-4 text-zinc-500 shrink-0" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={`Search semantic facts or learnings inside ${selectedAgent}...`}
          className="flex-1 bg-transparent text-xs text-stone-200 placeholder-zinc-500 focus:outline-none"
        />
      </div>

      {/* MEMORY ITEMS CONTAINER */}
      <div className="space-y-3 min-h-[300px]">
        <AnimatePresence mode="popLayout">
          {filtered.length > 0 ? (
            filtered.map((mem) => (
              <motion.div
                key={mem.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="p-5 rounded-2xl bg-[#09090b]/80 border border-white/15 flex items-start justify-between gap-4 group hover:border-[#10b981]/25 transition-all text-xs"
              >
                <div className="space-y-2">
                  <div className="flex items-center gap-2 font-mono text-[9px]">
                    <span className="px-2 py-0.5 bg-neutral-900 rounded border border-white/5 text-zinc-400 capitalize tracking-wider">{mem.category}</span>
                    <span className="text-zinc-650">•</span>
                    <span className="text-zinc-500">{mem.timestamp}</span>
                    
                    {/* Public or shared indicator */}
                    <span className="text-zinc-650">•</span>
                    <div className="flex items-center gap-1 text-zinc-500">
                      {mem.isPrivate ? (
                        <>
                          <EyeOff className="w-3 h-3 text-red-400" />
                          <span>Private</span>
                        </>
                      ) : (
                        <>
                          <Eye className="w-3 h-3 text-emerald-400" />
                          <span>Shared</span>
                        </>
                      )}
                    </div>
                  </div>

                  <p className="font-sans text-stone-200 leading-relaxed font-normal">{mem.text}</p>
                </div>

                {/* Actions (Delete and Pin/Unpin) */}
                <div className="flex items-center gap-1.5 opacity-40 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => togglePin(mem.id)}
                    className={`p-1.5 rounded-lg border hover:bg-white/5 transition cursor-pointer ${
                      mem.isPinned ? 'border-[#10b981]/30 text-[#10b981]' : 'border-transparent text-zinc-500'
                    }`}
                    title={mem.isPinned ? "Unpin memory block" : "Pin core memory block"}
                  >
                    <Pin className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => deleteMemory(mem.id)}
                    className="p-1.5 rounded-lg text-zinc-500 hover:text-red-400 border border-transparent hover:border-red-400/20 hover:bg-red-400/5 transition cursor-pointer"
                    title="Evict memory block from cache"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </motion.div>
            ))
          ) : (
            <motion.div
              layout
              className="p-12 rounded-2xl border border-dashed border-white/10 text-center flex flex-col items-center justify-center font-mono text-zinc-500 text-xs py-16"
            >
              <SearchCode className="w-8 h-8 mb-2 text-zinc-650" />
              <p className="uppercase tracking-wider font-bold">No Match Memories Found</p>
              <p className="text-[10px] text-zinc-650 mt-1">Refine filters or state-query strings to scan cognitive nodes.</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
