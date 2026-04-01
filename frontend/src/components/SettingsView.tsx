import { useEffect, useState } from "react";
import { startStandbyWorker, stopStandbyWorker, getStandbyWorkerStatus } from "@/lib/api";

export default function SettingsView() {
  const [running, setRunning] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void getStandbyWorkerStatus().then((s) => {
      if (mounted) setRunning(s.running);
    }).catch(() => {
      if (mounted) setRunning(false);
    });
    return () => { mounted = false; };
  }, []);

  const handleStart = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await startStandbyWorker();
      setMessage(res.status ?? "started");
      setRunning(true);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Failed to start worker");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await stopStandbyWorker();
      setMessage(res.status ?? "stopping");
      setRunning(false);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Failed to stop worker");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h2 className="text-xl font-semibold">Settings</h2>
      <div className="mt-4 space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <p className="text-sm text-apple-secondary">Standby worker (dev)</p>
            <p className="text-xs text-apple-secondary">Start a background worker inside this API process to monitor standby agents and trigger actions. Use for testing only.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleStart}
              disabled={loading || running === true}
              className="rounded-[8px] bg-apple-blue px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
            >
              Start
            </button>
            <button
              onClick={handleStop}
              disabled={loading || !running}
              className="rounded-[8px] bg-red-500 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
            >
              Stop
            </button>
          </div>
        </div>
        <div>
          <p className="text-sm">Status: {running === null ? "unknown" : running ? "running" : "stopped"}</p>
          {message && <p className="text-xs text-apple-secondary mt-1">{message}</p>}
        </div>
      </div>
    </div>
  );
}
