"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import TenderForm from "@/components/TenderForm";
import { Notice, PageHeading, Panel } from "@/components/ui";

export default function NewTenderPage() {
  const { user } = useAuth();
  const router = useRouter();
  if (user && user.role === "supplier") return <Notice kind="error">Only buyers can create tenders.</Notice>;
  return (
    <>
      <PageHeading title="Create tender" subtitle="Describe what you need and how bids will be scored." />
      <Panel>
        <TenderForm submitLabel="Publish tender" onSubmit={async (values) => {
          const created = await api.createTender(values);
          router.push(`/tenders/${created.id}`);
        }} />
      </Panel>
    </>
  );
}
