"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import type { Schemas } from "@/lib/api/client";

type MembershipResponse = Schemas["MembershipResponse"];

const CURRENT_ORG_KEY = "eaikp_current_org_id";

interface OrgContextValue {
  currentOrgId: string | null;
  currentMembership: MembershipResponse | null;
  memberships: MembershipResponse[];
  setCurrentOrgId: (organizationId: string) => void;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const memberships = useMemo(() => user?.memberships ?? [], [user]);
  const [currentOrgId, setCurrentOrgIdState] = useState<string | null>(null);

  useEffect(() => {
    async function resolveCurrentOrg() {
      if (memberships.length === 0) {
        setCurrentOrgIdState(null);
        return;
      }
      const stored = localStorage.getItem(CURRENT_ORG_KEY);
      const storedIsValid =
        stored !== null && memberships.some((m) => m.organization_id === stored);
      setCurrentOrgIdState(storedIsValid ? stored : (memberships[0]?.organization_id ?? null));
    }
    void resolveCurrentOrg();
  }, [memberships]);

  const setCurrentOrgId = (organizationId: string) => {
    localStorage.setItem(CURRENT_ORG_KEY, organizationId);
    setCurrentOrgIdState(organizationId);
  };

  const currentMembership = memberships.find((m) => m.organization_id === currentOrgId) ?? null;

  return (
    <OrgContext.Provider value={{ currentOrgId, currentMembership, memberships, setCurrentOrgId }}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrg(): OrgContextValue {
  const context = useContext(OrgContext);
  if (!context) {
    throw new Error("useOrg must be used within an OrgProvider.");
  }
  return context;
}
