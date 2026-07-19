export interface AgentNode {
  id: string;
  name: string;
  role: string;
  model: string;
  status: 'thinking' | 'tool_call' | 'critiquing' | 'endorsing' | 'waiting' | 'idle';
  x: number;
  y: number;
  connections: string[];
  avatarText: string;
  color: string;
  pulseTimer?: number;
}

export type DebateMessageType = 'propose' | 'critique' | 'endorse' | 'reply' | 'system';

export interface DebateMessage {
  id: string;
  round: number;
  senderId: string;
  senderName: string;
  type: DebateMessageType;
  text: string;
  badgeLabel: string;
  timestamp: string;
  agentColor?: string;
}

export interface GeneratedFile {
  filename: string;
  language: string;
  code: string;
}

export interface Session {
  id: string;
  goal: string;
  currentRound: number;
  maxRounds: number;
  consensusPct: number;
  status: 'idle' | 'running' | 'paused' | 'completed';
  messages: DebateMessage[];
  files: GeneratedFile[];
  timestamp: string;
  agentsPreset: string;
}

export interface InferenceProfile {
  id: string;
  name: string;
  provider: 'OpenAI' | 'Gemini' | 'Anthropic' | 'Ollama' | 'OpenRouter';
  model: string;
  temperature: number;
  topP: number;
  reasoningLevel: 'low' | 'medium' | 'high';
  description: string;
}
