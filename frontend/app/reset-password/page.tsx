"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { apiFetch } from "@/lib/api";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleReset() {
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("Missing reset token. Please use the link from your email.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const response = await apiFetch<{ message: string }>(
      "/auth/reset-password",
      {
        method: "POST",
        body: JSON.stringify({ token, new_password: newPassword })
      }
    );

    if (response.status === "ok") {
      setSuccess(true);
    } else {
      setError(response.error?.message || "Unable to reset password. The link may have expired.");
    }
    setSubmitting(false);
  }

  if (success) {
    return (
      <>
        <h2>Password Reset Complete</h2>
        <p>Your password has been updated successfully.</p>
        <a className="button" href="/dashboard">
          Sign In
        </a>
      </>
    );
  }

  return (
    <>
      <h2>Set a New Password</h2>
      <p>Enter your new password below.</p>
      <label>
        New Password
        <input
          className="input"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder="At least 8 characters"
        />
      </label>
      <label>
        Confirm New Password
        <input
          className="input"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
      </label>
      {error ? <p className="dashboard-error">{error}</p> : null}
      <button className="button" disabled={submitting} onClick={handleReset}>
        {submitting ? "Resetting..." : "Reset Password"}
      </button>
      <p className="dashboard-auth-switch">
        <a className="link-button" href="/dashboard">
          Back to Sign In
        </a>
      </p>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">Account</p>
        <h1>Reset Your Password</h1>
      </section>

      <div className="card dashboard-login-card">
        <Suspense fallback={<p>Loading...</p>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </main>
  );
}
