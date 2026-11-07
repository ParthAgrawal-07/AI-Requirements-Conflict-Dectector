# Channels and messages — contract

| | |
|---|---|
| **Producers** | Madhav (channels: `app/services/channels.py`, `app/api/channels.py`) · Dhavni didi (messages: `app/services/messages.py`, `app/api/messages.py`, gateway) |
| **Consumers** | Pranshu (`features/channels`) · Bansil (requirement posts, `app/intake/posts.py`) · Affan (tests) |
| **Stories** | US-28, US-29 (S2); requirement posts are the backend of US-30 (S3) |
| **Tables** | migration `0005b`: `channels`, `channel_members`, `channel_reads`, `messages` |

## 1. Visibility rules

1. The workspace membership is the gate (FR-38): a non-member gets **404** for every channel and message.
2. **Public** channels are open to every member of the workspace. **Private** channels exist only for the people listed
   on them: anyone else — a manager included — gets **404**, never 403 (ADR-12). `channel.manage` decides who may
   create, rename, archive and list people; it is not a key to every private channel.
3. **Archived** channels are read-only (409 `channel_archived` on any change or post) and hidden from the list unless
   `?include_archived=true`.
4. `#general` is created with every project (and backfilled for existing ones), is public and is never archived or
   renamed.

## 2. Endpoints

| Method and path | Permission | Notes |
|---|---|---|
| `POST /projects/{p}/channels` | `channel.manage` | `{name, topic?, is_private, member_ids?}`; the name is normalised (`" #Mobile App "` → `mobile-app`), unique per project (409) |
| `GET /projects/{p}/channels` | `view` | visible channels, `#general` first, with `unread_count` and `last_message_at` |
| `GET /channels/{c}` · `PATCH /channels/{c}` | `view` · `channel.manage` | rename, topic |
| `POST /channels/{c}/archive` | `channel.manage` | |
| `POST /channels/{c}/read` | `view` | moves the caller's own read marker (204); clears `unread_count` |
| `GET/POST /channels/{c}/members` · `DELETE /channels/{c}/members/{u}` | `view` · `channel.manage` | private channels only (409 `channel_public` otherwise) |
| `GET /channels/{c}/messages?before=&after=&limit=` | `view` | top-level messages, oldest first in the page; `next_cursor` |
| `POST /channels/{c}/messages` | `message.post` | `{body, parent_id?}`; rate-limited (`MESSAGES_PER_MINUTE`, 30) |
| `GET /messages/{id}` · `GET /messages/{id}/thread` | `view` | the thread: its root then the replies |
| `PATCH /messages/{id}` · `DELETE /messages/{id}` | `message.post` | your own **chat** messages only (403 / 409 `not_editable`) |
| `POST /channels/{c}/requirement-posts` | `req.propose` | Bansil: a `requirement_post` card plus a Proposed requirement |

## 3. Messages

* `kind`: `chat`, `requirement_post`, `change_request`, `analysis_card`, `system`. Only `chat` can be edited or deleted.
* **Threads** are one level deep; a reply's `parent_id` is a live top-level message of the same channel.
* **Mentions** are `<@user-uuid>` tokens in the body; the server keeps only people who can see the channel
  (`mentions` in the response and the event). Clients show them as `@Name`.
* **Bodies are plain text**, 1–4,000 characters, rendered as text — never as HTML.
* **Delete is soft**: the body is blanked, `deleted: true`, replies stay. A removed member's messages stay, with
  `author.is_member: false` ("former member").
* **Unread** counts top-level messages by others since the caller's read marker (or since they joined).
* **Cursors** are opaque; every message carries its own `cursor` for `after=` catch-up after a reconnect.

Events: see `realtime.md` (`channel.*`, `message.*`; ids only, `private` flag).
