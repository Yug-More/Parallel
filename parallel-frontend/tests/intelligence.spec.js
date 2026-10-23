import { test, expect } from "@playwright/test";

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name}: source-grounded decisions, continuity, delegated runs and exact approval`, async ({
    browser,
  }, testInfo) => {
    test.setTimeout(150000);
    const contexts = await Promise.all(
      [0, 1, 2].map(() =>
        browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
        }),
      ),
    );
    const [lead, colleague, stranger] = contexts;
    async function register(context, name) {
      const page = await context.newPage();
      await page.goto("/");
      await page.getByRole("button", { name: "Enter Dashboard" }).click();
      await page.getByRole("button", { name: "Create an account" }).click();
      await page.getByLabel("Full name").fill(name);
      await page
        .getByLabel("Email", { exact: true })
        .fill(`${name}-${viewport.name}-intelligence@example.test`);
      await page
        .getByLabel("Password", { exact: true })
        .fill("browser-test-password");
      await page.getByRole("button", { name: "Sign Up", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "Personal workspace", exact: true }),
      ).toBeVisible();
      return page;
    }
    const owner = await register(lead, "Jordan");
    const member = await register(colleague, "Maya");
    const outsider = await register(stranger, "Visitor");
    await owner.getByLabel("New workspace").fill("Release engineering");
    await owner
      .getByRole("button", { name: "Create workspace", exact: true })
      .click();
    await expect(
      owner.getByRole("heading", { name: "Release engineering", exact: true }),
    ).toBeVisible();
    const wid = await owner
      .getByLabel("Workspace", { exact: true })
      .inputValue();
    await owner.getByRole("button", { name: "Members", exact: true }).click();
    await owner
      .getByLabel("Invite registered user by email")
      .fill(`Maya-${viewport.name}-intelligence@example.test`);
    await owner.getByRole("button", { name: "Invite collaborator" }).click();
    await member.getByRole("button", { name: /^Invitations \(/ }).click();
    await member.getByRole("button", { name: "Accept invitation" }).click();
    await expect(
      member.getByRole("heading", { name: "Release engineering", exact: true }),
    ).toBeVisible();
    await owner
      .getByRole("button", { name: "Conversation", exact: true })
      .click();
    await owner
      .getByLabel("Message", { exact: true })
      .fill(
        "A copied login token must stop working after logout. Let us record the revocation decision.",
      );
    await owner.getByRole("button", { name: "Send", exact: true }).click();
    await owner.getByRole("button", { name: "Tasks", exact: true }).click();
    await owner.getByRole("button", { name: "New task", exact: true }).click();
    await owner.getByLabel("Task title").fill("Review session revocation");
    await owner
      .getByLabel("Description", { exact: true })
      .fill(
        "Verify copied-token logout and account-wide revocation before release.",
      );
    await owner
      .getByLabel("Assignee", { exact: true })
      .selectOption({ label: "Maya" });
    await owner.getByRole("button", { name: "Save task" }).click();
    await expect(owner.getByRole("status")).toHaveText("Task saved.");
    await owner.evaluate(() => window.scrollTo(0, 0));
    await owner.screenshot({
      path: testInfo.outputPath(`tasks-${viewport.name}.png`),
      fullPage: false,
    });
    await owner.getByRole("button", { name: "Decisions", exact: true }).click();
    async function record(title, statement, rationale, sourceType) {
      await owner
        .getByRole("button", { name: "New decision", exact: true })
        .click();
      await owner.getByLabel("Decision title").fill(title);
      await owner
        .getByLabel("Problem / context")
        .fill("Maintain secure access as teammates return to the project.");
      await owner.getByLabel("Decision statement").fill(statement);
      await owner.getByLabel("Rationale", { exact: true }).fill(rationale);
      await owner
        .getByLabel("Alternatives considered")
        .fill(
          "Short-lived stateless tokens; a database-backed revocation record.",
        );
      await owner
        .getByLabel("Tradeoffs", { exact: true })
        .fill(
          "A database lookup per authenticated request provides explicit revocation.",
        );
      await owner
        .getByLabel("Decision state", { exact: true })
        .selectOption("accepted");
      await owner
        .getByLabel("Source type", { exact: true })
        .selectOption(sourceType);
      if (sourceType === "message") {
        await owner
          .getByRole("button", {
            name: "Link source: Message from Jordan",
            exact: true,
          })
          .click();
      } else {
        await owner.getByLabel("Find source").fill("Review session revocation");
        await owner
          .getByRole("button", {
            name: "Link source: Review session revocation",
            exact: true,
          })
          .click();
      }
      await owner
        .getByRole("button", { name: "Save decision", exact: true })
        .click();
      await expect(
        owner.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
    }
    await record(
      "Authentication v1",
      "Use stateless signed login tokens.",
      "Initial implementation favored a small authentication surface.",
      "message",
    );
    await record(
      "Authentication v2",
      "Require a live revocable database session for every authenticated request.",
      "Copied tokens must lose access immediately after logout.",
      "task",
    );
    await owner
      .getByRole("button", { name: "Revise decision", exact: true })
      .click();
    await owner
      .getByLabel("Rationale", { exact: true })
      .fill(
        "Copied tokens must lose access after both single-session logout and logout-all.",
      );
    await owner
      .getByLabel("Revision reason")
      .fill("Clarify account-wide revocation after reviewing the task.");
    await owner
      .getByRole("button", { name: "Save decision", exact: true })
      .click();
    await expect(
      owner.getByRole("heading", { name: "Authentication v2", exact: true }),
    ).toBeVisible();
    await expect(
      owner.getByText(
        "Copied tokens must lose access after both single-session logout and logout-all.",
        { exact: true },
      ),
    ).toBeVisible();
    await owner.getByRole("button", { name: /^Authentication v1/ }).click();
    await owner
      .getByLabel("Replacement decision", { exact: true })
      .selectOption({ label: "Authentication v2" });
    await owner
      .getByLabel("Supersession reason")
      .fill("Replace the initial design after reviewing copied-token access.");
    await owner
      .getByRole("button", { name: "Supersede decision", exact: true })
      .click();
    await owner.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(
      owner.getByRole("button", { name: "Open replacement decision" }),
    ).toBeVisible();
    await owner.getByText(/Version 1 · accepted/).click();
    await expect(
      owner
        .getByText("Use stateless signed login tokens.", { exact: false })
        .first(),
    ).toBeVisible();
    await owner.evaluate(() => window.scrollTo(0, 0));
    await owner.screenshot({
      path: testInfo.outputPath(`decisions-${viewport.name}.png`),
      fullPage: false,
    });
    await owner
      .getByRole("button", { name: "Intelligence", exact: true })
      .click();
    await expect(
      owner.getByRole("heading", { name: "Current task state" }),
    ).toBeVisible();
    await expect(
      owner.getByText("superseded · Replace the initial design", {
        exact: false,
      }),
    ).toBeVisible();
    await owner.evaluate(() => window.scrollTo(0, 0));
    await owner.screenshot({
      path: testInfo.outputPath(`continuity-${viewport.name}.png`),
      fullPage: false,
    });
    await owner
      .getByRole("button", { name: "Search project knowledge", exact: true })
      .click();
    await owner.getByLabel("Search terms").fill("authentication");
    await owner
      .getByLabel("Record type", { exact: true })
      .selectOption("decision");
    await owner
      .getByRole("button", { name: "Search sources", exact: true })
      .click();
    await expect(
      owner
        .locator(".search-results")
        .getByRole("button", { name: /Authentication v2/ }),
    ).toBeVisible();
    await expect(
      owner
        .locator(".search-results")
        .getByRole("button", { name: /Authentication v1/ }),
    ).toHaveCount(0);
    await owner
      .locator(".search-results")
      .getByRole("button", { name: /Authentication v2/ })
      .click();
    await expect(
      owner.getByRole("dialog", { name: "Project source" }),
    ).toContainText("Require a live revocable database session");
    await owner.getByRole("button", { name: "Close source" }).click();
    await owner.getByLabel("Include superseded / rejected decisions").check();
    await owner
      .getByRole("button", { name: "Search sources", exact: true })
      .click();
    await expect(
      owner
        .locator(".search-results")
        .getByRole("button", { name: /Authentication v1/ }),
    ).toBeVisible();
    await owner.getByLabel("Search terms").fill("no-matching-evidence-xyz");
    await owner
      .getByRole("button", { name: "Search sources", exact: true })
      .click();
    await expect(
      owner.getByText(
        "No matching evidence. Try different terms or record filters.",
      ),
    ).toBeVisible();
    await member
      .getByRole("button", { name: "Agents & approvals", exact: true })
      .click();
    await member
      .getByLabel("Run objective")
      .fill("Prepare the release handoff");
    await member
      .getByLabel(
        "Request owner approval to publish the exact report to Conversation",
      )
      .check();
    await member
      .getByRole("button", { name: "Queue run", exact: true })
      .click();
    await expect(
      member
        .getByRole("article", { name: "Run details" })
        .locator(".status-badge"),
    ).toHaveText("waiting for approval", { timeout: 20000 });
    await expect(member.getByText("Owner approval required.")).toBeVisible();
    await owner
      .getByRole("button", { name: "Agents & approvals", exact: true })
      .click();
    await owner
      .getByRole("button", { name: /^Prepare the release handoff/ })
      .click();
    await expect(
      owner.getByRole("heading", { name: "Saved result", exact: true }),
    ).toBeVisible();
    await expect(
      owner.getByRole("button", { name: /local.status.v1 · completed/ }),
    ).toBeVisible();
    await expect(
      owner.getByRole("button", { name: /local.dependencies.v1 · completed/ }),
    ).toBeVisible();
    await owner.locator(".approval-section").screenshot({
      path: testInfo.outputPath(`approval-${viewport.name}.png`),
    });
    await owner
      .getByRole("button", { name: "Approve publication", exact: true })
      .click();
    await owner.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(owner.locator(".approval-item .status-badge")).toHaveText(
      "executed",
      { timeout: 15000 },
    );
    await expect(
      owner
        .getByRole("article", { name: "Run details" })
        .locator(".status-badge"),
    ).toHaveText("completed");
    await owner.evaluate(() => window.scrollTo(0, 0));
    await owner.screenshot({
      path: testInfo.outputPath(`agents-${viewport.name}.png`),
      fullPage: false,
    });
    const savedRuns = await (
      await lead.request.get(`http://127.0.0.1:18001/workspaces/${wid}/runs`)
    ).json();
    const runId = savedRuns.items[0].id;
    await owner.reload();
    await owner
      .getByRole("button", { name: "Agents & approvals", exact: true })
      .click();
    await owner
      .getByRole("button", { name: /^Prepare the release handoff/ })
      .click();
    await expect(
      owner.getByRole("heading", { name: "Saved result", exact: true }),
    ).toBeVisible();
    for (const resource of [
      "knowledge",
      "continuity",
      "decisions",
      "approvals",
      `runs/${runId}`,
    ]) {
      expect(
        (
          await stranger.request.get(
            `http://127.0.0.1:18001/workspaces/${wid}/${resource}`,
          )
        ).status(),
      ).toBe(404);
    }
    const memberId = (
      await (await colleague.request.get("http://127.0.0.1:18001/me")).json()
    ).id;
    expect(
      (
        await lead.request.delete(
          `http://127.0.0.1:18001/workspaces/${wid}/members/${memberId}`,
        )
      ).status(),
    ).toBe(200);
    await expect(
      member.getByRole("heading", { name: "Personal workspace", exact: true }),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      member.getByRole("heading", { name: "Saved result", exact: true }),
    ).toHaveCount(0);
    expect(
      (
        await colleague.request.get(
          `http://127.0.0.1:18001/workspaces/${wid}/knowledge`,
        )
      ).status(),
    ).toBe(404);
    expect(
      (
        await colleague.request.get(
          `http://127.0.0.1:18001/workspaces/${wid}/runs/${runId}`,
        )
      ).status(),
    ).toBe(404);
    expect(
      await owner.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    expect(
      await outsider.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await Promise.all(contexts.map((context) => context.close()));
  });
}
