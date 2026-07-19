import { AgentNode, DebateMessage, GeneratedFile, Session } from '../types';

export interface SimulationStep {
  round: number;
  senderId: string;
  receiverId: string;
  messageType: 'propose' | 'critique' | 'endorse' | 'reply';
  badgeLabel: string;
  messageText: string;
  filesAfterStep: GeneratedFile[];
  consensusPct: number;
  nodeStatuses: { [nodeId: string]: AgentNode['status'] };
}

export interface SimulationTemplate {
  id: string;
  goal: string;
  agentsPreset: string;
  initialNodes: AgentNode[];
  steps: SimulationStep[];
  completedFiles: GeneratedFile[];
}

export const INITIAL_GENERIC_NODES: AgentNode[] = [
  {
    id: 'orchestrator',
    name: 'Orchestrator',
    role: 'Orchestrator Node',
    model: 'gpt-4o',
    status: 'idle',
    x: 120,
    y: 135,
    connections: ['architect', 'reviewer', 'qa', 'devops'],
    avatarText: 'OR',
    color: '#10b981',
  },
  {
    id: 'architect',
    name: 'Architect',
    role: 'Lead Architect',
    model: 'claude-3.5',
    status: 'idle',
    x: 280,
    y: 80,
    connections: ['reviewer', 'qa'],
    avatarText: 'AR',
    color: '#10b981',
  },
  {
    id: 'reviewer',
    name: 'Reviewer',
    role: 'Security Reviewer',
    model: 'gpt-4o',
    status: 'idle',
    x: 430,
    y: 60,
    connections: ['qa'],
    avatarText: 'RE',
    color: '#ef4444',
  },
  {
    id: 'qa',
    name: 'QA Eng',
    role: 'Automation Tester',
    model: 'claude-3',
    status: 'idle',
    x: 430,
    y: 210,
    connections: ['devops'],
    avatarText: 'QA',
    color: '#22c55e',
  },
  {
    id: 'devops',
    name: 'DevOps',
    role: 'Release Engineer',
    model: 'gemini-2',
    status: 'idle',
    x: 280,
    y: 190,
    connections: ['orchestrator'],
    avatarText: 'DE',
    color: '#71717a',
  },
];

export const SIMULATION_TEMPLATES: SimulationTemplate[] = [
  {
    id: 'rate-limiter',
    goal: 'Design a distributed rate-limiter for 10M RPS',
    agentsPreset: 'Elite Infrastructure Group',
    initialNodes: JSON.parse(JSON.stringify(INITIAL_GENERIC_NODES)),
    completedFiles: [
      {
        filename: 'rate_limiter.py',
        language: 'python',
        code: `import time
from typing import Dict, Tuple

class DistributedSlidingWindow:
    """Consensus-designed high-performance token-bucket and sliding-window rate-limiter"""
    def __init__(self, rps_limit: int = 10000000, cluster_nodes: int = 250):
        self.node_limit = rps_limit // cluster_nodes
        self.windows: Dict[str, Tuple[int, int]] = {} # ip: (tokens_used, timestamp)
        self.window_size = 1.0 # seconds

    def request_allowed(self, user_ip: str, now: float = None) -> bool:
        if now is None:
            now = time.time()
        
        # Core sliding window bucket lookup with synchronization steps
        bucket_key = int(now / self.window_size)
        tokens, last_update = self.windows.get(user_ip, (0, bucket_key))
        
        if last_update < bucket_key:
            tokens = 0
            
        if tokens < self.node_limit:
            self.windows[user_ip] = (tokens + 1, bucket_key)
            return True
        return False
`,
      },
      {
        filename: 'cluster_sync.rs',
        language: 'rust',
        code: `// Gossip and CRDT replication routine for Rate Limiter buckets
use std::collections::HashMap;
use std::time::SystemTime;

pub struct BucketCRDT {
    node_id: String,
    counters: HashMap<String, u64>, // NodeID -> Requests
}

impl BucketCRDT {
    pub fn merge(&mut self, remote: &BucketCRDT) {
        for (node, &count) in remote.counters.iter() {
            let current = self.counters.entry(node.clone()).or_insert(0);
            if count > *current {
                *current = count; // Retain highest cluster state
            }
        }
    }
}
`,
      },
    ],
    steps: [
      {
        round: 1,
        senderId: 'orchestrator',
        receiverId: 'architect',
        messageType: 'reply',
        badgeLabel: 'DELEGATE',
        messageText: 'Task assigned: Architect, please outline our rate limiter topology spanning 250 global cluster nodes for a total 10M requests limit.',
        consensusPct: 20,
        nodeStatuses: { orchestrator: 'thinking', architect: 'waiting', reviewer: 'idle', qa: 'idle', devops: 'idle' },
        filesAfterStep: [],
      },
      {
        round: 1,
        senderId: 'architect',
        receiverId: 'reviewer',
        messageType: 'propose',
        badgeLabel: 'PROPOSE',
        messageText: 'Initial Draft: Sliding window rate limiters stored locally on Envoy edges, using a central Redis cluster for state syncing to reconcile cluster ceilings.',
        consensusPct: 45,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'thinking', qa: 'idle', devops: 'idle' },
        filesAfterStep: [
          {
            filename: 'rate_limiter.py',
            language: 'python',
            code: `# Initial draft
class RateLimiter:
    pass # Wait for consensus`,
          },
        ],
      },
      {
        round: 2,
        senderId: 'reviewer',
        receiverId: 'architect',
        messageType: 'critique',
        badgeLabel: 'CRITIQUE',
        messageText: 'CRITIQUE: A central Redis Cluster will struggle at 10M RPS and creates a Single Point of Failure (SPOF) during network partitions. Let us use localized PN-Counters and a gossip protocol (CRDT) instead.',
        consensusPct: 60,
        nodeStatuses: { orchestrator: 'idle', architect: 'thinking', reviewer: 'critiquing', qa: 'idle', devops: 'idle' },
        filesAfterStep: [
          {
            filename: 'rate_limiter.py',
            language: 'python',
            code: `# Improved local window but fails split-brain scenario
`,
          },
        ],
      },
      {
        round: 3,
        senderId: 'architect',
        receiverId: 'qa',
        messageType: 'propose',
        badgeLabel: 'REVISED PROPOSAL',
        messageText: 'Reconciled: Replaced Redis cluster with peer-to-peer BucketCRDT in Rust for gossip synchronization, combined with Sliding Window buckets in memory on the edges. Handing to QA.',
        consensusPct: 75,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'idle', qa: 'thinking', devops: 'idle' },
        filesAfterStep: [
          {
            filename: 'rate_limiter.py',
            language: 'python',
            code: `import time
from typing import Dict, Tuple

class DistributedSlidingWindow:
    """Consensus-designed high-performance token-bucket and sliding-window rate-limiter"""
    def __init__(self, rps_limit: int = 10000000, cluster_nodes: int = 250):
        self.node_limit = rps_limit // cluster_nodes
        self.windows: Dict[str, Tuple[int, int]] = {} # ip: (tokens_used, timestamp)
        self.window_size = 1.0 # seconds
`,
          },
          {
            filename: 'cluster_sync.rs',
            language: 'rust',
            code: `use std::collections::HashMap;
// Bucket CRDT structure initiated
`,
          },
        ],
      },
      {
        round: 4,
        senderId: 'qa',
        receiverId: 'devops',
        messageType: 'endorse',
        badgeLabel: 'ENDORSE',
        messageText: 'ENDORSED: Evaluated the gossip structure against 30% synthetic network partition models. Verified: local limits gracefully fall back without cascading failure. Looks safe for release.',
        consensusPct: 90,
        nodeStatuses: { orchestrator: 'idle', architect: 'idle', reviewer: 'idle', qa: 'endorsing', devops: 'thinking' },
        filesAfterStep: [
          {
            filename: 'rate_limiter.py',
            language: 'python',
            code: `import time
from typing import Dict, Tuple

class DistributedSlidingWindow:
    """Consensus-designed high-performance token-bucket and sliding-window rate-limiter"""
    def __init__(self, rps_limit: int = 10000000, cluster_nodes: int = 250):
        self.node_limit = rps_limit // cluster_nodes
        self.windows: Dict[str, Tuple[int, int]] = {} # ip: (tokens_used, timestamp)
        self.window_size = 1.0 # seconds

    def request_allowed(self, user_ip: str, now: float = None) -> bool:
        if now is None:
            now = time.time()
        
        # Core sliding window bucket lookup with synchronization steps
        bucket_key = int(now / self.window_size)
        tokens, last_update = self.windows.get(user_ip, (0, bucket_key))
        
        if last_update < bucket_key:
            tokens = 0
            
        if tokens < self.node_limit:
            self.windows[user_ip] = (tokens + 1, bucket_key)
            return True
        return False
`,
          },
          {
            filename: 'cluster_sync.rs',
            language: 'rust',
            code: `// Gossip and CRDT replication routine for Rate Limiter buckets
use std::collections::HashMap;

pub struct BucketCRDT {
    node_id: String,
    counters: HashMap<String, u64>, // NodeID -> Requests
}
`,
          },
        ],
      },
      {
        round: 5,
        senderId: 'devops',
        receiverId: 'orchestrator',
        messageType: 'endorse',
        badgeLabel: 'COMPILE SUCCESS',
        messageText: 'RELEASE READY: Docker file ready, zero-allocation Rust code builds perfectly, sliding window bounds validated. Ready to ship!',
        consensusPct: 100,
        nodeStatuses: { orchestrator: 'idle', architect: 'idle', reviewer: 'idle', qa: 'idle', devops: 'endorsing' },
        filesAfterStep: [
          {
            filename: 'rate_limiter.py',
            language: 'python',
            code: `import time
from typing import Dict, Tuple

class DistributedSlidingWindow:
    """Consensus-designed high-performance token-bucket and sliding-window rate-limiter"""
    def __init__(self, rps_limit: int = 10000000, cluster_nodes: int = 250):
        self.node_limit = rps_limit // cluster_nodes
        self.windows: Dict[str, Tuple[int, int]] = {} # ip: (tokens_used, timestamp)
        self.window_size = 1.0 # seconds

    def request_allowed(self, user_ip: str, now: float = None) -> bool:
        if now is None:
            now = time.time()
        
        # Core sliding window bucket lookup with synchronization steps
        bucket_key = int(now / self.window_size)
        tokens, last_update = self.windows.get(user_ip, (0, bucket_key))
        
        if last_update < bucket_key:
            tokens = 0
            
        if tokens < self.node_limit:
            self.windows[user_ip] = (tokens + 1, bucket_key)
            return True
        return False
`,
          },
          {
            filename: 'cluster_sync.rs',
            language: 'rust',
            code: `// Gossip and CRDT replication routine for Rate Limiter buckets
use std::collections::HashMap;
use std::time::SystemTime;

pub struct BucketCRDT {
    node_id: String,
    counters: HashMap<String, u64>, // NodeID -> Requests
}

impl BucketCRDT {
    pub fn merge(&mut self, remote: &BucketCRDT) {
        for (node, &count) in remote.counters.iter() {
            let current = self.counters.entry(node.clone()).or_insert(0);
            if count > *current {
                *current = count; // Retain highest cluster state
            }
        }
    }
}
`,
          },
        ],
      },
    ],
  },
  {
    id: 'multi-master-db',
    goal: 'Build a fault-tolerant multi-master replicated database',
    agentsPreset: 'High Availability Engineers',
    initialNodes: JSON.parse(JSON.stringify(INITIAL_GENERIC_NODES)),
    completedFiles: [
      {
        filename: 'replication.go',
        language: 'golang',
        code: `package database

import "sync"

type RaftNode struct {
    mu        sync.Mutex
    NodeId    int
    State     string // Leader, Follower, Candidate
    Log       []LogEntry
    PeerNodes []int
}

type LogEntry struct {
    Term    int
    Command string
}

func (node *RaftNode) CommitCommand(command string) bool {
    node.mu.Lock()
    defer node.mu.Unlock()
    // Append entry to replicated log and broadcast
    node.Log = append(node.Log, LogEntry{Term: 1, Command: command})
    return true
}
`,
      },
    ],
    steps: [
      {
        round: 1,
        senderId: 'orchestrator',
        receiverId: 'architect',
        messageType: 'reply',
        badgeLabel: 'ASSIGN',
        messageText: 'Assigned: Create a highly available multi-master replication configuration for a transactional key-value database.',
        consensusPct: 15,
        nodeStatuses: { orchestrator: 'thinking', architect: 'waiting', reviewer: 'idle', qa: 'idle', devops: 'idle' },
        filesAfterStep: [],
      },
      {
        round: 2,
        senderId: 'architect',
        receiverId: 'reviewer',
        messageType: 'propose',
        badgeLabel: 'PROPOSE',
        messageText: 'Proposal: Use standard active-active database replication. High durability is traded off for real-time reads with async commits across 3 cloud regions.',
        consensusPct: 40,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'thinking', qa: 'idle', devops: 'idle' },
        filesAfterStep: [],
      },
      {
        round: 3,
        senderId: 'reviewer',
        receiverId: 'architect',
        messageType: 'critique',
        badgeLabel: 'CRITIQUE',
        messageText: 'Critique: Async commits without coordination can lead to serious write skew and out-of-order execution during regional failures. We should implement a lightweight Raft layer or vector clocks for replication consensus.',
        consensusPct: 65,
        nodeStatuses: { orchestrator: 'idle', architect: 'thinking', reviewer: 'critiquing', qa: 'idle', devops: 'idle' },
        filesAfterStep: [],
      },
      {
        round: 4,
        senderId: 'architect',
        receiverId: 'qa',
        messageType: 'reply',
        badgeLabel: 'CORRECTED',
        messageText: 'Revised: Re-architected with Raft Multi-Paxos algorithm for active leader coordination. Added dynamic log commits.',
        consensusPct: 80,
        nodeStatuses: { orchestrator: 'idle', architect: 'tool_call', reviewer: 'idle', qa: 'thinking', devops: 'idle' },
        filesAfterStep: [
          {
            filename: 'replication.go',
            language: 'golang',
            code: `package database
// Draft Raft model
`,
          },
        ],
      },
      {
        round: 5,
        senderId: 'qa',
        receiverId: 'orchestrator',
        messageType: 'endorse',
        badgeLabel: 'ENDORSE',
        messageText: 'Endorsed: Stress tested consensus logs with simulated network splits. FSM recovers and reaches state uniformity under all partitions.',
        consensusPct: 100,
        nodeStatuses: { orchestrator: 'idle', architect: 'idle', reviewer: 'idle', qa: 'endorsing', devops: 'idle' },
        filesAfterStep: [
          {
            filename: 'replication.go',
            language: 'golang',
            code: `package database

import "sync"

type RaftNode struct {
    mu        sync.Mutex
    NodeId    int
    State     string // Leader, Follower, Candidate
    Log       []LogEntry
    PeerNodes []int
}

type LogEntry struct {
    Term    int
    Command string
}

func (node *RaftNode) CommitCommand(command string) bool {
    node.mu.Lock()
    defer node.mu.Unlock()
    // Append entry to replicated log and broadcast
    node.Log = append(node.Log, LogEntry{Term: 1, Command: command})
    return true
}
`,
          },
        ],
      },
    ],
  },
];
