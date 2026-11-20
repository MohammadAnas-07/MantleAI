import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { Link } from "react-router";

import { useHealth } from "../hooks/queries";
import { apiBaseUrl } from "../lib/api/client";
import { KEYS_UNREADABLE } from "../lib/llmErrors";
import { Button } from "./ui/Button";
import { Banner } from "./ui/Feedback";

/** Shown when the API can't be reached, instead of a blank page; Retry refetches everything. */
export function BackendBanner() {
  const health = useHealth();
  const client = useQueryClient();
  if (!health.isError && health.data?.database !== "down") {
    if (health.data?.keys !== "unreadable") return null;
    return (
      <Banner
        kind="warning"
        action={
          <Link to="/settings" className="text-sm">
            Open settings
          </Link>
        }
      >
        {KEYS_UNREADABLE}
      </Banner>
    );
  }

  const retry = () => {
    void client.invalidateQueries();
  };
  if (health.isError) {
    return (
      <Banner
        kind="danger"
        action={
          <Button
            size="sm"
            onClick={retry}
            busy={health.isFetching}
            icon={<RefreshCw aria-hidden className="size-4" />}
          >
            Retry
          </Button>
        }
      >
        Can&apos;t reach the Mantle API at <code>{apiBaseUrl()}</code>. Start it with{" "}
        <code>uvicorn app.main:app --reload</code> in <code>backend</code>.
      </Banner>
    );
  }
  return (
    <Banner
      kind="warning"
      action={
        <Button size="sm" onClick={retry}>
          Retry
        </Button>
      }
    >
      The API is running but its database is down. Run <code>docker compose up -d</code>.
    </Banner>
  );
}
