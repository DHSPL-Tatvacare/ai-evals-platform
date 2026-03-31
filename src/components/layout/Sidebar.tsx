import { useCallback, useState } from "react";
import {
  Plus,
  PanelLeftClose,
  PanelLeft,
  Settings,
  LayoutDashboard,
  FileText,
  ListChecks,
  ScrollText,
  BookOpen,
  MessageSquare,
  FileSpreadsheet,
  ShieldAlert,
  LogOut,
  Users,
  KeyRound,
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
import { InsideSalesSidebarContent } from "./InsideSalesSidebarContent";
import { ChangePasswordDialog } from "@/features/auth/ChangePasswordDialog";

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
    appId === "kaira-bot" ? routes.kaira.settings
    : appId === "inside-sales" ? routes.insideSales.settings
    : routes.voiceRx.settings;
  const isSettingsActive =
    location.pathname === routes.voiceRx.settings ||
    location.pathname === routes.kaira.settings ||
    location.pathname === routes.insideSales.settings;
  const isGuideActive = location.pathname === routes.guide;

  // Auth
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const isAdmin = !!(user?.isOwner || user?.permissions.some((p) => ['user:create', 'user:edit', 'user:invite'].includes(p)));
  const isAdminActive = location.pathname.startsWith('/admin');

  // Modal management (for batch/adversarial wizards)
  const openModal = useUIStore((s) => s.openModal);

  // Check app type
  const isKairaBot = appId === "kaira-bot";
  const isInsideSales = appId === "inside-sales";

  // Controlled state for the +New popover
  const [newMenuOpen, setNewMenuOpen] = useState(false);

  // Change password dialog
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);

  // User menu popover
  const [userMenuOpen, setUserMenuOpen] = useState(false);

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
          {!isInsideSales && (isKairaBot ? (
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
          ))}

          <div className="border-t border-[var(--border-subtle)] w-8 my-1" />
          {isInsideSales ? (
            <>
              <CollapsedNavLink
                to={routes.insideSales.listing}
                icon={LayoutDashboard}
                title="Listing"
              />
              <CollapsedNavLink
                to={routes.insideSales.evaluators}
                icon={FileText}
                title="Evaluators"
              />
              <CollapsedNavLink
                to={routes.insideSales.runs}
                icon={ListChecks}
                title="Runs"
              />
              <CollapsedNavLink
                to={routes.insideSales.dashboard}
                icon={LayoutDashboard}
                title="Dashboard"
              />
              <CollapsedNavLink
                to={routes.insideSales.logs}
                icon={ScrollText}
                title="Logs"
              />
            </>
          ) : isKairaBot ? (
            <>
              <CollapsedNavLink
                to={routes.kaira.dashboard}
                icon={LayoutDashboard}
                title="Dashboard"
              />
              <CollapsedNavLink
                to={routes.kaira.evaluators}
                icon={FileText}
                title="Evaluators"
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
                to={routes.voiceRx.evaluators}
                icon={FileText}
                title="Evaluators"
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
          <Link
            to={routes.guide}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-[6px] transition-colors",
              isGuideActive
                ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
            )}
            title="Guide"
          >
            <BookOpen className="h-5 w-5" />
          </Link>
          {isAdmin && (
            <Link
              to={routes.adminUsers}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-[6px] transition-colors",
                isAdminActive
                  ? "bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]",
              )}
              title="Admin"
            >
              <Users className="h-5 w-5" />
            </Link>
          )}
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
          {!isInsideSales && (isKairaBot ? (
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
          ))}
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
      {isInsideSales ? (
        <InsideSalesSidebarContent />
      ) : isKairaBot ? (
        <KairaSidebarContent
          searchPlaceholder={appMetadata.searchPlaceholder}
        />
      ) : (
        <VoiceRxSidebarContent
          searchPlaceholder={appMetadata.searchPlaceholder}
        />
      )}

      {/* Bottom: single user row → popover with all options */}
      {user && (
        <div className="mt-auto border-t border-[var(--border-subtle)] p-2">
          <Popover open={userMenuOpen} onOpenChange={setUserMenuOpen}>
            <PopoverTrigger asChild>
              <button
                className="flex w-full items-center gap-2.5 rounded-[6px] px-2 py-2 transition-colors hover:bg-[var(--interactive-secondary)]"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-accent)]/20 text-[10px] font-semibold text-[var(--text-brand)]">
                  {user.displayName
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .toUpperCase()
                    .slice(0, 2)}
                </div>
                <div className="min-w-0 flex-1 text-left">
                  <div className="truncate text-[12px] font-medium leading-tight text-[var(--text-primary)]">
                    {user.displayName}
                  </div>
                  <div className="truncate text-[11px] leading-tight text-[var(--text-muted)]">
                    {user.tenantName}
                    {user.roleName && (
                      <span className="ml-1 text-[var(--text-brand)]">{user.roleName}</span>
                    )}
                  </div>
                </div>
              </button>
            </PopoverTrigger>
            <PopoverContent side="top" align="start" className="w-[220px] p-1">
              <UserMenu
                settingsPath={settingsPath}
                isSettingsActive={isSettingsActive}
                isGuideActive={isGuideActive}
                isAdmin={isAdmin}
                isAdminActive={isAdminActive}
                onLogout={logout}
                onChangePassword={() => {
                  setUserMenuOpen(false);
                  setIsChangePasswordOpen(true);
                }}
              />
            </PopoverContent>
          </Popover>
        </div>
      )}
      <ChangePasswordDialog
        isOpen={isChangePasswordOpen}
        onClose={() => setIsChangePasswordOpen(false)}
      />
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

function UserMenu({
  settingsPath,
  isSettingsActive,
  isGuideActive,
  isAdmin,
  isAdminActive,
  onLogout,
  onChangePassword,
}: {
  settingsPath: string;
  isSettingsActive: boolean;
  isGuideActive: boolean;
  isAdmin: boolean;
  isAdminActive: boolean;
  onLogout: () => void;
  onChangePassword: () => void;
}) {
  const menuLinkClass = "flex w-full items-center gap-2.5 rounded-[6px] px-3 py-1.5 text-[13px] font-medium transition-colors text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]";
  const activeLinkClass = "flex w-full items-center gap-2.5 rounded-[6px] px-3 py-1.5 text-[13px] font-medium transition-colors bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]";

  return (
    <div className="py-1">
      <Link to={settingsPath} className={isSettingsActive ? activeLinkClass : menuLinkClass}>
        <Settings className="h-4 w-4" />
        Settings
      </Link>
      <Link to={routes.guide} className={isGuideActive ? activeLinkClass : menuLinkClass}>
        <BookOpen className="h-4 w-4" />
        Guide
      </Link>
      {isAdmin && (
        <Link to={routes.adminUsers} className={isAdminActive ? activeLinkClass : menuLinkClass}>
          <Users className="h-4 w-4" />
          Admin
        </Link>
      )}
      <div className="my-1 border-t border-[var(--border-subtle)]" />
      <button
        onClick={onChangePassword}
        className={menuLinkClass}
      >
        <KeyRound className="h-4 w-4" />
        Change Password
      </button>
      <button
        onClick={onLogout}
        className="flex w-full items-center gap-2.5 rounded-[6px] px-3 py-1.5 text-[13px] font-medium transition-colors text-red-400 hover:bg-red-500/10 hover:text-red-300"
      >
        <LogOut className="h-4 w-4" />
        Sign out
      </button>
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
