import { useEffect, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Progress,
  Space,
  Spin,
  Table,
  Timeline,
  type TableColumnsType,
} from "antd";
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
  const { modal } = AntApp.useApp();
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
    const doMove = () => run(() => api(`/requests/${requestId}/transition`, { method: "POST", body: { to_status: to } }));
    if (to === "rejected") {
      modal.confirm({
        title: "Reject this delivery?",
        content: "The operators will rework it and deliver again.",
        okText: "Reject delivery",
        okButtonProps: { danger: true },
        onOk: doMove,
      });
    } else {
      doMove();
    }
  }

  function unassign(episodeId: number) {
    run(() => api(`/requests/${requestId}/assignments/${episodeId}`, { method: "DELETE" }));
  }

  if (!request) {
    return (
      <Card>
        <Button type="link" onClick={onBack} className="back-link">
          ← Back to requests
        </Button>
        {error ? <Alert type="error" title={error} showIcon /> : <Spin />}
      </Card>
    );
  }

  const actions = ACTIONS.filter((a) => a.from === request.status && a.forClient === isClient);
  const canEditEpisodes = !isClient && EDITABLE.includes(request.status);
  const enough = request.assigned_count >= request.episodes_requested;
  // Progress bar: cap at 100 % visually even if over-assigned.
  const progressPct = Math.min(100, Math.round((request.assigned_count / request.episodes_requested) * 100));

  const episodeColumns: TableColumnsType<Episode> = [
    { title: "Episode", dataIndex: "episode_id" },
    { title: "Robot", dataIndex: "robot_id" },
    { title: "Task", dataIndex: "task_name" },
    { title: "Quality", dataIndex: "quality" },
    { title: "Recorded", dataIndex: "recorded_at", render: (v: string) => new Date(v).toLocaleString() },
    ...(canEditEpisodes
      ? [
          {
            title: "",
            key: "unassign",
            render: (_: unknown, e: Episode) => (
              <Button type="link" danger onClick={() => unassign(e.id)} disabled={busy}>
                Unassign
              </Button>
            ),
          },
        ]
      : []),
  ];

  return (
    <>
      <Button type="link" onClick={onBack} className="back-link">
        ← Back to requests
      </Button>

      <Card
        className="section"
        title={<span className="request-title">{request.task_name}</span>}
        extra={<StatusBadge status={request.status} />}
      >
        <Descriptions column={{ xs: 1, md: 2 }} className="section">
          <Descriptions.Item label="Episodes">
            <div className="progress-wrap">
              <span className={enough ? "" : "warn"}>
                {request.assigned_count} assigned of {request.episodes_requested} requested
              </span>
              <Progress
                percent={progressPct}
                size="small"
                showInfo={false}
                status={enough ? "success" : "active"}
                className="progress"
              />
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="Deadline">{request.deadline}</Descriptions.Item>
          {!isClient && <Descriptions.Item label="Client">{request.client_name}</Descriptions.Item>}
          {request.notes && <Descriptions.Item label="Notes">{request.notes}</Descriptions.Item>}
        </Descriptions>

        {error && <Alert type="error" title={error} showIcon className="form-alert" />}

        {isClient && (request.status === "submitted" || request.status === "in_progress" || request.status === "rejected") && (
          <Alert
            type="info"
            showIcon
            className="form-alert"
            title="Our operators are preparing your episodes. You can accept or reject the delivery once it is marked delivered."
          />
        )}

        {actions.length > 0 && (
          <Space className="section">
            {actions.map((a) => (
              <Button
                key={a.to}
                type="primary"
                danger={a.to === "rejected"}
                onClick={() => move(a.to)}
                loading={busy}
                size="large"
              >
                {a.label}
              </Button>
            ))}
          </Space>
        )}

        <h3 className="section-label">History</h3>
        <Timeline
          className="timeline"
          items={request.events.map((e) => ({
            content: (
              <div>
                <div className="timeline-time">{new Date(e.created_at).toLocaleString()}</div>
                {e.from_status ? `${e.from_status} → ` : "created as "}
                {e.to_status} <span className="muted">by {e.actor_name}</span>
              </div>
            ),
          }))}
        />
      </Card>

      <Card className="section" title={`Assigned episodes (${assigned.length})`}>
        <Table
          rowKey="id"
          columns={episodeColumns}
          dataSource={assigned}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          locale={{ emptyText: "None yet." }}
        />
      </Card>

      {canEditEpisodes && (
        <EpisodePicker requestId={request.id} defaultTaskName={request.task_name} onAssigned={load} onError={setError} />
      )}
    </>
  );
}
