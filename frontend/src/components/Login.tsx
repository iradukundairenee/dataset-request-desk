import { useState } from "react";
import { Alert, Button, Form, Input, Typography } from "antd";
import { api, errorMessage, setToken } from "../api";
import type { User } from "../types";
import Icon, { Logo } from "./Icon";

interface LoginResponse {
  access_token: string;
  user: User;
}

const FEATURES = [
  { title: "Request", text: "Clients describe the episodes they need and a deadline." },
  { title: "Fulfil", text: "Operators pick good or usable recordings and deliver." },
  { title: "Review", text: "Clients accept the delivery or send it back for rework." },
];

export default function Login({ onLoggedIn }: { onLoggedIn: (user: User) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(values: { email: string; password: string }) {
    setBusy(true);
    setError("");
    try {
      const result = await api<LoginResponse>("/auth/login", { method: "POST", body: values });
      setToken(result.access_token);
      onLoggedIn(result.user);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="landing">
      <section className="hero">
        <div className="hero-brand">
          <Logo size={36} />
          <span>Dataset Request Desk</span>
        </div>

        <div className="hero-copy">
          <p className="eyebrow">Robot teleoperation data</p>
          <h1>Robot episode datasets, delivered.</h1>
          <p className="hero-lead">
            One place to request, fulfil and review datasets of recorded robot episodes. No more spreadsheets.
          </p>
          <ul className="hero-features">
            {FEATURES.map((f) => (
              <li key={f.title}>
                <span className="hero-check">
                  <Icon name="check" size={14} />
                </span>
                <span>
                  <strong>{f.title}.</strong> {f.text}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="hero-footer">Internal platform · authorised staff and clients only</p>
      </section>

      <section className="login-panel">
        <div className="login">
          <Typography.Title level={2}>Welcome back</Typography.Title>
          <Typography.Paragraph type="secondary">Log in with your work email.</Typography.Paragraph>
          <Form layout="vertical" size="large" onFinish={submit} requiredMark={false}>
            <Form.Item label="Email" name="email" rules={[{ required: true, type: "email", message: "Enter your email" }]}>
              <Input autoFocus autoComplete="username" />
            </Form.Item>
            <Form.Item label="Password" name="password" rules={[{ required: true, message: "Enter your password" }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            {error && <Alert type="error" title={error} showIcon className="form-alert" />}
            <Button type="primary" htmlType="submit" block loading={busy}>
              Log in
            </Button>
          </Form>
        </div>
      </section>
    </div>
  );
}
