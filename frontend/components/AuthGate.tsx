"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getAuthConfig, getMe, type Me } from "@/lib/api";
import { clearToken, getToken, setToken, SIGNED_OUT } from "@/lib/auth";
import { Button } from "./ui";

type GoogleId = {
  initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

const GSI = "https://accounts.google.com/gsi/client";

type State =
  | { kind: "loading" }
  | { kind: "open" } // login is off on this server: nothing to do
  | { kind: "signin"; clientId: string; note?: string }
  | { kind: "in"; me: Me };

/** Shows the app only to a signed-in user. When the server has login switched off, it steps aside. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const clientId = useRef("");

  const check = useCallback(async (note?: string) => {
    const cfg = await getAuthConfig().catch(() => null);
    if (!cfg) return setState({ kind: "signin", clientId: "", note: "Cannot reach the server." });
    if (cfg.mode === "off") return setState({ kind: "open" });
    clientId.current = cfg.client_id;
    if (!getToken()) return setState({ kind: "signin", clientId: cfg.client_id, note });
    const { me, status } = await getMe();
    if (me) return setState({ kind: "in", me });
    clearToken();
    setState({ kind: "signin", clientId: cfg.client_id, note: status === 403 ? "That Google account is not allowed to use this app." : "Your session ended. Please sign in again." });
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async: state is only set after the server answers
    check();
    const onSignedOut = () => setState({ kind: "signin", clientId: clientId.current, note: "Your session ended. Please sign in again." });
    window.addEventListener(SIGNED_OUT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT, onSignedOut);
  }, [check]);

  if (state.kind === "loading") return <p className="p-8 text-sm text-mute">Loading…</p>;
  if (state.kind === "signin") return <SignIn clientId={state.clientId} note={state.note} onToken={(t) => { setToken(t); check(); }} />;
  if (state.kind === "open") return <>{children}</>;

  return (
    <>
      {children}
      <div className="fixed bottom-3 right-3 z-50 flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-mute shadow-sm">
        <span>{state.me.email}</span>
        <Button onClick={() => { clearToken(); check(); }}>Sign out</Button>
      </div>
    </>
  );
}

function SignIn({ clientId, note, onToken }: { clientId: string; note?: string; onToken: (token: string) => void }) {
  const slot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!clientId) return;
    const draw = () => {
      const id = window.google?.accounts.id;
      if (!id || !slot.current) return;
      id.initialize({ client_id: clientId, callback: (r) => onToken(r.credential) });
      id.renderButton(slot.current, { theme: "outline", size: "large", text: "signin_with" });
    };
    if (window.google) return draw();
    const script = document.createElement("script");
    script.src = GSI;
    script.async = true;
    script.onload = draw;
    document.head.appendChild(script);
  }, [clientId, onToken]);

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-lg font-semibold tracking-tight">Agent harness</h1>
      <p className="text-sm text-mute">Sign in to continue.</p>
      {note && <p role="alert" className="rounded-lg border border-line bg-panel px-3 py-2 text-sm">{note}</p>}
      <div ref={slot} />
    </main>
  );
}
