import type { ReactNode, RefObject } from "react";
import ExportButton from "./ExportButton";

interface PageHeaderProps {
  title?: string;
  subtitle?: ReactNode;
  pageTitle: string;
  contentRef: RefObject<HTMLDivElement | null>;
}

export default function PageHeader({
  title,
  subtitle,
  pageTitle,
  contentRef,
}: PageHeaderProps) {
  const hasHeaderContent = Boolean(title || subtitle);

  return (
    <div className={hasHeaderContent ? "relative mb-4" : "relative mb-2 h-9"}>
      {hasHeaderContent && (
        <div className="pr-16 sm:pr-20">
          {title && (
            <h2
              className="text-2xl font-bold leading-tight"
              style={{ color: "var(--text)" }}
            >
              {title}
            </h2>
          )}
          {subtitle && (
            <p
              className={
                title
                  ? "mt-1.5 text-sm leading-relaxed"
                  : "text-sm leading-relaxed"
              }
              style={{ color: "var(--text-secondary)" }}
            >
              {subtitle}
            </p>
          )}
        </div>
      )}
      <div className="absolute right-0 top-0 print:hidden">
        <ExportButton pageTitle={pageTitle} contentRef={contentRef} compact />
      </div>
    </div>
  );
}
