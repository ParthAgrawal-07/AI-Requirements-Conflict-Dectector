# Realtime WebSocket Contract (Sprint 0–1)

**Status:** Ratified for frontend client (`app/socket.ts`) and backend gateway (US-03, Dhvani).  
**Path:** `/ws`  
**Protocol:** WebSocket text frames carrying JSON payloads.

---

## 1. Overview & Architecture

- **One connection per browser tab:** Components never open sockets directly. They register interest via `useProjectRealtime(projectId)`.
- **Cache-invalidation model:** Realtime events are hints. Missed events while offline are never replayed. On every connection or reconnection `ready` frame, the client invalidates the relevant TanStack Query caches to re-sync state over REST.
- **Polling fallback:** If realtime is unavailable or disabled via `VITE_REALTIME_ENABLED=false`, screens fall back to polling (e.g. `useDocuments` polls every 3 s while documents are active).

---

## 2. Connection Lifecycle & Authentication

1. **Connect:** Client initiates WebSocket handshake at `ws://<api-host>/ws` (or `wss://` in production).
2. **First frame (Client -> Server):**
   ```json
   {
     "type": "auth",
     "token": "<JWT_ACCESS_TOKEN>"
   }
   ```
3. **Authentication response:**
   - **Success (Server -> Client):**
     ```json
     {
       "type": "ready",
       "user_id": "<uuid>"
     }
     ```
   - **Failure (Server closes connection):**
     - Code `4401` (`CLOSE_UNAUTHENTICATED`): Token invalid or expired. The client clears authentication state and prompts for sign-in.
     - Code `4403` (`CLOSE_REVOKED`): Membership revoked or access forbidden. The client invalidates workspace and permission caches and does not reconnect.

---

## 3. Subscriptions

Clients subscribe to project event rooms:

- **Subscribe (Client -> Server):**
  ```json
  {
    "type": "subscribe",
    "project_id": "<project_uuid>"
  }
  ```
- **Unsubscribe (Client -> Server):**
  When all components watching a project unmount:
  ```json
  {
    "type": "unsubscribe",
    "project_id": "<project_uuid>"
  }
  ```

---

## 4. Heartbeat (Ping/Pong)

To keep NAT mappings alive and detect dropped TCP sessions:

- **Ping (Client -> Server):** Sent every 25 seconds while connection is ready.
  ```json
  {
    "type": "ping"
  }
  ```
- **Pong (Server -> Client):**
  ```json
  {
    "type": "pong"
  }
  ```

---

## 5. Event Frame Format

When an event occurs on a subscribed project, the server pushes an event frame:

```json
{
  "type": "event",
  "event": {
    "type": "analysis.progress",
    "workspace_id": "<workspace_uuid>",
    "project_id": "<project_uuid>",
    "channel_id": null,
    "entity_id": "<document_uuid>",
    "at": "2026-10-24T12:00:00Z",
    "data": {
      "status": "processing",
      "progress_percent": 45,
      "current_stage": "extracting"
    }
  }
}
```

### Event Types
- `analysis.progress`: Document extraction/embedding status update.
  - `status`: `"queued"` | `"processing"` | `"done"` | `"failed"`
  - `progress_percent`: `0`–`100`
  - On `"done"`, client invalidates both `["documents", projectId]` and `["requirements", projectId]`.

---

## 6. Error & Reconnection Policy

- **Backoff:** On abnormal disconnect, client reconnects with exponential backoff (`delay = min(30000, 1000 * 2^attempts)`).
- **Retry Cap:** Client stops retrying after 5 consecutive failures, logging no further console errors and gracefully falling back to REST polling.
- **No retry on authentication errors:** No reconnect occurs after close code `4401` or `4403`.

