/**
 * Auth/session helpers — menyimpan token & profil user di localStorage.
 * Sumber kebenaran: backend Django (TokenAuthentication DRF).
 */

export interface AuthUser {
    id: number;
    email: string;
    username: string;
    role: "mahasiswa" | "admin";
    is_staff: boolean;
    created_at: string;
}

const TOKEN_KEY = "lumina_token";
const USER_KEY = "lumina_user";

function safeStorage(): Storage | null {
    if (typeof window === "undefined") return null;
    try {
        return window.localStorage;
    } catch {
        return null;
    }
}

export function getToken(): string | null {
    return safeStorage()?.getItem(TOKEN_KEY) ?? null;
}

export function getUser(): AuthUser | null {
    const raw = safeStorage()?.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw) as AuthUser;
    } catch {
        return null;
    }
}

export function setAuth(token: string, user: AuthUser): void {
    const storage = safeStorage();
    if (!storage) return;
    storage.setItem(TOKEN_KEY, token);
    storage.setItem(USER_KEY, JSON.stringify(user));
}

export function setUser(user: AuthUser): void {
    safeStorage()?.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
    const storage = safeStorage();
    if (!storage) return;
    storage.removeItem(TOKEN_KEY);
    storage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
    return Boolean(getToken());
}
