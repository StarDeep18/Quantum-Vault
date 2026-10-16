import type { SVGProps } from 'react'

export type IconName =
  | 'arrow-right' | 'sun' | 'moon' | 'lock' | 'unlock' | 'shield' | 'plus'
  | 'search' | 'eye' | 'eye-off' | 'copy' | 'key' | 'sparkle' | 'fingerprint'
  | 'globe' | 'grid' | 'file' | 'external' | 'dots' | 'check' | 'chevron'
  | 'x' | 'trash' | 'edit' | 'wifi' | 'cpu' | 'disc' | 'clock' | 'arrow-up-right'

export function Icon({ name, size = 18, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.65,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true as const,
    ...props,
  }
  const paths: Record<IconName, React.ReactNode> = {
    'arrow-right': <><path d="M4.5 12h14.5" /><path d="m13 5.5 6.5 6.5-6.5 6.5" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></>,
    moon: <path d="M20.6 15.1A8.8 8.8 0 0 1 8.9 3.4 8.9 8.9 0 1 0 20.6 15.1Z" />,
    lock: <><rect x="4.5" y="10" width="15" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /><path d="M12 14.5v2" /></>,
    unlock: <><rect x="4.5" y="10" width="15" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 7.8-1" /><path d="M12 14.5v2" /></>,
    shield: <><path d="M12 3 19 6v5.4c0 4.5-3 7.9-7 9.6-4-1.7-7-5.1-7-9.6V6l7-3Z" /><path d="m9 12.2 2 2 4-4.2" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m15.5 15.5 4.2 4.2" /></>,
    eye: <><path d="M2.5 12s3.3-6 9.5-6 9.5 6 9.5 6-3.3 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.7" /></>,
    'eye-off': <><path d="m3 3 18 18M10.6 6.2c.5-.1.9-.2 1.4-.2 6.2 0 9.5 6 9.5 6a14.9 14.9 0 0 1-3 3.7M6.2 6.5C3.8 8 2.5 12 2.5 12s3.3 6 9.5 6c1.1 0 2.1-.2 3-.5" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2" /></>,
    key: <><circle cx="8" cy="15.5" r="4.2" /><path d="m11.2 12.4 8.3-8.3 2 2-2.2 2.2 1.2 1.2-2.1 2.1-1.2-1.2-2.2 2.2" /><path d="M8 15.5h.01" /></>,
    sparkle: <><path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /><path d="m19 15 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z" /></>,
    fingerprint: <><path d="M12 11.2c-1 0-1.8.8-1.8 1.8 0 2.6-.3 4.8-1.2 6.7M12 7.5a5.5 5.5 0 0 0-5.5 5.5c0 2-.3 3.8-.9 5.3M12 4a9 9 0 0 0-9 9c0 .9-.1 1.7-.3 2.5" /><path d="M12 11.2c1 0 1.8.8 1.8 1.8 0 3.3.5 5.7 1.7 7.1M12 7.5a5.5 5.5 0 0 1 5.5 5.5c0 2.2.4 4.3 1.2 6" /><path d="M12 4a9 9 0 0 1 9 9c0 1.3.2 2.6.6 3.7" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3.5 12h17M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
    grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
    file: <><path d="M7 3.5h7l4 4v13H7a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2Z" /><path d="M14 3.5v4h4M8.5 12h7M8.5 15.5h7" /></>,
    external: <><path d="M13 4h7v7M20 4l-9 9" /><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" /></>,
    dots: <><circle cx="5" cy="12" r=".9" fill="currentColor" /><circle cx="12" cy="12" r=".9" fill="currentColor" /><circle cx="19" cy="12" r=".9" fill="currentColor" /></>,
    check: <path d="m5 12.5 4.2 4.2L19.5 6.5" />,
    chevron: <path d="m7 10 5 5 5-5" />,
    x: <><path d="m6 6 12 12M18 6 6 18" /></>,
    trash: <><path d="M4 7h16M10 11v6M14 11v6M5.5 7l.8 13h11.4l.8-13M9 7V4h6v3" /></>,
    edit: <><path d="M12 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8" /><path d="m14 5 5 5M10 14l8.8-8.8a2.1 2.1 0 0 1 3 3L13 17l-4 1 1-4Z" /></>,
    wifi: <><path d="M5 9.5a11 11 0 0 1 14 0M8 13a6.5 6.5 0 0 1 8 0m-5 3.5h.01" /><circle cx="12" cy="18.5" r="1" fill="currentColor" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4" /><path d="M10 10h4v4h-4z" /></>,
    disc: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3" /><path d="m5.5 5.5 4.4 4.4m4.2 4.2 4.4 4.4" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.2 2" /></>,
    'arrow-up-right': <><path d="M7 17 17 7M7 7h10v10" /></>,
  }
  return <svg {...common}>{paths[name]}</svg>
}

export function BrandMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="17.4" stroke="currentColor" strokeWidth="1.2" opacity=".72" />
      <circle cx="20" cy="20" r="12.2" stroke="currentColor" strokeWidth="1" opacity=".42" />
      <circle cx="20" cy="20" r="5.3" stroke="currentColor" strokeWidth="1.2" />
      <path d="M20 2.7v6.4M20 30.9v6.4M2.7 20h6.4m21.8 0h6.4M7.75 7.75l4.5 4.5m15.5 15.5 4.5 4.5M32.25 7.75l-4.5 4.5m-15.5 15.5-4.5 4.5" stroke="currentColor" strokeWidth="1.15" />
      <circle cx="20" cy="20" r="1.35" fill="currentColor" />
    </svg>
  )
}
