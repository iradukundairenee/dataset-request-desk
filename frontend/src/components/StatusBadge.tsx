import { Tag } from "antd";
import type { Status } from "../types";

const COLORS: Record<Status, string> = {
  submitted: "blue",
  in_progress: "gold",
  delivered: "purple",
  accepted: "green",
  rejected: "red",
};

export default function StatusBadge({ status }: { status: Status }) {
  return (
    <Tag color={COLORS[status]} className="status-tag">
      {status.replace("_", " ")}
    </Tag>
  );
}
