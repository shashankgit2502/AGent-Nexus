import { useState, useEffect } from 'react';
import { ThreeMeshBackground } from '../components/ThreeMeshBackground';
import { AgentGraph } from '../components/AgentGraph';
import { DebateThread } from '../components/DebateThread';
import { SIMULATION_TEMPLATES } from '../data/simulationTemplates';
import { DebateMessage, AgentNode } from '../types';
import { motion } from 'motion/react';
import { Terminal, Bot, Sparkles, HardDrive, ArrowRight, Layers, Sliders, ListChecks, CheckCircle, Flame, Check } from 'lucide-react';

interface LandingViewProps {
  onStartSession: (presetId?: string) => void;
  onNavigateToWorkspace: () => void;
  onNavigateToProfiles: () => void;
}

export function LandingView({ onStartSession, onNavigateToWorkspace, onNavigateToProfiles }: LandingViewProps) {
  // Let us run a gentle background loop of the Rate Limiter debate to make the landing page feel fully alive!
  const template = SIMULATION_TEMPLATES[0]; // Rate Limiter template
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [nodes, setNodes] = useState<AgentNode[]>(
    template ? JSON.parse(JSON.stringify(template.initialNodes)) : []
  );
  
  const [activeSender, setActiveSender] = useState<string | null>(null);
  const [activeReceiver, setActiveReceiver] = useState<string | null>(null);
  const [activeMessageType, setActiveMessageType] = useState<DebateMessage['type'] | null>(null);
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [consensusPct, setConsensusPct] = useState(15);

  useEffect(() => {
    if (!template) return;

    // Tick the simulation index forward periodically on the landing page
    const interval = setInterval(() => {
      setCurrentStepIdx((prevIdx) => {
        const nextIdx = prevIdx + 1;
        if (nextIdx > template.steps.length) {
          return 0; // Trigger reset
        }
        return nextIdx;
      });
    }, 4500);

    return () => clearInterval(interval);
  }, [template]);

  useEffect(() => {
    if (!template) return;

    if (currentStepIdx === 0) {
      // Clean baseline on cycle restart
      setMessages([]);
      setNodes(JSON.parse(JSON.stringify(template.initialNodes)));
      setConsensusPct(15);
      setActiveSender(null);
      setActiveReceiver(null);
      setActiveMessageType(null);
      return;
    }

    const currentStep = template.steps[currentStepIdx - 1];
    if (currentStep) {
      setActiveSender(currentStep.senderId);
      setActiveReceiver(currentStep.receiverId);
      setActiveMessageType(currentStep.messageType);
      setConsensusPct(currentStep.consensusPct);

      // Generate a deterministic unique message ID for this specific step in the simulation cycle to avoid duplicate key issues
      const msgId = `landing-${currentStepIdx - 1}-${currentStep.senderId}-${currentStep.round}`;

      const newMsg: DebateMessage = {
        id: msgId,
        round: currentStep.round,
        senderId: currentStep.senderId,
        senderName: currentStep.senderId.toUpperCase(),
        type: currentStep.messageType,
        text: currentStep.messageText,
        badgeLabel: currentStep.badgeLabel,
        timestamp: new Date().toLocaleTimeString(),
        agentColor: template.initialNodes.find((n) => n.id === currentStep.senderId)?.color,
      };

      setMessages((prev) => {
        if (prev.some((m) => m.id === msgId)) {
          return prev;
        }
        return [...prev, newMsg];
      });

      // Update node statuses for visualization
      setNodes((prevNodes) =>
        prevNodes.map((n) => ({
          ...n,
          status: currentStep.nodeStatuses[n.id] || 'idle',
        }))
      );
    }
  }, [currentStepIdx, template]);

  return (
    <motion.div
      id="landing-view-container"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.45, ease: 'easeOut' }}
      className="relative flex flex-col items-center overflow-x-hidden"
    >
      {/* Dynamic Starry Proximity Interactive Background Canvas */}
      <ThreeMeshBackground />


      {/* 3-COLUMN HERO LAYER (Artistic Flair signature) */}
      <section id="hero-layout" className="w-full max-w-7xl xl:max-w-[1550px] mt-8 md:mt-16 mb-20 px-6 md:px-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch relative z-10 text-stone-300">
        
        {/* LEFT COLUMN: Sidebar Rail */}
        <aside className="hidden lg:flex lg:col-span-1 flex-col items-center justify-between py-8 border-r border-white/10 pr-6">
          <div className="w-8 h-8 bg-white rounded flex items-center justify-center text-black font-mono font-black text-[11px] shadow-[0_0_15px_rgba(255,255,255,0.2)]">
            Nx
          </div>
          <div className="vertical-protocol text-[9px] font-mono tracking-[0.45em] text-zinc-500 uppercase select-none">
            CONVERGENCE_ENGINE
          </div>
          <div className="text-zinc-600 text-[10.5px] font-mono font-bold">
            ©26
          </div>
        </aside>

        {/* MIDDLE COLUMN: Hero Heading & CTAs */}
        <div className="col-span-12 lg:col-span-8 flex flex-col justify-center text-left lg:pr-10 py-4">
          {/* Multiplex Operating System Badge */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 }}
            className="inline-flex items-center gap-2 border border-white/10 bg-white/5 text-neutral-300 text-[10px] tracking-[0.2em] font-semibold px-4 py-2 rounded-full mb-6 w-fit shadow-[0_0_15px_rgba(255,255,255,0.05)] hover:border-white/20 transition-all uppercase"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse inline-block" />
            <span>Multi-Agent Operating System</span>
          </motion.div>

          {/* Display Typography pair headings */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-sans font-black tracking-tight leading-[1.05] mb-6 text-white"
          >
            Your autonomous <br />
            <span className="text-[#10b981] font-black drop-shadow-[0_2px_10px_rgba(16,185,129,0.2)]">engineering team,</span> <br />
            converging in real time
          </motion.h1>

          {/* Editorial Subtitle */}
          <motion.p
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="text-zinc-400 text-sm md:text-base max-w-xl leading-relaxed mb-8 font-sans font-normal"
          >
            NEX AGI orchestrates specialist AI agents that debate, critique, and synthesise — so complex software goals don't just get answered, they get solved.
          </motion.p>

          {/* Call To Actions */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="flex flex-wrap items-center gap-4"
          >
            <button
              onClick={() => onStartSession()}
              className="px-6 py-3.5 bg-white hover:bg-zinc-200 text-black font-extrabold text-[11px] tracking-widest uppercase rounded shadow-[0_4px_24px_rgba(255,255,255,0.15)] transition-all cursor-pointer hover:scale-[1.01] active:scale-95 flex items-center gap-2"
            >
              <span>Initialize Node</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            
            <button
              onClick={onNavigateToWorkspace}
              className="px-6 py-3.5 bg-transparent border border-white/20 hover:border-white/50 hover:bg-white/5 text-white font-extrabold text-[11px] tracking-widest uppercase rounded transition-all cursor-pointer active:scale-95"
            >
              <span>Watch live run</span>
            </button>

            <span className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 text-[9.5px] text-zinc-500 border border-white/10 rounded bg-white/5 font-mono select-none">
              <span>⌘</span><span>K</span>
            </span>
          </motion.div>
        </div>

        {/* RIGHT COLUMN: Autonomous Specialists Pane */}
        <aside className="col-span-12 lg:col-span-3 flex flex-col justify-between p-7 rounded-2xl artistic-pane">
          <div className="space-y-6">
            <div className="border-b border-white/10 pb-4">
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-1">CONVERGENCE SPEED</div>
              <div className="text-3xl font-mono text-white font-extrabold flex items-baseline gap-1">
                94.8<span className="text-xs text-[#10b981] font-sans font-bold">% Rate</span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Successful blueprint convergence reached across heterogenous mesh nodes.
              </p>
            </div>

            <div className="border-b border-white/10 pb-4">
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-1">DECISION INTERVAL</div>
              <div className="text-3xl font-mono text-white font-extrabold flex items-baseline gap-1">
                1.8<span className="text-xs text-[#10b981] font-sans font-bold">s Average</span>
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Average debate round validation and next-token consensus updates.
              </p>
            </div>

            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-[0.2em] text-zinc-500 mb-2">SYNTHESIS QUALITY</div>
              <div className="text-3xl font-mono text-white font-extrabold">A+ Grade</div>
              <p className="text-[10px] text-zinc-500 font-mono mt-1 leading-normal">
                Assures strict type safety, edge-case coverage and robust caching profiles.
              </p>
              {/* Progress Bar styled in pure monochrome design */}
              <div className="mt-3.5 h-[3px] bg-white/10 rounded-full overflow-hidden">
                <div className="w-[94.8%] h-full bg-[#10b981] rounded-full transition-all duration-1000" />
              </div>
            </div>
          </div>

          <div className="p-4 bg-white/[0.02] border border-white/5 rounded-lg text-[10px] leading-relaxed text-zinc-400 font-mono mt-8">
            NEX AGI coordinates specialist AI agent personas to debate, critique, and resolve complex software engineering bottlenecks under a custom-set consensus threshold.
          </div>
        </aside>
      </section>

      {/* WORKSPACE TEASER DASHBOARD (Transformed into gorgeous monochrome artistic viewport) */}
      <section id="teaser-workspace" className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-24 relative z-10">
        <div className="text-center mb-6">
          <p className="text-[10px] font-mono font-bold text-zinc-500 tracking-[0.3em] uppercase mb-1">LIVE RUN ABSTRACT TELEMETRY</p>
          <div className="w-12 h-[1px] bg-white/10 mx-auto rounded"></div>
        </div>

        <div className="artistic-pane rounded-2xl overflow-hidden shadow-[0_24px_60px_rgba(0,0,0,0.6)]">
          {/* Mock Header */}
          <div className="px-6 py-4.5 border-b border-white/10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-[rgba(5,5,5,0.7)]">
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 bg-white/5 border border-white/10 text-white text-[10px] font-mono rounded font-semibold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                Round {currentStepIdx > 0 ? template.steps[currentStepIdx - 1]?.round : 1} / 5
              </span>
              <span className="text-zinc-650 font-mono text-xs hidden md:inline">|</span>
              <span className="text-zinc-300 font-medium text-xs sm:text-sm">
                Goal: <span className="text-white font-bold">Design a distributed rate-limiter for 10M RPS</span>
              </span>
            </div>

            {/* Mirroring Consensus ring with gorgeous stardust design */}
            <div className="flex items-center gap-3 self-end sm:self-auto font-mono">
              <div className="relative w-8 h-8 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    className="text-white/10"
                    strokeWidth="3.5"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="text-white transition-all duration-500"
                    strokeDasharray={`${consensusPct}, 100`}
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span className="absolute text-[8px] text-zinc-300 font-black">{consensusPct}%</span>
              </div>
              <div className="text-right">
                <p className="text-[9px] text-zinc-500 font-bold tracking-wider uppercase">Stability Threshold</p>
                <p className="text-[11px] text-white font-black">{consensusPct}%</p>
              </div>
            </div>
          </div>

          {/* Side by side Graph + Debate Thread */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 p-5 bg-[rgba(5,5,5,0.2)]">
            <div className="lg:col-span-8 h-[340px]">
              <AgentGraph
                nodes={nodes}
                activeSenderId={activeSender}
                activeReceiverId={activeReceiver}
                activeMessageType={activeMessageType}
                selectedNodeId={null}
              />
            </div>

            <div className="lg:col-span-4 h-[340px]">
              <DebateThread messages={messages} />
            </div>
          </div>
        </div>
      </section>

      {/* CAPABILITIES SECTION */}
      <section id="capabilities" className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-24 relative z-10 text-stone-300">
        <div className="mb-14">
          <p className="text-zinc-500 text-[10px] font-mono font-bold tracking-[0.3em] uppercase mb-2">SYSTEM SPECS & LAYERS</p>
          <h2 className="text-3xl md:text-5xl font-extrabold text-white tracking-tight mb-4">Not a chat. An OS.</h2>
          <p className="text-zinc-400 text-sm md:text-base max-w-xl leading-relaxed">
            NEX AGI gives you a real-time view into how agents reason, debate, and converge — every interaction grounded in a real, trackable system coordinate.
          </p>
        </div>

        {/* Feature Grid with hover states */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            {
              icon: '⬡',
              title: 'Agent mesh graph',
              desc: 'React-driven interactive node map where connections only highlight when a message flows. No mock lines, absolute accuracy.',
            },
            {
              icon: '⊶',
              title: 'PR-style debate panel',
              desc: 'Every CRITIQUE, ENDORSE, and VOTE rendered sequentially as code review lines. Follow conflicts and resolutions objectively.',
            },
            {
              icon: '◎',
              title: 'Consensus ring',
              desc: 'Telemetry on multi-agent alignment. Watch percentages rise as specialist agents negotiate code standards.',
            },
            {
              icon: '⌬',
              title: 'Lifecycle-driven layout',
              desc: 'Adapts dynamically to the task phase: files occupy center-stage during drafting, collapsing when agent debate resumes.',
            },
            {
              icon: '⟐',
              title: 'Blackboard + scrubber',
              desc: 'Shared memory space with round-by-round time scrubbers. Replay agent messages and track file mutations.',
            },
            {
              icon: '⊛',
              title: 'Inference profiles',
              desc: 'Adjust temperature, top-P, and reasoning parameters per role. Overrides model limits at specific debate junctions.',
            },
          ].map((item, index) => (
            <motion.div
              id={`capability-card-${index}`}
              key={item.title}
              initial={{ opacity: 0, y: 15 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.05 }}
              className="p-6 rounded-2xl artistic-pane artistic-pane-hover group cursor-default"
            >
              <div className="w-10 h-10 rounded bg-white/5 border border-white/15 text-white font-mono text-sm flex items-center justify-center mb-4 group-hover:bg-white/10 group-hover:border-white/30 transition-all">
                {item.icon}
              </div>
              <h4 className="text-white font-extrabold text-sm mb-2 group-hover:text-[#a3a3a3] transition-colors">{item.title}</h4>
              <p className="text-zinc-400 text-xs leading-relaxed">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* STATS NUMERICAL BLOCKS ROW */}
      <section id="stats" className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-24 relative z-10">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 artistic-pane rounded-2xl p-6 divide-y lg:divide-y-0 lg:divide-x divide-white/10">
          {[
            {
              num: 'N²',
              desc: 'Fully connected agent mesh topology config',
            },
            {
              num: 'τ',
              desc: 'Configurable consensus threshold per session',
            },
            {
              num: '5+',
              desc: 'LLMs supported: Gemini, Claude, GPT, Ollama',
            },
            {
              num: 'AG-UI',
              desc: 'Contract-first atomic real-time protocol',
            },
          ].map((stat, idx) => (
            <div id={`stat-node-${idx}`} key={stat.num} className="p-4 flex flex-col justify-center text-center lg:text-left">
              <h3 className="text-3xl md:text-4xl font-mono font-black text-white mb-2">
                {stat.num === 'τ' ? (
                  <span className="text-white italic">τ</span>
                ) : (
                  <>
                    {stat.num.slice(0, -1)}
                    <span className="text-zinc-400 font-mono font-medium">{stat.num.slice(-1)}</span>
                  </>
                )}
              </h3>
              <p className="text-zinc-500 text-xs tracking-wide leading-relaxed font-mono">{stat.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* BOTTOM CTA CARD */}
      <section id="footer-cta" className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 mb-20 text-center relative z-10">
        <div className="relative artistic-pane rounded-3xl p-10 md:p-14 overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.4)]">
          {/* No unrequested radial ambient glow blocks */}

          <h2 className="text-2xl md:text-3.5xl font-extrabold text-white mb-3 tracking-tight">
            Run your first multi-agent session
          </h2>
          <p className="text-zinc-400 text-xs md:text-sm max-w-lg mx-auto mb-8 leading-relaxed">
            Set an ambitious engineering goal. Deploy your specialist agent mesh. Watch the debate, track consensus, and ship the synthesized files.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={() => onStartSession()}
              className="w-full sm:w-auto px-6 py-3 bg-white hover:bg-zinc-200 text-black font-extrabold rounded text-xs sm:text-sm tracking-wider uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-[0_4px_24px_rgba(255,255,255,0.15)]"
            >
              <span>Initialize uplink</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={onNavigateToProfiles}
              className="w-full sm:w-auto px-6 py-3 bg-transparent border border-white/20 hover:border-white/40 hover:bg-white/5 text-white font-bold rounded text-xs sm:text-sm tracking-wide uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <span>Manage Models</span>
            </button>
          </div>
        </div>
      </section>
    </motion.div>
  );
}
