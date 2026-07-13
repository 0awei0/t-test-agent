import type { PhaseName } from "../types";

interface Props {
  order: PhaseName[];
  labels: Record<PhaseName, string>;
  started: Set<PhaseName>;
  finished: Set<PhaseName>;
}

export function PhaseStepper({ order, labels, started, finished }: Props) {
  const completed = order.filter((p) => finished.has(p)).length;
  const progress = Math.round((completed / order.length) * 100);
  const activeIndex = order.findIndex((p) => started.has(p) && !finished.has(p));

  return (
    <div className="stepper">
      <div className="progressbar">
        <div className="progressfill" style={{ width: `${progress}%` }} />
      </div>
      <ol className="steps">
        {order.map((phase, i) => {
          const state = finished.has(phase)
            ? "done"
            : started.has(phase)
            ? "active"
            : "pending";
          const isCurrent = i === activeIndex;
          return (
            <li key={phase} className={`step ${state} ${isCurrent ? "current" : ""}`}>
              <span className="dot">{finished.has(phase) ? "✓" : i + 1}</span>
              <span className="label">{labels[phase]}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
