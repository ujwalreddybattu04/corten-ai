// useThread — hook for thread conversation management
export function useThread(threadId?: string) {
    // TODO: Implement thread loading and follow-up
    return {
        thread: null,
        messages: [],
        isLoading: false,
        error: null,
        sendFollowUp: async (_query: string) => { },
    };
}
