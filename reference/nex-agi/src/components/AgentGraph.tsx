import { useState, useEffect } from 'react';
import { AgentNode, DebateMessage } from '../types';
import { Play, Pause, RefreshCw, Cpu, HardDrive, Shield, CheckCircle2, User } from 'lucide-react';

interface AgentGraphProps {
  nodes: AgentNode[];
  activeSenderId: string | null;
  activeReceiverId: string | null;
  activeMessageType: 'propose' | 'critique' | 'endorse' | 'reply' | 'system' | null;
  onNodeClick?: (node: AgentNode) => void;
  selectedNodeId: string | null;
}

export function AgentGraph({
  nodes,
  activeSenderId,
  activeReceiverId,
  activeMessageType,
  onNodeClick,
  selectedNodeId,
}: AgentGraphProps) {
  const [pulsePos, setPulsePos] = useState(0);

  // Animate pulse traveling from activeSender to activeReceiver
  useEffect(() => {
    if (!activeSenderId || !activeReceiverId) {
      setPulsePos(0);
      return;
    }
    setPulsePos(0);
    const interval = setInterval(() => {
      setPulsePos((prev) => {
        if (prev >= 1) {
          return 1;
        }
        return prev + 0.05;
      });
    }, 40);

    return () => clearInterval(interval);
  }, [activeSenderId, activeReceiverId]);

  const senderNode = nodes.find((n) => n.id === activeSenderId);
  const receiverNode = nodes.find((n) => n.id === activeReceiverId);

  // Calculate dynamic pulse position on SVG mapping
  let pulseCoordinates = null;
  if (senderNode && receiverNode && pulsePos < 1) {
    pulseCoordinates = {
      x: senderNode.x + (receiverNode.x - senderNode.x) * pulsePos,
      y: senderNode.y + (receiverNode.y - senderNode.y) * pulsePos,
    };
  }

  // Helper colors for connectors
  const getConnectorColor = () => {
    switch (activeMessageType) {
      case 'propose':
        return '#10b981';
      case 'critique':
        return '#ef4444';
      case 'endorse':
        return '#22c55e';
      case 'reply':
        return '#3b82f6';
      default:
        return '#27272a';
    }
  };

  const getAgentIcon = (role: string) => {
    const r = role.toLowerCase();
    if (r.includes('orchestrat')) return <Cpu className="w-5 h-5 text-emerald-400" />;
    if (r.includes('architect')) return <HardDrive className="w-5 h-5 text-sky-400" />;
    if (r.includes('security')) return <Shield className="w-5 h-5 text-amber-500" />;
    if (r.includes('qa')) return <CheckCircle2 className="w-5 h-5 text-green-400" />;
    return <User className="w-5 h-5 text-purple-400" />;
  };

  return (
    <div id="workspace-agent-graph-container" className="relative w-full h-full min-h-[300px] bg-[#111113] rounded-xl border border-[#27272a] p-4 flex flex-col justify-between overflow-hidden">
      {/* Background Grid Pattern */}
      <div className="absolute inset-0 pointer-events-none opacity-5">
        <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="graph-inner-mesh" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#ffffff" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#graph-inner-mesh)" />
        </svg>
      </div>

      {/* Main SVG Graph */}
      <div className="relative flex-1 w-full h-full min-h-[220px]">
        <svg
          id="svg-node-mesh-canvas"
          className="w-full h-full min-h-[220px]"
          viewBox="0 0 800 280"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Defined Arrow Marker for connection lines & filters */}
          <defs>
            <style>{`
              @keyframes laser-flow {
                to {
                  stroke-dashoffset: -20;
                }
              }
              @keyframes connection-throb {
                0%, 100% { stroke-width: 1.5px; opacity: 0.5; }
                50% { stroke-width: 2.2px; opacity: 0.85; }
              }
              @keyframes node-agent-blink {
                0%, 100% { filter: drop-shadow(0 0 4px var(--node-glow-color, rgba(16, 185, 129, 0.4))); opacity: 0.95; }
                50% { filter: drop-shadow(0 0 18px var(--node-glow-color, rgba(16, 185, 129, 0.65))); opacity: 1; }
              }
              @keyframes halo-pulse-scale {
                0% { transform: scale(0.65); opacity: 0.85; }
                100% { transform: scale(1.45); opacity: 0; }
              }
              .laser-line {
                stroke-dasharray: 6 4;
                animation: laser-flow 1.5s linear infinite;
              }
              .static-connector {
                animation: connection-throb 3s ease-in-out infinite;
              }
              .working-agent-node {
                animation: node-agent-blink 2s ease-in-out infinite;
              }
              .halo-pulse-ring {
                transform-origin: 0px 0px;
                animation: halo-pulse-scale 1.8s cubic-bezier(0.16, 1, 0.3, 1) infinite;
              }
              .svg-g-wrapper {
                transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
              }
            `}</style>

            {/* Neon Glow Filter */}
            <filter id="neon-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <marker
              id="arrow-marker"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#3f3f46" />
            </marker>
            <marker
              id="active-arrow-marker"
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={getConnectorColor()} />
            </marker>
          </defs>

          {/* Render Connection Trails (Static lines) */}
          {nodes.map((node) =>
            node.connections.map((targetId) => {
              const targetNode = nodes.find((n) => n.id === targetId);
              if (!targetNode) return null;
              
              const isActiveLine =
                (activeSenderId === node.id && activeReceiverId === targetId) ||
                (activeSenderId === targetId && activeReceiverId === node.id);

              return (
                <line
                  id={`connector-${node.id}-${targetId}`}
                  key={`${node.id}-${targetId}`}
                  x1={node.x}
                  y1={node.y}
                  x2={targetNode.x}
                  y2={targetNode.y}
                  stroke={isActiveLine ? getConnectorColor() : '#27272a'}
                  strokeWidth={isActiveLine ? 2.5 : 1}
                  opacity={isActiveLine ? 0.95 : 0.3}
                  markerEnd={isActiveLine ? "url(#active-arrow-marker)" : "url(#arrow-marker)"}
                  className={`transition-all duration-300 ${isActiveLine ? 'laser-line' : 'static-connector'}`}
                  style={{
                    filter: isActiveLine ? 'url(#neon-glow)' : 'none'
                  }}
                />
              );
            })
          )}

          {/* Animated Message Laser pulse traveling */}
          {pulseCoordinates && (
            <circle
              cx={pulseCoordinates.x}
              cy={pulseCoordinates.y}
              r={7}
              fill={getConnectorColor()}
              className="drop-shadow-[0_0_10px_currentColor] animate-ping"
              style={{ color: getConnectorColor() }}
            />
          )}
          {pulseCoordinates && (
            <circle
              cx={pulseCoordinates.x}
              cy={pulseCoordinates.y}
              r={5}
              fill={getConnectorColor()}
              className="drop-shadow-[0_0_8px_currentColor]"
              style={{ color: getConnectorColor() }}
            />
          )}

          {/* Render Core Interactive Agent Nodes */}
          {nodes.map((node) => {
            const isSender = activeSenderId === node.id;
            const isReceiver = activeReceiverId === node.id;
            const isSelected = selectedNodeId === node.id;

            // Determine border color based on status
            const getBorderColor = () => {
              if (isSender) return getConnectorColor();
              if (isSelected) return '#10b981';
              switch (node.status) {
                case 'thinking':
                  return '#10b981';
                case 'tool_call':
                  return '#f59e0b';
                case 'critiquing':
                  return '#ef4444';
                case 'endorsing':
                  return '#22c55e';
                default:
                  return '#3f3f46';
              }
            };

            const isHoldingTask = node.status === 'thinking' || node.status === 'tool_call' || isSender || isReceiver;

            // Define custom glow properties for blinking
            const getGlowColorRGBA = () => {
              switch (node.status) {
                case 'thinking': return 'rgba(16, 185, 129, 0.5)';
                case 'tool_call': return 'rgba(245, 158, 11, 0.5)';
                case 'critiquing': return 'rgba(239, 68, 68, 0.5)';
                case 'endorsing': return 'rgba(34, 197, 94, 0.5)';
                default: return 'rgba(16, 185, 129, 0.3)';
              }
            };

            return (
              <g
                id={`node-group-${node.id}`}
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => onNodeClick?.(node)}
                className={`cursor-pointer group select-none svg-g-wrapper ${isHoldingTask ? 'working-agent-node' : ''}`}
                style={{
                  ['--node-glow-color' as any]: getGlowColorRGBA()
                }}
              >
                {/* Node Outer Pulsating / Wave halo ring with glow */}
                {isHoldingTask && (
                  <circle
                    r={34}
                    fill="none"
                    stroke={getBorderColor()}
                    strokeWidth={1.5}
                    opacity={0.35}
                    className="halo-pulse-ring"
                    style={{ transformOrigin: '0px 0px' }}
                  />
                )}

                {/* Node Outer ambient ring */}
                <circle
                  r={28}
                  fill="none"
                  stroke={isHoldingTask ? getBorderColor() : 'transparent'}
                  strokeWidth={1}
                  opacity={0.7}
                  className="animate-pulse"
                />

                {/* Node Core circle */}
                <circle
                  r={23}
                  fill={isSelected ? '#09090b' : '#141416'}
                  stroke={getBorderColor()}
                  strokeWidth={isSelected ? 3 : isHoldingTask ? 2 : 1.5}
                  className="transition-all duration-300 group-hover:scale-110"
                  style={{
                    filter: isHoldingTask ? 'url(#neon-glow)' : 'none'
                  }}
                />

                {/* Status Dot */}
                <circle
                  cx={16}
                  cy={-16}
                  r={5}
                  fill={
                    node.status === 'thinking'
                      ? '#10b981'
                      : node.status === 'tool_call'
                      ? '#f59e0b'
                      : node.status === 'critiquing'
                      ? '#ef4444'
                      : node.status === 'endorsing'
                      ? '#22c55e'
                      : '#52525b'
                  }
                  stroke="#141416"
                  strokeWidth={1.5}
                  className={isHoldingTask ? 'animate-pulse' : ''}
                />

                {/* Inner Icon / Text placeholder */}
                <text
                  y={-2}
                  textAnchor="middle"
                  fill="#fafafa"
                  fontSize="10px"
                  fontWeight="600"
                  fontFamily="Inter, sans-serif"
                  className="pointer-events-none select-none"
                >
                  {node.name}
                </text>

                {/* Small Subtitle model label */}
                <text
                  y={10}
                  textAnchor="middle"
                  fill="#71717a"
                  fontSize="7.5px"
                  fontFamily="JetBrains Mono, monospace"
                  className="pointer-events-none select-none"
                >
                  {node.model}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Embedded Svg Icons Legend inside Graph container */}
      <div className="border-t border-[#27272a]/70 pt-2 grid grid-cols-2 lg:grid-cols-5 gap-2 text-[10px] text-zinc-500 font-mono">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#10b981] inline-block animate-pulse"></span>
          <span>Thinking</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#f59e0b] inline-block"></span>
          <span>Tool/API Call</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#ef4444] inline-block"></span>
          <span>Critiquing</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#22c55e] inline-block"></span>
          <span>Endorsing</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#71717a] inline-block"></span>
          <span>Idle / Queue</span>
        </div>
      </div>
    </div>
  );
}
