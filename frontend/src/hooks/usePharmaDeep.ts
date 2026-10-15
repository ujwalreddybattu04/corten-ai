"use client";
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { getStorageAccount } from '@/lib/accountStorage';
import { actDeep, checkDeepJob, deepActive, prepareDeep, readDeep, startDeep, type DeepJob, type DeepOptions, type DeepPlan } from '@/lib/pharmaDeep';

export function usePharmaDeep(existingId: string) {
    const [job, setJob] = useState<DeepJob | null>(null), [history, setHistory] = useState<DeepJob[]>([]);
    const [options, setOptions] = useState<DeepOptions | null>(null), [error, setError] = useState('');
    const [operation, setOperation] = useState(''), [loading, setLoading] = useState(!!existingId);
    const [pollVersion, setPollVersion] = useState(0);
    const owner = useRef(getStorageAccount()), mounted = useRef(true), locked = useRef(false);
    useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
    const current = useCallback(() => mounted.current && owner.current === getStorageAccount(), []);
    const refreshHistory = useCallback(async (signal?: AbortSignal) => {
        const result = await api.get<{ items: DeepJob[] }>('/api/v1/pharma/deep', { signal });
        if (current()) setHistory(result.items.map(checkDeepJob));
    }, [current]);
    useEffect(() => {
        const controller = new AbortController(); owner.current = getStorageAccount();
        Promise.allSettled([api.get<DeepOptions>('/api/v1/pharma/deep/options', { signal: controller.signal }).then(result => { if (current()) setOptions(result); }), refreshHistory(controller.signal)])
            .then(results => { if (!controller.signal.aborted && current() && results[0].status === 'rejected') setError('Deep research is currently unavailable. Please retry shortly.'); });
        return () => controller.abort();
    }, [current, refreshHistory]);
    useEffect(() => {
        const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined, failures = 0;
        setJob(previous => previous?.id === existingId ? previous : null); setError(''); setLoading(!!existingId);
        if (!existingId) return () => controller.abort();
        const poll = async () => {
            try {
                const next = await readDeep(existingId, controller.signal);
                if (controller.signal.aborted || !current()) return;
                setJob(previous => previous?.id === next.id && previous.revision === next.revision ? previous : next); setError(''); failures = 0;
                if (deepActive(next)) timer = setTimeout(() => void poll(), document.hidden ? 10000 : 1800);
                else void refreshHistory(controller.signal).catch(() => undefined);
            } catch (failure) {
                if (controller.signal.aborted || !current()) return;
                setError(failure instanceof Error ? failure.message : 'Research progress could not be loaded.');
                if (++failures < 5) timer = setTimeout(() => void poll(), Math.min(15000, 2000 * failures));
            } finally { if (!controller.signal.aborted && current()) setLoading(false); }
        };
        void poll();
        return () => { controller.abort(); if (timer) clearTimeout(timer); };
    }, [existingId, current, refreshHistory, pollVersion]);
    const action = useCallback(async (name: string, task: () => Promise<DeepJob>) => {
        if (locked.current) return null;
        locked.current = true; setOperation(name); setError('');
        try {
            const next = await task();
            if (!current()) return null;
            setJob(next); if (name !== 'plan') setPollVersion(value => value + 1); void refreshHistory().catch(() => undefined); return next;
        } catch (failure) { if (current()) setError(failure instanceof Error ? failure.message : 'This action could not be completed.'); return null; }
        finally { locked.current = false; if (current()) setOperation(''); }
    }, [current, refreshHistory]);
    return { job, history, options, error, operation, loading,
        prepare: (query: string, allowSaved = false) => action('plan', () => prepareDeep(query, undefined, allowSaved)),
        start: (plan: DeepPlan) => job ? action('start', () => startDeep(job, plan)) : Promise.resolve(null),
        cancel: () => job ? action('cancel', () => actDeep(job, 'cancel')) : Promise.resolve(null),
        retry: () => job ? action('retry', () => actDeep(job, 'retry')) : Promise.resolve(null),
        reload: () => { if (job) void action('reload', () => readDeep(job.id)); },
    };
}
