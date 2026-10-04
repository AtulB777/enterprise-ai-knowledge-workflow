"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import { useOrg } from "@/lib/auth/org-context";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat" },
  { href: "/documents", label: "Documents" },
  { href: "/agents", label: "Agents" },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, isLoading, logout } = useAuth();
  const { currentOrgId, currentMembership, memberships, setCurrentOrgId } = useOrg();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-500">
        Loading…
      </div>
    );
  }

  // Matches require_platform_admin's backend check exactly (ADR-018
  // decision 1 / decision 4) — holds ADMIN in at least one organization,
  // not scoped to the currently-selected org. Kept in sync deliberately:
  // the UI shouldn't offer a link a request would then reject.
  const isPlatformAdmin = (user.memberships ?? []).some((m) => m.role === "admin");
  const navItems = isPlatformAdmin ? [...NAV_ITEMS, { href: "/admin", label: "Admin" }] : NAV_ITEMS;

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-ink-100 bg-white px-4 py-6">
        <div className="mb-8 px-2">
          <span className="font-display text-lg font-semibold text-ink-900">Archive</span>
        </div>

        {memberships.length > 1 && (
          <label className="mb-6 flex flex-col gap-1 px-2">
            <span className="text-xs font-medium uppercase tracking-wide text-ink-500">
              Organization
            </span>
            <select
              value={currentOrgId ?? ""}
              onChange={(e) => setCurrentOrgId(e.target.value)}
              className="rounded border border-ink-300 bg-white px-2 py-1.5 text-sm text-ink-900"
            >
              {memberships.map((m) => (
                <option key={m.organization_id} value={m.organization_id}>
                  {m.organization_name}
                </option>
              ))}
            </select>
          </label>
        )}
        {memberships.length === 1 && currentMembership && (
          <p className="mb-6 px-2 text-sm font-medium text-ink-700">
            {currentMembership.organization_name}
          </p>
        )}

        <nav className="flex flex-col gap-1">
          {navItems.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded px-2 py-2 text-sm font-medium ${
                  isActive ? "bg-ink-50 text-ink-900" : "text-ink-500 hover:text-ink-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-2 px-2 pt-6">
          <p className="truncate text-sm text-ink-700">{user.full_name}</p>
          <p className="truncate font-mono text-xs text-ink-300">{user.email}</p>
          <button
            type="button"
            onClick={async () => {
              await logout();
              router.push("/login");
            }}
            className="mt-2 self-start text-sm text-ink-500 underline hover:text-ink-900"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}
