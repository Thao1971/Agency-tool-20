import { createContext, useContext, useState, useEffect } from 'react';
import { authAPI } from '@/lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('as_token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      authAPI.me()
        .then(res => {
          setUser(res.data);
          setLoading(false);
        })
        .catch(() => {
          localStorage.removeItem('as_token');
          localStorage.removeItem('as_user');
          setToken(null);
          setUser(null);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (email, password) => {
    const res = await authAPI.login(email, password);
    const { token: t, user_id, email: em } = res.data;
    localStorage.setItem('as_token', t);
    localStorage.setItem('as_user', JSON.stringify({ id: user_id, email: em }));
    setToken(t);
    setUser({ id: user_id, email: em });
    return res.data;
  };

  const register = async (email, password) => {
    const res = await authAPI.register(email, password);
    const { token: t, user_id, email: em } = res.data;
    localStorage.setItem('as_token', t);
    localStorage.setItem('as_user', JSON.stringify({ id: user_id, email: em }));
    setToken(t);
    setUser({ id: user_id, email: em });
    return res.data;
  };

  const logout = () => {
    localStorage.removeItem('as_token');
    localStorage.removeItem('as_user');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
