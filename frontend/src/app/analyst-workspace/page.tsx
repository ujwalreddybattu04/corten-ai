import type { Metadata } from "next";
import "@/styles/analyst-workspace.css";

export const metadata: Metadata = {
  title: "Analyst Workspace | Corten AI",
};

export default function AnalystWorkspace() {
  return (
    <section className="aw-page" aria-labelledby="analyst-workspace-title">
      <header className="aw-header">
        <h1 id="analyst-workspace-title">Analyst Workspace</h1>
      </header>
    </section>
  );
}
