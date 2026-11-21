import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/Button";
import { GROUPS, useMarkRead, useNotificationCounts, useNotifications, type InboxGroup } from "./api";

/** The inbox (US-38, interface design §11): GitHub-style, grouped by why it is here. Each row
 *  opens its subject and marks it done; "Mark all read" clears the bell. */
export function Inbox() {
  const [group, setGroup] = useState<InboxGroup | null>(null);
  const [unread, setUnread] = useState(true);
  const counts = useNotificationCounts();
  const list = useNotifications(group, unread);
  const markRead = useMarkRead();
  const rows = list.data ?? [];

  return (
    <div className="page inbox">
      <header className="page-header">
        <h1>Inbox</h1>
        <Button variant="ghost" onClick={() => markRead.mutate("all")} disabled={!counts.data?.total}>
          Mark all read
        </Button>
      </header>
      <div className="inbox-layout">
        <nav aria-label="Inbox groups" className="inbox-groups">
          <button type="button" className="nav-link" aria-pressed={group === null} onClick={() => setGroup(null)}>
            Everything {counts.data ? <span className="count">{counts.data.total}</span> : null}
          </button>
          {GROUPS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="nav-link"
              aria-pressed={group === item.id}
              onClick={() => setGroup(item.id)}
            >
              {item.label} {counts.data?.[item.id] ? <span className="count">{counts.data[item.id]}</span> : null}
            </button>
          ))}
        </nav>
        <section aria-label="Notifications">
          <label className="checkbox">
            <input type="checkbox" checked={unread} onChange={(event) => setUnread(event.target.checked)} /> Unread
            only
          </label>
          {list.isLoading && <p className="muted">Loading…</p>}
          {!list.isLoading && rows.length === 0 && <p className="muted">Nothing here. You are up to date.</p>}
          <ul className="inbox-list">
            {rows.map((row) => (
              <li key={row.id} className={row.read ? "read" : "unread"}>
                <span className="sr-only">{row.read ? "Read: " : "Unread: "}</span>
                <span className="eyebrow">{GROUPS.find((g) => g.id === row.group)?.label}</span>
                <Link to={row.payload.url} onClick={() => !row.read && markRead.mutate([row.id])}>
                  {row.payload.title}
                </Link>{" "}
                <span className="muted small">{new Date(row.updated_at).toLocaleString()}</span>
                {!row.read && (
                  <>
                    {" "}
                    <Button variant="ghost" size="sm" onClick={() => markRead.mutate([row.id])}>
                      Mark done
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
