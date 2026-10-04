"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register(email, password, fullName, organizationName);
      router.push("/chat");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not create your account. Try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <h1 className="mb-1 font-display text-2xl font-semibold text-ink-900">
          Create your organization
        </h1>
        <p className="mb-8 text-sm text-ink-500">Start a new workspace and knowledge base.</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="Your name"
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <Input
            label="Organization name"
            required
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="text-xs text-ink-500">At least 8 characters, with a letter and a digit.</p>
          {error && (
            <p role="alert" className="rounded bg-brick-dim px-3 py-2 text-sm text-brick">
              {error}
            </p>
          )}
          <Button type="submit" disabled={isSubmitting} className="mt-2">
            {isSubmitting ? "Creating…" : "Create account"}
          </Button>
        </form>
        <p className="mt-6 text-sm text-ink-500">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-ink-900 underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
