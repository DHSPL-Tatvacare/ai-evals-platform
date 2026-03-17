import { create } from 'zustand';
import type { User, LoginCredentials } from '@/types/auth.types';
import { authApi } from '@/services/api/authApi';

interface AuthStore {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  loadUser: () => Promise<void>;
  setAccessToken: (token: string) => void;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  accessToken: localStorage.getItem('accessToken'),
  isAuthenticated: false,
  isLoading: true,

  login: async (credentials) => {
    const { accessToken, user } = await authApi.login(credentials);
    localStorage.setItem('accessToken', accessToken);
    set({ accessToken, user, isAuthenticated: true, isLoading: false });
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // Best-effort — clear local state regardless
    }
    localStorage.removeItem('accessToken');
    set({ accessToken: null, user: null, isAuthenticated: false, isLoading: false });
  },

  refreshToken: async () => {
    try {
      const { accessToken } = await authApi.refresh();
      localStorage.setItem('accessToken', accessToken);
      set({ accessToken });
      return true;
    } catch {
      return false;
    }
  },

  loadUser: async () => {
    const token = get().accessToken;
    if (!token) {
      set({ isLoading: false, isAuthenticated: false });
      return;
    }

    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      // Access token expired — try refresh
      const refreshed = await get().refreshToken();
      if (refreshed) {
        try {
          const user = await authApi.getMe();
          set({ user, isAuthenticated: true, isLoading: false });
          return;
        } catch {
          // Refresh succeeded but /me still failed — clear everything
        }
      }
      // Refresh failed — clear state
      localStorage.removeItem('accessToken');
      set({ accessToken: null, user: null, isAuthenticated: false, isLoading: false });
    }
  },

  setAccessToken: (token) => {
    localStorage.setItem('accessToken', token);
    set({ accessToken: token });
  },
}));
