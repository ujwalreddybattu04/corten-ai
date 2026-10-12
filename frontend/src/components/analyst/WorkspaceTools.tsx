"use client";

import { useState } from "react";
import { ChartNoAxesCombined, FlaskConical } from "lucide-react";
import YearlyMonthlyWorkspace from "./YearlyMonthlyWorkspace";
import PharmaWorkspace from "./PharmaWorkspace";

export default function WorkspaceTools() {
  const [tab, setTab] = useState("interpolation");
  const [openedPharma, setOpenedPharma] = useState(false);
  const select = (value: string) => {
    if (value === "pharma") setOpenedPharma(true);
    setTab(value);
  };
  return <>
    <div className="aw-tool-tabs" role="tablist" aria-label="Analyst tools" onKeyDown={(event) => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const next = event.key === "Home" ? "interpolation" : event.key === "End" ? "pharma" : tab === "pharma" ? "interpolation" : "pharma";
        select(next);
        document.getElementById(`aw-tab-${next}`)?.focus();
      }
    }}>
      {[{ id: "interpolation", label: "Monthly interpolation", Icon: ChartNoAxesCombined }, { id: "pharma", label: "Pharma intelligence", Icon: FlaskConical }].map(({ id, label, Icon }) =>
        <button key={id} id={`aw-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`aw-panel-${id}`} tabIndex={tab === id ? 0 : -1} onClick={() => select(id)}>
          <Icon size={16} aria-hidden="true" />{label}
        </button>)}
    </div>
    <div id="aw-panel-interpolation" role="tabpanel" aria-labelledby="aw-tab-interpolation" hidden={tab !== "interpolation"}>
      <YearlyMonthlyWorkspace />
    </div>
    <div id="aw-panel-pharma" role="tabpanel" aria-labelledby="aw-tab-pharma" hidden={tab !== "pharma"}>
      {openedPharma && <PharmaWorkspace active={tab === "pharma"} />}
    </div>
  </>;
}
