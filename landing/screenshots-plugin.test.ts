import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { findScreenshots, imageSize } from "./screenshots-plugin";

describe("screenshots", () => {
  it("reads PNG sizes and skips other files, with alt text from alt.json or the name", () => {
    const dir = mkdtempSync(join(tmpdir(), "shots-"));
    const png = Buffer.alloc(24);
    png.write("\x89PNG", 0, "latin1");
    png.writeUInt32BE(1280, 16);
    png.writeUInt32BE(800, 20);
    writeFileSync(join(dir, "chat-with-citations.png"), png);
    writeFileSync(join(dir, "workflow.png"), png);
    writeFileSync(join(dir, "notes.txt"), "not an image");
    writeFileSync(join(dir, "alt.json"), JSON.stringify({ "workflow.png": "The workflow page" }));

    expect(imageSize(png)).toEqual({ width: 1280, height: 800 });
    expect(findScreenshots(dir)).toEqual([
      {
        src: "./screenshots/chat-with-citations.png",
        alt: "Chat with citations",
        width: 1280,
        height: 800,
      },
      { src: "./screenshots/workflow.png", alt: "The workflow page", width: 1280, height: 800 },
    ]);
  });

  it("finds nothing when the folder is missing", () => {
    expect(findScreenshots(join(tmpdir(), "no-such-folder-for-mantle"))).toEqual([]);
  });
});
