import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Radar, ArrowRight } from 'lucide-react';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isRegister) {
        await register(email, password);
      } else {
        await login(email, password);
      }
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4" data-testid="login-page">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center">
            <Radar className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-50 font-heading">
              Agency Scraper
            </h1>
            <p className="text-xs uppercase tracking-[0.15em] text-zinc-500 font-medium">
              Sectoral Intelligence Platform
            </p>
          </div>
        </div>

        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader>
            <CardTitle className="text-lg font-heading text-zinc-50">
              {isRegister ? 'Create Account' : 'Sign In'}
            </CardTitle>
            <CardDescription className="text-zinc-400">
              {isRegister
                ? 'Register to start analyzing agencies'
                : 'Access your intelligence dashboard'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-zinc-300 text-xs uppercase tracking-wider">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  data-testid="login-email-input"
                  className="bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-zinc-300 text-xs uppercase tracking-wider">
                  Password
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min 4 characters"
                  required
                  minLength={4}
                  data-testid="login-password-input"
                  className="bg-zinc-950 border-zinc-700 text-zinc-50 placeholder:text-zinc-600 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              {error && (
                <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2" data-testid="login-error">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                disabled={loading}
                data-testid="login-submit-btn"
                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium"
              >
                {loading ? 'Processing...' : (isRegister ? 'Create Account' : 'Sign In')}
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>

              <div className="text-center">
                <button
                  type="button"
                  onClick={() => { setIsRegister(!isRegister); setError(''); }}
                  data-testid="toggle-auth-mode"
                  className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {isRegister ? 'Already have an account? Sign in' : 'Need an account? Register'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
