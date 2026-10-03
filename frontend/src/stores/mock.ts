// Mock dev state mirror for O18 and the ×N badge (APP-07 AC2, APP-08). Owner: EE.
import { createStore } from "zustand/vanilla";
import { useStore } from "zustand";
import { mockDev } from "../client";
import type { MockDevState } from "../mock/MockClient";
import type { ScenarioId } from "../mock/scenarios";
import type { DemoSpeed } from "../mock/timing.config";

export interface MockState extends MockDevState { available: boolean }

export const mock = createStore<MockState>(() => ({
  available: Boolean(mockDev),
  ...(mockDev?.getState() ?? { scenario: "default" as ScenarioId, speed: 1 as DemoSpeed, ready: false }),
}));

mockDev?.subscribe((s) => mock.setState(s));
void mockDev?.ready.then(() => mock.setState(mockDev!.getState()));

export const useMock = <T>(sel: (s: MockState) => T): T => useStore(mock, sel);

export const mockActions = {
  setScenario: (id: ScenarioId) => mockDev?.setScenario(id),
  setSpeed: (s: DemoSpeed) => mockDev?.setSpeed(s),
  setMockKey: () => mockDev?.setMockKey(),
};
