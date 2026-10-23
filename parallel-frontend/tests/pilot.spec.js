import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { writeFile } from "node:fs/promises";

for (const width of [1440, 390]) {
  test(`pilot persisted PDF and private GitHub workflow at ${width}px`, async ({
    browser,
  }, testInfo) => {
    test.setTimeout(150000);
    const context = await browser.newContext({
      viewport: { width, height: width === 390 ? 844 : 1000 },
    });
    const page = await context.newPage();
    const started = Date.now();
    let authenticated = false;
    const metrics = {
      viewport: width,
      humanParticipants: 0,
      interactions: 0,
      sectionChanges: 0,
      refreshChecks: 0,
      navigationErrors: 0,
      tasksCompleted: [],
      unexpectedResponses: [],
      expectedAnonymousChecks: 0,
    };
    page.on("response", (response) => {
      if (
        response.url().startsWith("http://127.0.0.1:18001") &&
        response.status() >= 400
      )
        if (
          !authenticated &&
          response.status() === 401 &&
          new URL(response.url()).pathname === "/me"
        )
          metrics.expectedAnonymousChecks++;
        else metrics.unexpectedResponses.push(response.status());
    });
    const click = async (locator) => {
      metrics.interactions++;
      await locator.click();
    };
    const fill = async (locator, value) => {
      metrics.interactions++;
      await locator.fill(value);
    };
    const section = async (name) => {
      metrics.sectionChanges++;
      const target = page.getByRole("button", { name, exact: true });
      try {
        await click(target);
        await expect(target).toHaveAttribute("aria-pressed", "true");
      } catch (error) {
        metrics.navigationErrors++;
        throw error;
      }
    };
    await page.goto("/");
    await click(page.getByRole("button", { name: "Enter Dashboard" }));
    await click(page.getByRole("button", { name: "Create an account" }));
    await fill(page.getByLabel("Full name"), "Pilot reviewer");
    await fill(
      page.getByLabel("Email", { exact: true }),
      `pilot-${width}@example.test`,
    );
    await fill(
      page.getByLabel("Password", { exact: true }),
      "browser-test-password",
    );
    await click(page.getByRole("button", { name: "Sign Up", exact: true }));
    await expect(
      page.getByRole("heading", { name: "Personal workspace", exact: true }),
    ).toBeVisible();
    authenticated = true;
    await section("Overview");
    await click(
      page.getByText("First project: setup and return checklist", {
        exact: true,
      }),
    );
    await expect(page.getByText(/Tasks stay unfinished/)).toBeVisible();
    await section("Documents");
    await fill(page.getByLabel("Document title"), "Pilot notes PDF");
    metrics.interactions++;
    await page
      .getByLabel("Text, Markdown or PDF file")
      .setInputFiles(
        fileURLToPath(new URL("./fixtures/pilot-notes.pdf", import.meta.url)),
      );
    await click(
      page.getByRole("button", { name: "Upload document", exact: true }),
    );
    const document = page.getByRole("article").filter({
      has: page.getByRole("heading", {
        name: "Pilot notes PDF",
        exact: true,
      }),
    });
    await expect(document).toContainText("ready", { timeout: 15000 });
    await page.reload();
    metrics.refreshChecks++;
    await expect(document).toContainText("ready");
    await click(
      page.getByRole("button", { name: "Build local passage index" }),
    );
    await expect(
      page.getByRole("article").filter({
        has: page.getByRole("heading", { name: "Optional passage index" }),
      }),
    ).toContainText("ready", { timeout: 10000 });
    await page
      .getByRole("region", { name: "Documents", exact: true })
      .screenshot({
        path: testInfo.outputPath(`pilot-documents-${width}.png`),
      });
    await section("Ask workspace");
    await fill(page.getByLabel("Project question"), "backup verification");
    await click(page.getByRole("button", { name: "Ask with evidence" }));
    await expect(page.getByRole("blockquote")).toContainText("Pilot rollback");
    await click(
      page.getByRole("button", { name: /document · Pilot notes PDF/ }),
    );
    await expect(
      page.getByRole("dialog", { name: "Project source" }),
    ).toContainText("page 1");
    await page
      .getByRole("dialog", { name: "Project source" })
      .screenshot({ path: testInfo.outputPath(`pilot-citation-${width}.png`) });
    await page.keyboard.press("Escape");
    metrics.interactions++;
    await expect(
      page.getByRole("dialog", { name: "Project source" }),
    ).not.toBeVisible();
    await expect(
      page.getByRole("button", { name: /document · Pilot notes PDF/ }),
    ).toBeFocused();
    metrics.tasksCompleted.push(
      "PDF upload, durable extraction, indexed passage and page citation",
    );
    await section("Connections");
    await fill(
      page.getByLabel("Selected private repository"),
      "parallel-example/private",
    );
    await fill(page.getByLabel("GitHub installation ID"), "42");
    await click(
      page.getByRole("button", { name: "Start GitHub authorization" }),
    );
    await expect(page.getByText("TEST-CODE", { exact: true })).toBeVisible();
    await page.reload();
    metrics.refreshChecks++;
    await expect(page.getByText("TEST-CODE", { exact: true })).toBeVisible();
    // This is a test-only GitHub transport; it proves the real persisted flow,
    // not live GitHub approval or a real private repository grant.
    await page.waitForTimeout(5500);
    await click(
      page.getByRole("button", { name: "Check GitHub authorization" }),
    );
    await expect(
      page
        .getByRole("article")
        .filter({
          has: page.getByRole("heading", {
            name: "parallel-example/private",
            exact: true,
          }),
        }),
    ).toContainText("completed · attempt 1/3", { timeout: 15000 });
    await expect(
      page.getByRole("region", { name: "Connections" }),
    ).toContainText("Read-only selected GitHub App connection");
    await page
      .getByRole("region", { name: "Connections" })
      .screenshot({ path: testInfo.outputPath(`pilot-private-${width}.png`) });
    metrics.tasksCompleted.push(
      "Private authorization, refresh persistence and imported evidence via fixture transport",
    );
    await section("Agents & approvals");
    metrics.interactions++;
    await page.getByLabel("Agent capability").selectOption("local.delivery.v1");
    await fill(
      page.getByLabel("Run objective", { exact: true }),
      "triage github issues",
    );
    await click(page.getByRole("button", { name: "Queue run", exact: true }));
    const proposals = page.getByRole("region", {
      name: "Native action proposals",
    });
    await expect(proposals).toContainText(
      "Review issue: Pilot rollback verification",
      { timeout: 20000 },
    );
    await click(proposals.getByRole("button", { name: "Approve task plan" }));
    const confirm = page.getByRole("dialog");
    await expect(
      confirm.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    await click(confirm.getByRole("button", { name: "Confirm", exact: true }));
    await expect(
      proposals.getByRole("heading", { name: "Execution receipt" }),
    ).toBeVisible({ timeout: 15000 });
    await proposals.screenshot({
      path: testInfo.outputPath(`pilot-triage-${width}.png`),
    });
    await section("Tasks");
    await expect(
      page.getByRole("button", {
        name: /Review issue: Pilot rollback verification/,
      }),
    ).toBeVisible();
    await page.reload();
    metrics.refreshChecks++;
    await expect(
      page.getByRole("button", {
        name: /Review issue: Pilot rollback verification/,
      }),
    ).toBeVisible();
    metrics.tasksCompleted.push(
      "Delegated issue triage, exact owner approval and persisted unfinished native task",
    );
    await section("Overview");
    await expect(
      page.getByRole("region", { name: "Project overview" }),
    ).toContainText("1 active");
    await page
      .getByRole("region", { name: "Project overview" })
      .screenshot({ path: testInfo.outputPath(`pilot-overview-${width}.png`) });
    metrics.horizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(metrics.horizontalOverflow).toBe(false);
    expect(metrics.unexpectedResponses).toEqual([]);
    metrics.durationMs = Date.now() - started;
    await writeFile(
      testInfo.outputPath(`pilot-metrics-${width}.json`),
      JSON.stringify(metrics, null, 2),
    );
    await testInfo.attach("automated-usability-metrics", {
      body: JSON.stringify(metrics, null, 2),
      contentType: "application/json",
    });
    await context.close();
  });
}
