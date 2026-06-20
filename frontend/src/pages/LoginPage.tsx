import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { User } from "../lib/types";

export function LoginPage() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await api<{ user: User }>("/api/v1/auth/login/", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setUser(response.user);
      navigate(response.user.must_change_password ? "/change-password" : "/staff");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "ログインに失敗しました。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="card" onSubmit={onSubmit}>
        <h1>ログイン</h1>
        <label>
          ユーザー名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          パスワード
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "ログイン中..." : "ログイン"}
        </button>
      </form>
    </div>
  );
}
