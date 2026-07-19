import React, { useState, useEffect, useRef } from 'react';
import { LandingView } from './views/LandingView';
import { WorkspaceView } from './views/WorkspaceView';
import { InferenceProfilesView } from './views/InferenceProfilesView';
import { HistoryView } from './views/HistoryView';
import { DashboardView } from './views/DashboardView';
import { ChatView } from './views/ChatView';
import { TeamsView } from './views/TeamsView';
import { KnowledgeView } from './views/KnowledgeView';
import { MemoryExplorerView } from './views/MemoryExplorerView';
import { Session } from './types';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Menu, X, Cpu, Sparkles, Terminal, LogOut, ChevronRight, 
  HardDrive, Settings, History, HelpCircle, Users, Bot, Layers, Database,
  Bell, BellOff, ChevronDown, CheckCircle2, ShieldAlert, AlertTriangle, Activity
} from 'lucide-react';

export interface GlobalToastAlert {
  id: string;
  agent: string;
  action: string;
  status: 'completes' | 'critique' | 'error' | 'sync';
  time: string;
  read: boolean;
}

type InnerActivePage = 'dashboard' | 'chat' | 'teams' | 'workspace' | 'knowledge' | 'memory' | 'profiles' | 'history';

const SIMULATED_AGENT_UPDATES = [
  { agent: 'Creative Architect', action: 'Drafted modular Redis clustering blueprint', status: 'completes' },
  { agent: 'Strict Auditor', action: 'Identified single-point-of-failure in master consensus path v2', status: 'critique' },
  { agent: 'Pedantic QA Tester', action: 'Completed automated stress injection on rate-limit queues', status: 'completes' },
  { agent: 'Zero-Latency DevOps', action: 'Successfully compiled build deliverables for isolated Docker container', status: 'sync' },
  { agent: 'NEX AGI Co-ordinator', action: 'Convergence rating raised to 94.8% after multi-round debate validation', status: 'completes' },
  { agent: 'Knowledge Vector Hub', action: 'Optimized 1536-dimension spatial indexes across pgvector database cluster', status: 'sync' },
  { agent: 'Security Monitor', action: 'Prevented anomalous thread concurrency leak from test simulation harness', status: 'error' },
];

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [activePage, setActivePage] = useState<InnerActivePage>('dashboard');
  const [activePresetSessionId, setActivePresetSessionId] = useState<string | undefined>(undefined);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Uncongested Navigation State
  const [isEnginesDropdownOpen, setIsEnginesDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Global Notification States
  const [toasts, setToasts] = useState<GlobalToastAlert[]>([
    { id: 't-init', agent: 'Orchestrating Router', action: 'Active cognition session started successfully', status: 'completes', time: '12:45 PM', read: true }
  ]);
  const [showFloatingOverlays, setShowFloatingOverlays] = useState(false); // Default false: toggle to show desktop overlays
  const [isNotificationPaneOpen, setIsNotificationPaneOpen] = useState(false);
  const [simActive, setSimActive] = useState(true);
  const notificationPaneRef = useRef<HTMLDivElement>(null);

  // Auto-scroll screen back to top when active page changes
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [activePage, isLoggedIn]);

  // Handle closing dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsEnginesDropdownOpen(false);
      }
      if (notificationPaneRef.current && !notificationPaneRef.current.contains(event.target as Node)) {
        setIsNotificationPaneOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Shared alert trigger function
  const triggerToast = (agent: string, action: string, status: 'completes' | 'critique' | 'error' | 'sync') => {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const newAlert: GlobalToastAlert = {
      id: `toast-${Date.now()}-${Math.random()}`,
      agent,
      action,
      status,
      time: timestamp,
      read: false
    };
    
    setToasts(prev => [newAlert, ...prev].slice(0, 32));
  };

  // Listen to custom alert events dispatched from internal screens
  useEffect(() => {
    const handleNewAlert = (e: Event) => {
      const customEvent = e as CustomEvent<{ agent: string; action: string; status: 'completes' | 'critique' | 'error' | 'sync' }>;
      if (customEvent.detail) {
        const { agent, action, status } = customEvent.detail;
        triggerToast(agent, action, status);
      }
    };
    window.addEventListener('nexagi-new-alert' as any, handleNewAlert);
    return () => window.removeEventListener('nexagi-new-alert' as any, handleNewAlert);
  }, []);

  // Background agent thread event simulation
  useEffect(() => {
    if (!simActive) return;
    const interval = setInterval(() => {
      const randomUpdate = SIMULATED_AGENT_UPDATES[Math.floor(Math.random() * SIMULATED_AGENT_UPDATES.length)];
      triggerToast(randomUpdate.agent, randomUpdate.action, randomUpdate.status as any);
    }, 11000); // Trigger every 11 seconds for gentle background realism
    return () => clearInterval(interval);
  }, [simActive]);

  // Handle saving completed runs from the workspace into local storage
  const handleSessionSaved = (newSession: Session) => {
    const rawSaved = localStorage.getItem('nexagi_sessions');
    let savedList: Session[] = [];
    try {
      if (rawSaved) {
        savedList = JSON.parse(rawSaved);
      }
    } catch (e) {
      console.error(e);
    }
    
    // Add unique completed run at the beginning of the array
    savedList = [newSession, ...savedList.filter((s) => s.id !== newSession.id)];
    localStorage.setItem('nexagi_sessions', JSON.stringify(savedList));
  };

  // Nav helper
  const navigateTo = (page: InnerActivePage, presetId?: string) => {
    setActivePage(page);
    setActivePresetSessionId(presetId);
    setIsMobileMenuOpen(false);
    setIsEnginesDropdownOpen(false);
  };

  // Login handler
  const handleLogin = (presetId?: string) => {
    setIsLoggedIn(true);
    if (presetId) {
      navigateTo('workspace', presetId);
    } else {
      navigateTo('dashboard');
    }
  };

  const getUnreadCount = () => toasts.filter(t => !t.read).length;

  const markAllAsRead = () => {
    setToasts(prev => prev.map(t => ({ ...t, read: true })));
  };

  const clearAllNotifications = () => {
    setToasts([]);
  };

  const dismissToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // High density core primary links
  const primaryNavItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Layers },
    { id: 'workspace', label: 'Session Workspace', icon: Cpu },
    { id: 'teams', label: 'Teams Builder', icon: Users },
    { id: 'chat', label: 'Chat Log', icon: Bot },
  ];

  // Secondary auxiliary views listed inside the compact Core Dropdown Menu
  const dropdownNavItems = [
    { id: 'knowledge', label: 'Knowledge Base', icon: Database, desc: 'Central vector indices' },
    { id: 'memory', label: 'Memory Explorer', icon: HardDrive, desc: 'LTM cognitive dumps' },
    { id: 'profiles', label: 'Inference Tuning', icon: Settings, desc: 'Model configs & parameters' },
    { id: 'history', label: 'Saved Sessions', icon: History, desc: 'Historic runs archiver' },
  ];

  const activeDropdownItem = dropdownNavItems.find(item => item.id === activePage);

  return (
    <div id="nex-agi-app-shell" className="min-h-screen bg-[#050506] text-[#fafafa] flex flex-col font-sans antialiased overflow-x-hidden selection:bg-emerald-500/20 selection:text-emerald-300 relative">
      
      {/* BACKGROUND ELEMENTS FROM ARTISTIC FLAIR THEME */}
      <div className="artistic-background" />
      <div className="artistic-grid" />
      <div className="artistic-glow-blob top-[15%] right-[10%]" />
      <div className="artistic-glow-blob bottom-[25%] left-[5%] opacity-60" style={{ width: '400px', height: '400px' }} />

      {/* GLOBAL HEADER BAR */}
      <header id="header-nav" className="sticky top-0 z-50 h-20 bg-[#050506]/75 backdrop-blur-2xl border-b border-white/10">
        <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto h-full flex items-center justify-between px-6 md:px-12">
          
          {/* Logo block */}
        <div 
          onClick={() => {
            if (isLoggedIn) {
              navigateTo('dashboard');
            } else {
              setIsLoggedIn(false);
            }
          }}
          className="flex items-center gap-3 cursor-pointer group shrink-0"
        >
          <div className="w-8 h-8 rounded bg-white flex items-center justify-center text-black font-mono font-black text-xs shadow-[0_0_20px_rgba(255,255,255,0.2)] group-hover:scale-105 transition-all">
            Nx
          </div>
          <span className="text-[12px] font-extrabold tracking-[0.25em] text-white uppercase font-sans">NEX AGI</span>
          {isLoggedIn && (
            <span className="px-2 py-0.5 bg-[#10b981]/15 border border-[#10b981]/25 text-[#10b981] text-[8px] font-mono rounded font-bold uppercase tracking-wider hidden md:inline select-none">
              v1.4
            </span>
          )}
        </div>

        {/* UNCONGESTED DESKTOP HEADER NAVIGATION */}
        {isLoggedIn ? (
          <nav className="hidden lg:flex items-center gap-1.5 px-4 py-1.5 bg-[#080d0a]/60 border border-white/5 rounded-2xl">
            {/* Primary high priority workspace tabs */}
            {primaryNavItems.map((item) => {
              const isSelected = activePage === item.id;
              return (
                <button
                  id={`nav-link-desktop-${item.id}`}
                  key={item.id}
                  onClick={() => navigateTo(item.id as InnerActivePage)}
                  className={`relative px-4 py-2 text-[10.5px] font-bold tracking-widest uppercase transition-all rounded-xl cursor-pointer flex items-center gap-1.5 select-none ${
                    isSelected 
                      ? 'text-white bg-white/5 border border-white/10 shadow-[0_0_12px_rgba(255,255,255,0.03)]' 
                      : 'text-zinc-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <item.icon className={`w-3.5 h-3.5 ${isSelected ? 'text-[#10b981]' : 'text-zinc-500'}`} />
                  <span>{item.label}</span>
                  {isSelected && (
                    <motion.div
                      layoutId="activeNavIndicator"
                      className="absolute bottom-[-1px] left-3.5 right-3.5 h-[2px] bg-emerald-450 rounded-full"
                      transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                    />
                  )}
                </button>
              );
            })}

            {/* Split Divider spacer to make it look premium */}
            <div className="w-[1px] h-4 bg-white/10 mx-2" />

            {/* Centralized engines dropdown to remove congestion completely */}
            <div className="relative" ref={dropdownRef}>
              <button
                id="engines-dropdown-trigger"
                onClick={() => setIsEnginesDropdownOpen(!isEnginesDropdownOpen)}
                className={`px-4 py-2 text-[10.5px] font-bold tracking-widest uppercase transition-all rounded-xl cursor-pointer flex items-center gap-1.5 ${
                  activeDropdownItem 
                    ? 'text-emerald-400 bg-[#10b981]/10 border border-[#10b981]/25' 
                    : 'text-zinc-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Settings className={`w-3.5 h-3.5 ${activeDropdownItem ? 'text-emerald-400 animate-spin-slow' : 'text-zinc-500'}`} />
                <span>{activeDropdownItem ? `Engine: ${activeDropdownItem.label}` : 'Aux Engines'}</span>
                <ChevronDown className="w-3 h-3 text-zinc-500 transition-transform duration-200" style={{ transform: isEnginesDropdownOpen ? 'rotate(180deg)' : 'none' }} />
              </button>

              <AnimatePresence>
                {isEnginesDropdownOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 10, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 10, scale: 0.95 }}
                    transition={{ duration: 0.15 }}
                    className="absolute right-0 top-full mt-2 w-64 bg-[#0a0f0c] border border-white/10 rounded-xl p-2 shadow-[0_12px_40px_rgba(0,0,0,0.85)] z-60"
                  >
                    <div className="px-3 py-1.5 mb-1.5 border-b border-white/5">
                      <p className="text-[8.5px] font-mono text-zinc-500 tracking-widest uppercase">Platform Auxiliary Systems</p>
                    </div>
                    <div className="space-y-1">
                      {dropdownNavItems.map((subItem) => {
                        const isSubSelected = activePage === subItem.id;
                        return (
                          <button
                            key={subItem.id}
                            onClick={() => navigateTo(subItem.id as InnerActivePage)}
                            className={`w-full text-left px-3 py-2 rounded-lg transition-all flex items-start gap-2.5 ${
                              isSubSelected 
                                ? 'bg-[#10b981]/15 text-white border-l-2 border-[#10b981]' 
                                : 'text-zinc-350 hover:bg-white/5 hover:text-white'
                            }`}
                          >
                            <subItem.icon className={`w-4 h-4 mt-0.5 shrink-0 ${isSubSelected ? 'text-emerald-400' : 'text-zinc-500'}`} />
                            <div className="min-w-0">
                              <p className="text-[10px] uppercase font-bold tracking-wider">{subItem.label}</p>
                              <p className="text-[8.5px] text-zinc-500 truncate mt-0.5">{subItem.desc}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </nav>
        ) : (
          <div className="hidden md:flex items-center">
            <span className="text-[10px] uppercase font-mono tracking-widest text-[#10b981]/80 mr-2 bg-[#10b981]/10 px-3 py-1.5 rounded-lg border border-emerald-500/10">SECURED AGENTIC CONVERGENCE</span>
          </div>
        )}

        {/* Standard right-side metrics actions & central notification hub trigger */}
        <div className="hidden md:flex items-center gap-4">
          
          {/* Notifications global action center bell */}
          {isLoggedIn && (
            <div className="relative" ref={notificationPaneRef}>
              <button
                id="global-notification-bell-trigger"
                onClick={() => {
                  setIsNotificationPaneOpen(!isNotificationPaneOpen);
                  markAllAsRead();
                }}
                className={`relative p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-center ${
                  isNotificationPaneOpen 
                    ? 'bg-[#10b981]/10 border-[#10b981]/30 text-emerald-400' 
                    : getUnreadCount() > 0 
                    ? 'border-[#10b981]/20 text-white hover:border-[#10b981]/40 bg-[#050506]' 
                    : 'border-white/10 text-zinc-400 hover:text-white hover:bg-white/5'
                }`}
                title="System event notifications"
              >
                <Bell className={`w-4 h-4 ${getUnreadCount() > 0 ? 'animate-bounce' : ''}`} />
                
                {/* Notification unread badge count */}
                {getUnreadCount() > 0 && (
                  <span className="absolute -top-1 -right-1 w-4.5 h-4.5 rounded-full bg-emerald-500 text-black font-black text-[9px] flex items-center justify-center border-2 border-[#050506] select-none scale-[1.1]">
                    {getUnreadCount()}
                  </span>
                )}
              </button>

              {/* Central notification drop table overlay */}
              <AnimatePresence>
                {isNotificationPaneOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 15, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 15, scale: 0.95 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className="absolute right-0 top-full mt-3 w-96 bg-[#090e0b]/95 backdrop-blur-2xl border border-white/15 rounded-xl p-4 shadow-[0_15px_50px_rgba(0,0,0,0.9)] z-65"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-white/15 mb-3">
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-wider text-white">Event Log Matrix</h4>
                        <p className="text-[9px] text-zinc-500 font-mono tracking-tight">AUTONOMOUS SWARM CHRONOLOGY</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {toasts.length > 0 && (
                          <button 
                            onClick={clearAllNotifications}
                            className="text-zinc-500 hover:text-zinc-300 font-mono text-[9px] uppercase tracking-wider cursor-pointer"
                          >
                            Clear All
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Integrated custom switches for strict control */}
                    <div className="p-2.5 bg-[#0c0c0e] border border-white/5 rounded-lg mb-3 space-y-2">
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-zinc-400 font-medium">Auto-Simulation Stream:</span>
                        <button
                          onClick={() => setSimActive(!simActive)}
                          className={`px-2 py-0.5 rounded text-[8.5px] font-mono font-bold tracking-widest border transition-all ${
                            simActive ? 'bg-emerald-500/10 border-emerald-500/35 text-emerald-400' : 'bg-zinc-900 border-white/5 text-zinc-550'
                          }`}
                        >
                          {simActive ? 'STREAMING' : 'MUTED'}
                        </button>
                      </div>
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-zinc-400 font-medium">Allow Temporary Toast Overlays:</span>
                        <button
                          onClick={() => setShowFloatingOverlays(!showFloatingOverlays)}
                          className={`px-2 py-0.5 rounded text-[8.5px] font-mono font-bold tracking-widest border transition-all ${
                            showFloatingOverlays ? 'bg-emerald-500/10 border-emerald-500/35 text-emerald-400' : 'bg-zinc-900 border-white/5 text-zinc-555'
                          }`}
                          title="Click to hide temporary popup banners"
                        >
                          {showFloatingOverlays ? 'SHOWING' : 'MUTED (LOG ONLY)'}
                        </button>
                      </div>
                    </div>

                    {/* List container */}
                    {toasts.length === 0 ? (
                      <div className="text-center py-8">
                        <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">No recent system integrations logged</p>
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {toasts.map((toast) => (
                          <div 
                            key={toast.id}
                            className="p-2 bg-black/40 border border-white/5 rounded-lg text-xs hover:border-white/10 transition-colors"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                  toast.status === 'completes' ? 'bg-[#10b981]' :
                                  toast.status === 'critique' ? 'bg-orange-500' :
                                  toast.status === 'error' ? 'bg-rose-500' : 'bg-sky-400'
                                }`} />
                                <span className="font-sans font-bold text-white uppercase text-[9.5px] truncate">{toast.agent}</span>
                              </div>
                              <span className="text-[8.5px] font-mono text-zinc-500 shrink-0">{toast.time}</span>
                            </div>
                            <p className="text-zinc-400 text-[10px] mt-1 leading-snug">{toast.action}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {isLoggedIn ? (
            <button 
              onClick={() => setIsLoggedIn(false)}
              className="flex items-center gap-2 px-3.5 py-2 bg-neutral-900 border border-white/10 text-stone-300 text-[10.5px] tracking-wider uppercase rounded-xl hover:text-white transition-all cursor-pointer hover:border-white/20"
              title="Logout from console"
            >
              <LogOut className="w-3.5 h-3.5 text-zinc-500" />
              <span>Exit Portal</span>
            </button>
          ) : (
            <button 
              onClick={() => handleLogin()}
              className="px-5 py-2.5 bg-white hover:bg-zinc-200 text-black font-black text-[10.5px] tracking-widest uppercase rounded-lg shadow-[0_4px_24px_rgba(255,255,255,0.15)] transition-all cursor-pointer hover:scale-[1.01] active:scale-95"
            >
              LOGIN
            </button>
          )}
        </div>

        {/* Mobile menu hamburger toggle button */}
        <div className="xl:hidden flex items-center gap-3">
          {isLoggedIn && (
            <div className="inline-flex items-center gap-1.5 text-[9px] text-[#10b981] bg-[#10b981]/10 border border-[#10b981]/20 px-2.5 py-0.5 rounded-full font-mono uppercase tracking-wider">
              <span>MEMBER</span>
            </div>
          )}
          
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="p-1.5 rounded-xl border border-white/10 text-zinc-400 hover:text-white hover:bg-white/5 transition cursor-pointer"
          >
            {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>
    </header>

      {/* MOBILE SEAMLESS OVERLAY NAVIGATION DRAWERS */}
      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            id="mobile-navigation-overlay"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="xl:hidden bg-[#050506]/95 border-b border-white/10 overflow-hidden flex flex-col z-40 relative px-6 py-4 space-y-3"
          >
            {isLoggedIn ? (
              <>
                {[
                  { id: 'dashboard', label: 'Dashboard' },
                  { id: 'chat', label: 'Chat Log Thread' },
                  { id: 'teams', label: 'Specialist Teams' },
                  { id: 'workspace', label: 'Session Workspace' },
                  { id: 'knowledge', label: 'Knowledge Base' },
                  { id: 'memory', label: 'Cognitive Memory' },
                  { id: 'profiles', label: 'Inference Tuning' },
                  { id: 'history', label: 'Archives Log' },
                ].map((item) => (
                  <button
                    id={`nav-link-mobile-${item.id}`}
                    key={item.id}
                    onClick={() => navigateTo(item.id as InnerActivePage)}
                    className={`w-full py-2.5 px-3 text-left rounded-xl text-[10px] font-bold uppercase tracking-wider border ${
                      activePage === item.id
                        ? 'bg-[#10b981]/10 border-[#10b981]/20 text-white'
                        : 'bg-transparent border-transparent text-zinc-450 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}

                <div className="border-t border-white/10 pt-3">
                  <button
                    onClick={() => setIsLoggedIn(false)}
                    className="w-full py-2.5 bg-neutral-900 text-stone-300 text-center font-black text-[10px] tracking-wider uppercase rounded-xl transition-colors border border-white/10"
                  >
                    EXIT PORTAL
                  </button>
                </div>
              </>
            ) : (
              <div className="space-y-4 py-2">
                <p className="text-zinc-500 font-mono text-[10px] text-center uppercase tracking-widest">Login required to access controls</p>
                <button
                  onClick={() => { setIsMobileMenuOpen(false); handleLogin(); }}
                  className="w-full py-3 bg-white text-black text-center font-black text-[10.5px] tracking-widest uppercase rounded-lg"
                >
                  LOGIN NOW
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* DYNAMIC SCREEN VIEWPORT PORTAL WITH SMOOTH FADE TRANSITIONS */}
      <main id="main-content" className="flex-1 flex flex-col items-center relative z-10 w-full">
        <AnimatePresence mode="wait">
          {!isLoggedIn ? (
            <motion.div 
              key="landing" 
              className="w-full flex justify-center" 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
            >
              <LandingView
                onStartSession={(presetId) => handleLogin(presetId)}
                onNavigateToWorkspace={() => handleLogin()}
                onNavigateToProfiles={() => handleLogin()}
              />
            </motion.div>
          ) : (
            <motion.div 
              key="portal" 
              className="w-full flex justify-center" 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
            >
              {activePage === 'dashboard' && <DashboardView />}
              
              {activePage === 'chat' && (
                <ChatView onExpandToWorkspace={(presetId) => navigateTo('workspace', presetId)} />
              )}
              
              {activePage === 'teams' && <TeamsView />}
              
              {activePage === 'workspace' && (
                <WorkspaceView
                  onSessionSaved={handleSessionSaved}
                  initialPresetId={activePresetSessionId}
                />
              )}
              
              {activePage === 'knowledge' && <KnowledgeView />}
              
              {activePage === 'memory' && <MemoryExplorerView />}
              
              {activePage === 'profiles' && <InferenceProfilesView />}
              
              {activePage === 'history' && (
                <HistoryView
                  onLoadSession={(presetId) => navigateTo('workspace', presetId)}
                />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* SECURE MINIMAL HUMAN-LABELED MARGIN LESS FOOTER */}
      <footer id="global-footer" className="artistic-pane !border-x-0 !border-b-0 py-6 text-center text-[10.5px] text-zinc-550 font-mono relative z-10 bg-black/40 backdrop-blur-md">
        <div className="w-full max-w-7xl xl:max-w-[1550px] mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4 px-6 md:px-12">
          <p>© 2026 NEX AGI. Human engineered, agentic state-machine orchestrated.</p>
          <div className="flex justify-center gap-4 text-zinc-650">
            <span>Status: Continuous Convergence</span>
            <span>•</span>
            <span>Region: Node-Bus</span>
            {isLoggedIn && (
              <>
                <span>•</span>
                <span className="text-emerald-500 cursor-pointer hover:underline" onClick={() => setIsLoggedIn(false)}>Exit Log</span>
              </>
            )}
          </div>
        </div>
      </footer>

      {/* DYNAMIC TEMPORARY FLOATING TOASTS BANNER PORTAL */}
      <div id="dynamic-floating-toast-portal" className="fixed bottom-6 right-6 z-55 w-full max-w-sm flex flex-col gap-3 pointer-events-none">
        <AnimatePresence>
          {showFloatingOverlays && toasts.slice(0, 4).map((toast) => {
            const getColorClasses = () => {
              switch (toast.status) {
                case 'completes':
                  return {
                    border: 'border-[#10b981]/30',
                    bg: 'bg-[#050506]/95',
                    dot: 'bg-emerald-400 shadow-[0_0_8px_#10b981]',
                  };
                case 'critique':
                  return {
                    border: 'border-orange-500/30',
                    bg: 'bg-[#0a0602]/95',
                    dot: 'bg-orange-400 shadow-[0_0_8px_#f97316]',
                  };
                case 'error':
                  return {
                    border: 'border-rose-500/30',
                    bg: 'bg-[#0c0204]/95',
                    dot: 'bg-rose-500 shadow-[0_0_8px_#ef4444]',
                  };
                default:
                  return {
                    border: 'border-sky-500/30',
                    bg: 'bg-[#020508]/95',
                    dot: 'bg-sky-450 shadow-[0_0_8px_#38bdf8]',
                  };
              }
            };

            const styles = getColorClasses();

            return (
              <motion.div
                id={`toast-card-${toast.id}`}
                key={toast.id}
                layout
                initial={{ opacity: 0, y: 35, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9, x: 40 }}
                transition={{ type: 'spring', stiffness: 350, damping: 26 }}
                className={`pointer-events-auto p-4 rounded-xl border ${styles.border} ${styles.bg} backdrop-blur-2xl shadow-[0_10px_35px_rgb(0,0,0,0.7)] flex items-start gap-3 relative overflow-hidden`}
              >
                {/* Accent neon bar */}
                <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${
                  toast.status === 'completes' ? 'bg-[#10b981]' :
                  toast.status === 'critique' ? 'bg-orange-500' :
                  toast.status === 'error' ? 'bg-rose-500' : 'bg-sky-400'
                }`} />

                {/* Left Colored status beacon */}
                <div className="pt-1.5 shrink-0">
                  <span className={`w-2 h-2 rounded-full block ${styles.dot}`} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9.5px] font-sans font-black text-white uppercase tracking-wider truncate">
                      {toast.agent}
                    </span>
                    <span className="text-[8.5px] font-mono text-zinc-500 shrink-0">
                      {toast.time}
                    </span>
                  </div>
                  <p className="text-[10.5px] text-zinc-300 font-medium leading-relaxed mt-1">
                    {toast.action}
                  </p>
                </div>

                {/* Close Action Trigger */}
                <button
                  onClick={() => dismissToast(toast.id)}
                  className="text-zinc-500 hover:text-white p-0.5 rounded transition-colors shrink-0 cursor-pointer self-start select-none"
                  aria-label="Dismiss Alert"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}
