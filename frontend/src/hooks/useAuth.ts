// useAuth — hook for authentication state
export function useAuth() {
    // TODO: Implement with Zustand auth store
    return {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        login: async (_email: string, _password: string) => { },
        signup: async (_name: string, _email: string, _password: string) => { },
        logout: () => { },
    };
}
