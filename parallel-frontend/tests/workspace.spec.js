import { test, expect } from "@playwright/test";

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name}: invitations, tasks, messages, removal, transfer and session revocation`, async ({
    browser,
  }) => {
    test.setTimeout(120000);
    const contexts = await Promise.all(
      [0, 1, 2].map(() =>
        browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
        }),
      ),
    );
    const [alice, bob, outsider] = contexts;
    const email = (name) => `${name}-${viewport.name}@example.test`;
    async function register(context, name) {
      const page = await context.newPage();
      await page.goto("/");
      await page.getByRole("button", { name: "Enter Dashboard" }).click();
      await page.getByRole("button", { name: "Create an account" }).click();
      await page.getByLabel("Full name").fill(name);
      await page.getByLabel("Email", { exact: true }).fill(email(name));
      await page
        .getByLabel("Password", { exact: true })
        .fill("browser-test-password");
      await page.getByRole("button", { name: "Sign Up", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "Personal workspace", exact: true }),
      ).toBeVisible();
      return page;
    }
    const owner = await register(alice, "Alice");
    const member = await register(bob, "Bob");
    const stranger = await register(outsider, "Other");
    const workspaceName = `Collaboration ${viewport.name}`;
    await owner.getByLabel("New workspace").fill(workspaceName);
    await owner
      .getByRole("button", { name: "Create workspace", exact: true })
      .click();
    await expect(
      owner.getByRole("heading", { name: workspaceName }),
    ).toBeVisible();
    const wid = await owner
      .getByLabel("Workspace", { exact: true })
      .inputValue();
    async function inviteBob() {
      await owner.getByRole("button", { name: "Members", exact: true }).click();
      await owner
        .getByLabel("Invite registered user by email")
        .fill(email("Bob"));
      await owner.getByRole("button", { name: "Invite collaborator" }).click();
      await expect(owner.getByRole("status")).toContainText(
        "In-app invitation created",
      );
      await member.getByRole("button", { name: /^Invitations \(/ }).click();
      await expect(
        member.getByRole("heading", { name: workspaceName }),
      ).toBeVisible();
      await member.getByRole("button", { name: "Accept invitation" }).click();
      await expect(
        member.getByRole("heading", { name: workspaceName }),
      ).toBeVisible();
      await expect(
        member.getByRole("button", { name: "Conversation", exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
    }
    await inviteBob();
    await owner.getByRole("button", { name: "Tasks", exact: true }).click();
    await owner.getByRole("button", { name: "New task", exact: true }).click();
    const title = `Prepare release ${viewport.name}`;
    await owner.getByLabel("Task title").fill(title);
    await owner
      .getByLabel("Description", { exact: true })
      .fill("Persistent collaboration details");
    await owner
      .getByLabel("Assignee", { exact: true })
      .selectOption({ label: "Bob" });
    await owner.getByLabel("Priority", { exact: true }).selectOption("high");
    await owner.getByLabel("Due date").fill("2026-12-01");
    await owner.getByRole("button", { name: "Save task" }).click();
    await expect(owner.getByRole("status")).toHaveText("Task saved.");
    await member.getByRole("button", { name: "Tasks", exact: true }).click();
    await member.getByRole("button", { name: new RegExp(title) }).click();
    await expect(member.getByLabel("Assignee", { exact: true })).toHaveValue(
      await owner.getByLabel("Assignee", { exact: true }).inputValue(),
    );
    await member.getByLabel("Task status").selectOption("in_progress");
    await member.getByRole("button", { name: "Save task" }).click();
    await expect(member.getByRole("status")).toHaveText("Task saved.");
    await expect(
      owner.getByRole("button", { name: new RegExp(`${title}.*In Progress`) }),
    ).toBeVisible();
    await owner.getByRole("button", { name: "Reload task" }).click();
    await expect(owner.getByLabel("Task status")).toHaveValue("in_progress");
    await owner
      .getByLabel("Description", { exact: true })
      .fill("Edited, persisted project details");
    await owner.getByRole("button", { name: "Save task" }).click();
    await expect(owner.getByRole("status")).toHaveText("Task saved.");
    expect(
      await owner.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await owner.screenshot({
      path: test.info().outputPath(`tasks-${viewport.name}.png`),
      fullPage: true,
    });
    for (const [page, content] of [
      [owner, "Alice shared message"],
      [member, "Bob shared message"],
    ]) {
      await page
        .getByRole("button", { name: "Conversation", exact: true })
        .click();
      await page.getByLabel("Message", { exact: true }).fill(content);
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(page.getByText(content, { exact: true })).toBeVisible();
    }
    await expect(
      owner.getByText("Bob shared message", { exact: true }),
    ).toBeVisible();
    await expect(
      member.getByText("Alice shared message", { exact: true }),
    ).toBeVisible();
    await owner.reload();
    await member.reload();
    for (const page of [owner, member]) {
      await page
        .getByLabel("Workspace", { exact: true })
        .selectOption({ label: workspaceName });
      await expect(
        page.getByText("Alice shared message", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("Bob shared message", { exact: true }),
      ).toBeVisible();
    }
    await expect(
      stranger.getByRole("option", { name: workspaceName }),
    ).toHaveCount(0);
    expect(
      (
        await stranger.request.get(
          `http://127.0.0.1:18001/workspaces/${wid}/tasks`,
        )
      ).status(),
    ).toBe(404);
    await member.getByRole("button", { name: "Tasks", exact: true }).click();
    await member.getByRole("button", { name: new RegExp(title) }).click();
    await expect(member.getByLabel("Description", { exact: true })).toHaveValue(
      "Edited, persisted project details",
    );
    await owner.getByRole("button", { name: "Members", exact: true }).click();
    await owner.getByRole("button", { name: "Remove", exact: true }).click();
    await owner
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(
      member.getByRole("option", { name: workspaceName }),
    ).toHaveCount(0);
    await expect(member.getByText(title, { exact: true })).toHaveCount(0);
    expect(
      (
        await member.request.get(
          `http://127.0.0.1:18001/workspaces/${wid}/messages`,
        )
      ).status(),
    ).toBe(404);
    await owner.getByRole("button", { name: "Tasks", exact: true }).click();
    await owner.getByRole("button", { name: new RegExp(title) }).click();
    await expect(owner.getByLabel("Assignee", { exact: true })).toHaveValue("");
    await inviteBob();
    await owner
      .getByRole("button", { name: "Make owner", exact: true })
      .click();
    await owner
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(
      owner.getByRole("button", { name: "Leave workspace" }),
    ).toBeVisible();
    await expect(
      owner.getByRole("button", { name: "Invite collaborator" }),
    ).toHaveCount(0);
    await member.getByRole("button", { name: "Members", exact: true }).click();
    await expect(
      member.getByRole("button", { name: "Invite collaborator" }),
    ).toBeVisible();
    await owner.getByRole("button", { name: "Leave workspace" }).click();
    await owner
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(
      owner.getByRole("option", { name: workspaceName }),
    ).toHaveCount(0);
    const copied = await browser.newContext({
      storageState: await bob.storageState(),
      viewport: { width: viewport.width, height: viewport.height },
    });
    const copiedPage = await copied.newPage();
    await copiedPage.goto("/");
    await expect(
      copiedPage.getByLabel("Workspace", { exact: true }),
    ).toBeVisible();
    await member
      .getByRole("button", { name: "Log out all sessions", exact: true })
      .click();
    await member
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(
      member.getByRole("button", { name: "Sign In", exact: true }),
    ).toBeVisible();
    await expect(
      copiedPage.getByRole("button", { name: "Sign In", exact: true }),
    ).toBeVisible();
    await Promise.all([...contexts, copied].map((context) => context.close()));
  });
}

test("invitation decline/revoke and task archival confirmations use real persisted outcomes", async ({
  browser,
}) => {
  test.setTimeout(60000);
  const ownerContext = await browser.newContext();
  const guestContext = await browser.newContext();
  for (const [context, name] of [
    [ownerContext, "Owner Lifecycle"],
    [guestContext, "Guest Lifecycle"],
  ]) {
    const response = await context.request.post(
      "http://127.0.0.1:18001/auth/register",
      {
        data: {
          name,
          email: `${name.replace(" ", "-")}@example.test`,
          password: "browser-test-password",
        },
      },
    );
    expect(response.status()).toBe(201);
  }
  const owner = await ownerContext.newPage();
  const guest = await guestContext.newPage();
  await owner.goto("/");
  await guest.goto("/");
  await owner.getByRole("button", { name: "Members", exact: true }).click();
  async function sendInvitation() {
    await owner
      .getByLabel("Invite registered user by email")
      .fill("Guest-Lifecycle@example.test");
    await owner.getByRole("button", { name: "Invite collaborator" }).click();
    await expect(owner.getByRole("status")).toContainText(
      "In-app invitation created",
    );
    await guest.getByRole("button", { name: /^Invitations \(/ }).click();
    await expect(
      guest.getByRole("button", { name: "Accept invitation" }),
    ).toBeVisible();
  }
  await sendInvitation();
  await guest.getByRole("button", { name: "Decline", exact: true }).click();
  await expect(
    guest.getByRole("button", { name: "Accept invitation" }),
  ).toHaveCount(0);
  await expect(owner.getByText(/^declined · Expires/)).toBeVisible();
  await sendInvitation();
  await owner.getByRole("button", { name: "Revoke", exact: true }).click();
  await owner
    .getByRole("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    guest.getByRole("button", { name: "Accept invitation" }),
  ).toHaveCount(0);
  await owner.getByRole("button", { name: "Tasks", exact: true }).click();
  await owner.getByRole("button", { name: "New task", exact: true }).click();
  await owner.getByLabel("Task title").fill("Archive example");
  await owner.getByRole("button", { name: "Save task" }).click();
  await expect(owner.getByRole("status")).toHaveText("Task saved.");
  await owner
    .getByRole("button", { name: "Archive task", exact: true })
    .click();
  await owner
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(owner.getByLabel("Task title")).toBeEnabled();
  await owner
    .getByRole("button", { name: "Archive task", exact: true })
    .click();
  await owner
    .getByRole("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    owner.getByRole("button", { name: /^Archive example/ }),
  ).toHaveCount(0);
  await owner.getByLabel("Show archived").check();
  await owner.getByRole("button", { name: /^Archive example/ }).click();
  await expect(owner.getByLabel("Task title")).toBeDisabled();
  await owner.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(
    owner.getByText("Archived task: Archive example", { exact: true }),
  ).toBeVisible();
  await ownerContext.close();
  await guestContext.close();
});
