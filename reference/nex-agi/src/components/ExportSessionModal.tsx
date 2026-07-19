import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  X, 
  Download, 
  Printer, 
  Copy, 
  Check, 
  FileJson, 
  FileText, 
  Cpu, 
  Clock, 
  Award, 
  Terminal, 
  ExternalLink,
  ShieldAlert,
  Sliders,
  Sparkles
} from 'lucide-react';
import { Session, AgentNode } from '../types';

interface ExportSessionModalProps {
  isOpen: boolean;
  onClose: () => void;
  session: Session | null;
  activeNodes: AgentNode[];
  consensusThreshold: number;
}

export function ExportSessionModal({ 
  isOpen, 
  onClose, 
  session, 
  activeNodes,
  consensusThreshold
}: ExportSessionModalProps) {
  const [activeTab, setActiveTab] = useState<'json' | 'preview'>('preview');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen || !session) return null;

  // Prepare full-context session export payload
  const exportPayload = {
    exportMetadata: {
      exportedAt: new Date().toISOString(),
      platform: "NEX AGI SYSTEM",
      protocolVersion: "v1.4.2"
    },
    session: {
      id: session.id,
      goal: session.goal,
      timestamp: session.timestamp,
      status: session.status,
      consensusPct: session.consensusPct,
      consensusThresholdPct: consensusThreshold,
      agentsPresetName: session.agentsPreset,
      allocatedAgents: activeNodes.map(an => ({
        id: an.id,
        name: an.name,
        role: an.role,
        model: an.model,
        avatarText: an.avatarText
      })),
      debateLogs: session.messages.map(msg => ({
        round: msg.round,
        agent: msg.senderName,
        agentId: msg.senderId,
        type: msg.type,
        actionBadge: msg.badgeLabel,
        contribution: msg.text,
        time: msg.timestamp
      })),
      blackboardArtifacts: session.files.map(file => ({
        filename: file.filename,
        language: file.language,
        code: file.code
      }))
    }
  };

  const jsonString = JSON.stringify(exportPayload, null, 2);

  // Download Action Logic
  const handleDownloadJSON = () => {
    try {
      const blob = new Blob([jsonString], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `nexagi-session-${session.id}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to dispatch download trigger', err);
    }
  };

  // Copy to Clipboard Action
  const handleCopyClipboard = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Print Summary Page Action
  const handlePrint = () => {
    window.print();
  };

  return (
    <>
      {/* Styles for direct print-to-PDF output styling with proper layouts */}
      <style>{`
        @media print {
          /* Hide overall workspace page elements completely */
          body * {
            visibility: hidden;
            background: transparent !important;
          }
          /* Isolate exactly our active printable summary block */
          #print-session-summary-area, #print-session-summary-area * {
            visibility: visible;
          }
          #print-session-summary-area {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            display: block !important;
            background: #ffffff !important;
            color: #0d0d0f !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
            padding: 30px !important;
          }
          .no-print {
            display: none !important;
          }
          /* Render crisp headers and page-breaks cleanly */
          .print-section {
            page-break-inside: avoid;
            margin-bottom: 25px;
            border-bottom: 1px solid #e4e4e7;
            padding-bottom: 15px;
          }
          .print-header {
            border-bottom: 3px double #18181b;
            padding-bottom: 15px;
            margin-bottom: 25px;
          }
          .print-badge {
            font-family: monospace;
            border: 1px solid #71717a;
            padding: 2px 6px;
            font-size: 10px;
          }
          .print-code {
            background-color: #f4f4f5 !important;
            border: 1px solid #e4e4e7 !important;
            color: #18181b !important;
            padding: 12px !important;
            font-family: monospace !important;
            font-size: 10px !important;
            white-space: pre-wrap !important;
            border-radius: 4px;
          }
        }
      `}</style>

      {/* Screen Interactive Backdrop Modal */}
      <div id="export-backdrop-overlay" className="fixed inset-0 bg-[#000]/80 backdrop-blur-md z-50 flex items-center justify-center p-4">
        <motion.div
          id="export-modal-panel"
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          className="bg-[#0b0c0e] border border-white/10 rounded-2xl w-full max-w-5xl h-[88vh] flex flex-col overflow-hidden text-zinc-300 shadow-[0_24px_60px_rgba(0,0,0,0.85)]"
        >
          {/* Header Bar */}
          <div className="p-5 border-b border-white/10 flex items-center justify-between bg-[#0e1013]">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <ExternalLink className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-white font-bold font-display text-sm uppercase tracking-wider">AGI Session Export Terminal</h3>
                <p className="text-[10px] text-zinc-500 font-mono">ID: {session.id}</p>
              </div>
            </div>
            
            {/* Action control bar */}
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="p-1.5 hover:bg-white/10 rounded-lg text-zinc-400 hover:text-white transition-all cursor-pointer"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Sub-Header Menu Tabs */}
          <div className="px-5 py-2 border-b border-white/5 bg-[#090a0c] flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-1 font-mono text-[11px]">
              <button
                onClick={() => setActiveTab('preview')}
                className={`px-3 py-1.5 rounded transition-all flex items-center gap-1.5 ${
                  activeTab === 'preview'
                    ? 'bg-white/10 text-white font-bold border border-white/10'
                    : 'text-zinc-500 hover:text-zinc-350 bg-transparent border border-transparent'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Document Abstract</span>
              </button>

              <button
                onClick={() => setActiveTab('json')}
                className={`px-3 py-1.5 rounded transition-all flex items-center gap-1.5 ${
                  activeTab === 'json'
                    ? 'bg-white/10 text-white font-bold border border-white/10'
                    : 'text-zinc-500 hover:text-zinc-350 bg-transparent border border-transparent'
                }`}
              >
                <FileJson className="w-3.5 h-3.5" />
                <span>Structured JSON Payload</span>
              </button>
            </div>

            {/* Quick Export triggers */}
            <div className="flex items-center gap-2 font-mono text-[11px]">
              {activeTab === 'json' && (
                <button
                  onClick={handleCopyClipboard}
                  className="px-3 py-1.5 bg-zinc-900 border border-white/10 text-zinc-300 hover:text-white rounded-lg hover:bg-zinc-800 hover:border-white/20 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? 'Copied Payloads' : 'Copy JSON'}</span>
                </button>
              )}

              <button
                onClick={handleDownloadJSON}
                className="px-3 py-1.5 bg-zinc-900 border border-white/10 text-zinc-300 hover:text-white rounded-lg hover:bg-zinc-800 hover:border-white/20 transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Save JSON File</span>
              </button>

              <button
                onClick={handlePrint}
                className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Printer className="w-3.5 h-3.5" />
                <span>Print or Export PDF</span>
              </button>
            </div>
          </div>

          {/* Interactive Modal Content Body */}
          <div className="flex-1 overflow-y-auto p-6 bg-[#07080a]" id="screen-interactive-viewer">
            
            {activeTab === 'json' ? (
              <div className="relative h-full">
                {/* Syntax styled interactive block container */}
                <div className="font-mono text-[11px] leading-relaxed bg-[#0c0d10] border border-white/5 p-5 rounded-xl h-full overflow-auto select-all text-emerald-400/90 shadow-inner">
                  <pre className="whitespace-pre-wrap text-zinc-300">{jsonString}</pre>
                </div>
              </div>
            ) : (
              /* High Fidelity Dark-themed aesthetic Document Abstract */
              <div id="interactive-abstract-pane" className="space-y-8 max-w-4xl mx-auto py-2">
                {/* Simulated Document Watermark / Header */}
                <div className="border border-white/10 bg-zinc-950/40 rounded-2xl p-6 relative overflow-hidden">
                  
                  {/* Decorative design line */}
                  <div className="w-full h-[1px] bg-gradient-to-r from-emerald-500/0 via-emerald-500/30 to-emerald-500/0 mb-6" />

                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[10px] font-mono tracking-[0.25em] text-emerald-400 uppercase font-bold">NEXUS AGENTIC CORE REPORT</span>
                        <span className="text-[9px] font-mono bg-zinc-900 border border-white/10 px-1.5 py-0.5 rounded text-zinc-400">SECURE ABSTRACT</span>
                      </div>
                      <h4 className="text-xl font-bold font-display text-white tracking-tight">{session.goal}</h4>
                      <p className="text-zinc-550 text-xs font-mono mt-1">GOSSIP PROTOCOL MATRIX OUTPUT DETAILS</p>
                    </div>

                    <div className="text-left md:text-right font-mono self-start md:self-auto shrink-0 border-l md:border-l-0 md:border-r border-white/10 pl-4 md:pl-0 md:pr-4">
                      <p className="text-[9.5px] uppercase text-zinc-500 font-bold tracking-wider">Consensus Cross-over</p>
                      <p className="text-2xl font-black text-white">{session.consensusPct}%</p>
                      <p className="text-[9px] text-zinc-500">Threshold Setup: {consensusThreshold}%</p>
                    </div>
                  </div>

                  {/* Quick summary grid metadata */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8 pt-6 border-t border-white/10 font-mono text-[10px]">
                    <div>
                      <span className="text-zinc-500 uppercase block mb-1">Session Reference</span>
                      <span className="text-zinc-350 font-bold truncate block">{session.id}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 uppercase block mb-1">Timestamp Register</span>
                      <span className="text-zinc-350 font-bold block">{session.timestamp}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 uppercase block mb-1">Active Specialist Group</span>
                      <span className="text-zinc-350 font-bold block">{session.agentsPreset}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 uppercase block mb-1">Gossip Rounds</span>
                      <span className="text-zinc-350 font-bold block">{session.currentRound} / {session.maxRounds}</span>
                    </div>
                  </div>
                </div>

                {/* Section 1: Active Specialist Network Allocations */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 border-b border-white/10 pb-2">
                    <Cpu className="w-4 h-4 text-emerald-400" />
                    <h5 className="text-[11px] font-bold tracking-widest text-[#ececec] uppercase font-mono">1. Allocated Network Nodes</h5>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                    {activeNodes.map(node => (
                      <div key={node.id} className="p-3 bg-zinc-950/50 border border-white/5 rounded-xl flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center font-mono font-bold text-xs text-white border border-white/10 shrink-0">
                          {node.avatarText}
                        </div>
                        <div className="min-w-0">
                          <p className="text-white text-xs font-bold truncate">{node.name}</p>
                          <p className="text-zinc-500 text-[9.5px] truncate font-mono">{node.model}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 2: Complete Debate Logs Timeline */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 border-b border-white/10 pb-2">
                    <Clock className="w-4 h-4 text-emerald-400" />
                    <h5 className="text-[11px] font-bold tracking-widest text-[#ececec] uppercase font-mono">2. Multi-Agent Communication Trace</h5>
                  </div>
                  
                  <div className="space-y-3 font-mono">
                    {session.messages.length === 0 ? (
                      <p className="text-xs text-zinc-550 italic p-3 text-center bg-white/[0.01] rounded-lg">No active gossip exchanges initialized in this session frame.</p>
                    ) : (
                      session.messages.map((msg, index) => (
                        <div key={msg.id || index} className="p-4 bg-zinc-950/40 border border-white/5 rounded-xl space-y-2 text-[11px]">
                          <div className="flex items-center justify-between gap-2 text-[10px] pb-1 border-b border-white/5">
                            <div className="flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: msg.agentColor || '#ffffff', boxShadow: `0 0 6px ${msg.agentColor || '#ffffff'}` }} />
                              <span className="text-white font-extrabold uppercase">{msg.senderName}</span>
                              <span className="text-[9px] bg-white/5 px-2 py-0.5 rounded border border-white/10 text-zinc-400 font-bold uppercase tracking-wider">
                                {msg.badgeLabel || msg.type.toUpperCase()}
                              </span>
                            </div>
                            <div className="text-zinc-500">
                              Round {msg.round} • {msg.timestamp}
                            </div>
                          </div>
                          <p className="text-zinc-300 leading-relaxed font-sans mt-2 whitespace-pre-wrap">{msg.text}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Section 3: Final Saved Output Consensus Code files */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 border-b border-white/10 pb-2">
                    <Award className="w-4 h-4 text-emerald-400" />
                    <h5 className="text-[11px] font-bold tracking-widest text-[#ececec] uppercase font-mono">3. Output Artifacts on Blackboard</h5>
                  </div>

                  <div className="space-y-4">
                    {session.files.length === 0 ? (
                      <p className="text-xs text-zinc-550 italic p-3 text-center bg-white/[0.01] rounded-lg">No finalized model files stored on the consensus Blackboard.</p>
                    ) : (
                      session.files.map((file, idx) => (
                        <div key={file.filename || idx} className="border border-white/10 rounded-xl overflow-hidden">
                          <div className="bg-[#0e1013] px-4 py-2 border-b border-white/5 flex items-center justify-between font-mono text-[10px]">
                            <span className="text-white font-bold">{file.filename}</span>
                            <span className="text-zinc-550 text-[9px] uppercase tracking-wider">{file.language}</span>
                          </div>
                          <pre className="bg-[#050608] p-4 text-[10px] text-zinc-300 font-mono overflow-x-auto leading-relaxed whitespace-pre select-all border-none">
                            <code>{file.code}</code>
                          </pre>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}

          </div>
        </motion.div>
      </div>

      {/* STATIC OFFLINE HIDDEN COMPONENT DEDICATED SOLELY FOR PRINTER DIALOG CODES (EXULTED HIGH DESIGN) */}
      <div id="print-session-summary-area" className="hidden">
        <div className="print-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '24px', letterSpacing: '-0.02em', textTransform: 'uppercase' }}>NEX AGI SYSTEM WORKFLOW REPORT</h1>
              <p style={{ margin: '4px 0 0 0', fontFamily: 'monospace', fontSize: '11px', color: '#555' }}>MULTIPARTY AGENTIC CONSENSUS SPECIFICATION RECORD</p>
            </div>
            <div style={{ textAlign: 'right', fontFamily: 'monospace' }}>
              <p style={{ margin: 0, fontSize: '11px' }}>SYSTEM TARGET ID: <strong>{session.id}</strong></p>
              <p style={{ margin: '2px 0 0 0', fontSize: '11px' }}>TIMESTAMP: {session.timestamp}</p>
            </div>
          </div>
        </div>

        <div className="print-section">
          <h3 style={{ fontSize: '14px', textTransform: 'uppercase', margin: '0 0 10px 0', borderBottom: '1px solid #000', paddingBottom: '3px' }}>Target Mission Goal</h3>
          <p style={{ fontSize: '13px', margin: '5px 0 10px 0', fontWeight: 'bold', color: '#111' }}>{session.goal}</p>
          
          <table style={{ width: '100%', fontSize: '11px', fontFamily: 'monospace', borderCollapse: 'collapse', marginTop: '15px' }}>
            <tbody>
              <tr>
                <td style={{ padding: '4px 0', width: '30%', color: '#666' }}>COORDINATED TEAM PRESET:</td>
                <td style={{ padding: '4px 0', fontWeight: 'bold' }}>{session.agentsPreset}</td>
                <td style={{ padding: '4px 0', width: '25%', color: '#666' }}>FINAL RATIO REACHED:</td>
                <td style={{ padding: '4px 0', fontWeight: 'bold', fontSize: '13px' }}>{session.consensusPct}% consensus</td>
              </tr>
              <tr>
                <td style={{ padding: '4px 0', color: '#666' }}>DECISION THRESHOLD:</td>
                <td style={{ padding: '4px 0', fontWeight: 'bold' }}>{consensusThreshold}%</td>
                <td style={{ padding: '4px 0', color: '#666' }}>GOSSIP TIMELINE DEPTH:</td>
                <td style={{ padding: '4px 0', fontWeight: 'bold' }}>{session.currentRound} Rounds Completed</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="print-section">
          <h3 style={{ fontSize: '13px', textTransform: 'uppercase', margin: '0 0 10px 0', borderBottom: '1px solid #999', paddingBottom: '3px' }}>1. Configured Agent Nodes</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
            {activeNodes.map(node => (
              <div key={node.id} style={{ border: '1px solid #ccc', padding: '8px', borderRadius: '4px' }}>
                <strong style={{ fontSize: '11px', display: 'block' }}>{node.name}</strong>
                <span style={{ fontSize: '9px', color: '#666', fontFamily: 'monospace' }}>Role: {node.role} ({node.model})</span>
              </div>
            ))}
          </div>
        </div>

        <div className="print-section">
          <h3 style={{ fontSize: '13px', textTransform: 'uppercase', margin: '20px 0 10px 0', borderBottom: '1px solid #999', paddingBottom: '3px' }}>2. Gossip Debate Sequences</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {session.messages.map((msg, index) => (
              <div key={msg.id || index} style={{ borderBottom: '1px dashed #ddd', paddingBottom: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', fontFamily: 'monospace', color: '#555', marginBottom: '4px' }}>
                  <span><strong>{msg.senderName}</strong> <span className="print-badge">{msg.badgeLabel || msg.type.toUpperCase()}</span></span>
                  <span>Round {msg.round} • {msg.timestamp}</span>
                </div>
                <p style={{ fontSize: '11px', margin: 0, lineHeight: '1.4', color: '#333' }}>{msg.text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="print-section" style={{ pageBreakBefore: 'always' }}>
          <h3 style={{ fontSize: '13px', textTransform: 'uppercase', margin: '0 0 10px 0', borderBottom: '1px solid #999', paddingBottom: '3px' }}>3. Finalized Blackboard Artifacts (Source Code)</h3>
          {session.files.map((file, idx) => (
            <div key={file.filename || idx} style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '10px', fontFamily: 'monospace', background: '#eee', padding: '4px 8px', fontWeight: 'bold' }}>
                Artifact Filename: {file.filename} ({file.language})
              </div>
              <pre className="print-code">{file.code}</pre>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
