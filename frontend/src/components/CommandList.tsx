import type { CommandEvent } from "../types";
import { fileUrl } from "../api";

interface Props {
  commands: CommandEvent[];
  runId: string;
  focusedCommand?: string;
}

function label(status: CommandEvent["status"]): string {
  if (status === "start") return "运行中";
  if (status === "ok") return "通过";
  if (status === "blocked") return "被拦截";
  return "失败";
}

export function CommandList({ commands, runId, focusedCommand = "" }: Props) {
  if (commands.length === 0) {
    return <div className="muted pad">尚无测试命令。</div>;
  }
  return (
    <ul className="cmdlist">
      {commands.map((c, index) => (
        <li id={`command-${index}`} key={c.id} className={`cmdrow ${c.status} ${focusedCommand === c.command ? "focused" : ""}`}>
          <span className={`cmdstatus ${c.status}`}>{label(c.status)}</span>
          <code className="cmd">{c.command}</code>
          {typeof c.returncode === "number" ? (
            <span className="rc">exit {c.returncode}</span>
          ) : null}
          {c.log_path ? (
            <a className="loglink" href={fileUrl(runId, c.log_path)} target="_blank" rel="noreferrer">
              日志
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
