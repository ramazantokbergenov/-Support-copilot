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
import { supabase, supabaseAuthEnabled } from "../lib/supabase";
import {
  clearLocalAccessToken,
  getLocalAccessToken,
  localAuthEnabled,
  signInLocal,
} from "../lib/localAuth";
import { LoadingState } from "../components/UI";

interface AuthValue {
  enabled: boolean;
  authenticated: boolean;
  loading: boolean;
  localMode: boolean;
  session: Session | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [localToken, setLocalToken] = useState<string | null>(getLocalAccessToken);
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
    enabled: supabaseAuthEnabled || localAuthEnabled,
    authenticated: supabaseAuthEnabled ? Boolean(session) : Boolean(localToken),
    loading,
    localMode: !supabaseAuthEnabled && localAuthEnabled,
    session,
    signIn: async (username, password) => {
      if (supabase) {
        const { error } = await supabase.auth.signInWithPassword({
          email: username.trim(),
          password,
        });
        if (error) throw error;
        return;
      }
      setLocalToken(await signInLocal(username.trim(), password));
    },
    signOut: async () => {
      if (supabase) {
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
      } else {
        clearLocalAccessToken();
        setLocalToken(null);
      }
    },
  }), [loading, localToken, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { enabled, loading, authenticated } = useAuth();
  if (loading) return <LoadingState label="Проверяем сессию оператора" />;
  if (!enabled || authenticated) return children;
  return <SignInForm />;
}

function SignInForm() {
  const { localMode, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
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
          <div className="panel-title"><img className="auth-brand-mark" src="/branding/support-copilot-icon.svg" alt="" /><span>Вход оператора</span></div>
        </div>
        <form className="dialog-form" onSubmit={(event) => void submit(event)}>
          <label className="field-label">{localMode ? "Имя оператора" : "Рабочая почта"}
            <input autoComplete="username" autoFocus onChange={(event) => setEmail(event.target.value)} required type={localMode ? "text" : "email"} value={email} />
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