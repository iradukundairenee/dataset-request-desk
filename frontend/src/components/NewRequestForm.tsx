import { useEffect, useState } from "react";
import { Alert, AutoComplete, Button, Card, DatePicker, Form, Input, InputNumber, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { api, errorMessage } from "../api";

interface FormValues {
  task_name: string;
  episodes_requested: number;
  deadline: Dayjs;
  notes?: string;
}

export default function NewRequestForm({ onCreated }: { onCreated: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [knownTasks, setKnownTasks] = useState<string[]>([]);

  // Suggest task names that exist in the recordings, so requests match episodes.
  useEffect(() => {
    api<string[]>("/episodes/tasks").then(setKnownTasks).catch(() => setKnownTasks([]));
  }, []);

  async function submit(values: FormValues) {
    setBusy(true);
    setError("");
    try {
      await api("/requests", {
        method: "POST",
        body: {
          task_name: values.task_name,
          episodes_requested: values.episodes_requested,
          deadline: values.deadline.format("YYYY-MM-DD"),
          notes: values.notes || null,
        },
      });
      onCreated();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="form-card">
      <Typography.Title level={4} className="card-heading">
        Describe the dataset you need
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        Pick a task from the suggestions so our operators can match it with recorded episodes. You can follow progress
        under “My requests”.
      </Typography.Paragraph>

      <Form layout="vertical" size="large" onFinish={submit} requiredMark={false}>
        <Form.Item label="Task" name="task_name" rules={[{ required: true, whitespace: true, message: "Enter a task" }]}>
          <AutoComplete
            placeholder="pick cup"
            options={knownTasks.map((t) => ({ value: t }))}
            filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
          />
        </Form.Item>
        <div className="form-row">
          <Form.Item label="Episodes" name="episodes_requested" rules={[{ required: true, message: "How many?" }]}>
            <InputNumber min={1} max={1000000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="Deadline" name="deadline" rules={[{ required: true, message: "Pick a date" }]}>
            <DatePicker
              style={{ width: "100%" }}
              format="YYYY-MM-DD"
              disabledDate={(d) => d.isBefore(dayjs(), "day")}
            />
          </Form.Item>
        </div>
        <Form.Item label="Notes" name="notes">
          <Input.TextArea rows={3} maxLength={2000} />
        </Form.Item>
        {error && <Alert type="error" title={error} showIcon className="form-alert" />}
        <Button type="primary" htmlType="submit" loading={busy}>
          Create request
        </Button>
      </Form>
    </Card>
  );
}
