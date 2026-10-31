import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";
import { LockKeyhole } from "lucide-react";
import { supabase, supabaseAuthEnabled } from "../lib/supabase";
import { LoadingState } from "../components/UI";

interface AuthValue {
  enabled: boolean;
  loading: boolean;
  session: Session | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(supabaseAuthEnabled);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        setLoading(false);
      }
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthValue>(() => ({
    enabled: supabaseAuthEnabled,
    loading,
    session,
    signOut: async () => {
      if (!supabase) return;
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    },
  }), [loading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { enabled, loading, session } = useAuth();
  if (loading) return <LoadingState label="Проверяем сессию оператора" />;
  if (!enabled || session) return children;
  return <SignInForm />;
}

function SignInForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { error: authError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (authError) throw authError;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выполнить вход.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-gate">
      <section className="panel auth-panel">
        <div className="panel-header">
          <div className="panel-title"><LockKeyhole size={16} /><span>Вход оператора</span></div>
        </div>
        <form className="dialog-form" onSubmit={(event) => void submit(event)}>
          <label className="field-label">Рабочая почта
            <input autoComplete="username" autoFocus onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label className="field-label">Пароль
            <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="button button-primary" disabled={busy} type="submit">
            {busy ? "Входим..." : "Войти"}
          </button>
        </form>
      </section>
    </main>
  );
}