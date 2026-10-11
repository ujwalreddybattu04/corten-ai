// useSpaces — hook for spaces management
export function useSpaces() {
    // TODO: Implement spaces CRUD
    return {
        spaces: [],
        isLoading: false,
        error: null,
        createSpace: async (_name: string, _description?: string) => { },
        deleteSpace: async (_id: string) => { },
    };
}
