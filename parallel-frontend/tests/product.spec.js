import { test, expect } from "@playwright/test";

const sections = [
  "Overview",
  "Conversation",
  "Tasks",
  "Decisions",
  "Intelligence",
  "Documents",
  "Connections",
  "Ask workspace",
  "Agents & approvals",
  "Members",
  "Activity",
];
const base = "http://127.0.0.1:18001";
async function account(browser, name, width = 1440) {
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    reducedMotion: "reduce",
  });
  const response = await context.request.post(`${base}/auth/register`, {
    data: {
      name,
      email: `${name}@example.test`,
      password: "synthetic-browser-password",
    },
  });
  expect(response.status()).toBe(201);
  const page = await context.newPage();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Personal workspace", exact: true }),
  ).toBeVisible();
  return {
    context,
    page,
    wid: await page.getByLabel("Workspace", { exact: true }).inputValue(),
  };
}
function contrast(a, b) {
  const luminance = (hex) => {
    const values = hex
      .match(/\w\w/g)
      .map((c) => parseInt(c, 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return values.reduce(
      (sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i],
      0,
    );
  };
  const [low, high] = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (high + 0.05) / (low + 0.05);
}

test("six widths and both themes: section access, labels, contrast, long text and keyboard dialogs", async ({
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  const { context, page } = await account(browser, "responsive-product-review");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const measurements = [];
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      if ((await page.locator("html").getAttribute("data-theme")) !== theme)
        await page
          .getByRole("button", { name: `Switch to ${theme} theme` })
          .click();
      for (const section of sections) {
        const nav = page.getByRole("button", { name: section, exact: true });
        await nav.click();
        await expect(nav).toHaveAttribute("aria-pressed", "true");
        await expect(page.locator("main")).toBeVisible();
        const sizes = await page.evaluate(() => ({
          viewport: innerWidth,
          document: document.documentElement.scrollWidth,
        }));
        expect(
          sizes.document,
          `${section} at ${width}px ${theme}`,
        ).toBeLessThanOrEqual(width);
        const unlabeled = await page
          .locator("main input, main select, main textarea")
          .evaluateAll(
            (nodes) =>
              nodes.filter(
                (node) =>
                  !node.getAttribute("aria-label") &&
                  !node.getAttribute("aria-labelledby") &&
                  !node.labels?.length,
              ).length,
          );
        expect(unlabeled).toBe(0);
        measurements.push({ width, theme, section, ...sizes });
      }
      const tokens = await page.evaluate(() => {
        const style = getComputedStyle(document.documentElement);
        return Object.fromEntries(
          [
            "text",
            "text-secondary",
            "surface",
            "bg",
            "accent",
            "control-border",
          ].map((name) => [name, style.getPropertyValue(`--${name}`).trim()]),
        );
      });
      for (const foreground of ["text", "text-secondary", "accent"])
        for (const background of ["surface", "bg"])
          expect(
            contrast(tokens[foreground], tokens[background]),
          ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(tokens["control-border"], tokens.surface),
      ).toBeGreaterThanOrEqual(3);
    }
    await page
      .getByRole("button", { name: "Conversation", exact: true })
      .click();
    const composer = page.getByRole("textbox", {
      name: "Message",
      exact: true,
    });
    await composer.fill(`Long source ${"unbroken-source-id".repeat(30)}`);
    await composer.press("Shift+Enter");
    await expect(composer).toHaveValue(/\n$/);
    await composer.press("Enter");
    await expect(composer).toHaveValue("");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.getByText("Account & security", { exact: true }).click();
    const opener = page.getByRole("button", {
      name: "Log out all sessions",
      exact: true,
    });
    await opener.click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    expect(
      await dialog.evaluate((node) => node.contains(document.activeElement)),
    ).toBe(true);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(opener).toBeFocused();
    await page.getByText("Verify account email", { exact: true }).click();
    await expect(page.getByLabel("Verification token")).toBeVisible();
    await page.getByText("Verify account email", { exact: true }).click();
    await page.getByText("Account & security", { exact: true }).click();
    if (width === 390)
      await page.screenshot({
        path: testInfo.outputPath("conversation-narrow.png"),
        fullPage: true,
      });
  }
  expect(errors).toEqual([]);
  await testInfo.attach("responsive-inspection", {
    body: JSON.stringify(measurements, null, 2),
    contentType: "application/json",
  });
  await context.close();
});

test("message failure preserves draft; explicit retry persists escaped Markdown without executable markup", async ({
  browser,
}) => {
  const { context, page, wid } = await account(
    browser,
    "message-reliability-review",
    390,
  );
  const composer = page.getByLabel("Message", { exact: true });
  const draft =
    '**Review** `session`\n\n```html\n<script>window.untrustedExecuted=true</script>\n```\n\n<img src=x onerror="window.untrustedExecuted=true">\n[unsafe](javascript:alert(1))';
  await page.route(`**/workspaces/${wid}/messages`, async (route) => {
    if (route.request().method() === "POST")
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Synthetic temporary failure" }),
      });
    else await route.continue();
  });
  await composer.fill(draft);
  await composer.press("Enter");
  await expect(page.getByRole("alert")).toContainText(
    "Synthetic temporary failure",
  );
  await expect(composer).toHaveValue(draft);
  await expect(page.locator(".conversation-entry")).toHaveCount(0);
  await page.unroute(`**/workspaces/${wid}/messages`);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const message = page.locator(".chat-bubble");
  await expect(message.locator("strong")).toHaveText("Review");
  await expect(message.locator("pre")).toContainText("<script>");
  await expect(message.locator("img,script,a")).toHaveCount(0);
  expect(await page.evaluate(() => window.untrustedExecuted)).toBeUndefined();
  await expect(composer).toHaveValue("");
  await expect(
    page.getByRole("log", { name: "Saved messages" }),
  ).toHaveAttribute("aria-relevant", "additions");
  await page.reload();
  await expect(page.locator(".conversation-entry")).toHaveCount(1);
  await expect(page.locator(".chat-bubble pre")).toContainText(
    "window.untrustedExecuted",
  );
  await page
    .getByRole("button", { name: "Ask workspace", exact: true })
    .click();
  await page.getByLabel("Project question").fill("session");
  await page.getByRole("button", { name: "Ask with evidence" }).click();
  const citation = page.locator(".source-link").first();
  await expect(citation).toBeVisible();
  await citation.click();
  const source = page.getByRole("dialog", { name: "Project source" });
  await expect(
    source.getByRole("button", { name: "Close source" }),
  ).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(
    await source.evaluate((node) => node.contains(document.activeElement)),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(source).not.toBeVisible();
  await expect(citation).toBeFocused();
  await page.getByLabel("New workspace").fill("Isolated second project");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Isolated second project", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".conversation-entry")).toHaveCount(0);
  await expect(composer).toHaveValue("");
  await context.close();
});

test("rejecting an exact native proposal creates no tasks and replay cannot approve it", async ({
  browser,
}, testInfo) => {
  test.setTimeout(60000);
  const { context, page, wid } = await account(
    browser,
    "proposal-rejection-review",
    390,
  );
  await page
    .getByRole("button", { name: "Agents & approvals", exact: true })
    .click();
  await page.getByLabel("Agent capability").selectOption("local.plan.v1");
  await page
    .getByLabel("Run objective")
    .fill("Review launch notes; Validate release evidence");
  await page.getByRole("button", { name: "Queue run", exact: true }).click();
  const proposals = page.getByRole("region", {
    name: "Native action proposals",
  });
  await expect(
    proposals.getByRole("button", { name: "Reject task plan" }),
  ).toBeVisible({ timeout: 20000 });
  const data = await (
    await context.request.get(`${base}/workspaces/${wid}/action-proposals`)
  ).json();
  const proposal = data.items[0];
  await proposals.getByRole("button", { name: "Reject task plan" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    proposals.getByRole("heading", { name: "Create task plan · rejected" }),
  ).toBeVisible();
  expect(
    (
      await context.request.post(
        `${base}/workspaces/${wid}/action-proposals/${proposal.id}/approve`,
        { data: { payload_hash: proposal.payload_hash } },
      )
    ).status(),
  ).toBe(409);
  const tasks = await (
    await context.request.get(`${base}/workspaces/${wid}/tasks`)
  ).json();
  expect(tasks.items).toEqual([]);
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Native action proposals" }),
  ).toContainText("rejected");
  await expect(
    page.getByRole("heading", { name: "Execution receipt", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("rejected-plan-mobile.png"),
    fullPage: true,
  });
  await context.close();
});
