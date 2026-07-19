import { useState } from 'react';
import { GeneratedFile } from '../types';
import { FileCode, Clipboard, Check, Terminal, ExternalLink, RefreshCw, Layers } from 'lucide-react';

interface BlackboardProps {
  files: GeneratedFile[];
  currentRound: number;
  maxRounds: number;
}

export function Blackboard({ files, currentRound, maxRounds }: BlackboardProps) {
  const [activeFileIndex, setActiveFileIndex] = useState(0);
  const [copied, setCopied] = useState(false);

  const activeFile = files[activeFileIndex] || null;

  const handleCopy = () => {
    if (!activeFile) return;
    navigator.clipboard.writeText(activeFile.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Format code display with line numbers and stylized block tags
  const renderCodeLines = (code: string) => {
    return code.split('\n').map((line, idx) => (
      <div key={idx} className="table-row text-[11.5px] font-mono leading-7 select-text">
        <span className="table-cell text-right pr-4 text-zinc-650 opacity-45 select-none w-10 text-[10.5px]">
          {idx + 1}
        </span>
        <span className="table-cell whitespace-pre text-zinc-200">
          {highlightSyntax(line)}
        </span>
      </div>
    ));
  };

  // Extremely basic dark syntax styling highlighter to look eye-catchy
  const highlightSyntax = (line: string) => {
    if (line.trim().startsWith('#') || line.trim().startsWith('//') || line.trim().startsWith('/*')) {
      return <span className="text-zinc-550 italic">{line}</span>;
    }

    // Capture typical keywords
    const keywords = /\b(def|class|import|from|return|import|const|let|function|async|await|interface|export|type|public|private)\b/g;
    const strings = /("(.*?)"|'(.*?)')/g;
    const types = /\b(int|string|bool|void|any|number|boolean|RedisClient|Promise|Config|Client)\b/g;

    // React JSX formatting
    let parts: any[] = [line];
    return <span className="text-zinc-300">{line}</span>; // Keep as crisp flat color, or subtle highlight to avoid overhead
  };

  return (
    <div id="blackboard-workspace-root" className="w-full bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden flex flex-col h-full">
      {/* Blackboard Title Bar */}
      <div className="px-4 py-3 border-b border-[#27272a]/80 bg-[#18181b] flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-emerald-400" />
          <div>
            <h4 className="text-[12px] font-bold text-zinc-200 tracking-wide uppercase">Blackboard Output Workspace</h4>
            <p className="text-[9.5px] text-zinc-500 font-mono">Consensus State Directory</p>
          </div>
        </div>

        {/* Action controllers */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#18181b] text-[9.5px] text-zinc-400 border border-[#27272a]/60 font-mono">
            <span>Round Scrubber:</span>
            <span className="text-emerald-400 font-bold">{currentRound}</span>
            <span className="text-zinc-600">/</span>
            <span className="text-zinc-500">{maxRounds}</span>
          </div>

          <button
            onClick={handleCopy}
            disabled={!activeFile}
            className="flex items-center gap-1.5 px-2.5 py-1 text-[10.5px] font-medium text-zinc-300 bg-[#27272a]/60 hover:bg-[#27272a] border border-[#27272a] rounded-lg transition-all active:scale-95 disabled:pointer-events-none disabled:opacity-40"
            title="Copy Generated Code File"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-green-400 animate-scale" />
                <span className="text-green-400 text-[10px]">Copied</span>
              </>
            ) : (
              <>
                <Clipboard className="w-3.5 h-3.5" />
                <span className="text-[10px]">Copy code</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Shared Directory tab selection bar */}
      {files.length > 0 ? (
        <div className="flex items-center gap-1.5 px-3 py-2 bg-[#09090b]/40 border-b border-[#27272a]/40 overflow-x-auto select-none">
          {files.map((file, idx) => (
            <button
              id={`blackboard-file-tab-${idx}`}
              key={file.filename}
              onClick={() => setActiveFileIndex(idx)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono border transition-all ${
                idx === activeFileIndex
                  ? 'bg-[#18181b] text-emerald-400 border-[#27272a] shadow-sm'
                  : 'bg-transparent text-zinc-500 border-transparent hover:text-zinc-300'
              }`}
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>{file.filename}</span>
            </button>
          ))}
        </div>
      ) : null}

      {/* Code Editor Frame */}
      <div className="flex-1 bg-[#09090b] overflow-y-auto p-4 flex flex-col justify-between min-h-[260px] max-h-[500px]">
        {activeFile ? (
          <div className="table w-full border-collapse">
            {renderCodeLines(activeFile.code)}
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center text-zinc-500 p-8 my-auto">
            <Terminal className="w-10 h-10 opacity-20 mb-3" />
            <h5 className="text-zinc-300 text-xs font-semibold mb-1">Dormant Output Canvas</h5>
            <p className="text-[10px] text-zinc-650 max-w-[280px]">
              The shared workspace expands dynamically with synthesised blueprints when consensus is initiated.
            </p>
          </div>
        )}
      </div>

      {/* Terminal Footer Indicator */}
      {activeFile && (
        <div className="px-4 py-2 border-t border-[#27272a]/80 bg-[#18181b] flex items-center justify-between text-[10px] text-zinc-500 font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>Synthesizer Workspace synced: {activeFile.language} format</span>
          </div>
          <span className="text-[9px] text-zinc-600">ReadOnly Buffer</span>
        </div>
      )}
    </div>
  );
}
