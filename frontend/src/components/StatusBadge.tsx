import type { Status } from "../types";

export default function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge status-${status}`}>{status.replace("_", " ")}</span>;
}
