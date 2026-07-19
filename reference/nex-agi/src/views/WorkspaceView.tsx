import { useState, useEffect, useRef } from 'react';
import { AgentGraph } from '../components/AgentGraph';
import { DebateThread } from '../components/DebateThread';
import { Blackboard } from '../components/Blackboard';
import { SIMULATION_TEMPLATES, INITIAL_GENERIC_NODES, SimulationTemplate } from '../data/simulationTemplates';
import { AgentNode, DebateMessage, GeneratedFile, Session } from '../types';
import { motion, AnimatePresence } from 'motion/react';
import { ExportSessionModal } from '../components/ExportSessionModal';
import {
  Play,
  Pause,
  RotateCcw,
  PlusCircle,
  HelpCircle,
  TrendingUp,
  Sliders,
  Cpu,
  Bookmark,
  Sparkles,
  ChevronRight,
  Info,
  Terminal,
  Activity,
  History,
  CheckSquare,
  ExternalLink
} from 'lucide-react';

interface WorkspaceViewProps {
  onSessionSaved: (session: Session) => void;
  initialPresetId?: string;
}

export function WorkspaceView({ onSessionSaved, initialPresetId }: WorkspaceViewProps) {
  // Config States
  const [goalInput, setGoalInput] = useState('Create a modular caching layer in Go with distributed lock validation');
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(initialPresetId || 'rate-limiter');
  const [consensusThreshold, setConsensusThreshold] = useState(85);
  const [activeGroupPreset, setActiveGroupPreset] = useState('Elite Infrastructure Group');
  
  // Selected Agents in the mesh
  const [selectedAgents, setSelectedAgents] = useState<{ [agentId: string]: boolean }>({
    orchestrator: true,
    architect: true,
    reviewer: true,
    qa: true,
    devops: true,
  });

  // Simulation Running State
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [sessionSteps, setSessionSteps] = useState<any[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState(1); // 1x, 2x, 5x, 10x

  // Inspection states
  const [inspectedNode, setInspectedNode] = useState<AgentNode | null>(null);
  const [activeTab, setActiveTab] = useState<'topology' | 'blackboard' | 'debate'>('topology');
  const [isExportOpen, setIsExportOpen] = useState(false);

  // Triggered Template Update
  useEffect(() => {
    if (initialPresetId) {
      const template = SIMULATION_TEMPLATES.find((t) => t.id === initialPresetId);
      if (template) {
        setSelectedTemplateId(initialPresetId);
        setGoalInput(template.goal);
        setActiveGroupPreset(template.agentsPreset);
      }
    }
  }, [initialPresetId]);

  // Handle Preset Selector changes
  const handleTemplateSelect = (id: string) => {
    if (id === 'custom') {
      setSelectedTemplateId('custom');
      return;
    }
    const template = SIMULATION_TEMPLATES.find((t) => t.id === id);
    if (template) {
      setSelectedTemplateId(id);
      setGoalInput(template.goal);
      setActiveGroupPreset(template.agentsPreset);
    }
  };

  // Helper calculation
  const getSimulatedNodes = () => {
    return INITIAL_GENERIC_NODES.filter((n) => selectedAgents[n.id]);
  };

  // Start / Deploy simulation
  const handleDeployMesh = () => {
    // Collect active agents
    const activeNodes = INITIAL_GENERIC_NODES.filter((n) => selectedAgents[n.id]);
    
    // Check if we have standard template matches, else construct a dynamic synthetic template for custom goals
    let stepsToUse = [];
    let finalFiles: GeneratedFile[] = [];

    const matchedTemplate = SIMULATION_TEMPLATES.find((t) => t.id === selectedTemplateId);
    if (matchedTemplate && selectedTemplateId !== 'custom') {
      stepsToUse = JSON.parse(JSON.stringify(matchedTemplate.steps));
      finalFiles = matchedTemplate.completedFiles;
    } else {
      // Build high-fidelity custom synthesis steps tailored specifically to their written goal!
      stepsToUse = generateSyntheticSteps(goalInput, activeNodes);
      finalFiles = generateSyntheticFiles(goalInput);
    }

    // Initialize session state
    const firstSession: Session = {
      id: `session-${Date.now()}`,
      goal: goalInput,
      currentRound: 1,
      maxRounds: stepsToUse[stepsToUse.length - 1]?.round || 5,
      consensusPct: 15,
      status: 'running',
      messages: [],
      files: [],
      timestamp: new Date().toLocaleDateString() + ' ' + new Date().toLocaleTimeString(),
      agentsPreset: activeGroupPreset,
    };

    setCurrentSession(firstSession);
    setSessionSteps(stepsToUse);
    setCurrentStepIndex(0);
    setIsPlaying(true);
    setInspectedNode(null);
  };

  // Simulation step clock loops
  useEffect(() => {
    if (!isPlaying || !currentSession || currentStepIndex < 0 || currentStepIndex >= sessionSteps.length) {
      if (currentStepIndex >= sessionSteps.length && currentSession && currentSession.status === 'running') {
        // Mark session completed!
        const completed: Session = {
          ...currentSession,
          status: 'completed',
          consensusPct: 100,
          currentRound: currentSession.maxRounds,
        };
        setCurrentSession(completed);
        setIsPlaying(false);
        onSessionSaved(completed);
      }
      return;
    }

    const duration = (4500 / speedMultiplier);
    const timer = setTimeout(() => {
      const step = sessionSteps[currentStepIndex];
      if (step) {
        // Build new debate message
        const stepSender = INITIAL_GENERIC_NODES.find((an) => an.id === step.senderId);
        const newMessage: DebateMessage = {
          id: `msg-${currentSession.id}-${currentStepIndex}`,
          round: step.round,
          senderId: step.senderId,
          senderName: stepSender?.name || 'System',
          type: step.messageType,
          text: step.messageText,
          badgeLabel: step.badgeLabel,
          timestamp: new Date().toLocaleTimeString(),
          agentColor: stepSender?.color,
        };

        // Update session
        setCurrentSession((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            consensusPct: step.consensusPct,
            currentRound: step.round,
            messages: [...prev.messages, newMessage],
            files: step.filesAfterStep,
          };
        });

        // Advance step index
        setCurrentStepIndex((prev) => prev + 1);
      }
    }, duration);

    return () => clearTimeout(timer);
  }, [isPlaying, currentStepIndex, speedMultiplier, currentSession, sessionSteps]);

  // Node Clicking audits its diagnostics profile
  const handleNodeClick = (clickedNode: AgentNode) => {
    // Enrich node dynamic state inside inspected dialog
    const enriched = {
      ...clickedNode,
      status: currentSession
        ? (sessionSteps[currentStepIndex - 1]?.nodeStatuses[clickedNode.id] || 'idle')
        : 'idle',
    };
    setInspectedNode(enriched);
  };

  // Reset Session
  const handleResetSession = () => {
    setCurrentSession(null);
    setSessionSteps([]);
    setCurrentStepIndex(-1);
    setIsPlaying(false);
    setInspectedNode(null);
  };

  // Skip simulation straight to results
  const handleFastForward = () => {
    if (!currentSession || sessionSteps.length === 0) return;
    
    // Gather all messages
    const allMsgs: DebateMessage[] = sessionSteps.map((step, idx) => {
      const sender = INITIAL_GENERIC_NODES.find((an) => an.id === step.senderId);
      return {
        id: `ff-msg-${idx}-${Date.now()}`,
        round: step.round,
        senderId: step.senderId,
        senderName: sender?.name || 'System',
        type: step.messageType,
        text: step.messageText,
        badgeLabel: step.badgeLabel,
        timestamp: new Date().toLocaleTimeString(),
        agentColor: sender?.color,
      };
    });

    const finalStep = sessionSteps[sessionSteps.length - 1];
    const completedSession: Session = {
      ...currentSession,
      status: 'completed',
      consensusPct: 100,
      currentRound: currentSession.maxRounds,
      messages: allMsgs,
      files: finalStep.filesAfterStep,
    };

    setCurrentSession(completedSession);
    setCurrentStepIndex(sessionSteps.length);
    setIsPlaying(false);
    onSessionSaved(completedSession);
  };

  // Generate mock structured steps for dynamic custom goal titles typed by the user
  const generateSyntheticSteps = (goal: string, activeNodes: AgentNode[]): any[] => {
    const filenames = goal.toLowerCase().includes('go')
      ? ['caching.go', 'lock_mgr.go']
      : goal.toLowerCase().includes('rust')
      ? ['main.rs', 'cache.rs']
      : ['index.ts', 'server.ts'];

    const firstFile: GeneratedFile = {
      filename: filenames[0],
      language: filenames[0].endsWith('go') ? 'golang' : 'typescript',
      code: `// Synthesizing custom architecture for: "${goal}"\npackage cache\n\ntype CacheStore struct {}`,
    };

    const finalFile1: GeneratedFile = {
      filename: filenames[0],
      language: filenames[0].endsWith('go') ? 'golang' : 'typescript',
      code: `// Highly-concurrent synthesized structure for: "${goal}"
package main

import (
    "sync"
    "time"
)

type ShardedLockManager struct {
    mu      sync.RWMutex
    records map[string]string
    locks   map[string]time.Time
}

func CreateStore() *ShardedLockManager {
    return &ShardedLockManager{
        records: make(map[string]string),
        locks: make(map[string]time.Time),
    }
}
`,
    };

    return [
      {
        round: 1,
        senderId: 'orchestrator',
        receiverId: 'architect',
        messageType: 'reply',
        badgeLabel: 'INITIALIZED',
        messageText: `Initiating agentic alignment context. Directing multi-agent workflow for custom target: "${goal}".`,
        consensusPct: 22,
        nodeStatuses: { orchestrator: 'thinking', architect: 'waiting', reviewer: 'idle', qa: 'idle', devops: 'idle' },
        filesAfterStep: [],
      },
      {
        round: 1,
        senderId: 'architect',
        receiverId: 'reviewer',
        messageType: 'propose',
        badgeLabel: 'DRAFT SHIPPED',
        messageText: `Constructed sharded map structures with mutex registers supporting localized atomic acquisitions. Relaying design proposal for code audit.`,
        consensusPct: 48,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'thinking', qa: 'idle', devops: 'idle' },
        filesAfterStep: [firstFile],
      },
      {
        round: 2,
        senderId: 'reviewer',
        receiverId: 'architect',
        messageType: 'critique',
        badgeLabel: 'SECURITY FAIL',
        messageText: `CRITIQUE: Lock acquisition lacks time-to-live attributes! This creates serious deadlock vulnerabilities during client disconnections. Add TTL leases immediately.`,
        consensusPct: 62,
        nodeStatuses: { orchestrator: 'idle', architect: 'thinking', reviewer: 'critiquing', qa: 'idle', devops: 'idle' },
        filesAfterStep: [firstFile],
      },
      {
        round: 3,
        senderId: 'architect',
        receiverId: 'qa',
        messageType: 'reply',
        badgeLabel: 'DEFECT CORRECTED',
        messageText: `Remediated: Introduced time.Time mapping to store dynamic key expirations. Added automatic lock reaping during high telemetry workloads. Relaying to automated QA tests.`,
        consensusPct: 84,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'idle', qa: 'thinking', devops: 'idle' },
        filesAfterStep: [finalFile1],
      },
      {
        round: 4,
        senderId: 'qa',
        receiverId: 'orchestrator',
        messageType: 'endorse',
        badgeLabel: 'TEST SUCCESS',
        messageText: `ENDORSED: Validated 1500 parallel test threads simulation. Zero lock leakage detected under high contention schedules. Consensus achieved.`,
        consensusPct: 100,
        nodeStatuses: { orchestrator: 'idle', architect: 'idle', reviewer: 'idle', qa: 'endorsing', devops: 'idle' },
        filesAfterStep: [finalFile1],
      },
    ];
  };

  const generateSyntheticFiles = (goal: string): GeneratedFile[] => {
    const ext = goal.toLowerCase().includes('go') ? 'go' : 'ts';
    return [
      {
        filename: `cache_optimizer.${ext}`,
        language: ext === 'go' ? 'golang' : 'typescript',
        code: `// Final compiled consensus artifact for: ${goal}\n// Created in Nex AGI multi-agent environment`,
      },
    ];
  };

  // Determine current active nodes during simulation
  const getSimulatedActiveNodes = (): AgentNode[] => {
    const baseNodes = INITIAL_GENERIC_NODES.filter((n) => selectedAgents[n.id]);
    if (!currentSession || currentStepIndex < 0) {
      return baseNodes.map((n) => ({ ...n, status: 'idle' }));
    }
    const step = sessionSteps[currentStepIndex - 1];
    if (!step) return baseNodes.map((n) => ({ ...n, status: 'idle' }));

    return baseNodes.map((node) => ({
      ...node,
      status: step.nodeStatuses[node.id] || 'idle',
    }));
  };

  const activeNodes = getSimulatedActiveNodes();
  const step = currentStepIndex >= 0 ? sessionSteps[currentStepIndex - 1] : null;

  return (
    <motion.div
      id="workspace-view"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.35 }}
      className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-6 md:py-10 grid grid-cols-1 lg:grid-cols-12 gap-8"
    >
      {/* LEFT COLUMN: PARAMETER SELECTION & NODE METRICS TUNING */}
      <div id="side-panel-controls" className="lg:col-span-4 flex flex-col gap-6">
        {/* Step 1: Aim & Presets Selector */}
        <div className="artistic-pane rounded-xl p-5 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
          <div className="flex items-center gap-2 mb-4">
            <Sliders className="w-4.5 h-4.5 text-white" />
            <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">Deploy Parameters</span>
          </div>

          <div className="space-y-4">
            {/* Goal Presets */}
            <div>
              <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">Preset Templates</label>
              <select
                id="preset-goal-selector"
                value={selectedTemplateId}
                onChange={(e) => handleTemplateSelect(e.target.value)}
                disabled={!!currentSession}
                className="w-full bg-[#111113] border border-white/10 hover:border-white/25 rounded p-2.5 text-xs text-zinc-200 outline-none focus:border-white/40 transition-all font-sans"
              >
                {SIMULATION_TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.id === 'rate-limiter' ? '🚀 ' : '💾 '} {t.goal}
                  </option>
                ))}
                <option value="custom">✍️ [Custom Goal Title]</option>
              </select>
            </div>

            {/* Custom goal edit text area */}
            <div>
              <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">Target Goal Title</label>
              <textarea
                id="goal-input-textarea"
                rows={3}
                value={goalInput}
                onChange={(e) => setGoalInput(e.target.value)}
                disabled={!!currentSession}
                placeholder="Type any software engineering bottleneck to solve..."
                className="w-full bg-[#111113] border border-white/10 rounded p-3 text-xs text-[#ececec] outline-none focus:border-white/40 resize-none font-sans leading-relaxed"
              />
            </div>

            {/* Active Specialist Group identifier */}
            <div>
              <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">Specialist Group</label>
              <input
                id="specialist-group-flag"
                type="text"
                value={activeGroupPreset}
                onChange={(e) => setActiveGroupPreset(e.target.value)}
                disabled={!!currentSession}
                className="w-full bg-[#111113] border border-white/10 rounded p-2.5 text-xs text-zinc-300 outline-none focus:border-white/40 font-sans"
              />
            </div>

            {/* Consensus slider (tau) */}
            <div>
              <div className="flex justify-between items-center mb-1 font-mono">
                <span className="text-[10.5px] font-bold text-zinc-500 uppercase">Threshold (τ)</span>
                <span className="text-xs text-white font-extrabold">{consensusThreshold}%</span>
              </div>
              <input
                id="consensus-threshold-slider"
                type="range"
                min="60"
                max="95"
                step="5"
                value={consensusThreshold}
                onChange={(e) => setConsensusThreshold(Number(e.target.value))}
                disabled={!!currentSession}
                className="w-full accent-white cursor-pointer opacity-80 hover:opacity-100 transition-opacity"
              />
              <p className="text-[10px] text-zinc-500 mt-2 font-mono leading-normal">
                Multi-agent state machines only save outputs if agreement levels cross the custom threshold target.
              </p>
            </div>
          </div>
        </div>

        {/* Step 2: Active Agents toggle checklists */}
        <div className="artistic-pane rounded-xl p-5 text-stone-300 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
          <div className="flex items-center gap-2 mb-3">
            <CheckSquare className="w-4.5 h-4.5 text-white" />
            <span className="text-[11px] font-bold tracking-widest uppercase text-zinc-300">Mesh Agent Allocations</span>
          </div>

          <p className="text-[10.5px] text-zinc-500 mb-4 leading-normal font-mono">
            Toggle which core specialist agent LLM nodes are active in the gossip coordinate:
          </p>

          <div className="space-y-2.5">
            {INITIAL_GENERIC_NODES.map((an) => (
              <label
                id={`agent-checkbox-wrap-${an.id}`}
                key={an.id}
                className={`flex items-center justify-between p-2.5 rounded border text-xs cursor-pointer select-none transition-all ${
                  selectedAgents[an.id]
                    ? 'bg-white/5 border-white/20 text-white'
                    : 'bg-transparent border-white/5 text-zinc-550 hover:border-white/10'
                } ${currentSession ? 'pointer-events-none' : ''}`}
              >
                <div className="flex items-center gap-2.5">
                  <input
                    id={`checkbox-for-${an.id}`}
                    type="checkbox"
                    checked={selectedAgents[an.id]}
                    onChange={(e) =>
                      setSelectedAgents((prev) => ({ ...prev, [an.id]: e.target.checked }))
                    }
                    className="rounded border-white/10 text-white focus:ring-white/20 bg-zinc-950"
                  />
                  <div>
                    <span className="font-extrabold text-[12px]">{an.name}</span>
                    <span className="block text-[9px] text-zinc-500 font-mono italic">{an.model}</span>
                  </div>
                </div>
                <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded border border-white/10 font-mono">
                  {an.avatarText}
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: CORE GRAPH AND BLACKBOARD MULTI-TABS INTERACTIVE LAB */}
      <div id="central-workspace-panels" className="lg:col-span-8 flex flex-col gap-6">
        {/* Setup / Start Session Command Bar */}
        <div className="artistic-pane p-4 rounded-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
          {!currentSession ? (
            <>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded bg-white/5 border border-white/10 flex items-center justify-center animate-pulse">
                  <Cpu className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h4 className="text-zinc-200 font-bold text-xs uppercase tracking-wider">Awaiting Deployment</h4>
                  <p className="text-[10.5px] text-zinc-500">Configure parameters on the left to start</p>
                </div>
              </div>
              <button
                onClick={handleDeployMesh}
                className="px-6 py-2.5 bg-white hover:bg-zinc-200 text-black font-black text-xs uppercase rounded transition-all shadow-[0_4px_20px_rgba(255,255,255,0.15)] hover:scale-[1.01] active:scale-95 cursor-pointer flex items-center gap-2 justify-center"
              >
                <span>Deploy Agent Mesh</span>
                <ChevronRight className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              {/* Active Session Controlling panel */}
              <div className="flex items-center gap-3">
                <span className={`w-3 h-3 rounded-full animate-ping bg-white`} />
                <div>
                  <h4 className="text-zinc-200 font-bold text-xs uppercase tracking-wider flex items-center gap-1.5 font-mono">
                    Session: <span className="text-white font-extrabold">{currentSession.status.toUpperCase()}</span>
                  </h4>
                  <p className="text-[10px] text-zinc-500 font-mono">
                    Round: <span className="font-bold text-zinc-350">{currentSession.currentRound}</span> / {currentSession.maxRounds} • Consensus Tracker: <span className="font-extrabold text-white">{currentSession.consensusPct}%</span>
                  </p>
                </div>
              </div>

              {/* Action buttons list */}
              <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto font-mono">
                {currentSession.status === 'running' && (
                  <button
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="p-2 bg-white/5 hover:bg-white/10 text-zinc-250 hover:text-white rounded border border-white/10 text-xs transition-all flex items-center gap-1.5"
                    title={isPlaying ? 'Pause' : 'Play'}
                  >
                    {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                    <span>{isPlaying ? 'Pause' : 'Resume'}</span>
                  </button>
                )}

                {currentSession.status === 'running' && (
                  <button
                    onClick={handleFastForward}
                    className="p-2 bg-white/5 border border-white/10 hover:bg-white/10 text-white rounded text-xs transition-colors"
                  >
                    ⏩ Skip to Output
                  </button>
                )}

                <button
                  onClick={() => setIsExportOpen(true)}
                  className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded border border-emerald-500/30 text-xs transition-colors flex items-center gap-1.5 cursor-pointer"
                  title="Export Session Summary & Artifacts"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Export & Print</span>
                </button>

                <button
                  onClick={handleResetSession}
                  className="p-2 bg-transparent hover:bg-white/5 text-zinc-400 hover:text-white rounded border border-white/5 text-xs transition-colors flex items-center gap-1"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Reset Workspace</span>
                </button>
              </div>
            </>
          )}
        </div>

        {/* Panel Switcher (For responsive views) */}
        <div className="flex border-b border-white/10 select-none text-zinc-400 font-mono">
          <button
            onClick={() => setActiveTab('topology')}
            className={`px-4 py-3 text-[10px] uppercase font-bold tracking-widest transition-all border-b-2 ${
              activeTab === 'topology'
                ? 'border-white text-white bg-white/5'
                : 'border-transparent hover:text-zinc-200 hover:bg-white/[0.01]'
            }`}
          >
            Topology Web ({activeNodes.length})
          </button>
          
          <button
            onClick={() => setActiveTab('debate')}
            className={`px-4 py-3 text-[10px] uppercase font-bold tracking-widest transition-all border-b-2 ${
              activeTab === 'debate'
                ? 'border-white text-white bg-white/5'
                : 'border-transparent hover:text-zinc-200 hover:bg-white/[0.01]'
            }`}
          >
            Debate Streams ({currentSession?.messages.length || 0})
          </button>

          <button
            onClick={() => setActiveTab('blackboard')}
            className={`px-4 py-3 text-[10px] uppercase font-bold tracking-widest transition-all border-b-2 ${
              activeTab === 'blackboard'
                ? 'border-white text-white bg-white/5'
                : 'border-transparent hover:text-zinc-200 hover:bg-white/[0.01]'
            }`}
          >
            Consensus Blackboard ({currentSession?.files.length || 0})
          </button>
        </div>

        {/* Dynamic Display area */}
        <div id="tabbed-view-ports" className="grid grid-cols-1 gap-6 min-h-[460px]">
          {activeTab === 'topology' && (
            <div className="flex flex-col gap-4">
              <div className="h-[340px] w-full">
                <AgentGraph
                  nodes={activeNodes}
                  activeSenderId={step?.senderId || null}
                  activeReceiverId={step?.receiverId || null}
                  activeMessageType={step?.messageType || null}
                  onNodeClick={handleNodeClick}
                  selectedNodeId={inspectedNode?.id || null}
                />
              </div>

              {/* Mini Node inspected details display */}
              <AnimatePresence>
                {inspectedNode ? (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="artistic-pane p-5 rounded-xl text-xs space-y-4 shadow-xl border border-white/10"
                  >
                    <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-white animate-pulse"></span>
                        <h5 className="font-extrabold text-white text-xs tracking-wider uppercase">{inspectedNode.name} Register</h5>
                      </div>
                      <span className="text-[10px] text-zinc-500 font-mono tracking-wider">{inspectedNode.model}</span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pb-2">
                      <div>
                        <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">Node Role</p>
                        <p className="text-zinc-300 font-bold">{inspectedNode.role}</p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">Temperature</p>
                        <p className="text-zinc-300 font-semibold font-mono">0.65</p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">Memory Buffer</p>
                        <p className="text-zinc-300 font-semibold font-mono">Active (CRDT)</p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">State Code</p>
                        <span className="px-2 py-0.5 bg-white/5 text-zinc-300 border border-white/10 rounded text-[9.5px] uppercase font-bold font-mono inline-block">
                          {inspectedNode.status}
                        </span>
                      </div>
                    </div>

                    <div>
                      <p className="text-[9px] uppercase font-bold tracking-[0.15em] text-zinc-500 mb-1 font-mono">System Prompt Directive</p>
                      <p className="text-zinc-400 text-[10.5px] leading-relaxed italic bg-black/40 p-3 rounded border border-white/5 font-mono">
                        "Implement fail-safe asynchronous consensus. Reject any centralized SPOF design, trigger code refactoring models to ensure self-healing partition endurance..."
                      </p>
                    </div>
                  </motion.div>
                ) : (
                  <div className="text-center p-6 bg-white/[0.01] border border-white/5 rounded-xl text-zinc-500">
                    <p className="text-[11px] font-mono">ℹ️ Click any agent node in the Topology Web above to audit its active telemetry registers</p>
                  </div>
                )}
              </AnimatePresence>
            </div>
          )}

          {activeTab === 'debate' && (
            <div className="h-[460px]">
              <DebateThread messages={currentSession?.messages || []} />
            </div>
          )}

          {activeTab === 'blackboard' && (
            <div className="h-[460px]">
              <Blackboard
                files={currentSession?.files || []}
                currentRound={currentSession?.currentRound || 1}
                maxRounds={currentSession?.maxRounds || 5}
              />
            </div>
          )}
        </div>
      </div>

      <AnimatePresence>
        {isExportOpen && (
          <ExportSessionModal
            isOpen={isExportOpen}
            onClose={() => setIsExportOpen(false)}
            session={currentSession}
            activeNodes={activeNodes}
            consensusThreshold={consensusThreshold}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}
