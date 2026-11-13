// Mentions (US-29, FR-52). On the wire a mention is a `<@user-id>` token; on screen it is
// "@Full Name". Bodies are always rendered as text segments — never as HTML (no injection).

export type Segment = { kind: "text"; text: string } | { kind: "mention"; userId: string; name: string };

const TOKEN = /<@([0-9a-fA-F-]{36})>/g;

/** Split a stored body into text and mention segments, naming mentions from `names`. */
export function segments(body: string, names: Map<string, string>): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const match of body.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) out.push({ kind: "text", text: body.slice(last, index) });
    const userId = match[1];
    out.push({ kind: "mention", userId, name: names.get(userId) ?? "unknown member" });
    last = index + match[0].length;
  }
  if (last < body.length) out.push({ kind: "text", text: body.slice(last) });
  return out;
}

export interface Picked {
  userId: string;
  name: string;
}

/** Replace each picked "@Name" in what the person typed by its `<@id>` token. Longest names
 *  first, so "@Riya Kapoor" is not cut short by a "@Riya" picked earlier. */
export function encode(text: string, picked: Picked[]): string {
  let result = text;
  for (const { userId, name } of [...picked].sort((a, b) => b.name.length - a.name.length)) {
    result = result.split(`@${name}`).join(`<@${userId}>`);
  }
  return result;
}

/** The "@query" being typed just before the caret, or null. */
export function activeQuery(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const match = /(?:^|\s)@([\p{L}\p{N}._-]{0,40})$/u.exec(before);
  if (!match) return null;
  return { start: caret - match[1].length - 1, query: match[1] };
}
