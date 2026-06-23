import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";

export function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { refresh } = useAuth();
  const navigate = useNavigate();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      await api<{ detail: string }>("/api/v1/auth/change-password/", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          new_password_confirm: confirmPassword,
        }),
      });
      await refresh();
      setMessage("Password updated.");
      navigate("/staff");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Password update failed.");
    }
  };

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Change Password</h1>
        <p className="subtle-text">Use a strong password with at least 8 characters.</p>
        <label>
          Current password
          <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        </label>
        <label>
          New password
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </label>
        <label>
          Confirm new password
          <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        </label>
        {message ? <p className="success">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        <button type="submit">Save Password</button>
      </form>
    </div>
  );
}
