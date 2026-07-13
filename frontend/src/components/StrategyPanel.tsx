interface Props {
  steps: string[];
}

export function StrategyPanel({ steps }: Props) {
  if (steps.length === 0) {
    return <div className="muted pad">策略形成过程将在此显示。</div>;
  }
  return (
    <ul className="planner">
      {steps.map((step, i) => {
        const separator = step.indexOf(":");
        const head = separator >= 0 ? step.slice(0, separator) : step;
        const tail = separator >= 0 ? step.slice(separator + 1) : "";
        return (
          <li key={i} className="pstep">
            <span className="pseq">{i + 1}</span>
            <span className={`pk ${head}`}>{head}</span>
            {tail ? <span className="ptail">{tail}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}
