import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import { STATUSES, type DatasetRequest, type Status, type User } from "../types";
import NewRequestForm from "./NewRequestForm";
import StatusBadge from "./StatusBadge";

// Clients see their own requests (the API filters them); operators and admins see all.
export default function RequestList({ user, onOpen }: { user: User; onOpen: (id: number) => void }) {
  const [requests, setRequests] = useState<DatasetRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const query = statusFilter ? `?status=${statusFilter}` : "";
      setRequests(await api<DatasetRequest[]>(`/requests${query}`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, [statusFilter]);

  const isClient = user.role === "client";

  return (
    <>
      {isClient && <NewRequestForm onCreated={load} />}

      <section className="card">
        <div className="row spread">
          <h2>{isClient ? "My requests" : "All requests"}</h2>
          <label className="inline">
            Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as Status | "")}>
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="error">{error}</p>}

        {requests.length === 0 ? (
          <p className="empty-state">No requests.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                {!isClient && <th>Client</th>}
                <th>Task</th>
                <th>Assigned</th>
                <th>Deadline</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => onOpen(r.id)}>
                  <td>{r.id}</td>
                  {!isClient && <td>{r.client_name}</td>}
                  <td>{r.task_name}</td>
                  <td>
                    {r.assigned_count} / {r.episodes_requested}
                  </td>
                  <td>{r.deadline}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
