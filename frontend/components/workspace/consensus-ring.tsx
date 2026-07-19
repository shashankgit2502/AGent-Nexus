"use client";

/**
 * Consensus ring (§9.2/§9.5) — the at-a-glance convergence signal in the header.
 * Animated arc from mean confidence (0–1); turns green at/above the target τ
 * (the completion cue, §9.9). Pure presentational: it reads numbers, the store
 * owns the data.
 */
import { motion } from "framer-motion";

interface ConsensusRingProps {
  /** mean confidence 0–1, or null before any consensus_update. */
  value: number | null;
  /** target threshold τ, 0–1. */
  target: number;
  size?: number;
}

export function ConsensusRing({ value, target, size = 56 }: ConsensusRingProps) {
  const pct = value ?? 0;
  const reached = value !== null && value >= target;
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const color = reached ? "#22c55e" : "#10b981";

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={false}
          animate={{ strokeDashoffset: circumference * (1 - pct) }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
          style={{ filter: reached ? "drop-shadow(0 0 6px #22c55e88)" : "none" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[12px] font-extrabold text-white leading-none font-mono">
          {value === null ? "—" : `${Math.round(pct * 100)}%`}
        </span>
        <span className="text-[7px] font-mono uppercase tracking-widest text-zinc-500 mt-0.5">
          τ {Math.round(target * 100)}
        </span>
      </div>
    </div>
  );
}
