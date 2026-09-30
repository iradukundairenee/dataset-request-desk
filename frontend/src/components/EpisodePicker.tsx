import { useEffect, useState } from "react";
import { Button, Card, Checkbox, Form, Input, Select, Table, type TableColumnsType } from "antd";
import { api, errorMessage } from "../api";
import type { Episode, EpisodePage, Quality } from "../types";

const PAGE_SIZE = 10;

interface Props {
  requestId: number;
  defaultTaskName: string;
  onAssigned: () => void;
  onError: (message: string) => void;
}

// Operator tool: browse episodes with filters, tick some, assign them to the request.
// Pagination happens in the API (limit/offset), so this works with millions of episodes.
export default function EpisodePicker({ requestId, defaultTaskName, onAssigned, onError }: Props) {
  const [taskName, setTaskName] = useState(defaultTaskName);
  const [quality, setQuality] = useState<Quality | "">("");
  const [unassignedOnly, setUnassignedOnly] = useState(true);
  const [pageNumber, setPageNumber] = useState(1);
  const [page, setPage] = useState<EpisodePage | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  async function load() {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((pageNumber - 1) * PAGE_SIZE) });
    if (taskName.trim()) params.set("task_name", taskName);
    if (quality) params.set("quality", quality);
    if (unassignedOnly) params.set("unassigned_only", "true");
    setLoading(true);
    try {
      setPage(await api<EpisodePage>(`/episodes?${params}`));
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [taskName, quality, unassignedOnly, pageNumber]);

  // Changing a filter goes back to the first page.
  function changeFilter(update: () => void) {
    update();
    setPageNumber(1);
  }

  async function assignSelected() {
    setBusy(true);
    try {
      await api(`/requests/${requestId}/assignments`, { method: "POST", body: { episode_ids: selected } });
      setSelected([]);
      onError("");
      onAssigned();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
      load();
    }
  }

  const columns: TableColumnsType<Episode> = [
    { title: "Episode", dataIndex: "episode_id" },
    { title: "Robot", dataIndex: "robot_id" },
    { title: "Task", dataIndex: "task_name" },
    { title: "Quality", dataIndex: "quality" },
    { title: "Duration", dataIndex: "duration_seconds", render: (v: number) => `${v}s`, align: "right" },
    { title: "Recorded", dataIndex: "recorded_at", render: (v: string) => new Date(v).toLocaleString() },
    { title: "On request", dataIndex: "assigned_request_id", render: (v: number | null) => (v ? `#${v}` : "") },
  ];

  const emptyText = (
    <span>
      No episodes match these filters
      {taskName.trim() && <> (no {unassignedOnly ? "unassigned " : ""}episodes for task “{taskName.trim()}”)</>}.
      {taskName.trim() && (
        <Button type="link" onClick={() => changeFilter(() => setTaskName(""))}>
          Clear task filter
        </Button>
      )}
    </span>
  );

  return (
    <Card
      className="section picker"
      title="Find episodes to assign"
      extra={
        <Button type="primary" onClick={assignSelected} disabled={selected.length === 0} loading={busy}>
          Assign {selected.length} selected
        </Button>
      }
    >
      <Form layout="inline" className="filters">
        <Form.Item label="Task">
          <Input value={taskName} onChange={(e) => changeFilter(() => setTaskName(e.target.value))} allowClear />
        </Form.Item>
        <Form.Item label="Quality">
          <Select
            value={quality}
            style={{ width: 200 }}
            onChange={(v) => changeFilter(() => setQuality(v))}
            options={[
              { value: "", label: "Any" },
              { value: "good", label: "good" },
              { value: "usable", label: "usable" },
              { value: "bad", label: "bad (not assignable)" },
            ]}
          />
        </Form.Item>
        <Form.Item>
          <Checkbox checked={unassignedOnly} onChange={(e) => changeFilter(() => setUnassignedOnly(e.target.checked))}>
            Unassigned only
          </Checkbox>
        </Form.Item>
      </Form>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={page?.items ?? []}
        loading={loading}
        locale={{ emptyText }}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as number[]),
          // Keep ticks when moving between pages.
          preserveSelectedRowKeys: true,
          // Only offer checkboxes for episodes the server would accept.
          getCheckboxProps: (e) => ({ disabled: e.quality === "bad" || e.assigned_request_id !== null }),
        }}
        pagination={{
          current: pageNumber,
          pageSize: PAGE_SIZE,
          total: page?.total ?? 0,
          onChange: setPageNumber,
          showSizeChanger: false,
          showTotal: (total, [from, to]) => `${from}–${to} of ${total}`,
        }}
      />
    </Card>
  );
}
