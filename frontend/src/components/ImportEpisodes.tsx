import { useState } from "react";
import { Alert, Button, Card, Col, Row, Statistic, Table, Typography, Upload } from "antd";
import { errorMessage, uploadCsv } from "../api";
import Icon from "./Icon";

interface ImportReport {
  inserted: number;
  already_imported: number;
  blank_lines: number;
  skipped: number;
  skipped_by_reason: Record<string, number>;
  warnings: Record<string, number>;
  issues: { line: number; episode_id: string | null; reason: string }[];
  issues_truncated: boolean;
}

// Operators upload a CSV export; the API validates every row and reports what it did.
export default function ImportEpisodes() {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError("");
    setReport(null);
    try {
      setReport(await uploadCsv<ImportReport>(`/episodes/import?filename=${encodeURIComponent(file.name)}`, file));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const reasonRows = report
    ? [
        ...Object.entries(report.skipped_by_reason).map(([reason, count]) => ({ reason, count, warning: false })),
        ...Object.entries(report.warnings).map(([reason, count]) => ({ reason, count, warning: true })),
      ]
    : [];

  return (
    <>
      <Card className="section">
        <Typography.Title level={4} className="card-heading">
          Upload a CSV export
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          Safe to run more than once: episodes that already exist are never duplicated or changed. Every skipped row is
          listed with its line number and reason.
        </Typography.Paragraph>

        {/* beforeUpload returns false: we only keep the file here and send it ourselves on "Import file". */}
        <Upload.Dragger
          accept=".csv,text/csv"
          maxCount={1}
          beforeUpload={(f) => {
            setFile(f);
            return false;
          }}
          onRemove={() => setFile(null)}
          className="section"
        >
          <p className="upload-icon">
            <Icon name="upload" size={32} />
          </p>
          <p className="upload-text">Click or drag a CSV file here</p>
          <p className="upload-hint">Columns: episode_id, robot_id, task_name, recorded_at, duration_seconds, operator_name, quality</p>
        </Upload.Dragger>

        <Button type="primary" size="large" onClick={submit} disabled={!file} loading={busy} className="top-gap">
          Import file
        </Button>
        {error && <Alert type="error" title={error} showIcon className="form-alert top-gap" />}
      </Card>

      {report && (
        <>
          <Row gutter={[16, 16]} className="section">
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Inserted" value={report.inserted} styles={{ content: { color: "#15803d" } }} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Already imported" value={report.already_imported} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Skipped" value={report.skipped} styles={{ content: { color: "#dc2626" } }} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card className="stat-card">
                <Statistic title="Warnings" value={Object.values(report.warnings).reduce((a, b) => a + b, 0)} />
                <Typography.Text type="secondary" className="stat-note">
                  {report.blank_lines} blank lines ignored
                </Typography.Text>
              </Card>
            </Col>
          </Row>

          {report.issues.length > 0 && (
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={10}>
                <Card title="Skipped, by reason">
                  <Table
                    rowKey="reason"
                    pagination={false}
                    dataSource={reasonRows}
                    columns={[
                      {
                        title: "Reason",
                        dataIndex: "reason",
                        render: (reason: string, row) => (
                          <>
                            <code>{reason}</code>
                            {row.warning && <span className="muted"> (warning, row imported)</span>}
                          </>
                        ),
                      },
                      { title: "Rows", dataIndex: "count", align: "right" },
                    ]}
                  />
                </Card>
              </Col>
              <Col xs={24} lg={14}>
                <Card title="Rows needing attention">
                  <Table
                    rowKey={(row) => `${row.line}-${row.reason}`}
                    dataSource={report.issues}
                    pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
                    columns={[
                      { title: "Line", dataIndex: "line", align: "right", width: 80 },
                      {
                        title: "Episode",
                        dataIndex: "episode_id",
                        render: (v: string | null) => v ?? <span className="muted">(none)</span>,
                      },
                      { title: "Reason", dataIndex: "reason", render: (v: string) => <code>{v}</code> },
                    ]}
                  />
                  {report.issues_truncated && (
                    <Typography.Text type="secondary">Only the first 500 issues are listed.</Typography.Text>
                  )}
                </Card>
              </Col>
            </Row>
          )}
        </>
      )}
    </>
  );
}
