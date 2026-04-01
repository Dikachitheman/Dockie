import { Ship, Home, MessageSquare, MapPin, BarChart3, Settings, LogOut, Bell } from "lucide-react";
import type { User } from "@supabase/supabase-js";
import { supabase } from "@/integrations/supabase/client";

interface AppSidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
  unreadNotifications?: number;
  user?: User;
}

const navItems = [
  { id: "home", label: "Home", icon: Home },
  { id: "shipments", label: "Shipments", icon: Ship },
  { id: "tracking", label: "Tracking", icon: MapPin },
  { id: "agents", label: "Agents", icon: MessageSquare },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
];

const bottomItems = [
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "settings", label: "Settings", icon: Settings },
];

function getInitials(user?: User): string {
  const name = user?.user_metadata?.full_name as string | undefined;
  if (name) {
    return name.split(" ").map((part: string) => part[0]).slice(0, 2).join("").toUpperCase();
  }
  const email = user?.email ?? "";
  return email.slice(0, 2).toUpperCase();
}

function getDisplayName(user?: User): string {
  return (user?.user_metadata?.full_name as string | undefined) ?? user?.email?.split("@")[0] ?? "User";
}

export default function AppSidebar({ activeView, onViewChange, unreadNotifications = 0, user }: AppSidebarProps) {
  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  return (
    <aside className="flex h-screen w-[220px] flex-col border-r border-apple-divider/70 bg-white">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-apple-blue">
          <Ship className="h-4 w-4 text-white" strokeWidth={1.5} />
        </div>
        <span className="text-lg font-bold tracking-tight text-apple-text">dockie</span>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 pt-2">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={`flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
              activeView === item.id
                ? "apple-card text-apple-text"
                : "text-apple-secondary hover:bg-apple-hover"
            }`}
          >
            <item.icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
            {item.label}
          </button>
        ))}
      </nav>

      <div className="space-y-0.5 px-3 py-3">
        {bottomItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-sm text-apple-secondary transition-all duration-150 hover:bg-apple-hover"
          >
            <item.icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
            {item.label}
            {item.id === "notifications" && unreadNotifications > 0 && (
              <span className="ml-auto rounded-full bg-apple-blue px-2 py-0.5 text-[10px] font-semibold text-white">
                {unreadNotifications}
              </span>
            )}
          </button>
        ))}
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-sm text-apple-secondary transition-all duration-150 hover:bg-apple-hover"
        >
          <LogOut className="h-[18px] w-[18px]" strokeWidth={1.5} />
          Logout
        </button>
      </div>

      <div className="px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-apple-blue/10 text-xs font-bold text-apple-blue">
            {getInitials(user)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-apple-text">{getDisplayName(user)}</p>
            <p className="truncate text-xs text-apple-secondary">{user?.email ?? ""}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
