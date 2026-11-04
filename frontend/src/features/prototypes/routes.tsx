import type { RouteObject } from "react-router-dom";
import { MapSpike } from "./MapSpike";
import {
  ChangeRequestPrototype,
  ComposerPrototype,
  IssuePrototype,
  JoinPrototype,
  PrototypeIndex,
} from "./Prototypes";

/** Throwaway prototype routes (no sign-in, no data) for usability sessions and the map spike. */
export const prototypeRoutes: RouteObject[] = [
  { path: "/prototypes", element: <PrototypeIndex /> },
  { path: "/prototypes/join", element: <JoinPrototype /> },
  { path: "/prototypes/composer", element: <ComposerPrototype /> },
  { path: "/prototypes/issue", element: <IssuePrototype /> },
  { path: "/prototypes/change-request", element: <ChangeRequestPrototype /> },
  { path: "/prototypes/map-spike", element: <MapSpike /> },
];
