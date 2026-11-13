import { useState } from "react";
import type { FormEvent } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { usePermissions } from "../../app/usePermissions";
import { Button } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { useChannels, useCreateChannel } from "./api";

export interface ChannelListProps {
  workspaceId: string;
  projectId: string;
}

/** The sidebar's Channels group (US-28): channels the member can see, unread counts in words as
 *  well as a number, and "+ Channel" for those who may create one. */
export function ChannelList({ workspaceId, projectId }: ChannelListProps) {
  const channels = useChannels(projectId);
  const { can } = usePermissions({ projectId });
  const [creating, setCreating] = useState(false);
  const base = `/w/${workspaceId}/p/${projectId}/channels`;

  return (
    <div className="nav-group">
      <div className="eyebrow nav-group-title">
        Channels
        {can("channel.manage") && (
          <button type="button" className="btn btn-ghost btn-sm" aria-label="New channel" onClick={() => setCreating(true)}>
            +
          </button>
        )}
      </div>
      {channels.isError && <p className="muted">Channels unavailable</p>}
      {channels.data?.map((channel) => (
        <NavLink key={channel.id} to={`${base}/${channel.id}`} className="nav-link channel-link">
          <span aria-hidden="true">{channel.is_private ? "🔒" : "#"}</span> {channel.name}
          {channel.unread_count > 0 && (
            <span className="unread" aria-label={`${channel.unread_count} unread`}>
              {channel.unread_count}
            </span>
          )}
        </NavLink>
      ))}
      <CreateChannel projectId={projectId} base={base} open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}

function CreateChannel({
  projectId,
  base,
  open,
  onClose,
}: {
  projectId: string;
  base: string;
  open: boolean;
  onClose: () => void;
}) {
  const create = useCreateChannel(projectId);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [isPrivate, setPrivate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const channel = await create.mutateAsync({ name, topic: topic || null, is_private: isPrivate });
      setName("");
      setTopic("");
      onClose();
      navigate(`${base}/${channel.id}`);
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? (failure.fieldErrors["body.name"] ?? failure.message)
          : "The channel could not be created.",
      );
    }
  }

  return (
    <Drawer open={open} title="New channel" onClose={onClose}>
      <form onSubmit={submit} className="form-stack">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={81} placeholder="mobile-app" />
        </label>
        <p className="muted hint">Lowercase letters, digits, “-” and “_”. Spaces become “-”.</p>
        <label>
          Topic (optional)
          <input value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={250} />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={isPrivate} onChange={(e) => setPrivate(e.target.checked)} />
          Private: only people you add can see it
        </label>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={create.isPending}>
          Create channel
        </Button>
      </form>
    </Drawer>
  );
}
