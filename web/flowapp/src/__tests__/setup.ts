// jsdom lacks what React Flow measures with; minimal stand-ins so components render in tests.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();   // without vitest globals, Testing Library does not unmount between tests by itself
  window.history.replaceState(null, "", "/");   // the address mirrors the selection (DVDG-564): no leaks between tests
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

if (!("DOMMatrixReadOnly" in globalThis)) {
  class DOMMatrixReadOnlyStub {
    m22 = 1;
    constructor(transform?: string) {
      const scale = /scale\(([\d.]+)\)/.exec(transform ?? "");
      this.m22 = scale ? Number(scale[1]) : 1;
    }
  }
  (globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = DOMMatrixReadOnlyStub;
}

if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {},
       removeListener() {}, dispatchEvent: () => false }) as MediaQueryList;
}
