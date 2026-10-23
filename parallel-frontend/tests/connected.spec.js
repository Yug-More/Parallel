import { Buffer } from "node:buffer";
import { test, expect } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`connected workspace at ${width}px: documents, answers, delegated plan, native receipt and revocation`, async ({
    browser,
  }, testInfo) => {
    test.setTimeout(150000);
    const context = await browser.newContext({
      viewport: { width, height: width === 390 ? 844 : 1000 },
    });
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("button", { name: "Enter Dashboard" }).click();
    await page.getByRole("button", { name: "Create an account" }).click();
    await page.getByLabel("Full name").fill("Morgan");
    await page
      .getByLabel("Email", { exact: true })
      .fill(`connected-${width}@example.test`);
    await page
      .getByLabel("Password", { exact: true })
      .fill("browser-test-password");
    await page.getByRole("button", { name: "Sign Up", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Personal workspace", exact: true }),
    ).toBeVisible();
    const wid = await page
      .getByLabel("Workspace", { exact: true })
      .inputValue();
    async function section(name) {
      await page.getByRole("button", { name, exact: true }).click();
    }
    await section("Documents");
    await page.getByLabel("Document title").fill("Release context");
    await page
      .getByLabel("Text or Markdown file")
      .setInputFiles({
        name: "release.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(
          "Revocable sessions must reject copied tokens after logout. Review the session database before release.",
        ),
      });
    await page
      .getByRole("button", { name: "Upload document", exact: true })
      .click();
    const doc = page
      .getByRole("article")
      .filter({
        has: page.getByRole("heading", {
          name: "Release context",
          exact: true,
        }),
      });
    await expect(doc).toContainText("ready", { timeout: 15000 });
    await page.reload();
    await expect(doc).toContainText("ready");
    await page
      .getByRole("region", { name: "Documents", exact: true })
      .screenshot({ path: testInfo.outputPath(`documents-${width}.png`) });
    await section("Ask workspace");
    await page.getByLabel("Project question").fill("revocable sessions");
    await page.getByRole("button", { name: "Ask with evidence" }).click();
    await expect(page.getByRole("blockquote")).toContainText("copied tokens");
    await page
      .getByRole("button", { name: /document · Release context/ })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Project source" }),
    ).toContainText("release.md");
    await page.getByRole("button", { name: "Close source" }).click();
    await page
      .getByRole("region", { name: "Grounded answers" })
      .screenshot({ path: testInfo.outputPath(`answers-${width}.png`) });
    await section("Connections");
    await page.getByLabel("GitHub repository").fill("parallel-example/demo");
    await page
      .getByRole("button", { name: "Connect public repository" })
      .click();
    await expect(
      page.getByRole("region", { name: "Connections" }),
    ).toContainText("completed", { timeout: 15000 });
    await page
      .getByRole("region", { name: "Connections" })
      .screenshot({ path: testInfo.outputPath(`connections-${width}.png`) });
    await section("Agents & approvals");
    await page.getByLabel("Agent capability").selectOption("local.delivery.v1");
    await page
      .getByLabel("Run objective")
      .fill("Review revocable sessions; Verify copied-token logout");
    await page.getByRole("button", { name: "Queue run", exact: true }).click();
    await expect(
      page
        .getByRole("article", { name: "Run details" })
        .locator(".status-badge"),
    ).toHaveText("completed", { timeout: 20000 });
    await expect(
      page.getByRole("button", { name: /local.plan.v1 · completed/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /local.research.v1 · completed/ }),
    ).toBeVisible();
    const proposals = page.getByRole("region", {
      name: "Native action proposals",
    });
    await expect(proposals).toContainText("Review revocable sessions");
    await proposals.getByRole("button", { name: "Approve task plan" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(
      proposals.getByRole("heading", { name: "Execution receipt" }),
    ).toBeVisible({ timeout: 15000 });
    await expect(proposals).toContainText("2 tasks created");
    await proposals.screenshot({
      path: testInfo.outputPath(`native-actions-${width}.png`),
    });
    await section("Tasks");
    await expect(
      page.getByRole("button", { name: /Review revocable sessions/ }),
    ).toBeVisible();
    const tasks = await context.request.get(
      `http://127.0.0.1:18001/workspaces/${wid}/tasks`,
    );
    const taskData = await tasks.json();
    expect(taskData.items).toHaveLength(2);
    expect(
      taskData.items.every(
        (task) => task.status === "todo" && task.assignee_id === null,
      ),
    ).toBe(true);
    await section("Overview");
    await expect(
      page.getByRole("region", { name: "Project overview" }),
    ).toContainText("2 active");
    await expect(
      page.getByRole("region", { name: "Project overview" }),
    ).toContainText("Worker recently polling");
    await page
      .getByRole("region", { name: "Project overview" })
      .screenshot({ path: testInfo.outputPath(`overview-${width}.png`) });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await section("Connections");
    await page.getByRole("button", { name: "Revoke connection" }).click();
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Connections" }),
    ).toContainText("Revoked; imported sources unavailable");
    const external = await context.request.get(
      `http://127.0.0.1:18001/workspaces/${wid}/knowledge?kind=external`,
    );
    expect((await external.json()).total).toBe(0);
    await section("Documents");
    await page.getByRole("button", { name: "Archive document" }).click();
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(doc).toContainText("Archived");
    await section("Ask workspace");
    await expect(
      page.getByRole("region", { name: "Grounded answers" }),
    ).toContainText("saved answer is hidden");
    await expect(page.getByRole("blockquote")).toHaveCount(0);
    await context.close();
  });
}
