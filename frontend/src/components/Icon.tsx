// A few inline SVG icons (24x24, stroke style), so we need no icon library.

const PATHS: Record<string, string> = {
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  plus: "M12 5v14M5 12h14",
  chart: "M3 3v18h18M7 15l4-4 3 3 5-6",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  check: "M20 6 9 17l-5-5",
  robot: "M12 8V4M8 8h8a4 4 0 0 1 4 4v4a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-4a4 4 0 0 1 4-4ZM9 13h.01M15 13h.01",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6Z",
};

export default function Icon({ name, size = 18 }: { name: keyof typeof PATHS; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect width="28" height="28" rx="7" fill="url(#logo-gradient)" />
      <rect x="7" y="7" width="6" height="6" rx="1.5" fill="white" />
      <rect x="15" y="7" width="6" height="6" rx="1.5" fill="white" fillOpacity=".6" />
      <rect x="7" y="15" width="6" height="6" rx="1.5" fill="white" fillOpacity=".6" />
      <rect x="15" y="15" width="6" height="6" rx="1.5" fill="white" fillOpacity=".3" />
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="28" y2="28">
          <stop stopColor="#6366f1" />
          <stop offset="1" stopColor="#2563eb" />
        </linearGradient>
      </defs>
    </svg>
  );
}
