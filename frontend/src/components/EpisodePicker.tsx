import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import type { EpisodePage, Quality } from "../types";

const PAGE_SIZE = 20;

interface Props {
  requestId: number;
  defaultTaskName: string;
  onAssigned: () => void;
  onError: (message: string) => void;
}

// Operator tool: browse episodes with filters, tick some, assign them to the request.
export default function EpisodePicker({ requestId, defaultTaskName, onAssigned, onError }: Props) {
  const [taskName, setTaskName] = useState(defaultTaskName);
  const [quality, setQuality] = useState<Quality | "">("");
  const [unassignedOnly, setUnassignedOnly] = useState(true);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<EpisodePage | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  async function load() {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (taskName.trim()) params.set("task_name", taskName);
    if (quality) params.set("quality", quality);
    if (unassignedOnly) params.set("unassigned_only", "true");
    try {
      setPage(await api<EpisodePage>(`/episodes?${params}`));
    } catch (e) {
      onError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, [taskName, quality, unassignedOnly, offset]);

  // Changing a filter goes back to the first page.
  function changeFilter(update: () => void) {
    update();
    setOffset(0);
  }

  function toggle(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function assignSelected() {
    setBusy(true);
    try {
      await api(`/requests/${requestId}/assignments`, {
        method: "POST",
        body: { episode_ids: [...selected] },
      });
      setSelected(new Set());
      onError("");
      onAssigned();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
      load();
    }
  }

  return (
    <section className="card">
      <div className="row spread">
        <h3>Find episodes to assign</h3>
        <button onClick={assignSelected} disabled={busy || selected.size === 0}>
          Assign {selected.size} selected
        </button>
      </div>

      <div className="row">
        <label>
          Task
          <input value={taskName} onChange={(e) => changeFilter(() => setTaskName(e.target.value))} />
        </label>
        <label>
          Quality
          <select value={quality} onChange={(e) => changeFilter(() => setQuality(e.target.value as Quality | ""))}>
            <option value="">Any</option>
            <option value="good">good</option>
            <option value="usable">usable</option>
            <option value="bad">bad (not assignable)</option>
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={unassignedOnly}
            onChange={(e) => changeFilter(() => setUnassignedOnly(e.target.checked))}
          />
          Unassigned only
        </label>
      </div>

      {page && page.items.length === 0 && (
        <p className="empty-state">
          No episodes match these filters
          {taskName.trim() && <> (no {unassignedOnly ? "unassigned " : ""}episodes for task “{taskName.trim()}”)</>}.
          {taskName.trim() && (
            <button className="link" onClick={() => changeFilter(() => setTaskName(""))}>
              Clear task filter
            </button>
          )}
        </p>
      )}

      {page && page.items.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Episode</th>
                <th>Robot</th>
                <th>Task</th>
                <th>Quality</th>
                <th>Duration</th>
                <th>Recorded</th>
                <th>On request</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((e) => {
                // Only offer checkboxes for episodes the server would accept.
                const assignable = e.quality !== "bad" && e.assigned_request_id === null;
                return (
                  <tr key={e.id} className={assignable ? "" : "muted"}>
                    <td>
                      <input
                        type="checkbox"
                        disabled={!assignable}
                        checked={selected.has(e.id)}
                        onChange={() => toggle(e.id)}
                        aria-label={`Select ${e.episode_id}`}
                      />
                    </td>
                    <td>{e.episode_id}</td>
                    <td>{e.robot_id}</td>
                    <td>{e.task_name}</td>
                    <td>{e.quality}</td>
                    <td>{e.duration_seconds}s</td>
                    <td>{new Date(e.recorded_at).toLocaleString()}</td>
                    <td>{e.assigned_request_id ? `#${e.assigned_request_id}` : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="row spread">
            <span className="muted">
              {offset + 1}–{offset + page.items.length} of {page.total}
            </span>
            <span className="row">
              <button className="secondary" disabled={offset === 0} onClick={() => setOffset(offset - PAGE_SIZE)}>
                Previous
              </button>
              <button
                className="secondary"
                disabled={offset + PAGE_SIZE >= page.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </span>
          </div>
        </>
      )}
    </section>
  );
}
