export function VaultSilhouette({ className = '' }: { className?: string }) {
  return (
    <div className={`vault-scene-fallback ${className}`} aria-hidden="true">
      <svg viewBox="0 0 640 560" role="presentation">
        <defs>
          <linearGradient id="safe-metal" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#777d77" /><stop offset=".42" stopColor="#333a38" /><stop offset="1" stopColor="#171c1b" /></linearGradient>
          <radialGradient id="safe-face"><stop stopColor="#727772" /><stop offset=".7" stopColor="#424947" /><stop offset="1" stopColor="#222826" /></radialGradient>
          <filter id="safe-shadow" x="-25%" y="-25%" width="150%" height="150%"><feGaussianBlur stdDeviation="16" /></filter>
        </defs>
        <ellipse cx="322" cy="486" rx="210" ry="31" fill="#303531" opacity=".2" filter="url(#safe-shadow)" />
        <path d="M106 100 Q106 84 122 84h378q17 0 17 17v346q0 17-17 17H122q-16 0-16-17Z" fill="url(#safe-metal)" stroke="#92958c" strokeOpacity=".34" strokeWidth="2" />
        <path d="M127 105h369v337H127z" fill="#414846" stroke="#aaa58f" strokeOpacity=".38" strokeWidth="3" />
        <rect x="148" y="126" width="327" height="294" rx="20" fill="#373e3c" stroke="#8e938d" strokeOpacity=".45" strokeWidth="2" />
        <circle cx="311" cy="273" r="134" fill="url(#safe-face)" stroke="#a2a398" strokeOpacity=".8" strokeWidth="11" />
        <circle cx="311" cy="273" r="112" fill="none" stroke="#b6b2a5" strokeOpacity=".65" strokeWidth="2" />
        <circle cx="311" cy="273" r="90" fill="none" stroke="#a0a39a" strokeOpacity=".45" strokeWidth="3" />
        <g fill="#c0b99f" stroke="#353b38" strokeWidth="3">
          <rect x="300" y="138" width="22" height="37" rx="5" /><rect x="300" y="371" width="22" height="37" rx="5" />
          <rect x="176" y="262" width="37" height="22" rx="5" /><rect x="409" y="262" width="37" height="22" rx="5" />
          <rect x="212" y="170" width="22" height="37" rx="5" transform="rotate(-45 223 188)" /><rect x="390" y="345" width="22" height="37" rx="5" transform="rotate(-45 401 363)" />
          <rect x="390" y="170" width="22" height="37" rx="5" transform="rotate(45 401 188)" /><rect x="212" y="345" width="22" height="37" rx="5" transform="rotate(45 223 363)" />
        </g>
        <circle cx="311" cy="273" r="47" fill="#242a28" stroke="#b19a6a" strokeWidth="4" />
        <g stroke="#babcb4" strokeWidth="8" strokeLinecap="round">
          <path d="M311 273h61M311 273v-61M311 273l-43 43M311 273l43 43" />
        </g>
        <circle cx="311" cy="273" r="15" fill="#b39a65" stroke="#252a27" strokeWidth="4" />
        <g fill="#b4b2a4" opacity=".8"><circle cx="164" cy="143" r="5"/><circle cx="459" cy="143" r="5"/><circle cx="164" cy="402" r="5"/><circle cx="459" cy="402" r="5"/></g>
      </svg>
    </div>
  )
}
