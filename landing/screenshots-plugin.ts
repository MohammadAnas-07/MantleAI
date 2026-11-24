// Finds real screenshots in public/screenshots/ at build time and hands their paths, sizes and
// alt text to the page as the module "virtual:screenshots". No files: an empty list, and the
// page shows no figure at all. Alt text comes from public/screenshots/alt.json
// ({ "file.png": "What the screen shows" }), else from the file name.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Plugin } from "vite";

const ID = "virtual:screenshots";
const RESOLVED = `\0${ID}`;

export interface Shot {
  src: string;
  alt: string;
  width: number;
  height: number;
}

/** Width and height from a PNG or WebP header, or null if the file is neither. */
export function imageSize(bytes: Buffer): { width: number; height: number } | null {
  if (bytes.subarray(1, 4).toString("ascii") === "PNG") {
    return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
  }
  if (bytes.subarray(0, 4).toString("ascii") !== "RIFF") return null;
  const kind = bytes.subarray(12, 16).toString("ascii");
  if (kind === "VP8X") {
    return { width: 1 + bytes.readUIntLE(24, 3), height: 1 + bytes.readUIntLE(27, 3) };
  }
  if (kind === "VP8L") {
    const bits = bytes.readUInt32LE(21);
    return { width: 1 + (bits & 0x3fff), height: 1 + ((bits >> 14) & 0x3fff) };
  }
  if (kind === "VP8 ") {
    return { width: bytes.readUInt16LE(26) & 0x3fff, height: bytes.readUInt16LE(28) & 0x3fff };
  }
  return null;
}

const fromName = (file: string) => {
  const words = file
    .replace(/\.(png|webp)$/i, "")
    .replace(/[-_]+/g, " ")
    .trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

export function findScreenshots(dir: string): Shot[] {
  if (!existsSync(dir)) return [];
  const altFile = join(dir, "alt.json");
  const alts = existsSync(altFile)
    ? (JSON.parse(readFileSync(altFile, "utf-8")) as Record<string, string>)
    : {};
  return readdirSync(dir)
    .filter((f) => /\.(png|webp)$/i.test(f))
    .sort()
    .flatMap((file) => {
      const size = imageSize(readFileSync(join(dir, file)));
      if (!size) return [];
      return [{ src: `./screenshots/${file}`, alt: alts[file] ?? fromName(file), ...size }];
    });
}

export function screenshots(publicDir: string): Plugin {
  return {
    name: "landing-screenshots",
    resolveId: (id) => (id === ID ? RESOLVED : null),
    load: (id) =>
      id === RESOLVED
        ? `export default ${JSON.stringify(findScreenshots(join(publicDir, "screenshots")))};`
        : null,
  };
}
