import { describe, expect, it } from "vitest";

import { createCommandId } from "./command-id";

describe("createCommandId", () => {
  it("generates distinct UUID-shaped IDs when randomUUID is unavailable on HTTP origins", () => {
    let seed = 0;
    const insecureOriginCrypto = {
      getRandomValues(bytes: Uint8Array) {
        bytes.fill(seed++);
        return bytes;
      },
    };

    const first = createCommandId(insecureOriginCrypto);
    const second = createCommandId(insecureOriginCrypto);

    expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(second).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(second).not.toBe(first);
  });
});
