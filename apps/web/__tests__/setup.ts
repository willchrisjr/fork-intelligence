import "@testing-library/jest-dom/vitest";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  value: ResizeObserverStub,
});

/**
 * Web Storage stub.
 *
 * Node 22+ ships its own experimental `localStorage` global that stays inert
 * unless the process is started with `--localstorage-file`. That global shadows
 * the one jsdom installs, so inside a test `"localStorage" in window` is true
 * while every read yields `undefined`, and any component calling it unguarded
 * throws. Accessing it also emits Node's ExperimentalWarning.
 *
 * Providing a spec-shaped implementation keeps the tests exercising the real
 * persistence path rather than mocking the component's own calls, so the
 * assertions still describe production behavior.
 */
class StorageStub implements Storage {
  #entries = new Map<string, string>();

  get length(): number {
    return this.#entries.size;
  }

  key(index: number): string | null {
    return [...this.#entries.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    // Storage returns null for absent keys, never undefined.
    return this.#entries.get(String(key)) ?? null;
  }

  setItem(key: string, value: string): void {
    // Storage coerces both key and value to strings.
    this.#entries.set(String(key), String(value));
  }

  removeItem(key: string): void {
    this.#entries.delete(String(key));
  }

  clear(): void {
    this.#entries.clear();
  }
}

function installStorage(name: "localStorage" | "sessionStorage"): void {
  // Only stand in when the environment does not supply a working Storage, so
  // this quietly stops applying once the underlying issue is fixed upstream.
  const existing = (globalThis as Record<string, unknown>)[name];
  if (existing) {
    return;
  }
  const storage = new StorageStub();
  for (const target of [globalThis, globalThis.window]) {
    if (!target) {
      continue;
    }
    Object.defineProperty(target, name, {
      value: storage,
      configurable: true,
      writable: false,
    });
  }
}

installStorage("localStorage");
installStorage("sessionStorage");
