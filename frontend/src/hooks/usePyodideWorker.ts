"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export interface ExecutionResult {
  error: string | null;
  interrupted: boolean;
}

type LineCallback = (line: string) => void;
type ImageCallback = (b64: string) => void;

interface PendingExec {
  onStdout: LineCallback;
  onStderr: LineCallback;
  onImage?: ImageCallback;
  resolve: (result: ExecutionResult) => void;
  timeout: ReturnType<typeof setTimeout>;
}

// ─── Module-level singleton ───────────────────────────────────────────────────
let _worker: Worker | null = null;
let _isReady = false;
const _readyCbs: Array<() => void> = [];
const _pending = new Map<string, PendingExec>();
const _readyStateListeners = new Set<(ready: boolean) => void>();

function _dispatch(ready: boolean) {
  _readyStateListeners.forEach((fn) => fn(ready));
}

function _handleMessage(event: MessageEvent) {
  const { type, id, data, isInterrupt } = event.data;

  if (type === "ready") {
    _isReady = true;
    _readyCbs.forEach((fn) => fn());
    _readyCbs.length = 0;
    _dispatch(true);
    return;
  }

  if (type === "init-error") {
    console.error("[Pyodide] Init failed:", data);
    return;
  }

  // Stream stdout/stderr to current execution
  if (type === "stdout") {
    _pending.forEach((p) => p.onStdout(data));
    return;
  }
  if (type === "stderr") {
    _pending.forEach((p) => p.onStderr(data));
    return;
  }
  if (type === "status") {
    // Package loading status — treat as info stdout
    _pending.forEach((p) => p.onStdout(`[${data}]`));
    return;
  }
  if (type === "image") {
    _pending.forEach((p) => p.onImage?.(data));
    return;
  }

  // Execution result / error
  const cb = _pending.get(id);
  if (!cb) return;
  clearTimeout(cb.timeout);
  _pending.delete(id);

  if (type === "result") {
    cb.resolve({ error: null, interrupted: false });
  } else if (type === "error") {
    cb.resolve({
      error: isInterrupt ? null : data,
      interrupted: !!isInterrupt,
    });
  }
}

function _createWorker(): Worker {
  const w = new Worker("/pyodide-worker.js");
  w.onmessage = _handleMessage;
  w.onerror = (e) => console.error("[Pyodide Worker]", e.message);
  return w;
}

function _getWorker(): Worker {
  if (!_worker) {
    _worker = _createWorker();
  }
  return _worker;
}

function _recreateWorker() {
  if (_worker) {
    _worker.terminate();
    _worker = null;
  }
  _isReady = false;

  // Reject all pending with "stopped"
  _pending.forEach((cb) => {
    clearTimeout(cb.timeout);
    cb.resolve({ error: null, interrupted: true });
  });
  _pending.clear();

  _dispatch(false);

  // Recreate and re-init
  _worker = _createWorker();
}

/** Call this early to pre-warm Pyodide (background download ~8MB). */
export function preloadPyodide(): void {
  if (typeof window !== "undefined" && !_worker) {
    _getWorker();
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────
export function usePyodideWorker() {
  const [isReady, setIsReady] = useState<boolean>(_isReady);
  const [isRunning, setIsRunning] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    // Subscribe to ready state changes
    const listener = (ready: boolean) => {
      if (mountedRef.current) setIsReady(ready);
    };
    _readyStateListeners.add(listener);

    // Trigger worker creation + Pyodide loading
    if (!_worker) {
      _getWorker();
    }
    // If already ready, sync state
    if (_isReady && !isReady) {
      setIsReady(true);
    }

    return () => {
      mountedRef.current = false;
      _readyStateListeners.delete(listener);
    };
  }, []);

  const runPython = useCallback(
    async (
      code: string,
      timeoutMs: number = 30_000,
      onStdout: LineCallback = () => {},
      onStderr: LineCallback = () => {},
      onImage: ImageCallback = () => {}
    ): Promise<ExecutionResult> => {
      const worker = _getWorker();

      // Wait for Pyodide to be ready
      if (!_isReady) {
        await new Promise<void>((resolve) => {
          if (_isReady) {
            resolve();
            return;
          }
          _readyCbs.push(resolve);
        });
      }

      if (mountedRef.current) setIsRunning(true);

      return new Promise<ExecutionResult>((resolve) => {
        const id = crypto.randomUUID();

        const timeout = setTimeout(() => {
          _pending.delete(id);
          // Terminate + recreate to stop infinite loop
          _recreateWorker();
          if (mountedRef.current) setIsRunning(false);
          resolve({
            error: `Timed out after ${timeoutMs / 1000}s`,
            interrupted: true,
          });
        }, timeoutMs);

        _pending.set(id, {
          onStdout,
          onStderr,
          onImage,
          resolve: (result) => {
            if (mountedRef.current) setIsRunning(false);
            resolve(result);
          },
          timeout,
        });

        worker.postMessage({ type: "run", id, code });
      });
    },
    []
  );

  /** Stop running Python execution by terminating + recreating the worker. */
  const stop = useCallback(() => {
    _recreateWorker();
    if (mountedRef.current) {
      setIsRunning(false);
      setIsReady(false);
    }
  }, []);

  return { runPython, stop, isReady, isRunning };
}
