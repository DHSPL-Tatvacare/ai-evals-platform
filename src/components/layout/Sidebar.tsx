import { useCallback, useState } from "react";
import {
  Plus,
  PanelLeftClose,
  PanelLeft,
  Settings,
  LayoutDashboard,
  ListChecks,
  ScrollText,
  BookOpen,
  MessageSquare,
  FileSpreadsheet,
  ShieldAlert,
  LogOut,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Button,
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui";
import {
  useUIStore,
  useAppStore,
  useChatStore,
  useKairaBotSettings,
} from "@/stores";
import { useAuthStore } from "@/stores/authStore";
import { useCurrentAppMetadata } from "@/hooks";
import { cn } from "@/utils";
import { routes } from "@/config/routes";
import { AppSwitcher } from "./AppSwitcher";
import { KairaSidebarContent } from "./KairaSidebarContent";
import { VoiceRxSidebarContent } from "./VoiceRxSidebarContent";

interface SidebarProps {
  onNewEval?: () => void;
}

export function Sidebar({ onNewEval }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const appId = useAppStore((state) => state.currentApp);
  const appMetadata = useCurrentAppMetadata();
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  // Kaira chat specific
  const { createSession, isCreatingSession, isStreaming } = useChatStore();
  const { settings: kairaBotSettings } = useKairaBotSettings();
  const kairaChatUserId = kairaBotSettings.kairaChatUserId;

  // Compute settings path based on current app
  const settingsPath =
    appId === "kaira-bot" ? routes.kaira.settings : routes.voiceRx.settings;
  const isSettingsActive =
    location.pathname === routes.voiceRx.settings ||
    location.pathname === routes.kaira.settings;
  const guideUrl = import.meta.env.VITE_GUIDE_URL || "http://localhost:5174";

  // Auth
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  // Modal management (for batch/adversarial wizards)
  const openModal = useUIStore((s) => s.openModal);

  // Check if this is Kaira Bot app
  const isKairaBot = appId === "kaira-bot";

  // Controlled state for the +New popover
  const [newMenuOpen, setNewMenuOpen] = useState(false);

  // Disable new button when creating session or streaming
  const isNewButtonDisabled =
    isKairaBot && (!kairaChatUserId || isCreatingSession || isStreaming);

  // Handle new button click - different behavior for Kaira vs Voice Rx
  const handleNewClick = useCallback(async () => {
    if (isKairaBot && kairaChatUserId) {
      // Guard handled by store, but also check here for early return
      if (isCreatingSession || isStreaming) return;

      try {
        // Create new Kaira chat session — createSession already sets
        // currentSessionId in the store, so no separate selectSession needed.
        // Navigate to the new session URL and let KairaBotTabView sync.
        const session = await createSession(appId, kairaChatUserId);
        navigate(routes.kaira.chatSession(session.id));
      } catch (err) {
        // Session creation failed (likely concurrent creation guard)
        console.warn("Session creation skipped:", err);
      }
    } else if (!isKairaBot && onNewEval) {
      // Voice Rx - use existing handler
      onNewEval();
    }
  }, [
    isKairaBot,
    kairaChatUserId,
    isCreatingSession,
    isStreaming,
    appId,
    createSession,
    navigate,
    onNewEval,
  ]);

  // Collapsed sidebar
  if (sidebarCollapsed) {
    return (
      <aside className="flex h-screen w-14 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
        <div className="flex h-14 items-center justify-center border-b border-[var(--border-subtle)]">
          <button
            onClick={toggleSidebar}
            className="rounded-md p-2 text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
            title="Expand sidebar"
          >
            <PanelLeft className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 flex flex-col items-center py-3 gap-2">
          {isKairaBot ? (
            <Popover open={newMenuOpen} onOpenChange={setNewMenuOpen}>
              <PopoverTrigger asChild>
                <Button
                  size="sm"
                  disabled={isNewButtonDisabled}
                  className="h-9 w-9 p-0"
                  title="New"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                side="right"
                align="start"
                className="w-[220px] p-1"
              >
                <KairaNewMenu
                  onNewChat={handleNewClick}
                  onBatchEval={() => openModal("batchEval")}
                  onAdversarialTest={() => openModal("adversarialTest")}
                  onClose={() => setNewMenuOpen(false)}
                />
              </PopoverContent>
            </Popover>
          ) : (
            <Button
              size="sm"
              onClick={handleNewClick}
              disabled={isNewButtonDisabled}
              className="h-9 w-9 p-0"
              title="New evaluation"
            >
              <Plus className="h-4 w-4" />
            </Button>
          )}

          <div className="border-t border-[var(--border-subtle)] w-8 my-1" />
          {isKairaBot ? (
            <>
              <CollapsedNavLink
                to={routes.kaira.dashboard}
                icon={LayoutDashboard}
                title="Dashboard"
              />
              <CollapsedNavLink
                to={routes.kaira.runs}
                icon={ListChecks}
                title="Runs"
              />
              <CollapsedNavLink
                to={routes.kaira.logs}
                icon={ScrollText}
                title="Logs"
              />
            </>
          ) : (
            <>
              <CollapsedNavLink
                to={routes.voiceRx.dashboard}
                icon={LayoutDashboard}
                title="Dashboard"
              />
              <CollapsedNavLink
                to={routes.voiceRx.runs}
                icon={ListChecks}
                title="Runs"
              />
              <CollapsedNavLink
                to={routes.voiceRx.logs}
                icon={ScrollText}
                title="Logs"
              />
            </>
          )}
        </div>
        <div className="border-t border-[var(--border-subtle)] p-2 space-y-1">
          <Link
            to={settingsPath}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-[6px] transition-colors",
              isSettingsActive
                ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
            )}
            title="Settings"
          >
            <Settings className="h-5 w-5" />
          </Link>
          <a
            href={guideUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex h-9 w-9 items-center justify-center rounded-[6px] text-[var(--text-secondary)] transition-colors hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]"
            title="Guide"
          >
            <BookOpen className="h-5 w-5" />
          </a>
          {user && (
            <button
              onClick={logout}
              className="flex h-9 w-9 items-center justify-center rounded-[6px] text-[var(--text-secondary)] transition-colors hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]"
              title={`Logout (${user.email})`}
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-screen w-[280px] flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
      <div className="flex h-14 items-center justify-between border-b border-[var(--border-subtle)] px-4">
        <AppSwitcher />
        <div className="flex items-center gap-1">
          {isKairaBot ? (
            <Popover open={newMenuOpen} onOpenChange={setNewMenuOpen}>
              <PopoverTrigger asChild>
                <Button
                  size="sm"
                  disabled={isNewButtonDisabled}
                  isLoading={isCreatingSession}
                >
                  <Plus className="h-4 w-4" />
                  New
                </Button>
              </PopoverTrigger>
              <PopoverContent
                side="bottom"
                align="end"
                className="w-[260px] p-1"
              >
                <KairaNewMenu
                  onNewChat={handleNewClick}
                  onBatchEval={() => openModal("batchEval")}
                  onAdversarialTest={() => openModal("adversarialTest")}
                  onClose={() => setNewMenuOpen(false)}
                />
              </PopoverContent>
            </Popover>
          ) : (
            <Button
              size="sm"
              onClick={handleNewClick}
              disabled={isNewButtonDisabled}
              isLoading={isCreatingSession}
            >
              <Plus className="h-4 w-4" />
              New
            </Button>
          )}
          <button
            onClick={toggleSidebar}
            className="ml-1 rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Conditional content based on app */}
      {isKairaBot ? (
        <KairaSidebarContent
          searchPlaceholder={appMetadata.searchPlaceholder}
        />
      ) : (
        <VoiceRxSidebarContent
          searchPlaceholder={appMetadata.searchPlaceholder}
        />
      )}

      <div className="border-t border-[var(--border-subtle)] p-3 space-y-1">
        <Link
          to={settingsPath}
          className={cn(
            "flex items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium transition-colors",
            isSettingsActive
              ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
              : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
          )}
        >
          <Settings className="h-4 w-4" />
          Settings
        </Link>
        <a
          href={guideUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]"
          title="Guide"
        >
          <BookOpen className="h-4 w-4" />
          Guide
        </a>
      </div>
      {user && (
        <div className="border-t border-[var(--border-subtle)] p-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-accent)]/20 text-[11px] font-semibold text-[var(--text-brand)]">
              {user.displayName
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-[var(--text-primary)]">
                {user.displayName}
              </div>
              <div className="truncate text-[11px] text-[var(--text-muted)]">
                {user.tenantName}
                {(user.role === 'admin' || user.role === 'owner') && (
                  <span className="ml-1 text-[var(--text-brand)]">
                    {user.role}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={logout}
              className="shrink-0 rounded-md p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}

function KairaNewMenu({
  onNewChat,
  onBatchEval,
  onAdversarialTest,
  onClose,
}: {
  onNewChat: () => void;
  onBatchEval: () => void;
  onAdversarialTest: () => void;
  onClose: () => void;
}) {
  const items = [
    {
      icon: MessageSquare,
      label: "New Chat",
      description: "Start a new Kaira conversation",
      action: onNewChat,
    },
    {
      icon: FileSpreadsheet,
      label: "Batch Evaluation",
      description: "Evaluate threads from CSV data",
      action: onBatchEval,
    },
    {
      icon: ShieldAlert,
      label: "Adversarial Test",
      description: "Run adversarial inputs against Kaira",
      action: onAdversarialTest,
    },
  ];

  return (
    <div className="py-1">
      {items.map((item) => (
        <button
          key={item.label}
          onClick={() => {
            onClose();
            item.action();
          }}
          className="w-full flex items-start gap-3 px-3 py-2 text-left rounded-md hover:bg-[var(--interactive-secondary)] transition-colors"
        >
          <item.icon className="h-4 w-4 mt-0.5 text-[var(--text-secondary)] shrink-0" />
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-[var(--text-primary)]">
              {item.label}
            </div>
            <div className="text-[11px] text-[var(--text-muted)] leading-tight">
              {item.description}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

function CollapsedNavLink({
  to,
  icon: Icon,
  title,
}: {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
}) {
  const location = useLocation();
  const isActive = location.pathname.startsWith(to);
  return (
    <Link
      to={to}
      className={cn(
        "flex h-9 w-9 items-center justify-center rounded-[6px] transition-colors",
        isActive
          ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
      )}
      title={title}
    >
      <Icon className="h-5 w-5" />
    </Link>
  );
}
