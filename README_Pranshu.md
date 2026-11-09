# Pranshu — Sprint 2

**Merge order:** #10 (frontend; the backend zips #1–#3 provide its API). See `MERGE_ORDER.md`. Branch:
`us-28-us-29-channels-ui`.

## Status against the plan

| Task (Detailed Sprint Guide) | Status |
|---|---|
| `features/channels/{ChannelList,ChannelView,MessageList,Composer,Thread}.tsx`, `features/channels/api.ts` | ✅ (plus `MessageItem.tsx`, `mentions.ts`) |
| Channel sidebar, message list with virtual scroll, thread drawer, @mention autocomplete, socket events patch the query cache | ✅ |
| Done when: matches the Channels board; keyboard-only send works | ✅ tested (Enter sends, Shift+Enter new line, the mention picker works with arrows/Enter/Tab/Escape) |

## What this zip adds

| File | Change |
|---|---|
| `features/channels/api.ts` | hooks for channels, messages (infinite, cursor), threads, members; `upsertMessage()` used by mutations and realtime alike |
| `features/channels/ChannelList.tsx` | the sidebar group: `#`/🔒 names, unread counts (number **and** words for screen readers), "+" new channel for `channel.manage` |
| `features/channels/ChannelView.tsx` | header, archived banner (read-only), history, composer, thread drawer at `?thread=<id>`; marks the channel read |
| `features/channels/MessageList.tsx` | oldest-at-top history, "Load older messages", stays pinned to the bottom; windowed with `@tanstack/react-virtual` beyond 80 messages |
| `features/channels/MessageItem.tsx` | author or "(former member)", time, "edited", deleted placeholder, requirement-post card badge, thread link, Edit/Delete on your own chat messages |
| `features/channels/Composer.tsx`, `mentions.ts` | `@` opens an accessible listbox; picked names are sent as `<@user-id>` tokens and shown as `@Name`; bodies are always rendered as text |
| `app/socket.ts` | `watchChannel()` / `useChannelRealtime()` (re-subscribed after every reconnect); `applyEvent` re-reads `message.*` by id and patches the cache, refreshes channel lists on `channel.*` and unread counts on new messages |
| `app/AppShell.tsx`, `app/routes.tsx` | the real channel list replaces the `# general` placeholder; route `channels/:channelId` |
| `styles/components.css` | channel, message, composer and mention styles |
| `package.json` | **adds `@tanstack/react-virtual`** (same vendor as TanStack Query). Run `npm install`; `npm audit` reports no new advisories from it |
| `tests/channels.test.tsx`, `tests/socket.test.ts` | rendering as text, mentions, keyboard send, mention picking, archived read-only, threads, own-message actions, cache patching, channel re-subscription |

## Verified

`npm run typecheck`, `npm run lint`, `npx vitest run` — **46 tests** at this stage; `vite build` passes.
