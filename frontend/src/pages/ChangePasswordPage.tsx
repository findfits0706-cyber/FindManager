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
      setMessage("変更しました。");
      navigate("/staff");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "変更に失敗しました。");
    }
  };

  return (
    <div className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>初回パスワード変更</h1>
        <p>8文字以上で、英字と数字を含むパスワードを設定してください。</p>
        <label>
          現在のパスワード
          <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        </label>
        <label>
          新しいパスワード
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </label>
        <label>
          新しいパスワード確認
          <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        </label>
        {message ? <p className="success">{message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        <button type="submit">変更する</button>
      </form>
    </div>
  );
}
