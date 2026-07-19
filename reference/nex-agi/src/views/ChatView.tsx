import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Send, Users, Bot, Layers, Sparkles, AlertCircle, Plus, 
  Trash2, HelpCircle, HardDrive, Cpu, Paperclip, X, Minimize2, Maximize2 
} from 'lucide-react';
import { SIMULATION_TEMPLATES } from '../data/simulationTemplates';

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  agentName?: string;
  avatarText?: string;
  text: string;
  timestamp: string;
  isDeep?: boolean;
  hasGraph?: boolean;
  files?: string[];
}

export function ChatView({ onExpandToWorkspace }: { onExpandToWorkspace: (presetId?: string) => void }) {
  const [scope, setScope] = useState<'team' | 'single'>('team');
  const [deepCollaborate, setDeepCollaborate] = useState(false);
  const [selectedModel, setSelectedModel] = useState('gemini-2.5-pro');
  const [chats, setChats] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      agentName: 'NEX AGI Co-Ordinator',
      avatarText: 'Nx',
      text: 'Greetings. I can route queries directly to single specialist models or employ a custom Multi-Agent Consensus Team. How would you like to start?',
      timestamp: '11:15 AM'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto Scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chats, isStreaming]);

  // Handle Send
  const handleSend = () => {
    if (!inputValue.trim() && attachments.length === 0) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: inputValue || `Uploaded ${attachments.length} context file(s) for mesh digestion.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      files: attachments.map(f => f.name)
    };

    setChats(prev => [...prev, userMsg]);
    setInputValue('');
    setAttachments([]);
    setIsStreaming(true);

    // Simulate Agent stream answering
    setTimeout(() => {
      let responseText = '';
      let hasGraph = false;

      if (scope === 'team') {
        if (deepCollaborate) {
          responseText = 'INITIATING DEEP CONVERGENCE ROUTINE: Our backend has spawned five specialized nodes to draft, validate, and audit the response. High reliability consensus reached across multiple rounds.';
          hasGraph = true;
        } else {
          responseText = 'LIGHTWEIGHT SYNTHESIS: Architect drafted a fast single-round model blueprint, checked briefly by DevOps. High accessibility cached result has been produced.';
        }
      } else {
        responseText = `SINGLE ENGINE REPORT (${selectedModel}): Direct query processed in 1.4 seconds. No structural debate occurred because team consensus was switched off.`;
      }

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        agentName: scope === 'team' ? 'Consensus Team' : `Model Engine (${selectedModel})`,
        avatarText: scope === 'team' ? 'Swm' : 'Llm',
        text: responseText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isDeep: deepCollaborate && scope === 'team',
        hasGraph: hasGraph
      };

      setChats(prev => [...prev, assistantMsg]);
      setIsStreaming(false);
    }, 2200);
  };

  // Drag and Drop files
  const [isDragActive, setIsDragActive] = useState(false);
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const files = Array.from(e.dataTransfer.files);
      setAttachments(prev => [...prev, ...files]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const files = Array.from(e.target.files);
      setAttachments(prev => [...prev, ...files]);
    }
  };

  const removeAttachment = (index: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-8 space-y-6 flex flex-col h-[calc(100vh-140px)] text-stone-300">
      
      {/* COGNITIVE SCOPE SHIFTER */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-4 gap-4">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#10b981]">CONVERSATIONAL ENGINE</p>
          <h2 className="text-xl font-sans font-black text-white tracking-tight mt-1">Multi-Agent Workspace Composer</h2>
        </div>

        {/* Chat target selectors */}
        <div className="flex items-center gap-1 bg-neutral-900/60 p-1 border border-white/10 rounded-xl">
          <button
            onClick={() => setScope('team')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
              scope === 'team' ? 'bg-[#10b981]/15 text-white border border-[#10b981]/25' : 'text-zinc-500 hover:text-white'
            }`}
          >
            <Users className="w-4 h-4" />
            <span>Autonomous Team</span>
          </button>
          <button
            onClick={() => setScope('single')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
              scope === 'single' ? 'bg-[#10b981]/15 text-white border border-[#10b981]/25' : 'text-zinc-500 hover:text-white'
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>Single LLM Model</span>
          </button>
        </div>
      </div>

      {/* CORE WORKSPACE CONTENT PANEL */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0">
        
        {/* VIEWPORT THREAD */}
        <div className="lg:col-span-8 flex flex-col justify-between border border-white/10 rounded-2xl bg-[#09090b]/80 overflow-hidden relative">
          
          {/* Thread messages container */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {chats.map((chat) => (
              <motion.div
                key={chat.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-4 ${chat.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* Agent Avatar */}
                {chat.sender === 'assistant' && (
                  <div className="w-8 h-8 rounded bg-[#10b981]/10 border border-[#10b981]/25 flex items-center justify-center text-[#10b981] font-mono text-xs font-extrabold shrink-0">
                    {chat.avatarText}
                  </div>
                )}

                {/* Msg Content */}
                <div className={`max-w-[80%] rounded-2xl p-4 text-xs leading-relaxed border ${
                  chat.sender === 'user' 
                    ? 'bg-neutral-900 border-white/5 text-stone-200 rounded-tr-none' 
                    : 'bg-white/[0.01] border-white/10 text-stone-100 rounded-tl-none'
                }`}>
                  <div className="flex items-center justify-between gap-4 mb-1.5 border-b border-white/5 pb-1">
                    <span className="font-bold uppercase tracking-wider font-mono text-[10px] text-zinc-400">
                      {chat.sender === 'user' ? 'USER ADVISOR' : chat.agentName}
                    </span>
                    <span className="text-[9px] text-zinc-600 font-mono">{chat.timestamp}</span>
                  </div>
                  
                  <p className="font-sans leading-relaxed text-zinc-350">{chat.text}</p>

                  {/* Attachment labels if present */}
                  {chat.files && chat.files.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-white/5">
                      {chat.files.map((filename, i) => (
                        <span key={i} className="inline-flex items-center gap-1.5 bg-neutral-800 border border-white/10 text-neutral-300 text-[9px] font-mono px-2 py-0.5 rounded-md">
                          <Paperclip className="w-2.5 h-2.5" />
                          <span>{filename}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* EXPAND AFFORDANCE IF CONVERGING TO WORKSPACE */}
                  {chat.hasGraph && (
                    <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-[10px] font-mono text-[#10b981]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                        <span>Mesh Debate Recorded</span>
                      </div>
                      <button 
                        onClick={() => onExpandToWorkspace('rate-limiter')}
                        className="px-3 py-1.5 bg-[#10b981] hover:bg-emerald-600 text-black text-[10px] font-mono font-extrabold tracking-widest uppercase rounded transition-all cursor-pointer"
                      >
                        EXPLORE MESH SESSION
                      </button>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}

            {/* Simulated Streaming Pulse */}
            {isStreaming && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-[#10b981] font-mono text-xs font-black shrink-0 animate-pulse">
                  ••
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.01] border border-white/10 text-xs font-mono text-zinc-400 max-w-[40%] animate-pulse">
                  Connecting to node cloud. Processing consensus rules...
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* DRAG OVERLAY */}
          {isDragActive && (
            <div 
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              className="absolute inset-0 bg-[#050506]/90 border-2 border-dashed border-[#10b981] z-20 flex flex-col items-center justify-center p-6 text-center text-[#10b981] backdrop-blur-sm"
            >
              <Paperclip className="w-10 h-10 mb-3 animate-bounce" />
              <p className="font-bold text-sm tracking-widest uppercase">Release to Upload Context Files</p>
              <p className="text-xs text-zinc-500 mt-1">Files will be buffered for multi-agent synthesis digestion.</p>
            </div>
          )}

          {/* ATTACHMENT CHIPS PREVIEW AND COMPOSER INPUT */}
          <div className="p-4 border-t border-white/10 bg-[#060608]/90">
            {/* Attachment preview panel */}
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {attachments.map((file, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 bg-neutral-900 border border-white/10 text-stone-300 text-[10px] font-mono px-2.5 py-1 rounded-lg">
                    <Paperclip className="w-3 h-3 text-emerald-400" />
                    <span className="truncate max-w-[120px]">{file.name}</span>
                    <button onClick={() => removeAttachment(i)} className="text-zinc-500 hover:text-white transition">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3 bg-neutral-900 border border-white/10 rounded-xl px-3 py-1.5 focus-within:border-[#10b981]/40 transition-all">
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileSelect} 
                multiple 
                className="hidden" 
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 hover:bg-white/5 text-zinc-400 hover:text-white rounded-lg transition shrink-0"
                title="Attach context file(s)"
              >
                <Paperclip className="w-4 h-4" />
              </button>

              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder={scope === 'team' ? "State software design goal for consensus team..." : "Direct query single model..."}
                className="flex-1 bg-transparent text-xs text-white placeholder-zinc-500 focus:outline-none min-w-0"
              />

              <button
                onClick={handleSend}
                className="p-2 bg-white hover:bg-zinc-200 text-black rounded-lg transition shrink-0 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* SIDEBAR: CONTEXT CONFIG RULES */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="p-5 rounded-2xl bg-[#09090b]/80 border border-white/10 space-y-5">
            <div>
              <p className="text-[9.5px] font-mono tracking-widest text-[#10b981] uppercase">SESSION PARAMETERS</p>
              <h3 className="text-sm font-bold text-white mt-1">Digestion Setup & Controls</h3>
            </div>

            {scope === 'team' ? (
              <div className="space-y-4">
                {/* Deep Collaborate Switch */}
                <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold font-sans text-neutral-200">DEEP COLLABORATE</span>
                    <input 
                      type="checkbox"
                      checked={deepCollaborate}
                      onChange={(e) => setDeepCollaborate(e.target.checked)}
                      className="accent-[#10b981] h-3.5 w-3.5 cursor-pointer rounded"
                    />
                  </div>
                  <p className="text-[10px] text-zinc-500 leading-normal">
                    When active, specialized agents spin up in multiple rounds, generating mutual critique benchmarks and optimizing reliability.
                  </p>
                </div>

                <div className="text-[10.5px] text-zinc-450 font-mono space-y-1.5 leading-normal">
                  <p className="font-bold text-zinc-300">Active Multi-Agent Swarm:</p>
                  <p>• Orchestrator (Router/Integrator)</p>
                  <p>• Creative Architect (Design Blueprints)</p>
                  <p>• Strict Reviewer (Security & Pitfalls)</p>
                  <p>• Pedantic QA (Robust Edge Cases)</p>
                  <p>• Zero-latency DevOps (Final Builds)</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Model Catalogs Selector */}
                <div className="space-y-2">
                  <label className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">Model Selection</label>
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="w-full bg-neutral-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none"
                  >
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (Extreme logic)</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Ultra low latency)</option>
                    <option value="claude-3.5-sonnet">Claude 3.5 Sonnet</option>
                    <option value="gpt-4o">GPT-4o Engine</option>
                  </select>
                </div>

                <p className="text-[10.5px] text-zinc-500 leading-normal font-mono">
                  Single Model Engine bypasses peer reviews. Suitable for quick explanations, basic translations, and flat syntax conversions.
                </p>
              </div>
            )}
          </div>

          <div className="p-4 bg-[#10b981]/5 border border-[#10b981]/15 rounded-xl text-[10px] leading-relaxed text-zinc-400 font-mono">
            <strong>Pro Tip:</strong> Drag and drop any software code snippet or architecture manifest directly onto the chat window to seed context files transiently.
          </div>
        </div>
      </div>
    </div>
  );
}
