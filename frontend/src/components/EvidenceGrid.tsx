import { useEffect, useState } from "react";
import type { EvidenceEvent } from "../types";
import { fileUrl } from "../api";

interface Props {
  evidence: EvidenceEvent[];
  runId: string;
}

export function EvidenceGrid({ evidence, runId }: Props) {
  const [activeEvidence, setActiveEvidence] = useState<EvidenceEvent | null>(null);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveEvidence(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  if (evidence.length === 0) {
    return <div className="muted pad">暂无证据（截图 / 日志）。</div>;
  }
  return (
    <>
      <div className="evidence-grid">
        {evidence.map((e) => (
          <div key={e.path} className={`evidence ${e.kind}`}>
            {e.kind === "screenshot" ? (
              <button type="button" className="evidence-trigger" onClick={() => setActiveEvidence(e)} aria-label={`查看原图：${e.caption || e.path}`}>
                <img src={fileUrl(runId, e.path)} alt={e.caption || e.path} loading="lazy" />
              </button>
            ) : (
              <a className="logcard" href={fileUrl(runId, e.path)} target="_blank" rel="noreferrer">
                📄 {e.caption || e.path}
              </a>
            )}
            <div className="caption">{e.caption || e.path}</div>
          </div>
        ))}
      </div>
      {activeEvidence ? (
        <div className="evidence-modal" role="dialog" aria-modal="true" aria-label="截图原图" onClick={() => setActiveEvidence(null)}>
          <div className="evidence-modal-content" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="evidence-modal-close" onClick={() => setActiveEvidence(null)} aria-label="关闭原图">关闭 ×</button>
            <img src={fileUrl(runId, activeEvidence.path)} alt={activeEvidence.caption || activeEvidence.path} />
            <p>{activeEvidence.caption || activeEvidence.path}</p>
          </div>
        </div>
      ) : null}
    </>
  );
}
