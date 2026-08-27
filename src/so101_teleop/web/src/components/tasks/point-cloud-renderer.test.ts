// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class WebGLRenderer {
    domElement = document.createElement("canvas");
    private pixelRatio = 1;

    setPixelRatio(value: number) {
      this.pixelRatio = value;
    }

    setSize(width: number, height: number, updateStyle = true) {
      this.domElement.width = Math.floor(width * this.pixelRatio);
      this.domElement.height = Math.floor(height * this.pixelRatio);
      if (updateStyle) {
        this.domElement.style.width = `${width}px`;
        this.domElement.style.height = `${height}px`;
      }
    }

    setAnimationLoop() {}
    render() {}
    dispose() {}
  }
  return { ...actual, WebGLRenderer };
});

import { createThreePointCloudRenderer } from "./point-cloud-viewer";

describe("createThreePointCloudRenderer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the canvas at the host's logical size on a Retina display", () => {
    vi.stubGlobal("devicePixelRatio", 2);
    const host = document.createElement("div");
    Object.defineProperty(host, "clientWidth", { configurable: true, value: 800 });

    const pointCloud = createThreePointCloudRenderer(host);
    const canvas = host.querySelector("canvas");

    expect(canvas?.style.width).toBe("800px");
    expect(canvas?.style.height).toBe("500px");
    expect(canvas?.width).toBe(1600);
    expect(canvas?.height).toBe(1000);
    pointCloud.dispose();
  });
});
