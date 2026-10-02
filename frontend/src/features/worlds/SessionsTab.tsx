// S13 History = the hub's Sessions tab (R13, HIST-01..03, MULTI-15). World-scoped rows with mode icon, title (renameable),
// cast heads, message count, last updated and verdict badge; filters by mode and character; Replay / Resume /
// Continue live / Rename / Export / Delete. Demo: a "FEATURED RECORDING" strip heads the list. Owner: Builder A.
import { useState } from "react";
import { useNow } from "../../client/hooks";
import type { Character, Session, SessionMode } from "../../contract/types";
import { formatRelative } from "../../domain/format";
import type { Route } from "../../router";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import { ChipGroup, Segmented } from "../../ui/Controls";
import { Select, TextField } from "../../ui/Fields";
import { Skeleton } from "../../ui/Data";
import { EmptyState } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { PlayIcon } from "../../ui/icons";
import {
  featuredCta, filterSessions, formatSessionFilter, isFiltered, MODE_LABEL, parseSessionFilter, resumeLabel,
  sessionSubtitle, verdictBadge,
} from "./hubLogic";
import type { ModeFilter, SessionFilter, SortOrder } from "./hubLogic";
import { MoreMenu } from "./MoreMenu";
import { headUrl } from "./portraitUrls";
import { continueLive, deleteSession, exportSession, renameSession, replaySession, resumeSession } from "./sessionActions";
import s from "./Hub.module.css";

interface Props {
  worldId: string;
  route: Extract<Route, { name: "hub" }>;
  chars: Character[];
  sessions: Session[];
  loading: boolean;
  demo: boolean;
  featured: Session | null;
}

const MODE_GLYPH: Record<SessionMode, string> = { one_on_one: "1:1", group: "GRP", debate: "VS", watch: "▶" };

export function SessionsTab({ worldId, route, chars, sessions, loading, demo, featured }: Props) {
  const f = parseSessionFilter(route.filter);
  const setF = (patch: Partial<SessionFilter>) => {
    const filter = formatSessionFilter({ ...f, ...patch });
    navigate({ name: "hub", worldId, tab: "sessions", ...(filter ? { filter } : {}) }, { transition: "none", replace: true });
  };
  const byId = new Map(chars.map((c) => [c.id, c]));
  const castIds = [...new Set(sessions.flatMap((x) => x.participants.map((p) => p.characterId)))].filter((id) => byId.has(id));
  const rows = filterSessions(sessions, f);
  const showFeatured = demo && featured && !isFiltered(f);

  return (
    <div className={s.history}>
      {showFeatured && featured && (
        <div className={s.featured}>
          <Tape tone="brand" size="md" className={s.featuredTape}>FEATURED RECORDING ▶</Tape>
          <div className={s.featuredText}>
            <span className={s.featuredTitle}>{featured.title}</span>
            <span className={s.featuredSub}>{sessionSubtitle(featured)}</span>
          </div>
          <Heads ids={featured.participants.map((p) => p.characterId)} byId={byId} />
          <Button size="lg" icon={<PlayIcon />} onClick={() => replaySession(featured)}>{featuredCta(featured)}</Button>
        </div>
      )}

      <div className={s.filters} role="search" aria-label="Filter sessions">
        <ChipGroup<ModeFilter>
          label="Mode"
          hideLabel
          size="sm"
          value={f.mode}
          onChange={(mode) => setF({ mode })}
          options={[
            { value: "all", label: "All" },
            { value: "one_on_one", label: "1:1" },
            { value: "group", label: "Group" },
            { value: "debate", label: "Debate" },
            { value: "watch", label: "Watch" },
          ]}
        />
        <div className={s.filterRight}>
          <Select<string>
            label="Character"
            hideLabel
            value={f.characterId ?? "__all"}
            onChange={(v) => setF({ characterId: v === "__all" ? null : v })}
            options={[{ value: "__all", label: "Every character" }, ...castIds.map((id) => ({ value: id, label: byId.get(id)!.profile.name }))]}
            className={s.charSelect}
          />
          <Segmented<SortOrder>
            label="Sort"
            value={f.sort}
            onChange={(sort) => setF({ sort })}
            options={[{ value: "recent", label: "Most recent" }, { value: "oldest", label: "Oldest" }]}
          />
        </div>
      </div>

      {loading ? (
        <div className={s.rows} aria-busy="true">
          {[0, 1, 2, 3].map((i) => <div key={i} className={s.rowSkeleton}><Skeleton lines={2} widths={["40%", "70%"]} /></div>)}
        </div>
      ) : sessions.length === 0 ? (
        <EmptyState
          title="No conversations yet"
          className={s.empty}
          action={{ label: "Start chatting", run: () => navigate({ name: "setup", worldId }) }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing matches these filters"
          className={s.empty}
          action={{ label: "Clear filters", run: () => setF({ mode: "all", characterId: null }) }}
        />
      ) : (
        <ul className={s.rows} aria-label="Sessions">
          {rows.map((x, i) => <SessionRow key={x.id} session={x} byId={byId} demo={demo} index={i} />)}
        </ul>
      )}
    </div>
  );
}

function Heads({ ids, byId, max = 5 }: { ids: string[]; byId: Map<string, Character>; max?: number }) {
  const list = ids.map((id) => byId.get(id)).filter((c): c is Character => !!c);
  return (
    <span className={s.heads} aria-label={list.map((c) => c.profile.name).join(", ")}>
      {list.slice(0, max).map((c, i) => (
        <img key={c.id} src={headUrl(c)} alt="" title={c.profile.name} style={{ zIndex: max - i }} loading="lazy" />
      ))}
      {list.length > max && <span className={s.headsMore}>+{list.length - max}</span>}
    </span>
  );
}

function SessionRow({ session: x, byId, demo, index }: { session: Session; byId: Map<string, Character>; demo: boolean; index: number }) {
  const now = useNow(60_000);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(x.title);
  const badge = verdictBadge(x);
  const commit = async () => {
    if (await renameSession(x, title)) setRenaming(false);
    else {
      setTitle(x.title);
      setRenaming(false);
    }
  };
  return (
    <li className={s.row} style={{ ["--i" as string]: Math.min(index, 8) }} data-mode={x.mode}>
      <span className={s.modeIcon} aria-label={MODE_LABEL[x.mode]} title={MODE_LABEL[x.mode]}>{MODE_GLYPH[x.mode]}</span>
      <div className={s.rowMain}>
        {renaming ? (
          <form
            className={s.renameForm}
            onSubmit={(e) => {
              e.preventDefault();
              void commit();
            }}
          >
            <TextField
              label="Session title"
              hideLabel
              value={title}
              maxLength={80}
              autoFocus
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  e.stopPropagation();
                  setTitle(x.title);
                  setRenaming(false);
                }
              }}
            />
            <Button size="sm" type="submit">Save</Button>
          </form>
        ) : (
          <button type="button" className={s.rowTitle} onClick={() => resumeSession(x)}>
            {x.title}
          </button>
        )}
        <span className={s.rowSub}>
          <span className={s.rowMode}>{MODE_LABEL[x.mode]}</span>
          <span className={s.rowSubText}>{sessionSubtitle(x)}</span>
        </span>
      </div>
      <Heads ids={x.participants.map((p) => p.characterId)} byId={byId} max={4} />
      <span className={s.rowMeta}>
        <b>{x.messageCount}</b> msg
        <span className={s.rowDim}>{formatRelative(x.lastMessageAt ?? x.updatedAt, now)}</span>
      </span>
      <span className={s.rowBadges}>
        {x.isSeed && <Tape tone="paper" size="sm">RECORDING</Tape>}
        {badge && <Tape tone={badge.tone} size="sm">{badge.text}</Tape>}
        {!badge && x.status !== "ended" && !x.isSeed && <Tape tone={x.status === "active" ? "ok" : "ink"} size="sm">{x.status.toUpperCase()}</Tape>}
      </span>
      <span className={s.rowActions}>
        <Button size="sm" icon={<PlayIcon />} onClick={() => replaySession(x)} aria-label={`Replay ${x.title}`}>Replay</Button>
        {x.isSeed ? (
          <Button size="sm" variant="secondary" keyLocked={demo} onClick={() => void continueLive(x, demo)}>Continue live</Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => resumeSession(x)}>{resumeLabel(x)}</Button>
        )}
        <MoreMenu<"open" | "rename" | "export" | "delete">
          label={`More for ${x.title}`}
          size="sm"
          items={[
            ...(x.isSeed ? [{ id: "open" as const, label: resumeLabel(x) }] : []),
            { id: "rename", label: "Rename" },
            { id: "export", label: "Export Markdown" },
            { id: "delete", label: "Delete…", danger: true, divider: true },
          ]}
          onSelect={(id) => {
            if (id === "open") resumeSession(x);
            else if (id === "rename") setRenaming(true);
            else if (id === "export") void exportSession(x);
            else deleteSession(x);
          }}
        />
      </span>
    </li>
  );
}
