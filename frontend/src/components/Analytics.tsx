import { useEffect, useState } from "react";
import { Alert, Card, Col, DatePicker, Row, Statistic, Table, Typography, type TableColumnsType } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { api, errorMessage } from "../api";
import type { Status } from "../types";
import StatusBadge from "./StatusBadge";

interface AnalyticsResult {
  episodes_per_day_per_robot: { day: string; robot_id: string; episodes: number }[];
  requests_by_status: Record<Status, number>;
  submitted_to_delivered: { median_seconds: number | null; median_hours: number | null; delivered_requests: number };
  top_tasks_by_good_episodes: { task_name: string; good_episodes: number }[];
}

// 42 -> "42 s", 1500 -> "25 min", 7200 -> "2 h", 259200 -> "3 days"
function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 2 * 86400) return `${Math.round((seconds / 3600) * 10) / 10} h`;
  return `${Math.round((seconds / 86400) * 10) / 10} days`;
}

// Every number is computed by the API (in SQL); this page only arranges them.
export default function Analytics() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(90, "day"), dayjs()]);
  const [data, setData] = useState<AnalyticsResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const [from, to] = range.map((d) => d.format("YYYY-MM-DD"));
    setError("");
    setLoading(true);
    api<AnalyticsResult>(`/analytics?from=${from}&to=${to}`)
      .then(setData)
      .catch((e) => {
        setData(null);
        setError(errorMessage(e));
      })
      .finally(() => setLoading(false));
  }, [range]);

  // Turn the (day, robot, count) rows into one row per day with a column per robot.
  const rows = data?.episodes_per_day_per_robot ?? [];
  const robots = [...new Set(rows.map((r) => r.robot_id))].sort();
  const days = [...new Set(rows.map((r) => r.day))].sort().reverse();
  const dayRows = days.map((day) => {
    const row: Record<string, string | number> = { day };
    for (const r of rows.filter((r) => r.day === day)) row[r.robot_id] = r.episodes;
    return row;
  });
  const dayColumns: TableColumnsType<Record<string, string | number>> = [
    { title: "Day", dataIndex: "day" },
    ...robots.map((robot) => ({
      title: robot,
      dataIndex: robot,
      align: "right" as const,
      render: (v?: number) => v ?? <span className="muted">·</span>,
    })),
  ];

  const totalEpisodes = rows.reduce((sum, r) => sum + r.episodes, 0);
  const totalRequests = data ? Object.values(data.requests_by_status).reduce((sum, n) => sum + n, 0) : 0;
  const median = data?.submitted_to_delivered;

  return (
    <>
      <Card className="section">
        <div className="range-row">
          <span className="range-label">Date range</span>
          <DatePicker.RangePicker
            value={range}
            allowClear={false}
            format="YYYY-MM-DD"
            onChange={(values) => values?.[0] && values?.[1] && setRange([values[0], values[1]])}
          />
          <Typography.Text type="secondary">Both dates included, in UTC. At most 366 days.</Typography.Text>
        </div>
        {error && <Alert type="error" title={error} showIcon className="form-alert" />}
      </Card>

      {data && (
        <>
          <Row gutter={[16, 16]} className="section">
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Episodes recorded" value={totalEpisodes} loading={loading} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Requests created" value={totalRequests} loading={loading} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic
                  title="Median time to deliver"
                  value={median?.median_seconds != null ? formatDuration(median.median_seconds) : "–"}
                  loading={loading}
                />
                <Typography.Text type="secondary" className="stat-note">
                  over {median?.delivered_requests ?? 0} delivered requests
                </Typography.Text>
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic
                  title="Top task (good episodes)"
                  value={data.top_tasks_by_good_episodes[0]?.task_name ?? "–"}
                  loading={loading}
                  styles={{ content: { fontSize: 22 } }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]} className="section">
            <Col xs={24} lg={12}>
              <Card title="Requests by status" className="full-height">
                <Table
                  rowKey="status"
                  showHeader={false}
                  pagination={false}
                  dataSource={(Object.keys(data.requests_by_status) as Status[]).map((status) => ({
                    status,
                    count: data.requests_by_status[status],
                  }))}
                  columns={[
                    { dataIndex: "status", render: (s: Status) => <StatusBadge status={s} /> },
                    { dataIndex: "count", align: "right" },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="Top 5 tasks by good episodes" className="full-height">
                <Table
                  rowKey="task_name"
                  pagination={false}
                  dataSource={data.top_tasks_by_good_episodes.map((t, i) => ({ ...t, rank: i + 1 }))}
                  locale={{ emptyText: "No good episodes in this range." }}
                  columns={[
                    { title: "#", dataIndex: "rank", width: 60 },
                    { title: "Task", dataIndex: "task_name" },
                    { title: "Good episodes", dataIndex: "good_episodes", align: "right" },
                  ]}
                />
              </Card>
            </Col>
          </Row>

          <Card title="Episodes per day, per robot" className="section">
            <Table
              rowKey="day"
              columns={dayColumns}
              dataSource={dayRows}
              loading={loading}
              pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
              locale={{ emptyText: "No episodes recorded in this range." }}
            />
          </Card>
        </>
      )}
    </>
  );
}
