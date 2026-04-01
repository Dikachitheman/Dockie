import { Bell } from "lucide-react";
import type { AgentNotification, AgentOutput } from "@/lib/standby-agents";

interface AgentNotificationsViewProps {
  notifications: AgentNotification[];
  outputs: AgentOutput[];
  onMarkNotificationsRead: () => void | Promise<void>;
  onOpenOutput?: (outputId: string) => void;
}

export default function AgentNotificationsView({
  notifications,
  outputs,
  onMarkNotificationsRead,
  onOpenOutput,
}: AgentNotificationsViewProps) {
  const outputById = new Map(outputs.map((output) => [output.id, output]));

  return (
    <div className="flex flex-1 overflow-y-auto bg-white p-8 scrollbar-thin">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <div className="rounded-[24px] bg-[linear-gradient(135deg,#07111f_0%,#17334f_100%)] p-6 text-white shadow-apple">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/70">
            <Bell className="h-4 w-4" strokeWidth={1.5} />
            Notifications
          </div>
          <h1 className="mt-3 text-2xl font-semibold">Agent updates and fired actions</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-white/80">
            This feed shows what each standby agent did, including notifications, sent emails, and generated outputs.
          </p>
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-apple-secondary">{notifications.length} update{notifications.length === 1 ? "" : "s"}</p>
          <button onClick={() => void onMarkNotificationsRead()} className="apple-btn-secondary px-4 py-2 text-xs">
            Mark all read
          </button>
        </div>

        <div className="space-y-4">
          {notifications.length === 0 ? (
            <div className="apple-card p-6 text-center">
              <p className="text-sm font-medium text-apple-text">No notifications yet</p>
              <p className="mt-2 text-sm leading-relaxed text-apple-secondary">
                Fired standby agents will start showing their updates here.
              </p>
            </div>
          ) : (
            notifications.map((notification) => {
              const output = notification.outputId ? outputById.get(notification.outputId) : null;
              return (
                <div key={notification.id} className="apple-card p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-apple-text">{notification.title}</p>
                        {notification.unread && <span className="h-2 w-2 rounded-full bg-apple-blue" />}
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-apple-secondary">{notification.detail}</p>
                    </div>
                    <span className="apple-badge-blue">{notification.channel}</span>
                  </div>
                  {output && (
                    <div className="mt-4 rounded-[14px] bg-apple-surface p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-medium text-apple-text">{output.title}</p>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] uppercase tracking-[0.12em] text-apple-blue">{output.outputType}</span>
                          {onOpenOutput && (
                            <button
                              type="button"
                              onClick={() => onOpenOutput(output.id)}
                              className="rounded-full border border-apple-divider bg-white px-3 py-1 text-[11px] font-medium text-apple-blue transition-colors hover:bg-[#eef6ff]"
                            >
                              Open full output
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-apple-secondary">{output.previewText}</p>
                      <p className="mt-3 line-clamp-3 whitespace-pre-wrap text-sm text-apple-text">{output.content}</p>
                    </div>
                  )}
                  <p className="mt-3 text-[11px] text-apple-secondary/70">
                    {notification.createdAt ? new Date(notification.createdAt).toLocaleString() : "Pending"}
                  </p>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
