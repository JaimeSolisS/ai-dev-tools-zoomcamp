/**
 * Guest-link bearer tokens are only returned once by the backend. The
 * interviewer's browser remembers the ones it created so "Copy link" keeps
 * working from the dashboard.
 */
const KEY = 'archboard:link-vault';

function read(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}');
  } catch {
    return {};
  }
}

export function rememberLinkToken(linkId: string, token: string): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...read(), [linkId]: token }));
  } catch {
    /* storage unavailable */
  }
}

export function recallLinkToken(linkId: string): string | null {
  return read()[linkId] ?? null;
}

export function joinUrl(token: string): string {
  return `${window.location.origin}/join/${encodeURIComponent(token)}`;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
