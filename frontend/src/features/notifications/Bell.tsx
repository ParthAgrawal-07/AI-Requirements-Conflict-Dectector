import { NavLink } from "react-router-dom";
import { useNotificationCounts } from "./api";

/** The bell in the top bar (US-38): the unread count, live, linking to the inbox. */
export function Bell() {
  const counts = useNotificationCounts();
  const total = counts.data?.total ?? 0;
  return (
    <NavLink
      to="/inbox"
      className="bell"
      aria-label={total ? `Inbox, ${total} unread` : "Inbox, nothing unread"}
    >
      <span aria-hidden="true">🔔</span>
      {total > 0 && (
        <span className="bell-count" aria-hidden="true">
          {total > 99 ? "99+" : total}
        </span>
      )}
    </NavLink>
  );
}
