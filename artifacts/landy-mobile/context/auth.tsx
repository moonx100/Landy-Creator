import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { setTokenGetter } from '@/lib/api';
import { queryClient } from '@/lib/queryClient';

const TOKEN_KEY = 'landy_token';
const USER_KEY = 'landy_user';

interface User {
  user_id: string;
  email: string;
  display_name: string | null;
}

interface AuthContextValue {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  setSession: (token: string, user: User) => Promise<void>;
  clearSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function restore() {
      try {
        const [storedToken, storedUser] = await Promise.all([
          AsyncStorage.getItem(TOKEN_KEY),
          AsyncStorage.getItem(USER_KEY),
        ]);
        if (storedToken) setToken(storedToken);
        if (storedUser) setUser(JSON.parse(storedUser));
      } finally {
        setIsLoading(false);
      }
    }
    restore();
  }, []);

  // Wire the token getter into the API module once on mount.
  useEffect(() => {
    setTokenGetter(() => AsyncStorage.getItem(TOKEN_KEY));
  }, []);

  const setSession = useCallback(async (newToken: string, newUser: User) => {
    await Promise.all([
      AsyncStorage.setItem(TOKEN_KEY, newToken),
      AsyncStorage.setItem(USER_KEY, JSON.stringify(newUser)),
    ]);
    setToken(newToken);
    setUser(newUser);
  }, []);

  const clearSession = useCallback(async () => {
    await Promise.all([
      AsyncStorage.removeItem(TOKEN_KEY),
      AsyncStorage.removeItem(USER_KEY),
    ]);
    // Purge all cached query data so the next user cannot see a previous
    // user's documents or analysis results within the same app process.
    queryClient.clear();
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, isLoading, setSession, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
