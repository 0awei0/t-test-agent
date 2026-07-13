import type { CommandEvent } from "../types";
import { fileUrl } from "../api";

interface Props {
  failures: CommandEvent[];
  runId: string;
}

export function FailureBanner({ failures, runId }: Props) {
  return (
    <div className="failure">
      <div className="failure-head">⚠ 失败定位：{failures.length} 条命令未通过</div>
      <ul className="failure-list">
        {failures.map((c) => (
          <li key={c.id} className="failure-item">
            <code>{c.command}</code>
            {typeof c.returncode === "number" ? (
              <span className="rc">exit {c.returncode}</span>
            ) : null}
            {c.log_path ? (
              <a href={fileUrl(runId, c.log_path)} target="_blank" rel="noreferrer">
                查看失败日志 →
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
