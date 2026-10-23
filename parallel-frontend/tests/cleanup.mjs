import { rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname } from "node:path";
import process from "node:process";

export default async function cleanup() {
  const path = process.env.PARALLEL_E2E_OUTBOX;
  if (
    !path ||
    dirname(path) !== tmpdir() ||
    !/^parallel-e2e-outbox-[a-f0-9-]{36}$/.test(basename(path))
  )
    throw new Error("Refusing to clean a non-test outbox");
  const info = await stat(path).catch(() => null);
  if (info && (!process.getuid || info.uid === process.getuid()))
    await rm(path, { recursive: true });
}
