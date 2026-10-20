'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from 'react';

import { api, AUTH_TOKEN_KEY } from '@/lib/api';

interface UserContextType {
  userId: string;
  setUserId: (id: string) => void;
  password: string;
  setPassword: (password: string) => void;
  authenticated: boolean;
  authReady: boolean;
  role: string;
  login: () => Promise<boolean>;
  register: () => Promise<boolean>;
  logout: () => Promise<void>;
}

const UserContext = createContext<UserContextType>({
  userId: '',
  setUserId: () => {},
  password: '',
  setPassword: () => {},
  authenticated: false,
  authReady: false,
  role: 'student',
  login: async () => false,
  register: async () => false,
  logout: async () => {},
});

export const useUser = () => useContext(UserContext);

export const UserProvider = ({ children }: { children: ReactNode }) => {
  const [userId, setUserId] = useState(() =>
    typeof window !== 'undefined'
      ? localStorage.getItem('t2p_user_id') || ''
      : ''
  );
  const [password, setPassword] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [role, setRole] = useState('student');

  const clearSession = () => {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
    setAuthenticated(false);
    setRole('student');
  };

  useEffect(() => {
    const restore = async () => {
      if (!sessionStorage.getItem(AUTH_TOKEN_KEY)) {
        setAuthReady(true);
        return;
      }
      try {
        const response = await api.get('/auth/me');
        setUserId(response.data.user.user_id);
        setRole(response.data.user.role || 'student');
        setAuthenticated(true);
      } catch {
        clearSession();
      } finally {
        setAuthReady(true);
      }
    };
    void restore();
  }, []);

  const authenticate = async (route: '/auth/login' | '/auth/register') => {
    if (!userId.trim() || !password) return false;
    try {
      const response = await api.post(route, {
        user_id: userId.trim(),
        password,
      });
      sessionStorage.setItem(AUTH_TOKEN_KEY, response.data.access_token);
      localStorage.setItem('t2p_user_id', userId.trim());
      setPassword('');
      setAuthenticated(true);
      setRole(response.data.user.role || 'student');
      return true;
    } catch (error) {
      console.error('Authentication failed', error);
      return false;
    }
  };

  const login = () => authenticate('/auth/login');
  const register = () => authenticate('/auth/register');

  const logout = async () => {
    try {
      if (sessionStorage.getItem(AUTH_TOKEN_KEY)) {
        await api.post('/auth/logout');
      }
    } catch {
      // Local revocation still prevents the browser from reusing the session.
    } finally {
      clearSession();
      setPassword('');
    }
  };

  return (
    <UserContext.Provider
      value={{
        userId,
        setUserId,
        password,
        setPassword,
        authenticated,
        authReady,
        role,
        login,
        register,
        logout,
      }}
    >
      {children}
    </UserContext.Provider>
  );
};
