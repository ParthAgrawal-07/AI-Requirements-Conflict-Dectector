import type { FeedItem } from "./useGraphDeltas";

export interface ChangesFeedProps {
  items: FeedItem[];
  onSelect: (elementIds: string[]) => void;
}

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The written feed under the map (US-14): every change as a sentence, newest first, read out by
 *  screen readers as it arrives. Choosing a sentence highlights what it is about. */
export function ChangesFeed({ items, onSelect }: ChangesFeedProps) {
  return (
    <section className="changes-feed" aria-label="Changes">
      <h2 className="eyebrow">
        <span aria-hidden="true">◉ </span>Live
      </h2>
      <p className="sr-only" aria-live="polite">
        {items[0]?.sentence ?? ""}
      </p>
      {items.length === 0 ? (
        <p className="muted small">Changes appear here as they happen.</p>
      ) : (
        <ol className="feed-list">
          {items.map((item) => (
            <li key={item.key}>
              <button type="button" className="feed-item" onClick={() => onSelect(item.elementIds)}>
                <time className="muted small" dateTime={item.at}>
                  {time(item.at)}
                </time>{" "}
                {item.sentence}
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
