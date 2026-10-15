// The sign-in token (a Google ID token) is kept for this browser tab only. It lives about an hour.
// Trade-off: any script on the page could read it, which is why a real product would prefer an httpOnly cookie.
const KEY = "harness.token";

export const getToken = (): string | null => {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null; // storage can be blocked; then every visit signs in again
  }
};

export const setToken = (token: string) => {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {}
};

export const clearToken = () => {
  try {
    sessionStorage.removeItem(KEY);
  } catch {}
};

export const SIGNED_OUT = "harness:signed-out"; // fired when the server says our token is no longer good
