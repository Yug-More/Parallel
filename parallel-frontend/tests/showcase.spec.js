import { test, expect } from "@playwright/test";
import { Buffer } from "node:buffer";
import process from "node:process";
import { fileURLToPath } from "node:url";

// Real synthetic workflows. Only an explicit capture run updates curated docs;
// ordinary CI keeps screenshots in its isolated result directory.
test("populated synthetic product walkthrough and reproducible screenshots", async ({
  browser,
}, testInfo) => {
  test.setTimeout(90000);
  const owner = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const member = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const base = "http://127.0.0.1:18001";
  for (const [context, name] of [
    [owner, "Casey"],
    [member, "Riley"],
  ])
    expect(
      (
        await context.request.post(`${base}/auth/register`, {
          data: {
            name,
            email: `showcase-${name}@example.test`,
            password: "synthetic-browser-password",
          },
        })
      ).status(),
    ).toBe(201);
  const page = await owner.newPage();
  const colleague = await member.newPage();
  await page.goto("/");
  await colleague.goto("/");
  const save = async (name) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    const path =
      process.env.PARALLEL_CAPTURE_PRODUCT === "true"
        ? fileURLToPath(
            new URL(
              `../../docs/screenshots/product/${name}.png`,
              import.meta.url,
            ),
          )
        : testInfo.outputPath(`${name}.png`);
    await page.screenshot({
      path,
      fullPage: name.endsWith("-mobile"),
      animations: "disabled",
    });
  };
  const section = async (name) => {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("main h2").first()).toBeVisible();
  };
  await page.getByLabel("New workspace").fill("Release workspace · Demo");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Release workspace · Demo",
      exact: true,
    }),
  ).toBeVisible();
  const wid = await page.getByLabel("Workspace", { exact: true }).inputValue();
  await section("Members");
  await page
    .getByLabel("Invite registered user by email")
    .fill("showcase-Riley@example.test");
  await page.getByRole("button", { name: "Invite collaborator" }).click();
  await colleague.getByRole("button", { name: /^Invitations \(/ }).click();
  await colleague.getByRole("button", { name: "Accept invitation" }).click();
  await expect(
    page.getByText("owner · 2 members", { exact: true }),
  ).toBeVisible();
  await section("Conversation");
  await page
    .getByLabel("Message", { exact: true })
    .fill(
      "## Release checkpoint\n\nKeep the **rollback checklist** and its evidence together. Owners review the exact task plan before it changes project work.\n\n```text\nReview → Approve → Verify receipt\n```",
    );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".chat-bubble pre")).toBeVisible();
  await colleague
    .getByLabel("Message", { exact: true })
    .fill(
      "I’ll review the rollback evidence. A completed report does not mean the release tasks are done.",
    );
  await colleague.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByText(
      "I’ll review the rollback evidence. A completed report does not mean the release tasks are done.",
      { exact: true },
    ),
  ).toBeVisible();
  await save("conversation");
  const messages = await (
    await owner.request.get(`${base}/workspaces/${wid}/messages`)
  ).json();
  expect(
    (
      await owner.request.post(`${base}/workspaces/${wid}/decisions`, {
        data: {
          title: "Require explicit owner review",
          context: "Release actions need an accountable review boundary.",
          statement:
            "Approve the exact task plan and inspect the execution receipt.",
          rationale: "A proposal is separate from committed project state.",
          status: "accepted",
          sources: [{ kind: "message", id: messages[0].id }],
        },
      })
    ).status(),
  ).toBe(201);
  await section("Tasks");
  await page.getByRole("button", { name: "New task", exact: true }).click();
  await page.getByLabel("Task title").fill("Review rollback checklist");
  await page
    .getByLabel("Description", { exact: true })
    .fill("Verify the evidence and document any release blockers.");
  await page
    .getByLabel("Assignee", { exact: true })
    .selectOption({ label: "Riley" });
  await page.getByRole("button", { name: "Save task" }).click();
  await expect(page.getByRole("status")).toHaveText("Task saved.");
  await section("Documents");
  await page.getByLabel("Document title").fill("Release review notes");
  await page.getByLabel("Text, Markdown or PDF file").setInputFiles({
    name: "release-review.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "Release rollback checklist: verify session revocation, preserve source-linked decisions, and inspect the native task receipt before continuing.\n\nOwner review is required for the exact task plan. Created tasks remain To do until a person completes the work.",
    ),
  });
  await page
    .getByRole("button", { name: "Upload document", exact: true })
    .click();
  await expect(
    page.getByRole("article").filter({
      has: page.getByRole("heading", {
        name: "Release review notes",
        exact: true,
      }),
    }),
  ).toContainText("ready");
  await section("Ask workspace");
  await page.getByLabel("Project question").fill("release rollback checklist");
  await page.getByRole("button", { name: "Ask with evidence" }).click();
  await expect(page.getByRole("blockquote").first()).toBeVisible();
  await save("answers");
  const documentSource = page
    .getByRole("button", { name: /document · Release review notes/ })
    .first();
  await documentSource.click();
  await expect(
    page.getByRole("dialog", { name: "Project source" }),
  ).toContainText("Release rollback checklist");
  await save("evidence");
  await page.getByRole("button", { name: "Close source", exact: true }).click();
  await section("Members");
  await expect(
    page.locator(".member-list").getByText("Riley", { exact: true }),
  ).toBeVisible();
  await save("shared");
  await section("Intelligence");
  await page
    .getByText("What this workspace remembers", { exact: true })
    .click();
  await expect(
    page.getByText(/Search uses this workspace’s messages/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Current task state", exact: true }),
  ).toBeVisible();
  await save("memory");
  await section("Agents & approvals");
  await page.getByLabel("Agent capability").selectOption("local.delivery.v1");
  await page
    .getByLabel("Run objective")
    .fill("Review release evidence; Validate rollback checklist");
  await page.getByRole("button", { name: "Queue run", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Run details" }).locator(".status-badge"),
  ).toHaveText("completed", { timeout: 20000 });
  await save("agents");
  const proposals = page.getByRole("region", {
    name: "Native action proposals",
  });
  await expect(
    proposals.getByRole("button", { name: "Approve task plan" }),
  ).toBeVisible();
  await proposals.getByRole("button", { name: "Approve task plan" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "exactly the displayed tasks",
  );
  await save("approval");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    proposals.getByRole("heading", { name: "Execution receipt" }),
  ).toBeVisible({ timeout: 15000 });
  await section("Overview");
  await expect(
    page.getByRole("region", { name: "Project overview" }),
  ).toContainText("3 active");
  await save("workspace");
  await page.setViewportSize({ width: 390, height: 844 });
  await section("Conversation");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await save("conversation-mobile");
  await owner.close();
  await member.close();
});
