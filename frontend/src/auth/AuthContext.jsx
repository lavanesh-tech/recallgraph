import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { api } from "../api/client.js";

// Tokens live in memory only (never localStorage): a page reload signs the user out.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);

  const login = useCallback(async (email, password) => {
    const tokens = await api("/auth/login", { method: "POST", body: { email, password } });
    setSession({ email, accessToken: tokens.access_token });
  }, []);

  const register = useCallback(
    async (email, password) => {
      await api("/auth/register", { method: "POST", body: { email, password } });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => setSession(null), []);

  const value = useMemo(
    () => ({ session, token: session?.accessToken, login, register, logout }),
    [session, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
