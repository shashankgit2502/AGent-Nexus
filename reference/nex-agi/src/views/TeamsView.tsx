import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Users, Bot, HardDrive, Cpu, Sliders, List, Save, Sparkles, 
  Settings, Layers, Play, Clock, ArrowRight, ShieldAlert, Check, Plus, Trash2, Globe, FileCode 
} from 'lucide-react';

interface Agent {
  id: string;
  name: string;
  role: string;
  model: string;
  avatarText: string;
  skills: string[];
  systemPrompt: string;
  knowledgeSources: string[];
  capabilities: {
    rag: boolean;
    webSearch: boolean;
    codeInterpreter: boolean;
  };
}

export function TeamsView() {
  const [selectedTeam, setSelectedTeam] = useState<'infrastructure' | 'frontend'>('infrastructure');
  const [activeTab, setActiveTab] = useState<'overview' | 'agents' | 'skills' | 'knowledge' | 'memory'>('overview');
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);

  // Initial Agents catalog
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: 'orchestrator',
      name: 'Orchestrating Router',
      role: 'Consensus coordinator & blueprint formulator',
      model: 'gemini-2.5-pro',
      avatarText: 'Or',
      skills: ['Planning', 'Router', 'Consensus'],
      systemPrompt: 'You coordinate debates across specialized sub-nodes. Collect comments, synthesise agreements, and score confidence.',
      knowledgeSources: ['Distributed design specs', 'Gossip protocols manifest'],
      capabilities: { rag: true, webSearch: false, codeInterpreter: true }
    },
    {
      id: 'architect',
      name: 'Creative Architect',
      role: 'Core systems structurer & code generator',
      model: 'claude-3.5-sonnet',
      avatarText: 'Ar',
      skills: ['System Design', 'Code Generation', 'Drafting'],
      systemPrompt: 'You design modular software frameworks. Favour strict type guarantees, localized caching models, interfaces, and separation of concerns.',
      knowledgeSources: ['Best practices standard v2', 'Go caching profiles'],
      capabilities: { rag: true, webSearch: true, codeInterpreter: false }
    },
    {
      id: 'reviewer',
      name: 'Strict Auditor',
      role: 'Vulnerability finder & performance auditor',
      model: 'gemini-2.5-pro',
      avatarText: 'Rv',
      skills: ['Security review', 'Stress calculations', 'Critiques'],
      systemPrompt: 'Inspect code against edge-case failures, memory leaks, high volume connection throttling patterns, and security leaks.',
      knowledgeSources: ['Vulnerability logs', 'AWS checklist'],
      capabilities: { rag: false, webSearch: true, codeInterpreter: true }
    }
  ]);

  // Handle saving edited agent configurations
  const handleSaveAgent = (updated: Agent) => {
    setAgents(prev => prev.map(a => a.id === updated.id ? updated : a));
    setSelectedAgent(null);
  };

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-8 space-y-6 text-stone-300">
      
      {/* HEADER SECTION */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-white/10 pb-4 gap-4">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981]">MANAGEMENT PLATFORM</p>
          <h2 className="text-xl font-sans font-black text-white tracking-tight mt-1">Specialist Team Workspaces</h2>
        </div>

        {/* Selected Hub Team */}
        <div className="flex items-center gap-1.5 p-1 bg-neutral-900 border border-white/10 rounded-xl">
          <button
            onClick={() => setSelectedTeam('infrastructure')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
              selectedTeam === 'infrastructure' ? 'bg-white/5 text-white' : 'text-zinc-500'
            }`}
          >
            Elite Infrastructure
          </button>
          <button
            onClick={() => setSelectedTeam('frontend')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
              selectedTeam === 'frontend' ? 'bg-white/5 text-white' : 'text-zinc-500'
            }`}
          >
            Client Experience
          </button>
        </div>
      </div>

      {/* INNER PAGES WORKSPACE WITH TOP MENU TABS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        
        {/* TABS VIEWPORT */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          {/* Horizontal custom bar */}
          <div className="flex flex-wrap items-center gap-2 border-b border-white/10 pb-2">
            {[
              { id: 'overview', label: 'Overview' },
              { id: 'agents', label: 'Specialist Agents' },
              { id: 'skills', label: 'Assigned Skills' },
              { id: 'knowledge', label: 'Indexed Knowledge' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id as any); setSelectedAgent(null); }}
                className={`px-4 py-2 text-[10.5px] font-bold tracking-widest uppercase rounded transition-all cursor-pointer ${
                  activeTab === tab.id 
                    ? 'text-[#10b981] bg-[#10b981]/5 border border-[#10b981]/20' 
                    : 'text-zinc-400 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {activeTab === 'overview' && (
              <motion.div
                key="overview"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-6 bg-[#09090b]/80 border border-white/10 rounded-2xl p-6"
              >
                <div>
                  <h3 className="text-[#10b981] font-mono text-[10px] tracking-widest uppercase">TEAM MISSION & STRATEGY</h3>
                  <h2 className="text-lg font-bold text-white mt-1">High Availability Software Architecture Specialist Team</h2>
                </div>
                
                <p className="text-sans text-xs text-zinc-400 leading-relaxed">
                  Collaborates across concurrent debate rounds to formulate robust backends, distribute load rules, configure databases, and clear system stress bottlenecks safely prior to synthesis deployment.
                </p>

                {/* Team stats indicators */}
                <div className="grid grid-cols-3 gap-4 pt-4 border-t border-white/5 font-mono">
                  <div className="bg-white/[0.01] border border-white/5 p-4 rounded-xl">
                    <p className="text-[10px] text-zinc-550 uppercase">AVERAGE LATENCY</p>
                    <p className="text-xl font-bold text-white mt-1">1.8s</p>
                  </div>
                  <div className="bg-white/[0.01] border border-white/5 p-4 rounded-xl">
                    <p className="text-[10px] text-zinc-550 uppercase">ACTIVE DISKS</p>
                    <p className="text-xl font-bold text-white mt-1">4 sources</p>
                  </div>
                  <div className="bg-white/[0.01] border border-white/5 p-4 rounded-xl">
                    <p className="text-[10px] text-zinc-550 uppercase">RELIABILITY INDEX</p>
                    <p className="text-xl font-bold text-emerald-400 mt-1">99.8%</p>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'agents' && (
              <motion.div
                key="agents"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="grid grid-cols-1 sm:grid-cols-2 gap-4"
              >
                {agents.map((agent) => (
                  <div
                    key={agent.id}
                    onClick={() => setSelectedAgent(agent)}
                    className="p-5 rounded-2xl bg-[#09090b]/80 border border-white/10 flex flex-col justify-between h-44 hover:border-[#10b981]/30 transition-all cursor-pointer relative group"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded bg-[#10b981]/10 border border-[#10b981]/25 flex items-center justify-center text-[#10b981] font-mono text-xs font-black">
                          {agent.avatarText}
                        </div>
                        <div>
                          <h4 className="text-white font-bold text-xs">{agent.name}</h4>
                          <p className="text-[10px] text-zinc-500 font-mono">{agent.model}</p>
                        </div>
                      </div>
                      <span className="text-[9.5px] px-2.5 py-1 rounded bg-white/5 border border-white/10 font-mono text-zinc-400">READY</span>
                    </div>

                    <p className="text-[11px] text-zinc-400 leading-normal line-clamp-2 mt-3">{agent.role}</p>

                    <div className="flex flex-wrap gap-1.5 mt-4">
                      {agent.skills.map((s, idx) => (
                        <span key={idx} className="px-2 py-0.5 bg-neutral-950 border border-white/5 rounded text-[8px] font-mono text-zinc-500">{s}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </motion.div>
            )}

            {activeTab === 'skills' && (
              <motion.div
                key="skills"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-4 bg-[#09090b]/80 border border-white/10 rounded-2xl p-6"
              >
                <div>
                  <h3 className="text-white font-bold text-sm">Orchestrated Skills Inventory</h3>
                  <p className="text-zinc-500 text-xs mt-0.5">Assigne capabilities to individual agents to dictate their operational behaviors.</p>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-4">
                  {[
                    { title: 'Planning Parser', desc: 'Allows structuring full system steps recursively.' },
                    { title: 'Pedantic Reviewer', desc: 'Forces system audits and highlights bottlenecks.' },
                    { title: 'Consensus Broker', desc: 'Schedules agreement votes across target threads.' },
                    { title: 'Zero latency Compiler', desc: 'Drafts code payloads in Go, Rust, or YAML.' },
                  ].map((s, i) => (
                    <div key={i} className="p-3.5 rounded-xl bg-white/[0.01] border border-white/5 text-xs font-mono score-card">
                      <span className="text-[#10b981] font-bold block mb-1">■ {s.title}</span>
                      <p className="text-zinc-400 font-sans">{s.desc}</p>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {activeTab === 'knowledge' && (
              <motion.div
                key="knowledge"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-4 bg-[#09090b]/80 border border-white/10 rounded-2xl p-6"
              >
                <div>
                  <h3 className="text-white font-bold text-sm">Team-Scoped RAG Archives</h3>
                  <p className="text-zinc-500 text-xs mt-0.5">Static context collections embedded for fast vector retrieval.</p>
                </div>

                <div className="space-y-3">
                  {[
                    { source: 'distributed_blueprints v2.pdf', weight: '242 KB', status: 'INDEXED' },
                    { source: 'gossip_consensus_reps.docs', weight: '18 KB', status: 'INDEXED' },
                    { source: 'cache_eviction_metrics.json', weight: '124 KB', status: 'INDEXED' },
                  ].map((k, i) => (
                    <div key={i} className="flex justify-between items-center bg-white/[0.01] border border-white/5 p-3.5 rounded-xl text-xs font-mono">
                      <span className="text-white">✓ {k.source}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-zinc-600">{k.weight}</span>
                        <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[8.5px] font-bold rounded">{k.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* 3-COLUMN AGENT BUILDER (REVEALS UPON SELECTION) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col justify-between">
          <AnimatePresence mode="wait">
            {selectedAgent ? (
              <motion.div
                key={selectedAgent.id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="p-6 rounded-2xl border border-white/15 bg-neutral-900/90 shadow-[0_8px_32px_rgba(16,185,129,0.06)] space-y-5"
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded bg-[#10b981]/15 flex items-center justify-center text-[#10b981] font-mono text-xs font-black">
                      {selectedAgent.avatarText}
                    </div>
                    <div>
                      <h3 className="text-white font-bold text-xs">Agent Configurator</h3>
                      <p className="text-[10px] text-zinc-500 font-mono">Customizing parameters</p>
                    </div>
                  </div>
                  <button onClick={() => setSelectedAgent(null)} className="text-zinc-500 hover:text-white transition text-xs">✕</button>
                </div>

                {/* Column 1: Identity */}
                <div className="space-y-1.5">
                  <label className="text-[9px] font-mono text-zinc-400 uppercase tracking-widest block">AGENT NAME</label>
                  <input
                    type="text"
                    value={selectedAgent.name}
                    onChange={(e) => handleSaveAgent({ ...selectedAgent, name: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-lg p-2 text-xs text-white"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[9px] font-mono text-[#10b981] uppercase tracking-widest block">SYSTEM INSTRUCTIONS</label>
                  <textarea
                    rows={4}
                    value={selectedAgent.systemPrompt}
                    onChange={(e) => handleSaveAgent({ ...selectedAgent, systemPrompt: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-lg p-2.5 text-xs text-white leading-normal"
                  />
                </div>

                {/* Column 2: RAG / Knowledge sources toggling */}
                <div className="p-3.5 rounded-xl bg-neutral-950 border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">RAG / Scoped Knowledge</span>
                    <input
                      type="checkbox"
                      checked={selectedAgent.capabilities.rag}
                      onChange={(e) => handleSaveAgent({
                        ...selectedAgent,
                        capabilities: { ...selectedAgent.capabilities, rag: e.target.checked }
                      })}
                      className="accent-[#10b981] cursor-pointer"
                    />
                  </div>
                  <p className="text-[9px] text-zinc-500 leading-normal">
                    Locks the agent query context strictly to vector index archives. Disallows any generic LLM pre-trained bias parameters.
                  </p>
                </div>

                {/* Column 3: Capabilities checkboxes */}
                <div className="space-y-2 pt-2 border-t border-white/5">
                  <p className="text-[9.5px] font-mono text-zinc-400 uppercase tracking-widest">Execution Tools</p>
                  <div className="flex flex-col gap-2 font-mono text-[10px] text-zinc-400">
                    <label className="flex items-center gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedAgent.capabilities.webSearch}
                        onChange={(e) => handleSaveAgent({
                          ...selectedAgent,
                          capabilities: { ...selectedAgent.capabilities, webSearch: e.target.checked }
                        })}
                        className="accent-[#10b981]"
                      />
                      Active Web Search (live internet tool)
                    </label>
                    <label className="flex items-center gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedAgent.capabilities.codeInterpreter}
                        onChange={(e) => handleSaveAgent({
                          ...selectedAgent,
                          capabilities: { ...selectedAgent.capabilities, codeInterpreter: e.target.checked }
                        })}
                        className="accent-[#10b981]"
                      />
                      Code Interpreter (sandboxed environment)
                    </label>
                  </div>
                </div>

                {/* Confirm actions */}
                <button
                  onClick={() => handleSaveAgent(selectedAgent)}
                  className="w-full py-2.5 mt-2 bg-[#10b981] hover:bg-emerald-600 text-black text-xs font-black tracking-widest uppercase rounded-lg transition-colors cursor-pointer"
                >
                  Apply and Deploy Agent
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="p-6 rounded-2xl border border-dashed border-white/10 text-center flex flex-col items-center justify-center h-full text-zinc-500 font-mono py-12"
              >
                <Bot className="w-10 h-10 mb-3 text-zinc-600" />
                <p className="text-xs uppercase tracking-wider font-bold">Select an Agent to Customize</p>
                <p className="text-[10px] text-zinc-650 mt-1 max-w-[200px] mx-auto leading-normal">
                  Customize identity, prompts, models, RAG boundaries, and active computation capabilities.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
