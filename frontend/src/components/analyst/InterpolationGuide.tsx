import { ArrowRight, FileSpreadsheet } from "lucide-react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A format guide, with no example values or simulated calculation results. */
export default function InterpolationGuide() {
  return <div className="mi-guide" aria-hidden="true">
    <div className="mi-guide-sheet">
      <div className="mi-guide-label"><FileSpreadsheet size={14} /> Yearly input</div>
      <div className="mi-guide-columns"><span>Year</span><span>Value</span></div>
      {[0, 1, 2].map(row => <div className="mi-guide-row" key={row}><i /><i /></div>)}
      <div className="mi-guide-caption">Your CSV</div>
    </div>
    <div className="mi-guide-arrow"><ArrowRight size={22} strokeWidth={1.5} /></div>
    <div className="mi-guide-sheet mi-guide-months">
      <div className="mi-guide-label">Monthly detail</div>
      <div className="mi-month-grid">{MONTHS.map(month => <span key={month}>{month}</span>)}</div>
      <div className="mi-guide-caption">12 months per year</div>
    </div>
  </div>;
}
