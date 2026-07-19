import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Users, Bot, HardDrive, Cpu, Terminal, Shield, 
  Layers, Zap, CheckCircle2, Server, Database, Cloud, Key, HelpCircle,
  Bell, Play, Pause, Trash2, ShieldAlert, Wifi, Activity, AlertTriangle
} from 'lucide-react';

interface ToastAlert {
  id: string;
  agent: string;
  action: string;
  status: 'completes' | 'critique' | 'error' | 'sync';
  time: string;
}

export function DashboardView() {
  const [selectedBackend, setSelectedBackend] = useState<'fastapi' | 'node' | 'firebase'>('fastapi');
  const [toasts, setToasts] = useState<ToastAlert[]>([
    { id: 't-init', agent: 'Orchestrating Router', action: 'Active cognition session started successfully', status: 'completes', time: '12:45 PM' }
  ]);
  const [simActive, setSimActive] = useState(true);

  // Sync recent alert journal with global custom events
  useEffect(() => {
    const handleGlobalAlert = (e: Event) => {
      const customEvent = e as CustomEvent<any>;
      if (customEvent.detail) {
        const { id, agent, action, status, time } = customEvent.detail;
        const mappedToast: ToastAlert = {
          id: id || `toast-${Date.now()}`,
          agent,
          action,
          status,
          time: time || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        };
        setToasts(prev => [mappedToast, ...prev].slice(0, 16));
      }
    };
    window.addEventListener('nexagi-notification-received' as any, handleGlobalAlert);
    return () => window.removeEventListener('nexagi-notification-received' as any, handleGlobalAlert);
  }, []);

  // Dispatch manual simulation actions to the global event flow
  const triggerToast = (agent: string, action: string, status: 'completes' | 'critique' | 'error' | 'sync') => {
    window.dispatchEvent(new CustomEvent('nexagi-new-alert', {
      detail: { agent, action, status }
    }));
  };

  const clearToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // Custom counts representing active state metrics
  const stats = [
    { label: 'Active Teams', value: '4', change: 'Ready', icon: Users, color: 'text-emerald-400' },
    { label: 'Specialist Agents', value: '18', change: '+3 new', icon: Bot, color: 'text-teal-400' },
    { label: 'Memories Captured', value: '1,842', change: '84.2 MB', icon: HardDrive, color: 'text-emerald-500' },
    { label: 'Consensus Rate', value: '94.8%', change: 'A+ Grade', icon: Cpu, color: 'text-green-400' },
  ];

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-8 space-y-10 text-stone-300">
      
      {/* HEADER SUMMARY */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-white/10 pb-6 gap-4">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981]">SYSTEM OVERVIEW</p>
          <h2 className="text-2xl font-sans font-black text-white tracking-tight mt-1">Autonomous Agent Control Room</h2>
        </div>
        <div className="flex items-center gap-2 bg-neutral-900/60 border border-white/10 px-3 py-1.5 rounded-lg text-xs font-mono text-zinc-400">
          <span className="w-2 h-2 rounded-full bg-[#10b981] animate-ping" />
          <span>MESH STATE: ACTIVE COGNITION</span>
        </div>
      </div>

      {/* STATS BENTO GRID */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="p-5 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between h-36 relative overflow-hidden group hover:border-[#10b981]/30 transition-all"
          >
            <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-all">
              <stat.icon className="w-24 h-24 stroke-[1.5]" />
            </div>
            
            <div className="flex items-center justify-between">
              <stat.icon className={`w-5 h-5 ${stat.color}`} />
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">{stat.change}</span>
            </div>

            <div className="mt-4">
              <p className="text-[11px] font-mono uppercase tracking-wider text-zinc-400">{stat.label}</p>
              <p className="text-2xl font-sans font-black text-white mt-1">{stat.value}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* MAIN TWO PANEL DETAILS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        
        {/* RECOMMENDED BACKEND ADVISOR (Answers prompt "suggest me options of the best backend as well") */}
        <div className="lg:col-span-8 p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[8.5px] rounded font-mono font-bold tracking-wider uppercase">ARCHITECTURAL DESIGN</span>
              <span className="text-zinc-650 font-mono text-xs">•</span>
              <p className="text-[10px] font-mono tracking-widest text-zinc-400 uppercase">Interactive Backend Adviser</p>
            </div>
            <h3 className="text-lg font-bold text-white mb-4">Select the Ideal Backend & Storage Strategy</h3>
            
            <p className="text-zinc-400 text-xs leading-relaxed mb-6">
              NEX AGI uses a multi-agent state machine. To build a production-ready application, select the backend configuration that best fits your scale, real-time sync needs, and memory database constraints.
            </p>

            {/* Backends Selection Toggles */}
            <div className="grid grid-cols-3 gap-2 mb-6">
              {[
                { id: 'fastapi', name: 'Python FASTAPI', desc: 'Best for RAG & AI', icon: Server },
                { id: 'node', name: 'Node.js Express', desc: 'Unified JS Stack', icon: Zap },
                { id: 'firebase', name: 'Google Firebase', desc: 'Serverless Realtime', icon: Database },
              ].map((b) => (
                <button
                  key={b.id}
                  onClick={() => setSelectedBackend(b.id as any)}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    selectedBackend === b.id 
                      ? 'bg-emerald-550/10 border-[#10b981] text-white' 
                      : 'bg-white/[0.02] border-white/5 text-zinc-400 hover:border-white/10 hover:bg-white/[0.04]'
                  }`}
                >
                  <b.icon className={`w-4 h-4 mb-1.5 ${selectedBackend === b.id ? 'text-[#10b981]' : 'text-zinc-400'}`} />
                  <p className="font-bold text-[11px] leading-tight tracking-wider uppercase">{b.name}</p>
                  <p className="text-[9px] text-zinc-500 mt-0.5">{b.desc}</p>
                </button>
              ))}
            </div>

            {/* Content per selected stack */}
            <AnimatePresence mode="wait">
              {selectedBackend === 'fastapi' && (
                <motion.div
                  key="fastapi"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="space-y-4 bg-white/[0.02] border border-white/5 rounded-xl p-4 text-xs font-mono"
                >
                  <div className="flex items-center justify-between text-[11px] text-[#10b981]">
                    <span className="font-bold">✓ OPTION A: Python + FastAPI + PostgreSQL (pgvector)</span>
                    <span className="px-2 py-0.5 bg-[#10b981]/10 text-[9px] rounded font-bold">RECOMMENDED FOR AGENTS</span>
                  </div>
                  <p className="text-zinc-400 text-[11px] leading-relaxed">
                    This stack is superior for Agentic platforms. LangChain, LlamaIndex, and native embedding drivers compile fastest here. pgvector handles structural cognitive memory vectors natively.
                  </p>
                  <div className="grid grid-cols-2 gap-4 text-[10px] text-zinc-500 pt-1">
                    <div>
                      <span className="block font-black text-zinc-400">Primary Database:</span>
                      PostgreSQL with <span className="text-[#10b981]">pgvector</span> extension
                    </div>
                    <div>
                      <span className="block font-black text-zinc-400">Embedding Engine:</span>
                      OpenAI text-embedding-3 or Gemini Embed
                    </div>
                  </div>
                </motion.div>
              )}

              {selectedBackend === 'node' && (
                <motion.div
                  key="node"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="space-y-4 bg-white/[0.02] border border-white/5 rounded-xl p-4 text-xs font-mono"
                >
                  <div className="flex items-center justify-between text-[11px] text-[#10b981]">
                    <span className="font-bold">✓ OPTION B: Node.js + Express + Drizzle / Prisma Schema</span>
                    <span className="px-2 py-0.5 bg-zinc-800 text-[9px] text-zinc-400 rounded font-bold">HIGH SPEED</span>
                  </div>
                  <p className="text-zinc-400 text-[11px] leading-relaxed">
                    Ideal when sharing models/validators between your frontend SPA and server backend easily. Runs beautifully inside serverless edge containers. Uses WebSocket connections for seamless real-time stream reductions.
                  </p>
                  <div className="grid grid-cols-2 gap-4 text-[10px] text-zinc-500 pt-1">
                    <div>
                      <span className="block font-black text-zinc-400">ORM Integration:</span>
                      Drizzle / Prisma TypeScript schema
                    </div>
                    <div>
                      <span className="block font-black text-zinc-400">WebSocket Transport:</span>
                      WebSockets coupled with Node EventEmitters
                    </div>
                  </div>
                </motion.div>
              )}

              {selectedBackend === 'firebase' && (
                <motion.div
                  key="firebase"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="space-y-4 bg-white/[0.02] border border-white/5 rounded-xl p-4 text-xs font-mono"
                >
                  <div className="flex items-center justify-between text-[11px] text-[#10b981]">
                    <span className="font-bold">✓ OPTION C: Serverless Firestore Database + Firebase Auth</span>
                    <span className="px-2 py-0.5 bg-zinc-805 text-[9px] text-zinc-400 rounded font-bold">ZERO INFRASTRUCTURE</span>
                  </div>
                  <p className="text-zinc-400 text-[11px] leading-relaxed">
                    Provides built-in document sync directly to the browser with security listeners. No server state setup or express routing required for general CRUD state stores.
                  </p>
                  <div className="grid grid-cols-2 gap-4 text-[10px] text-zinc-500 pt-1">
                    <div>
                      <span className="block font-black text-zinc-400">Database Engine:</span>
                      Durable Cloud Google Firestore
                    </div>
                    <div>
                      <span className="block font-black text-zinc-400">Security Layers:</span>
                      Built-in declarative Firestore rules
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="text-[10px] text-zinc-550 border-t border-white/5 pt-4 mt-6 flex items-center justify-between">
            <span>Enterprise grade RAG vectors: pgvector or Pinecone.</span>
            <span className="font-semibold text-emerald-400 hover:underline cursor-pointer">Learn details in System BlueprintDocs</span>
          </div>
        </div>

        {/* MESH HEALTH MONITOR */}
        <div className="lg:col-span-4 p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between">
          <div className="space-y-5">
            <div>
              <p className="text-[9.5px] font-mono tracking-widest text-zinc-500 uppercase">SYSTEM HEALTH</p>
              <h4 className="text-sm font-bold text-white mt-1">Autonomous Host Telemetry</h4>
            </div>

            {/* Simulated Heat / Traffic */}
            <div className="space-y-3.5">
              <div>
                <div className="flex justify-between text-[10px] font-mono text-zinc-400 mb-1">
                  <span>CONSENX STARDUST INTENSITY</span>
                  <span className="text-white">96% Status</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full w-[96%]" />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-[10px] font-mono text-zinc-400 mb-1">
                  <span>VECTOR INDEX SYNC</span>
                  <span className="text-white">100% Synced</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-[#10b981] rounded-full w-full" />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-[10px] font-mono text-zinc-400 mb-1">
                  <span>THREAD CONCURRENCY</span>
                  <span className="text-white">8/12 Threads</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-teal-400 rounded-full w-[66%]" />
                </div>
              </div>
            </div>

            {/* Log list representing simulated event reductions */}
            <div className="space-y-2 border-t border-white/5 pt-3">
              <p className="text-[9px] font-mono text-zinc-500 tracking-wider">LATEST LOGS</p>
              {[
                { log: 'Conducted round 5 validation on Rate-Limiter', time: '11:24' },
                { log: 'Cached 28 cognitive memory facts to pgvector', time: '11:15' },
                { log: 'Assigned "Pedantic critique" behavior style to QA', time: '11:02' },
              ].map((item, i) => (
                <div key={i} className="flex justify-between gap-2.5 text-[9.5px] font-mono text-zinc-400">
                  <span className="truncate">▶ {item.log}</span>
                  <span className="text-zinc-650 shrink-0">{item.time}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-white/5 bg-white/[0.01] p-3 rounded-lg text-[10px] leading-relaxed text-zinc-400 font-mono">
            <strong>System summary:</strong> Your multi-agent swarm has processed all active consensus routines properly and generated stable builds.
          </div>
        </div>
      </div>

      {/* REAL-TIME NOTIFICATION SYSTEM & WORKER TRAFFIC INTERACTION CONTROLS */}
      <div id="realtime-notification-system-panel" className="p-6 rounded-2xl bg-[#09090b]/80 border border-white/10 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-white/10 gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <p className="text-[10px] font-mono tracking-[0.2em] text-[#10b981] uppercase font-bold">EVENT BUS MATRIX</p>
            </div>
            <h3 className="text-base font-bold text-white mt-1">Real-Time Swarm Notification Simulator</h3>
            <p className="text-zinc-500 text-[11px] font-medium">Click any of the telemetry nodes below to inject real-time state machine reductions into the viewport overlay.</p>
          </div>

          {/* Trigger Auto Simulation Toggles */}
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-mono text-zinc-400 uppercase">Auto-Generate (7.5s):</span>
            <button
              id="sim-active-toggle-button"
              onClick={() => setSimActive(!simActive)}
              className={`px-3 py-1.5 rounded-lg text-[9.5px] font-mono font-bold uppercase border tracking-wider transition-all flex items-center gap-1.5 cursor-pointer ${
                simActive 
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                  : 'bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-400'
              }`}
            >
              {simActive ? <Wifi className="w-3.5 h-3.5 animate-pulse text-emerald-400" /> : <Pause className="w-3.5 h-3.5" />}
              <span>{simActive ? 'STREAMING ACTIVE' : 'STREAM MUTED'}</span>
            </button>
          </div>
        </div>

        {/* Action simulators array */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Creative Architect', action: 'Approved React styling layer guidelines', status: 'completes', desc: 'Notify completion', color: 'border-emerald-500/45 hover:bg-emerald-500/5 hover:border-emerald-400' },
            { label: 'Strict Auditor', action: 'Detected unhandled state recursion trace in thread Q', status: 'critique', desc: 'Notify warning', color: 'border-rose-500/45 hover:bg-rose-500/5 hover:border-rose-400' },
            { label: 'Pedantic QA Tester', action: 'Injected 50 concurrent client mocks without latency loss', status: 'completes', desc: 'Notify test metrics', color: 'border-teal-500/45 hover:bg-teal-500/5 hover:border-teal-400' },
            { label: 'Zero-Latency DevOps', action: 'Refreshed pgvector connection pool', status: 'sync', desc: 'Notify sync event', color: 'border-sky-500/45 hover:bg-sky-500/5 hover:border-sky-400' },
          ].map((trigger, i) => (
            <button
              id={`trigger-alert-${i}`}
              key={i}
              onClick={() => triggerToast(trigger.label, trigger.action, trigger.status as any)}
              className={`p-3.5 rounded-xl border text-left bg-black/40 transition-all cursor-pointer flex flex-col justify-between h-24 ${trigger.color}`}
            >
              <div className="flex items-center justify-between w-full">
                <span className="text-[10px] font-sans font-black text-white uppercase tracking-wider">{trigger.label}</span>
                <Zap className="w-3.5 h-3.5 text-zinc-450 shrink-0" />
              </div>
              <div className="mt-2 text-left">
                <p className="text-[10.5px] text-zinc-300 leading-snug line-clamp-1 font-medium">{trigger.action}</p>
                <p className="text-[8.5px] text-zinc-550 font-mono mt-0.5 uppercase tracking-widest">{trigger.desc}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Alert Register Archive */}
        <div className="bg-[#111113]/30 border border-white/5 rounded-xl p-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest flex items-center gap-1.5">
              <Bell className="w-3.5 h-3.5 text-[#10b981]" />
              Recent Alert Journal ({toasts.length})
            </span>
            {toasts.length > 0 && (
              <button 
                onClick={() => setToasts([])}
                className="text-zinc-500 hover:text-white font-mono text-[9px] uppercase tracking-wider flex items-center gap-1 cursor-pointer"
              >
                <Trash2 className="w-3 h-3" /> Clear Journal
              </button>
            )}
          </div>
          {toasts.length === 0 ? (
            <div className="text-center py-6">
              <p className="text-[10.5px] font-mono text-zinc-500 uppercase tracking-wider">No active event logs recorded in journal</p>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-48 overflow-y-auto pr-2">
              {toasts.map((toast) => (
                <div 
                  key={toast.id} 
                  className="flex items-center justify-between p-2.5 bg-[#09090b]/80 border border-white/10 rounded-lg text-xs"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      toast.status === 'completes' ? 'bg-[#10b981]' :
                      toast.status === 'critique' ? 'bg-orange-500' :
                      toast.status === 'error' ? 'bg-rose-500' : 'bg-sky-400'
                    }`} />
                    <span className="font-sans font-bold text-white uppercase tracking-tight text-[10px] w-28 truncate select-none">{toast.agent}</span>
                    <span className="text-zinc-400 font-mono text-[11px] truncate">{toast.action}</span>
                  </div>
                  <span className="text-[9.5px] font-mono text-zinc-500 ml-4 shrink-0">{toast.time}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

