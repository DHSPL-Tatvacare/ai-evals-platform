import { useState, useEffect, useCallback, type ComponentType } from "react";
import {
  LayoutDashboard,
  GitBranch,
  Users,
  Key,
  FileText,
  FlaskConical,
  Workflow,
  Code2,
  Database,
  Package,
  Terminal,
  Lightbulb,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeft,
  ArrowLeft,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { navigation } from "@/features/guide/data/navigation";
import { useTheme } from "@/features/guide/hooks/useTheme";
import { cn } from "@/utils";
import SectionRail from "./SectionRail";
import {
  Overview,
  Workflows,
  UsersTenants,
  ApiAuth,
  PromptsSchemas,
  Evaluators,
  Pipelines,
  BrainMap,
  DbApiRef,
  Sbom,
  ApiExplorer,
  ForWhatItsWorth,
} from "@/features/guide/pages";

import "@/features/guide/styles/guide.css";

const iconMap: Record<string, ComponentType<{ className?: string }>> = {
  Layout: LayoutDashboard,
  GitBranch,
  Users,
  Key,
  FileText,
  FlaskConical,
  Workflow,
  Code2,
  Database,
  Package,
  Terminal,
  Lightbulb,
};

const pageMap: Record<string, ComponentType> = {
  overview: Overview,
  workflows: Workflows,
  "users-tenants": UsersTenants,
  "api-auth": ApiAuth,
  "prompts-schemas": PromptsSchemas,
  evaluators: Evaluators,
  pipelines: Pipelines,
  "brain-map": BrainMap,
  "db-api-ref": DbApiRef,
  sbom: Sbom,
  "api-explorer": ApiExplorer,
  fwiw: ForWhatItsWorth,
};

function getHashPage(): string {
  const hash = window.location.hash.replace("#", "");
  return hash && pageMap[hash] ? hash : "overview";
}

export default function GuideLayout() {
  const [activePage, setActivePage] = useState(getHashPage);
  const [collapsed, setCollapsed] = useState(false);
  const { theme, toggle } = useTheme();
  const appNavigate = useNavigate();

  useEffect(() => {
    const onHashChange = () => setActivePage(getHashPage());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((id: string) => {
    window.location.hash = id;
  }, []);

  const PageComponent = pageMap[activePage] ?? Overview;

  // Collapsed sidebar
  if (collapsed) {
    return (
      <div className="guide-root flex h-screen overflow-hidden" style={{ '--sidebar-width': '56px' } as React.CSSProperties}>
        <aside className="flex h-screen w-14 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <div className="flex h-14 items-center justify-center border-b border-[var(--border-subtle)]">
            <button
              onClick={() => setCollapsed(false)}
              className="rounded-md p-2 text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Expand sidebar"
            >
              <PanelLeft className="h-5 w-5" />
            </button>
          </div>
          <div className="flex-1 flex flex-col items-center py-3 gap-1">
            <button
              onClick={() => appNavigate("/")}
              className="flex h-9 w-9 items-center justify-center rounded-[6px] text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Back to app"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="border-t border-[var(--border-subtle)] w-8 my-1" />
            {navigation.map((item) => {
              const Icon = iconMap[item.icon];
              const isActive = activePage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => navigate(item.id)}
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-[6px] transition-colors",
                    isActive
                      ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
                  )}
                  title={item.label}
                >
                  {Icon && <Icon className="h-5 w-5" />}
                </button>
              );
            })}
          </div>
          <div className="border-t border-[var(--border-subtle)] p-2">
            <button
              onClick={toggle}
              className="flex h-9 w-9 items-center justify-center rounded-[6px] text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            >
              {theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
            </button>
          </div>
        </aside>

        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          <SectionRail pageKey={activePage} />
          <main className="mx-auto max-w-[1200px] w-full px-4 py-6 sm:px-8 flex-1">
            <PageComponent key={activePage} />
          </main>
        </div>
      </div>
    );
  }

  // Expanded sidebar
  return (
    <div className="guide-root flex h-screen overflow-hidden" style={{ '--sidebar-width': '280px' } as React.CSSProperties}>
      <aside className="flex h-screen w-[280px] flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
        {/* Header */}
        <div className="flex h-14 items-center justify-between border-b border-[var(--border-subtle)] px-4">
          <div className="flex items-center gap-2 min-w-0">
            <img
              src="/guide/favicon.jpeg"
              className="w-6 h-6 rounded-md shrink-0"
              alt="AI Evals"
            />
            <span className="text-[13px] font-semibold text-[var(--text-primary)] truncate">
              Guide
            </span>
          </div>
          <button
            onClick={() => setCollapsed(true)}
            className="ml-1 rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-2 px-2">
          {/* Back to app */}
          <button
            onClick={() => appNavigate("/")}
            className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 text-[12px] font-medium text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors mb-1"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to app
          </button>

          <div className="border-t border-[var(--border-subtle)] my-1.5" />

          {/* Page links */}
          <div className="space-y-0.5">
            {navigation.map((item) => {
              const Icon = iconMap[item.icon];
              const isActive = activePage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => navigate(item.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium transition-colors",
                    isActive
                      ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {Icon && <Icon className="h-4 w-4" />}
                  {item.label}
                </button>
              );
            })}
          </div>
        </nav>

        {/* Footer — theme toggle */}
        <div className="border-t border-[var(--border-subtle)] p-2">
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            {theme === "light" ? "Dark mode" : "Light mode"}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
        <SectionRail pageKey={activePage} />
        <main className="mx-auto max-w-[1200px] w-full px-4 py-6 sm:px-8 flex-1">
          <PageComponent key={activePage} />
        </main>
      </div>
    </div>
  );
}
