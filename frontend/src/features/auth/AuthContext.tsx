/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState } from "react";
import { api, SESSION_EXPIRED_EVENT } from "../../api/client";
import type { User } from "../../lib/types";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setUser: (user: User | null) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const me = await api<User>("/api/v1/auth/me/");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    const clearExpiredSession = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, clearExpiredSession);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, clearExpiredSession);
  }, []);

  return <AuthContext.Provider value={{ user, loading, refresh, setUser }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("AuthContext is not available");
  }
  return value;
}
