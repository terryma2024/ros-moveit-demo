import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no layout observer. Radix Slider uses it to measure the thumb;
// actual geometry and pointer interaction are verified in the browser gate.
globalThis.ResizeObserver ??= class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

afterEach(cleanup);
