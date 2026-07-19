import { useState } from 'react';
import { InferenceProfile } from '../types';
import { Sliders, Cpu, Save, RotateCcw, AlertCircle, Sparkles, Check, Info } from 'lucide-react';
import { motion } from 'motion/react';

export function InferenceProfilesView() {
  const [profiles, setProfiles] = useState<InferenceProfile[]>([
    {
      id: 'architect',
      name: 'Creative Architect',
      provider: 'Anthropic',
      model: 'claude-3.5-sonnet',
      temperature: 0.7,
      topP: 0.85,
      reasoningLevel: 'high',
      description: 'Responsible for high-level software blueprints, design patterns, and structural layout.',
    },
    {
      id: 'reviewer',
      name: 'Strict Reviewer',
      provider: 'Gemini',
      model: 'gemini-2.5-pro',
      temperature: 0.2,
      topP: 0.9,
      reasoningLevel: 'high',
      description: 'Audits proposed designs against security constraints, scalability bottlenecks, and architectural traps.',
    },
    {
      id: 'qa',
      name: 'Pedantic QA Tester',
      provider: 'OpenAI',
      model: 'gpt-4o',
      temperature: 0.1,
      topP: 0.95,
      reasoningLevel: 'medium',
      description: 'Validates code robustness with automated partition simulations, stress testing boundaries.',
    },
    {
      id: 'devops',
      name: 'Zero-Latency DevOps',
      provider: 'Ollama',
      model: 'llama3.1-70b',
      temperature: 0.4,
      topP: 0.8,
      reasoningLevel: 'low',
      description: 'Compiles final deliverables, configures YAML deployments, and monitors package compatibility.',
    },
  ]);

  const [activeProfileId, setActiveProfileId] = useState('architect');
  const [savedSuccess, setSavedSuccess] = useState(false);

  const activeProfile = profiles.find((p) => p.id === activeProfileId) || profiles[0];

  const handleUpdateField = (field: keyof InferenceProfile, value: any) => {
    setProfiles((prev) =>
      prev.map((p) => (p.id === activeProfile.id ? { ...p, [field]: value } : p))
    );
  };

  const handleSave = () => {
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  const handleReset = () => {
    // Revert back to original defaults
    setProfiles([
      {
        id: 'architect',
        name: 'Creative Architect',
        provider: 'Anthropic',
        model: 'claude-3.5-sonnet',
        temperature: 0.7,
        topP: 0.85,
        reasoningLevel: 'high',
        description: 'Responsible for high-level software blueprints, design patterns, and structural layout.',
      },
      {
        id: 'reviewer',
        name: 'Strict Reviewer',
        provider: 'Gemini',
        model: 'gemini-2.5-pro',
        temperature: 0.2,
        topP: 0.9,
        reasoningLevel: 'high',
        description: 'Audits proposed designs against security constraints, scalability bottlenecks, and security traps.',
      },
      {
        id: 'qa',
        name: 'Pedantic QA Tester',
        provider: 'OpenAI',
        model: 'gpt-4o',
        temperature: 0.1,
        topP: 0.95,
        reasoningLevel: 'medium',
        description: 'Validates code robustness with automated partition simulations, stress testing boundaries.',
      },
      {
        id: 'devops',
        name: 'Zero-Latency DevOps',
        provider: 'Ollama',
        model: 'llama3.1-70b',
        temperature: 0.4,
        topP: 0.8,
        reasoningLevel: 'low',
        description: 'Compiles final deliverables, configures YAML deployments, and monitors package compatibility.',
      },
    ]);
  };

  // Helper stats calculation of convergence factor
  const calculateStats = () => {
    // Higher temp and low reasoning increases consensus cycles
    const totalTemp = profiles.reduce((acc, p) => acc + p.temperature, 0);
    const highReasoners = profiles.filter((p) => p.reasoningLevel === 'high').length;
    
    // Average temperature
    const avgTemp = totalTemp / profiles.length;
    
    // Convergence rate (higher temp = slower, higher reasoning = faster, cleaner)
    const convergenceSpeed = Math.max(2, Math.round(10 - avgTemp * 6 + highReasoners * 1.5));
    const codeQuality = Math.min(100, Math.round(70 + highReasoners * 8 - avgTemp * 15));

    return { convergenceSpeed, codeQuality };
  };

  const stats = calculateStats();

  return (
    <motion.div
      id="profiles-workbench-container"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
      className="w-full max-w-7xl xl:max-w-[1550px] px-6 md:px-12 py-6 md:py-10 grid grid-cols-1 lg:grid-cols-12 gap-8 text-stone-300"
    >
      {/* Intro info box */}
      <div className="col-span-12">
        <h2 className="text-2xl font-bold tracking-tight text-white mb-2">Inference Tuning Lab</h2>
        <p className="text-zinc-400 text-xs md:text-sm max-w-xl leading-relaxed">
          Calibrate LLM provider registers, temp bounds, and token reasoning layers. Modifying agent weights dynamically alters local consensus speed and code quality vectors.
        </p>
      </div>

      {/* LEFT COLUMN: ACTIVE PROFILES GRID */}
      <div className="lg:col-span-4 flex flex-col gap-4">
        <label className="text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest pl-1">Active Profiles</label>
        
        {profiles.map((profile) => {
          const isActive = profile.id === activeProfileId;
          return (
            <button
              id={`profile-card-button-${profile.id}`}
              key={profile.id}
              onClick={() => setActiveProfileId(profile.id)}
              className={`w-full p-4 rounded text-left border transition-all cursor-pointer ${
                isActive
                  ? 'bg-white/5 text-white border-white/20 shadow-md'
                  : 'bg-[#111113]/40 text-zinc-400 border-white/5 hover:border-white/10'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <h4 className="font-extrabold text-xs uppercase tracking-wide">{profile.name}</h4>
                <Cpu className={`w-4 h-4 ${isActive ? 'text-white animate-pulse' : 'text-zinc-605'}`} />
              </div>
              <p className="text-[10px] text-zinc-500 font-mono mb-2">
                {profile.provider} • {profile.model}
              </p>
              <p className="text-[11px] leading-snug line-clamp-2 text-zinc-450 font-medium">
                {profile.description}
              </p>
            </button>
          );
        })}
      </div>

      {/* MIDDLE COLUMN: FINE PARAMETERS PANEL */}
      <div className="lg:col-span-5 artistic-pane rounded-xl p-6 flex flex-col justify-between shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
        <div className="space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-white/10">
            <h3 className="text-white font-extrabold text-xs tracking-wider uppercase">{activeProfile.name} Parameters</h3>
            <span className="text-[10px] font-mono bg-white/5 text-zinc-450 px-2.5 py-0.5 rounded border border-white/10">
              ID: {activeProfile.id}
            </span>
          </div>

          {/* Target Model Provider */}
          <div>
            <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">LLM Engine Provider</label>
            <select
              id="model-provider-selector"
              value={activeProfile.provider}
              onChange={(e) => handleUpdateField('provider', e.target.value)}
              className="w-full bg-[#111113] border border-white/10 rounded p-2.5 text-xs text-zinc-200 outline-none focus:border-white/40 transition-all font-mono"
            >
              {['Gemini', 'OpenAI', 'Anthropic', 'Ollama', 'OpenRouter'].map((prov) => (
                <option key={prov} value={prov}>
                  {prov} register link
                </option>
              ))}
            </select>
          </div>

          {/* Specific Model Identifier */}
          <div>
            <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">Model Credentials ID</label>
            <input
              id="model-id-field"
              type="text"
              value={activeProfile.model}
              onChange={(e) => handleUpdateField('model', e.target.value)}
              className="w-full bg-[#111113] border border-white/10 rounded p-2.5 text-xs text-zinc-300 outline-none focus:border-white/40 font-mono"
            />
          </div>

          {/* Temperature slider */}
          <div>
            <div className="flex justify-between items-center mb-1 font-mono">
              <span className="text-[10.5px] font-bold text-zinc-500 uppercase">Temperature</span>
              <span className="text-xs text-white font-bold">{activeProfile.temperature}</span>
            </div>
            <input
              id="temperature-slider-weight"
              type="range"
              min="0.0"
              max="1.0"
              step="0.05"
              value={activeProfile.temperature}
              onChange={(e) => handleUpdateField('temperature', Number(e.target.value))}
              className="w-full accent-white cursor-pointer opacity-80 hover:opacity-100 transition-opacity"
            />
            <p className="text-[9.5px] text-zinc-500 mt-2 font-mono">
              Lower temperatures enforce deterministic code generation; higher levels allow wider pattern critiques.
            </p>
          </div>

          {/* Top-P weights */}
          <div>
            <div className="flex justify-between items-center mb-1 font-mono">
              <span className="text-[10.5px] font-bold text-zinc-500 uppercase">Top-P Nucleus Sampling</span>
              <span className="text-xs text-white font-bold">{activeProfile.topP}</span>
            </div>
            <input
              id="topp-slider-weight"
              type="range"
              min="0.5"
              max="1.0"
              step="0.05"
              value={activeProfile.topP}
              onChange={(e) => handleUpdateField('topP', Number(e.target.value))}
              className="w-full accent-white cursor-pointer opacity-80 hover:opacity-100 transition-opacity"
            />
          </div>

          {/* Reasoning Depth selections */}
          <div>
            <label className="block text-[10.5px] font-mono font-bold text-zinc-500 uppercase mb-2">Reasoning Grid Depth</label>
            <div className="grid grid-cols-3 gap-2 font-mono">
              {['low', 'medium', 'high'].map((lvl) => {
                const isActive = activeProfile.reasoningLevel === lvl;
                return (
                  <button
                    id={`reason-selector-${lvl}`}
                    key={lvl}
                    onClick={() => handleUpdateField('reasoningLevel', lvl)}
                    className={`p-2 rounded text-[9.5px] font-extrabold uppercase border tracking-wider transition-all cursor-pointer ${
                      isActive
                        ? 'bg-white/5 text-white border-white/20 shadow-sm'
                        : 'bg-transparent text-zinc-550 border-white/5 hover:border-white/10 hover:text-zinc-300'
                    }`}
                  >
                    {lvl}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Console action bar */}
        <div className="flex items-center justify-between border-t border-white/10 pt-5 mt-6">
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded border border-white/10 bg-transparent text-zinc-400 hover:text-white hover:border-white/20 text-xs transition-colors cursor-pointer"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Reset Defaults</span>
          </button>

          <button
            onClick={handleSave}
            className="flex items-center gap-1.5 px-4.5 py-2 rounded bg-white hover:bg-zinc-200 text-black font-black text-[10.5px] uppercase tracking-wider transition-all cursor-pointer shadow-[0_4px_24px_rgba(255,255,255,0.15)] active:scale-95"
          >
            {savedSuccess ? (
              <>
                <Check className="w-4 h-4 animate-bounce" />
                <span>Saved Success</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Apply Weights</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* RIGHT COLUMN: PREDICTIVE METRICS SUMMARY */}
      <div className="lg:col-span-3 artistic-pane rounded-xl p-5 space-y-6 shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
        <label className="text-[10px] font-mono font-bold text-zinc-500 uppercase tracking-widest pl-1">Predictive Analytics</label>

        {/* Predictive Consensus cycles */}
        <div className="p-4 rounded-lg bg-black/30 border border-white/10 text-center">
          <p className="text-[9px] text-zinc-500 font-mono uppercase tracking-wider font-extrabold">Convergence Rounds</p>
          <p className="text-4xl font-mono font-black text-white my-1 tracking-tight">
            {stats.convergenceSpeed} <span className="text-xs text-zinc-550 ml-0.5">steps</span>
          </p>
          <div className="w-full bg-white/10 h-[3px] rounded-full overflow-hidden mt-3">
            <div
              className="bg-white h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, stats.convergenceSpeed * 10)}%` }}
            />
          </div>
        </div>

        {/* Code Quality Prediction */}
        <div className="p-4 rounded-lg bg-black/30 border border-white/10 text-center">
          <p className="text-[9px] text-zinc-500 font-mono uppercase tracking-wider font-extrabold">Synthesis Quality</p>
          <p className="text-4xl font-mono font-black text-white my-1 tracking-tight">
            {stats.codeQuality}<span className="text-zinc-500 text-lg ml-0.5">%</span>
          </p>
          <div className="w-full bg-white/10 h-[3px] rounded-full overflow-hidden mt-3">
            <div
              className="bg-white h-full rounded-full transition-all duration-500"
              style={{ width: `${stats.codeQuality}%` }}
            />
          </div>
        </div>

        {/* Quality breakdown info */}
        <div className="text-[10.5px] text-zinc-500 font-mono leading-relaxed border-t border-white/10 pt-4 space-y-3">
          <div className="flex items-start gap-1.5 text-zinc-400">
            <Sparkles className="w-4 h-4 text-white shrink-0 mt-0.5" />
            <p>
              Applying low temperatures increases convergence deterministic paths, but reduces code quality parameters. High reasoning capabilities boost output security indices.
            </p>
          </div>
          <div className="flex items-start gap-1.5">
            <Info className="w-4 h-4 text-zinc-650 shrink-0 mt-0.5" />
            <p>
              Predictive models are calculated in real time using the current profile weights matrix.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
