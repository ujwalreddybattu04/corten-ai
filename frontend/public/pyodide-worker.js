/**
 * Pyodide Web Worker
 * Runs Python code in a sandboxed WebAssembly environment.
 * Streams stdout/stderr line-by-line back to the main thread.
 */

importScripts("https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js");

let pyodide = null;
let isInterrupted = false;

async function initPyodide() {
  try {
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/",
    });

    pyodide.setStdout({
      batched: function (line) {
        self.postMessage({ type: "stdout", data: line });
      },
    });

    pyodide.setStderr({
      batched: function (line) {
        self.postMessage({ type: "stderr", data: line });
      },
    });

    // Raise EOFError on input() — no stdin in sandbox
    pyodide.setStdin({ error: true });

    self.postMessage({ type: "ready" });
  } catch (err) {
    self.postMessage({ type: "init-error", data: String(err.message || err) });
  }
}

const initPromise = initPyodide();

self.onmessage = async function (event) {
  var msg = event.data;

  if (msg.type === "interrupt") {
    isInterrupted = true;
    return;
  }

  if (msg.type === "run") {
    await initPromise;
    var id = msg.id;
    var code = msg.code;
    isInterrupted = false;

    try {
      // Auto-download Pyodide packages used in imports (numpy, pandas, etc.)
      await pyodide.loadPackagesFromImports(code, {
        messageCallback: function (message) {
          self.postMessage({ type: "status", data: message });
        },
        errorCallback: function (err) {
          self.postMessage({ type: "stderr", data: String(err) });
        },
      });

      // If matplotlib/seaborn is used, force the non-interactive Agg backend
      // and override plt.show() to emit a base64 PNG to the UI thread.
      var hasMpl =
        /\bimport\s+matplotlib/.test(code) ||
        /\bfrom\s+matplotlib/.test(code) ||
        /\bimport\s+seaborn/.test(code) ||
        /\bfrom\s+seaborn/.test(code);

      if (hasMpl) {
        // Expose a JS callable so Python can postMessage the image
        pyodide.globals.set("_worker_post_image", function (b64) {
          self.postMessage({ type: "image", id: id, data: b64 });
        });

        await pyodide.runPythonAsync(`
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as _plt_patched
import io as _io, base64 as _b64

def _patched_show(*args, **kwargs):
    figs = [_plt_patched.figure(n) for n in _plt_patched.get_fignums()]
    if not figs:
        figs = [_plt_patched.gcf()]
    for fig in figs:
        buf = _io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        _worker_post_image(_b64.b64encode(buf.read()).decode('utf-8'))
    _plt_patched.close('all')

_plt_patched.show = _patched_show
`);
      }

      await pyodide.runPythonAsync(code);

      self.postMessage({ type: "result", id: id, data: null });
    } catch (err) {
      var errMsg = String(err.message || err);
      var isKBI =
        errMsg.includes("KeyboardInterrupt") ||
        (err.type && err.type === "KeyboardInterrupt") ||
        isInterrupted;

      self.postMessage({
        type: "error",
        id: id,
        data: isKBI ? "Execution interrupted" : errMsg,
        isInterrupt: isKBI,
      });
    }
  }
};
