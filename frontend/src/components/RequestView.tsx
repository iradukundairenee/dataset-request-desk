import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import type { Episode, RequestDetail, Status, User } from "../types";
import EpisodePicker from "./EpisodePicker";
import StatusBadge from "./StatusBadge";

// The buttons we offer. The server enforces the same rules; this only decides
// what to show, so a client never sees "Mark delivered", for example.
const ACTIONS: { from: Status; to: Status; label: string; forClient: boolean }[] = [
  { from: "submitted", to: "in_progress", label: "Start work", forClient: false },
  { from: "rejected", to: "in_progress", label: "Restart work (rework)", forClient: false },
  { from: "in_progress", to: "delivered", label: "Mark delivered", forClient: false },
  { from: "delivered", to: "accepted", label: "Accept delivery", forClient: true },
  { from: "delivered", to: "rejected", label: "Reject delivery", forClient: true },
];

// Assignments can only change while the request is being worked on.
const EDITABLE: Status[] = ["submitted", "in_progress", "rejected"];

interface Props {
  user: User;
  requestId: number;
  onBack: () => void;
}

export default function RequestView({ user, requestId, onBack }: Props) {
  const [request, setRequest] = useState<RequestDetail | null>(null);
  const [assigned, setAssigned] = useState<Episode[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isClient = user.role === "client";

  async function load() {
    try {
      const [detail, episodes] = await Promise.all([
        api<RequestDetail>(`/requests/${requestId}`),
        api<Episode[]>(`/requests/${requestId}/assignments`),
      ]);
      setRequest(detail);
      setAssigned(episodes);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, [requestId]);

  // Run an action, show the API's error message if it fails, then reload.
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
      await load();
    }
  }

  function move(to: Status) {
    if (to === "rejected" && !window.confirm("Reject this delivery? The operators will rework it.")) return;
    run(() => api(`/requests/${requestId}/transition`, { method: "POST", body: { to_status: to } }));
  }

  function unassign(episodeId: number) {
    run(() => api(`/requests/${requestId}/assignments/${episodeId}`, { method: "DELETE" }));
  }

  if (!request) {
    return (
      <section className="card">
        <button className="link" onClick={onBack}>
          ← Back
        </button>
        {error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  const actions = ACTIONS.filter((a) => a.from === request.status && a.forClient === isClient);
  const canEditEpisodes = !isClient && EDITABLE.includes(request.status);
  const enough = request.assigned_count >= request.episodes_requested;

  return (
    <>
      <section className="card">
        <button className="link" onClick={onBack}>
          ← All requests
        </button>
        <div className="row spread">
          <h2>
            Request #{request.id}: {request.task_name}
          </h2>
          <StatusBadge status={request.status} />
        </div>

        <dl className="facts">
          <dt>Episodes</dt>
          <dd className={enough ? "" : "warn"}>
            {request.assigned_count} assigned of {request.episodes_requested} requested
          </dd>
          <dt>Deadline</dt>
          <dd>{request.deadline}</dd>
          {!isClient && (
            <>
              <dt>Client</dt>
              <dd>{request.client_name}</dd>
            </>
          )}
          {request.notes && (
            <>
              <dt>Notes</dt>
              <dd>{request.notes}</dd>
            </>
          )}
        </dl>

        {error && <p className="error">{error}</p>}

        {isClient && (request.status === "submitted" || request.status === "in_progress" || request.status === "rejected") && (
          <p className="muted">
            Our operators are preparing your episodes. You can accept or reject the delivery once it is marked
            delivered.
          </p>
        )}

        {actions.length > 0 && (
          <div className="row">
            {actions.map((a) => (
              <button key={a.to} onClick={() => move(a.to)} disabled={busy} className={a.to === "rejected" ? "danger" : ""}>
                {a.label}
              </button>
            ))}
          </div>
        )}

        <h3>History</h3>
        <ol className="history">
          {request.events.map((e, i) => (
            <li key={i}>
              {new Date(e.created_at).toLocaleString()}: {e.from_status ? `${e.from_status} → ` : "created as "}
              {e.to_status} <span className="muted">by {e.actor_name}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="card">
        <h3>Assigned episodes ({assigned.length})</h3>
        {assigned.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Episode</th>
                <th>Robot</th>
                <th>Task</th>
                <th>Quality</th>
                <th>Recorded</th>
                {canEditEpisodes && <th></th>}
              </tr>
            </thead>
            <tbody>
              {assigned.map((e) => (
                <tr key={e.id}>
                  <td>{e.episode_id}</td>
                  <td>{e.robot_id}</td>
                  <td>{e.task_name}</td>
                  <td>{e.quality}</td>
                  <td>{new Date(e.recorded_at).toLocaleString()}</td>
                  {canEditEpisodes && (
                    <td>
                      <button className="link" onClick={() => unassign(e.id)} disabled={busy}>
                        Unassign
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {canEditEpisodes && (
        <EpisodePicker
          requestId={request.id}
          defaultTaskName={request.task_name}
          onAssigned={load}
          onError={setError}
        />
      )}
    </>
  );
}
