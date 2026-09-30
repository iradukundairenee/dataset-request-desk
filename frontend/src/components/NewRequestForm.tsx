import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../api";

export default function NewRequestForm({ onCreated }: { onCreated: () => void }) {
  const [taskName, setTaskName] = useState("");
  const [count, setCount] = useState("");
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [knownTasks, setKnownTasks] = useState<string[]>([]);

  // Suggest task names that exist in the recordings, so requests match episodes.
  useEffect(() => {
    api<string[]>("/episodes/tasks").then(setKnownTasks).catch(() => setKnownTasks([]));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/requests", {
        method: "POST",
        body: {
          task_name: taskName,
          episodes_requested: Number(count),
          deadline,
          notes: notes || null,
        },
      });
      setTaskName("");
      setCount("");
      setDeadline("");
      setNotes("");
      onCreated();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <form className="card" onSubmit={submit}>
      <h2>New request</h2>
      <div className="row">
        <label>
          Task
          <input
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            list="known-tasks"
            placeholder="pick cup"
            required
          />
          <datalist id="known-tasks">
            {knownTasks.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </label>
        <label>
          Episodes
          <input type="number" min={1} value={count} onChange={(e) => setCount(e.target.value)} required />
        </label>
        <label>
          Deadline
          <input type="date" min={today} value={deadline} onChange={(e) => setDeadline(e.target.value)} required />
        </label>
      </div>
      <label>
        Notes
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create request"}
      </button>
    </form>
  );
}
