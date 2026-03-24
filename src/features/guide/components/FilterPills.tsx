interface FilterPillsProps {
  options: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export default function FilterPills({
  options,
  active,
  onChange,
  className = "",
}: FilterPillsProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {options.map((opt) => {
        const isActive = active === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className="rounded-full px-3 py-1.5 text-[13px] font-medium cursor-pointer transition-colors"
            style={{
              background: isActive ? "var(--accent)" : "var(--bg-secondary)",
              color: isActive ? "#ffffff" : "var(--text-secondary)",
              border: isActive ? "none" : "1px solid var(--border)",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
