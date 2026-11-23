import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useSetWatch, useWatch, type WatchSubject } from "./api";

export interface WatchButtonProps {
  subject: WatchSubject;
  id: string;
}

/** Watch a requirement, issue or change request and hear about its activity (US-53, US-38).
 *  A toggle button: its pressed state is announced to screen readers. */
export function WatchButton({ subject, id }: WatchButtonProps) {
  const watch = useWatch(subject, id);
  const setWatch = useSetWatch(subject, id);
  const notify = useToast();
  const watching = watch.data?.watching ?? false;
  const count = watch.data?.watchers ?? 0;
  return (
    <Button
      size="sm"
      variant="ghost"
      aria-pressed={watching}
      loading={setWatch.isPending}
      disabled={watch.isLoading}
      onClick={() =>
        setWatch.mutate(!watching, {
          onError: (error) => notify(error instanceof ApiError ? error.message : "Could not change it", "error"),
        })
      }
    >
      {watching ? "◉ Watching" : "○ Watch"}
      {count > 0 && <span className="muted small"> · {count}</span>}
    </Button>
  );
}
