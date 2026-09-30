import { useEffect, useState } from "react";
import { Alert, Card, Col, Row, Select, Statistic, Table, type TableColumnsType } from "antd";
import { api, errorMessage } from "../api";
import { STATUSES, type DatasetRequest, type Status, type User } from "../types";
import StatusBadge from "./StatusBadge";

// The stat cards at the top. Clicking one filters the table.
const STAT_CARDS: { label: string; statuses: Status[] }[] = [
  { label: "Open", statuses: ["submitted", "in_progress", "rejected"] },
  { label: "Awaiting review", statuses: ["delivered"] },
  { label: "Accepted", statuses: ["accepted"] },
];

// Clients see their own requests (the API filters them); operators and admins see all.
// We load them all once and filter in the browser, so the stat cards always show totals.
export default function RequestList({ user, onOpen }: { user: User; onOpen: (id: number) => void }) {
  const [requests, setRequests] = useState<DatasetRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<DatasetRequest[]>("/requests")
      .then(setRequests)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  const isClient = user.role === "client";
  const shown = statusFilter ? requests.filter((r) => r.status === statusFilter) : requests;
  const count = (statuses: Status[]) => requests.filter((r) => statuses.includes(r.status)).length;

  const columns: TableColumnsType<DatasetRequest> = [
    { title: "#", dataIndex: "id", width: 70 },
    ...(isClient ? [] : [{ title: "Client", dataIndex: "client_name" }]),
    { title: "Task", dataIndex: "task_name" },
    {
      title: "Assigned",
      key: "assigned",
      render: (_, r) => `${r.assigned_count} / ${r.episodes_requested}`,
    },
    { title: "Deadline", dataIndex: "deadline" },
    { title: "Status", dataIndex: "status", render: (status: Status) => <StatusBadge status={status} /> },
  ];

  const cards = [{ label: "Total", statuses: [] as Status[] }, ...STAT_CARDS];

  return (
    <>
      <Row gutter={[16, 16]} className="section">
        {cards.map((card) => {
          const active =
            card.statuses.length === 0 ? statusFilter === "" : statusFilter !== "" && card.statuses.includes(statusFilter);
          return (
            <Col key={card.label} xs={12} lg={6}>
              <Card
                hoverable
                className={`stat-card${active ? " active" : ""}`}
                onClick={() => setStatusFilter(card.statuses.length === 1 ? card.statuses[0] : "")}
              >
                <Statistic
                  title={card.label}
                  value={card.statuses.length === 0 ? requests.length : count(card.statuses)}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      <Card
        title={isClient ? "Your requests" : "Requests"}
        extra={
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 180 }}
            aria-label="Status"
            options={[
              { value: "", label: "All statuses" },
              ...STATUSES.map((s) => ({ value: s, label: s.replace("_", " ") })),
            ]}
          />
        }
      >
        {error && <Alert type="error" title={error} showIcon className="form-alert" />}
        <Table
          rowKey="id"
          columns={columns}
          dataSource={shown}
          loading={loading}
          pagination={{ pageSize: 10, hideOnSinglePage: true, showTotal: (total) => `${total} requests` }}
          onRow={(r) => ({ onClick: () => onOpen(r.id), className: "clickable" })}
          locale={{
            emptyText:
              requests.length === 0
                ? isClient
                  ? "No requests yet. Use “New request” in the menu to create one."
                  : "No requests yet."
                : "No requests with this status.",
          }}
        />
      </Card>
    </>
  );
}
