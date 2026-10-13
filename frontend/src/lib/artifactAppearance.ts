/** Presentation inside the existing sandbox. The downloadable source is unchanged. */
export function artifactAppearance(document: string): string {
    const style = `<style id="corten-preview-appearance">
      :root{color-scheme:dark}
      html,body,#root{background:#101014!important;color:#e4e4e7!important}
      body{font-family:"Plus Jakarta Sans",system-ui,sans-serif;line-height:1.6}
      body h1,body h2,body h3,body h4{color:inherit}
      body h1{font-size:clamp(18px,2.5vw,24px);line-height:1.45;margin:0 0 14px}
      .bg-white,.bg-gray-50,.bg-slate-50,.bg-zinc-50,
      [style*="background: white"],[style*="background: #fff"],[style*="background:#fff"],
      [style*="background-color: white"],[style*="background-color: rgb(255, 255, 255)"],
      [style*="background: rgb(255, 255, 255)"]{background:#18181e!important;border-color:#303038!important}
      .text-black,.text-gray-900,.text-slate-900,.text-zinc-900,
      [style*="color: rgb(17, 24, 39)"],[style*="color: rgb(15, 23, 42)"],
      [style*="color: rgb(0, 0, 0)"],[style*="color: rgb(17, 17, 17)"]{color:#e4e4e7!important}
      svg text{fill:#a1a1aa}
      svg line[stroke="#eee"],svg line[stroke="#ddd"],svg line[stroke="#e5e7eb"],svg line[stroke="#f1f5f9"]{stroke:#303038}
      input,select,textarea{color-scheme:dark}
    </style>`;
    return /<\/head\s*>/i.test(document) ? document.replace(/<\/head\s*>/i, style + "$&") : style + document;
}
