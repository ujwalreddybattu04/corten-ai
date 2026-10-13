import type { Metadata } from "next";
import WorkspaceTools from "@/components/analyst/WorkspaceTools";
import "@/styles/analyst-workspace.css";
import "@/styles/pharma-workspace.css";
import "@/styles/monthly-interpolation.css";

export const metadata: Metadata = {
  title: "Analyst Workspace | Corten AI",
};

export default function AnalystWorkspace() {
  return (
    <section className="aw-page" aria-labelledby="analyst-workspace-title">
      <header className="aw-header">
        <h1 id="analyst-workspace-title">Analyst Workspace</h1>
      </header>
      <WorkspaceTools />
    </section>
  );
}
