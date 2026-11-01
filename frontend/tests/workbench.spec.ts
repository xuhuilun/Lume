import { expect, test } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

test("real API → worker → answer → source and image workbench", async ({
  page,
}) => {
  const tokenFile = process.env.LUME_UI_TOKEN_FILE;
  test.skip(
    !tokenFile,
    "Provide a local seeded API, running worker, and LUME_UI_TOKEN_FILE",
  );
  const token = (await readFile(tokenFile!, "utf8")).trim();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("访问令牌").fill(token);
  await page.getByRole("button", { name: "连接工作空间" }).click();
  await expect(page.getByText("知识查证", { exact: true })).toBeVisible();
  await page.getByLabel("查证问题").fill("E_CONN_42 之前是如何处理的？");
  await page.getByRole("button", { name: "开始查证" }).click();
  await expect(page.locator(".state")).toHaveText("查证完成", {
    timeout: 20_000,
  });
  await expect(page.locator(".answer-text")).toContainText("20");
  await expect(page.locator(".history button.active-task")).toBeVisible();
  await page.locator(".history button.active-task").click();
  await expect(page.locator(".answer-text")).toContainText("20");
  await page
    .getByRole("button", { name: /查看来源/ })
    .first()
    .click();
  await expect(page.locator(".source-card").first()).toBeVisible();
  await page.getByLabel("查证问题").fill("截图中的连接池参数是多少？");
  await page.getByRole("button", { name: "开始查证" }).click();
  await expect(page.locator(".state")).toHaveText("依据不足", {
    timeout: 20_000,
  });
  await expect(page.locator(".answer-text")).toContainText(
    "演示引擎不判断视觉语义",
  );
  await page
    .getByRole("button", { name: /查看来源/ })
    .first()
    .click();
  await expect(page.locator(".image-card img").first()).toBeVisible();
  await page
    .locator(".image-card img")
    .first()
    .evaluate(async (element: HTMLImageElement) => {
      if (!element.complete)
        await new Promise<void>((resolve) => {
          element.onload = () => resolve();
        });
    });
  const directory = resolve(
    process.env.LUME_UI_ARTIFACT_DIR || "test-results/screenshots",
  );
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: resolve(directory, "workbench.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("查证问题")).toBeVisible();
  await expect(page.locator(".image-card img").first()).toBeVisible();
  await page.screenshot({
    path: resolve(directory, "workbench-mobile.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

for (const mode of ["history", "submit"] as const) {
  test(`late ${mode} response cannot cross an identity change`, async ({
    page,
  }) => {
    const aliceFile = process.env.LUME_UI_TOKEN_FILE;
    const bobFile = process.env.LUME_UI_SECOND_TOKEN_FILE;
    test.skip(
      !aliceFile || !bobFile,
      "Two separately initialized local identities are required",
    );
    const alice = (await readFile(aliceFile!, "utf8")).trim();
    const bob = (await readFile(bobFile!, "utf8")).trim();
    // Keep real HTTP requests but deliberately ignore transport cancellation, so generation
    // guards are tested even when an already-arrived response cannot be aborted.
    await page.addInitScript(() => {
      const original = window.fetch.bind(window);
      window.fetch = (input, options) =>
        original(input, { ...options, signal: undefined });
    });
    await page.goto("/");
    await page.getByLabel("访问令牌").fill(alice);
    await page.getByRole("button", { name: "连接工作空间" }).click();
    await expect(page.getByText("知识查证", { exact: true })).toBeVisible();
    let release!: () => void;
    let entered!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const waiting = new Promise<void>((resolve) => {
      entered = resolve;
    });
    let captured = false;
    const method = mode === "history" ? "GET" : "POST";
    await page.route("**/api/tasks", async (route) => {
      const request = route.request();
      if (
        !captured &&
        request.method() === method &&
        request.headers()["authorization"] === "Bearer " + alice
      ) {
        captured = true;
        const response = await route.fetch();
        const body = await response.body();
        entered();
        await gate;
        await route.fulfill({ response, body });
      } else await route.continue();
    });
    const marker = `合成旧身份${mode}内容-${Date.now()}`;
    try {
      await page.getByLabel("查证问题").fill(marker);
      await page.getByRole("button", { name: "开始查证" }).click();
      await waiting;
      await page.getByRole("button", { name: "退出", exact: true }).click();
      await page.getByLabel("访问令牌").fill(bob);
      await page.getByRole("button", { name: "连接工作空间" }).click();
      await expect(page.locator(".rail-footer strong")).toHaveText(
        "browser-bob",
      );
      const delivered = page.waitForResponse(
        (response) =>
          response.url().endsWith("/api/tasks") &&
          response.request().method() === method &&
          response.request().headers()["authorization"] === "Bearer " + alice,
      );
      release();
      await delivered;
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await expect(page.locator("body")).not.toContainText(marker);
      await expect(page.locator(".welcome")).toBeVisible();
    } finally {
      release();
    }
  });
}
