import { useEffect, useRef } from 'react';
import { DebateMessage } from '../types';
import { motion, AnimatePresence } from 'motion/react';
import { Flame, MessageSquareOff, HelpCircle, Terminal, RefreshCw, Sparkles } from 'lucide-react';

interface DebateThreadProps {
  messages: DebateMessage[];
}

export function DebateThread({ messages }: DebateThreadProps) {
  const debateContainerRef = useRef<HTMLDivElement>(null);

  // Auto scroll debate log to bottom when messages list expands
  useEffect(() => {
    if (debateContainerRef.current) {
      debateContainerRef.current.scrollTo({
        top: debateContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages.length]);

  // Color map for message badges
  const getBadgeStyle = (type: DebateMessage['type']) => {
    switch (type) {
      case 'propose':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25';
      case 'critique':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/25';
      case 'endorse':
        return 'bg-green-500/12 text-green-400 border-green-500/25';
      case 'reply':
        return 'bg-sky-500/10 text-sky-400 border-sky-500/25';
      default:
        return 'bg-zinc-800 text-zinc-400 border-zinc-700';
    }
  };

  const getAgentTextColor = (color: string | undefined) => {
    if (!color) return 'text-zinc-300';
    if (color === '#10b981') return 'text-emerald-400';
    if (color === '#ef4444') return 'text-rose-400';
    if (color === '#22c55e') return 'text-green-400';
    if (color === '#f59e0b') return 'text-amber-400';
    return 'text-sky-400';
  };

  return (
    <div id="debate-thread-panel-root" className="w-full h-full bg-[#18181b] rounded-xl border border-[#27272a] overflow-hidden flex flex-col">
      {/* Debate Header */}
      <div className="px-4 py-3 border-b border-[#27272a] flex items-center justify-between bg-[#111113]">
        <div className="flex items-center gap-2">
          <Flame className="w-4 h-4 text-emerald-400 animate-pulse" />
          <span className="text-[11px] font-bold tracking-wider text-zinc-400 uppercase">Debate Thread</span>
        </div>
        <div className="flex items-center gap-1.5 text-[9px] text-zinc-500 bg-zinc-800/60 px-2 py-0.5 rounded-full font-mono">
          <Terminal className="w-3 h-3" />
          <span>Active Log</span>
        </div>
      </div>

      {/* Message Stream */}
      <div
        id="debate-chat-stream"
        ref={debateContainerRef}
        className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent min-h-[220px]"
      >
        <AnimatePresence initial={false}>
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 my-auto">
              <MessageSquareOff className="w-8 h-8 opacity-20 mb-2" />
              <p className="text-xs">No active discussions cataloged</p>
              <p className="text-[10px] text-zinc-600 mt-1">Deploy AGI agents to initiate live session synthesis</p>
            </div>
          ) : (
            messages.map((message, index) => (
              <motion.div
                id={`debate-message-${message.id}`}
                key={message.id}
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className={`p-3 rounded-lg border bg-[#111113]/70 transition-colors ${
                  message.type === 'critique'
                    ? 'border-rose-900/30 hover:border-rose-800/40'
                    : message.type === 'endorse'
                    ? 'border-green-900/30 hover:border-green-800/40'
                    : 'border-zinc-800/80 hover:border-zinc-700/80'
                }`}
              >
                {/* Message Meta Info */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[11px] font-semibold ${getAgentTextColor(message.agentColor)}`}>
                      {message.senderName}
                    </span>
                    <span className="text-[9px] text-zinc-600 font-mono">Round {message.round}</span>
                  </div>
                  <span className={`text-[8px] px-1.5 py-0.5 rounded-full border font-mono font-bold uppercase transition-all ${getBadgeStyle(message.type)}`}>
                    {message.badgeLabel}
                  </span>
                </div>

                {/* Body Message content */}
                <p className="text-[11.5px] leading-relaxed text-zinc-300 font-sans tracking-wide">
                  {message.text}
                </p>

                {/* Small timestamp */}
                <div className="flex justify-end mt-1 text-[8px] text-zinc-600 font-mono">
                  {message.timestamp}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Consensus quick bar */}
      {messages.length > 0 && (
        <div className="bg-[#111113] p-1.5 px-3 border-t border-[#27272a] flex items-center justify-between text-[10px] text-zinc-500 font-mono">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-amber-500 animate-spin" style={{ animationDuration: '3s' }} />
            <span>NEX Event Event-Bus synchronizing</span>
          </div>
          <span>Active</span>
        </div>
      )}
    </div>
  );
}
