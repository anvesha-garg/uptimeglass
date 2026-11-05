import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/auth-context";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassInput } from "../components/glass/GlassInput";
import { AuthLayout } from "../components/layout/AuthLayout";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});

  // On success AuthProvider flips to "authenticated", and PublicOnlyRoute moves us on.
  const mutation = useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      login(credentials.email, credentials.password),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!EMAIL_PATTERN.test(email.trim())) next.email = "Enter a valid email address.";
    if (!password) next.password = "Enter your password.";
    setErrors(next);
    if (next.email || next.password) return;
    mutation.mutate({ email: email.trim(), password });
  }

  const formError = mutation.error
    ? mutation.error instanceof ApiError
      ? mutation.error.message
      : "Something went wrong. Please try again."
    : null;

  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New here? <Link to="/register">Create an account</Link>
        </>
      }
    >
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <GlassInput
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={errors.email}
        />
        <GlassInput
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={errors.password}
        />
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <GlassButton type="submit" loading={mutation.isPending}>
          Sign in
        </GlassButton>
      </form>
    </AuthLayout>
  );
}
