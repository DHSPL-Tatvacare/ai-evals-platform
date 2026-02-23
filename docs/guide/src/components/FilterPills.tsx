interface FilterPillsProps {
  options: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}

export default function FilterPills({ options, active, onChange }: FilterPillsProps) {
  return (
    <div className="flex flex-wrap gap-2 my-4">
      {options.map((opt) => {
        const isActive = active === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className="px-4 py-2 rounded-full text-sm font-medium cursor-pointer transition-colors"
            style={{
              background: isActive ? 'var(--accent)' : 'var(--bg-secondary)',
              color: isActive ? '#ffffff' : 'var(--text-secondary)',
              border: isActive ? 'none' : '1px solid var(--border)',
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
