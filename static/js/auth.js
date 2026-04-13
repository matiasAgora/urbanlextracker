/**
 * Urban Lex Tracker — Auth JS Module
 * Shared across all pages for session management.
 */

const ULT = {
  TOKEN_KEY: "ult_token",
  USER_KEY: "ult_user",

  // ─── Token management ───
  getToken() { return localStorage.getItem(this.TOKEN_KEY); },
  getUser() {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY)); }
    catch { return null; }
  },
  saveSession(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },
  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },
  isAuthenticated() { return !!this.getToken(); },

  // ─── API helper ───
  async apiFetch(path, options = {}) {
    const token = this.getToken();
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const resp = await fetch(path, { ...options, headers });
    if (resp.status === 401) {
      this.clearSession();
      window.location.href = "/login";
      return null;
    }
    return resp;
  },

  // ─── Route protection ───
  requireAuth() {
    if (!this.isAuthenticated()) {
      window.location.href = "/login";
      return false;
    }
    return true;
  },
  redirectIfAuth() {
    if (this.isAuthenticated()) {
      window.location.href = "/dashboard";
    }
  },

  // ─── Login ───
  async login(email, password) {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Error al iniciar sesión");
    this.saveSession(data.access_token, data.user);
    return data;
  },

  // ─── Register ───
  async register(email, password, nombre, profesion) {
    const resp = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, nombre, profesion })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Error al crear cuenta");
    this.saveSession(data.access_token, data.user);
    return data;
  },

  logout() {
    this.clearSession();
    window.location.href = "/login";
  },

  // ─── UI helpers ───
  showToast(msg, type = "success") {
    const colors = {
      success: "bg-green-800 border-green-600 text-green-100",
      error: "bg-red-900 border-red-700 text-red-100",
      info: "bg-blue-900 border-blue-700 text-blue-100"
    };
    const toast = document.createElement("div");
    toast.className = `fixed top-5 right-5 z-[9999] px-5 py-3 rounded-xl border text-sm font-semibold shadow-2xl transition-all duration-300 ${colors[type] || colors.info}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = "0"; setTimeout(() => toast.remove(), 300); }, 3500);
  },

  setLoadingBtn(btn, loading, originalText) {
    if (loading) {
      btn.disabled = true;
      btn.dataset.originalText = btn.textContent;
      btn.innerHTML = `<span class="inline-block animate-spin mr-2">⟳</span> ${originalText || "Cargando..."}`;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.originalText || originalText;
    }
  }
};
