import type { ToolCallEvent } from "../types";

interface Props {
  calls: ToolCallEvent[];
}

function statusLabel(status: ToolCallEvent["status"]): string {
  if (status === "start") return "运行中";
  if (status === "ok") return "完成";
  return "出错";
}

export function Timeline({ calls }: Props) {
  if (calls.length === 0) {
    return <div className="muted pad">尚无工具调用。</div>;
  }
  return (
    <ul className="timeline">
      {calls.map((c) => (
        <li key={c.id} className={`tcard ${c.status}`}>
          <div className="tcard-head">
            <span className="tool">{c.tool}</span>
            <span className={`tstatus ${c.status}`}>
              {c.status === "start" ? <span className="spinner" /> : null}
              {statusLabel(c.status)}
            </span>
          </div>
          {c.input ? <div className="tinput">输入：{c.input}</div> : null}
          {c.status !== "start" && c.output ? (
            <pre className="toutput">{c.output}</pre>
          ) : null}
          {c.status === "error" && c.error ? (
            <pre className="terror">{c.error}</pre>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
