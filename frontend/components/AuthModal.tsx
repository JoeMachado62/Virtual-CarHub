"use client";

import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { AuthState, saveAuthState } from "@/lib/auth";

type AuthView = "login" | "register" | "forgot-password";

type AuthModalProps = {
  onClose: () => void;
  onAuthenticated: (auth: AuthState) => void;
};

export function AuthModal({ onClose, onAuthenticated }: AuthModalProps) {
  const [authView, setAuthView] = useState<AuthView>("login");

  // Login fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Registration fields
  const [regFirstName, setRegFirstName] = useState("");
  const [regLastName, setRegLastName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPhone, setRegPhone] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirmPassword, setRegConfirmPassword] = useState("");
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);

  // Forgot password fields
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSubmitting, setForgotSubmitting] = useState(false);
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  const [forgotError, setForgotError] = useState<string | null>(null);

  async function login() {
    setLoggingIn(true);
    setLoginError(null);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    if (response.status === "ok") {
      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
      };
      saveAuthState(nextAuth);
      onAuthenticated(nextAuth);
    } else {
      setLoginError(response.error?.message || "Unable to sign in.");
    }
    setLoggingIn(false);
  }

  async function register() {
    if (regPassword !== regConfirmPassword) {
      setRegisterError("Passwords do not match.");
      return;
    }
    if (regPassword.length < 8) {
      setRegisterError("Password must be at least 8 characters.");
      return;
    }
    if (!regFirstName.trim() || !regLastName.trim()) {
      setRegisterError("First and last name are required.");
      return;
    }

    setRegistering(true);
    setRegisterError(null);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
      ghl_contact_id: string | null;
      is_new_user: boolean;
    }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: regEmail,
        password: regPassword,
        first_name: regFirstName,
        last_name: regLastName,
        phone: regPhone || undefined,
      }),
    });

    if (response.status === "ok") {
      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email: regEmail,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
      };
      saveAuthState(nextAuth);
      onAuthenticated(nextAuth);
    } else {
      setRegisterError(response.error?.message || "Unable to create account.");
    }
    setRegistering(false);
  }

  async function forgotPassword() {
    if (!forgotEmail.trim()) {
      setForgotError("Please enter your email address.");
      return;
    }
    setForgotSubmitting(true);
    setForgotError(null);
    setForgotMessage(null);
    const response = await apiFetch<{ message: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email: forgotEmail }),
    });
    if (response.status === "ok") {
      setForgotMessage(response.data.message);
    } else {
      setForgotError(response.error?.message || "Something went wrong. Please try again.");
    }
    setForgotSubmitting(false);
  }

  return (
    <div className="auth-modal-overlay" onClick={onClose}>
      <div className="card auth-modal" onClick={(e) => e.stopPropagation()}>
        <button className="auth-modal-close" onClick={onClose} aria-label="Close">&times;</button>

        <div className="dashboard-auth-tabs">
          <button
            className={`dashboard-auth-tab${authView === "login" ? " active" : ""}`}
            onClick={() => { setAuthView("login"); setLoginError(null); }}
          >
            Sign In
          </button>
          <button
            className={`dashboard-auth-tab${authView === "register" ? " active" : ""}`}
            onClick={() => { setAuthView("register"); setRegisterError(null); }}
          >
            Create Account
          </button>
        </div>

        {authView === "forgot-password" ? (
          <>
            <h2>Reset Your Password</h2>
            <p>Enter the email address you used to create your account and we&apos;ll send you a link to reset your password.</p>
            <label>
              Email
              <input
                className="input"
                type="email"
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.target.value)}
              />
            </label>
            {forgotError ? <p className="dashboard-error">{forgotError}</p> : null}
            {forgotMessage ? <p className="dashboard-success">{forgotMessage}</p> : null}
            <button className="button" disabled={forgotSubmitting} onClick={forgotPassword}>
              {forgotSubmitting ? "Sending..." : "Send Reset Link"}
            </button>
            <p className="dashboard-auth-switch">
              <button className="link-button" onClick={() => { setAuthView("login"); setForgotError(null); setForgotMessage(null); }}>
                Back to Sign In
              </button>
            </p>
          </>
        ) : authView === "login" ? (
          <>
            <h2>Welcome Back</h2>
            <p>Sign in to access My Garage, saved vehicles, and your deal workspace.</p>
            <label>
              Email
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Password
              <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {loginError ? <p className="dashboard-error">{loginError}</p> : null}
            <button className="button" disabled={loggingIn} onClick={login}>
              {loggingIn ? "Signing in..." : "Sign In"}
            </button>
            <p className="dashboard-auth-switch">
              <button className="link-button" onClick={() => { setAuthView("forgot-password"); setForgotEmail(email); }}>
                Forgot your password?
              </button>
            </p>
            <p className="dashboard-auth-switch">
              Don&apos;t have an account?{" "}
              <button className="link-button" onClick={() => setAuthView("register")}>
                Create one now
              </button>
            </p>
          </>
        ) : (
          <>
            <h2>Create Your Garage Account</h2>
            <p>Set up your account to save vehicles, track deals, and get personalized recommendations.</p>
            <div className="grid two">
              <label>
                First Name <span className="required">*</span>
                <input className="input" value={regFirstName} onChange={(e) => setRegFirstName(e.target.value)} />
              </label>
              <label>
                Last Name <span className="required">*</span>
                <input className="input" value={regLastName} onChange={(e) => setRegLastName(e.target.value)} />
              </label>
            </div>
            <label>
              Email <span className="required">*</span>
              <input className="input" type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} />
            </label>
            <label>
              Phone <span className="muted-copy">(optional)</span>
              <input className="input" type="tel" value={regPhone} onChange={(e) => setRegPhone(e.target.value)} placeholder="(555) 555-1234" />
            </label>
            <label>
              Password <span className="required">*</span>
              <input className="input" type="password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} placeholder="At least 8 characters" />
            </label>
            <label>
              Confirm Password <span className="required">*</span>
              <input className="input" type="password" value={regConfirmPassword} onChange={(e) => setRegConfirmPassword(e.target.value)} />
            </label>
            {registerError ? <p className="dashboard-error">{registerError}</p> : null}
            <button className="button" disabled={registering} onClick={register}>
              {registering ? "Creating account..." : "Create Account"}
            </button>
            <p className="dashboard-auth-switch">
              Already have an account?{" "}
              <button className="link-button" onClick={() => setAuthView("login")}>
                Sign in
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
