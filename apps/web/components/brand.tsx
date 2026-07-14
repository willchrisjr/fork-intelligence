import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/" aria-label="Fork Intelligence home">
      <svg
        className="brand-mark"
        aria-hidden="true"
        width={compact ? 24 : 31}
        height={compact ? 24 : 31}
        viewBox="0 0 32 32"
        fill="none"
      >
        <path
          d="M9 5v19c0 2 1.5 3 3 3h2"
          stroke="currentColor"
          strokeWidth="2.7"
        />
        <path
          d="M9 15h7c4 0 7-3 7-7V6"
          stroke="currentColor"
          strokeWidth="2.7"
        />
        <circle cx="9" cy="4.5" r="3.2" fill="currentColor" />
        <circle cx="23" cy="5.5" r="3.2" fill="currentColor" />
        <circle cx="16" cy="27" r="3.2" fill="currentColor" />
      </svg>
      <span>Fork Intelligence</span>
    </Link>
  );
}
