import { test, expect } from "@playwright/test";
import { readdir, readFile } from "node:fs/promises";
import process from "node:process";
import { join } from "node:path";
import { Buffer } from "node:buffer";

async function deliveredToken(email, purpose) {
  let token;
  await expect
    .poll(async () => {
      const files = await readdir(process.env.PARALLEL_E2E_OUTBOX).catch(
        () => [],
      );
      for (const file of files) {
        const record = JSON.parse(
          await readFile(join(process.env.PARALLEL_E2E_OUTBOX, file), "utf8"),
        );
        if (record.email === email && record.purpose === purpose)
          token = record.token;
      }
      return Boolean(token);
    })
    .toBe(true);
  return token;
}

for (const width of [1440, 390]) {
  test(`hardening at ${width}px: fixture embeddings, evidence, retention and private account delivery`, async ({
    browser,
  }) => {
    test.setTimeout(150000);
    const context = await browser.newContext({
      viewport: { width, height: width === 390 ? 844 : 1000 },
    });
    const page = await context.newPage();
    const email = `hardening-${width}@example.test`;
    await page.goto("/");
    await page.getByRole("button", { name: "Enter Dashboard" }).click();
    await page.getByRole("button", { name: "Create an account" }).click();
    await page.getByLabel("Full name").fill("Sam");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("browser-test-password");
    await page.getByRole("button", { name: "Sign Up", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Personal workspace", exact: true }),
    ).toBeVisible();
    await page.getByText("Verify account email", { exact: true }).click();
    await page
      .getByRole("button", { name: "Request verification instructions" })
      .click();
    await page
      .getByLabel("Verification token")
      .fill(await deliveredToken(email, "verify"));
    await page.getByRole("button", { name: "Complete verification" }).click();
    await expect(page.getByRole("status")).toContainText(
      "Verification completed",
    );
    await page.getByText("Verify account email", { exact: true }).click();
    await page.getByRole("button", { name: "Documents", exact: true }).click();
    await page.getByLabel("Document title").fill("Cobalt reference");
    await page
      .getByLabel("Text, Markdown or PDF file")
      .setInputFiles({
        name: "cobalt.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("Project uses durable session records."),
      });
    await page
      .getByRole("button", { name: "Upload document", exact: true })
      .click();
    await expect(
      page
        .getByRole("article")
        .filter({
          has: page.getByRole("heading", {
            name: "Cobalt reference",
            exact: true,
          }),
        }),
    ).toContainText("ready");
    await page
      .getByRole("button", { name: "Build trained index · owner only" })
      .click();
    await expect(
      page.getByText(
        /ready · 1 passages · fabricated-vectors-not-quality-evidence/,
      ),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Ask workspace", exact: true })
      .click();
    await page.getByLabel("Project question").fill("unmatched vocabulary");
    await page.getByLabel("Evidence retrieval").selectOption("trained");
    await page.getByRole("button", { name: "Ask with evidence" }).click();
    await expect(page.getByRole("blockquote")).toContainText(
      "durable session records",
    );
    await page.getByRole("button", { name: "Members", exact: true }).click();
    await page
      .getByText("Retention and workspace closure · owner only", {
        exact: true,
      })
      .click();
    await page.getByLabel("Retention scope").selectOption("document");
    await page
      .getByLabel("Retention target")
      .selectOption({
        label: await page
          .getByLabel("Retention target")
          .locator("option")
          .nth(1)
          .textContent(),
      });
    await page
      .getByRole("button", { name: "Preview erasure", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Review exact erasure scope" }),
    ).toBeVisible();
    await page.screenshot({
      path: `../docs/screenshots/phase101112-retention-${width}.png`,
      fullPage: true,
    });
    await page
      .getByLabel("Type ERASE REVIEWED CONTENT")
      .fill("ERASE REVIEWED CONTENT");
    await page
      .getByRole("button", { name: "Erase reviewed content", exact: true })
      .click();
    await expect(page.getByText(/Content erasure completed/)).toBeVisible();
    await page
      .getByRole("button", { name: "Ask workspace", exact: true })
      .click();
    await expect(page.getByRole("blockquote")).toHaveCount(0);
    await page.getByRole("button", { name: "Log out", exact: true }).click();
    await page.getByText("Recover your account", { exact: true }).click();
    await page.getByLabel("Recovery email").fill(email);
    await page
      .getByRole("button", { name: "Request recovery instructions" })
      .click();
    await page
      .getByLabel("Recovery token")
      .fill(await deliveredToken(email, "reset"));
    await page
      .getByLabel("New password", { exact: true })
      .fill("replacement-browser-password");
    await page.getByRole("button", { name: "Complete password reset" }).click();
    await expect(page.getByRole("status")).toContainText("Password updated");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("replacement-browser-password");
    await page.getByRole("button", { name: "Sign In", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Personal workspace", exact: true }),
    ).toBeVisible();
    await context.close();
  });
}
