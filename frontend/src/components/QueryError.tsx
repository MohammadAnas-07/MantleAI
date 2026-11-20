import { RefreshCw } from "lucide-react";

import { errorMessage } from "../lib/api/errors";
import { Button } from "./ui/Button";
import { Banner } from "./ui/Feedback";

/** A failed load: the reason and a Retry button, never an empty panel. */
export function QueryError({
  error,
  onRetry,
  retrying = false,
}: {
  error: unknown;
  onRetry: () => void;
  retrying?: boolean;
}) {
  return (
    <Banner
      kind="danger"
      action={
        <Button
          size="sm"
          onClick={onRetry}
          busy={retrying}
          icon={<RefreshCw aria-hidden className="size-4" />}
        >
          Retry
        </Button>
      }
    >
      {errorMessage(error)}
    </Banner>
  );
}
