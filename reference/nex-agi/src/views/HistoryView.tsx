import { useState, useEffect } from 'react';
import { Session } from '../types';
import { History, Trash2, ChevronRight, HardDrive, Clock, BadgeCheck, FileCode, Search, Filter } from 'lucide-react';
import { motion } from 'motion/react';

interface HistoryViewProps {
  onLoadSession: (presetId: string) => void;
}

export function HistoryView({ onLoadSession }: HistoryViewProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  useEffect(() => {
    // Read from localStorage
    const saved = localStorage.getItem('nexagi_sessions');
    if (saved) {
      try {
        setSessions(JSON.parse(saved));
      } catch (e) {
        console.error(e);
      }
    } else {
      // Seed initial mock sessions so history is highly authentic and beautiful on first visit!
      const initialMockSessions: Session[] = [
        {
          id: 'seeded-1',
          goal: 'Design a distributed rate-limiter for 10M RPS',
          currentRound: 5,
          maxRounds: 5,
          consensusPct: 100,
          status: 'completed',
          timestamp: '2026-06-18 10:45:12',
          agentsPreset: 'Elite Infrastructure Group',
          messages: [],
          files: [
            { filename: 'rate_limiter.py', code: '', language: 'python' },
            { filename: 'cluster_sync.rs', code: '', language: 'rust' },
          ],
        },
        {
          id: 'seeded-2',
          goal: 'Establish an active-active transactional key-value replication pipeline',
          currentRound: 5,
          maxRounds: 5,
          consensusPct: 100,
          status: 'completed',
          timestamp: '2026-06-18 08:30:00',
          agentsPreset: 'High Availability Engineers',
          messages: [],
          files: [
            { filename: 'replication.go', code: '', language: 'golang' },
          ],
        },
      ];
      setSessions(initialMockSessions);
      localStorage.setItem('nexagi_sessions', JSON.stringify(initialMockSessions));
    }
  }, []);

  const handleClear = () => {
    localStorage.removeItem('nexagi_sessions');
    setSessions([]);
  };

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) || null;

  return (
    <motion.div
      id="session-history-container"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.35 }}
      className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-6 md:py-10 grid grid-cols-1 lg:grid-cols-12 gap-8 text-stone-300"
    >
      <div className="col-span-12 flex items-center justify-between border-b border-[#27272a]/50 pb-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white mb-2">Saved Session Catalog</h2>
          <p className="text-zinc-400 text-xs md:text-sm max-w-lg leading-relaxed">
            Review previous multi-agent synthesis loops. Load any prior session history to inspect completed blackboard files or replay active debate coordinates.
          </p>
        </div>

        {sessions.length > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-1 px-3 py-2 border border-rose-900/40 hover:border-rose-900/80 bg-rose-950/15 hover:bg-rose-950/30 text-rose-450 text-xs rounded-lg transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear Catalog</span>
          </button>
        )}
      </div>

      {sessions.length === 0 ? (
        <div className="col-span-12 py-20 text-center flex flex-col items-center justify-center text-zinc-500">
          <History className="w-12 h-12 opacity-15 mb-4 animate-spin" style={{ animationDuration: '8s' }} />
          <h4 className="text-zinc-400 font-semibold text-sm mb-1">Catalog Registry Clean</h4>
          <p className="text-xs text-zinc-600 max-w-xs mt-1">
            Deploy an active agent mesh session in the Workspace. Synthesized outcomes populate here automatically.
          </p>
        </div>
      ) : (
        <>
          {/* SESSIONS LIST PANEL */}
          <div className="lg:col-span-7 space-y-4">
            <label className="text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest pl-1 block mb-2">Previous Runs</label>
            
            {sessions.map((sess) => {
              const belongs = sess.id === selectedSessionId;
              return (
                <div
                  id={`history-card-item-${sess.id}`}
                  key={sess.id}
                  onClick={() => setSelectedSessionId(sess.id)}
                  className={`p-4 rounded border transition-all cursor-pointer group ${
                    belongs
                      ? 'bg-white/5 border-white/20 text-white shadow-md'
                      : 'bg-[#111113]/40 text-zinc-405 border-white/5 hover:border-white/10'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <h4 className="font-extrabold text-xs sm:text-sm tracking-tight text-zinc-200 leading-relaxed group-hover:text-white transition-colors">
                      {sess.goal}
                    </h4>
                    <span className="shrink-0 flex items-center gap-1 text-[8px] font-mono font-bold text-white bg-white/5 border border-white/15 px-2 py-0.5 rounded uppercase">
                      <BadgeCheck className="w-3 h-3 text-white" />
                      <span>{sess.consensusPct}% τ</span>
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-zinc-505 font-mono mt-3">
                    <span className="flex items-center gap-1 text-[9.5px]">
                      <Clock className="w-3.5 h-3.5 text-zinc-600" />
                      <span>{sess.timestamp}</span>
                    </span>
                    <span>•</span>
                    <span>Group: {sess.agentsPreset}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <FileCode className="w-3.5 h-3.5 text-zinc-650" />
                      <span>{sess.files.length} flat outputs</span>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* SESSIONS DETAIL REPORT INSPECTOR */}
          <div className="lg:col-span-5">
            <label className="text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest pl-1 block mb-3">Synthesis Abstract</label>
            {selectedSession ? (
              <div className="artistic-pane rounded-xl p-5 space-y-5 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
                <div className="border-b border-white/10 pb-3">
                  <h3 className="text-zinc-200 font-extrabold text-xs uppercase tracking-wider leading-relaxed mb-1">{selectedSession.goal}</h3>
                  <p className="text-[10px] text-stone-500 font-mono italic">ID Ref: {selectedSession.id}</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <h5 className="text-[9px] uppercase font-bold text-zinc-500 font-mono tracking-widest mb-1.5">Consensus Path Parameters</h5>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="bg-white/5 p-2.5 rounded border border-white/10 font-mono">
                        <p className="text-[9px] text-zinc-505">Agreement Result</p>
                        <p className="text-white font-extrabold mt-1 text-[11px]">{selectedSession.consensusPct}% achieved</p>
                      </div>
                      <div className="bg-white/5 p-2.5 rounded border border-white/10 font-mono">
                        <p className="text-[9px] text-zinc-505">Debate Rounds</p>
                        <p className="text-zinc-305 font-bold mt-1 text-[11px]">{selectedSession.currentRound} / {selectedSession.maxRounds} cycles</p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h5 className="text-[9px] uppercase font-bold text-zinc-500 font-mono tracking-widest mb-1.5">Synthesized File Map</h5>
                    <div className="space-y-1.5 font-mono text-[10.5px]">
                      {selectedSession.files.map((file) => (
                        <div key={file.filename} className="p-2.5 bg-black/45 border border-white/5 rounded flex items-center justify-between text-zinc-350">
                          <div className="flex items-center gap-1.55">
                            <FileCode className="w-3.5 h-3.5 text-zinc-500" />
                            <span>{file.filename}</span>
                          </div>
                          <span className="text-[9.5px] text-zinc-650">{file.language} format</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-white/10 mt-2 flex justify-end">
                  <button
                    onClick={() => onLoadSession(selectedSession.id === 'seeded-2' ? 'multi-master-db' : 'rate-limiter')}
                    className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-zinc-200 text-black font-black uppercase text-[10px] tracking-wider rounded transition-all shadow-[0_4px_20px_rgba(255,255,255,0.15)] active:scale-95 cursor-pointer"
                  >
                    <span>Load into Workspace</span>
                    <ChevronRight className="w-3.5 h-3.5 shrink-0" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="artistic-pane rounded-xl p-8 text-center text-zinc-500">
                <Search className="w-8 h-8 opacity-20 mb-2 mx-auto" />
                <p className="text-xs">No active abstract selected</p>
                <p className="text-[10px] text-zinc-650 mt-1">Select any saved run on the left to audit consensus indices</p>
              </div>
            )}
          </div>
        </>
      )}
    </motion.div>
  );
}
