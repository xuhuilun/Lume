import { expect, test } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

test("explicit image requirement reaches actual model evidence in the workbench", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  test.skip(
    process.env.LUME_UI_REAL_MODELS !== "1" || !process.env.LUME_UI_TOKEN_FILE,
    "Opt in with a local Ollama API, seeded synthetic database and token file",
  );
  const health = await request.get("/api/health");
  expect((await health.json()).provider).toBe("ollama");
  const token = (
    await readFile(process.env.LUME_UI_TOKEN_FILE!, "utf8")
  ).trim();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("访问令牌").fill(token);
  await page.getByRole("button", { name: "连接工作空间" }).click();
  const checkbox = page.getByRole("checkbox", { name: /核查原图/ });
  await expect(checkbox).not.toBeChecked();
  await checkbox.check();
  await page
    .getByLabel("查证问题")
    .fill("请核查连接池参数示意图，图中的pool_size和status分别是什么？");
  const submission = page.waitForRequest(
    (req) => req.url().endsWith("/api/tasks") && req.method() === "POST",
  );
  await page.getByRole("button", { name: "开始查证" }).click();
  expect((await submission).postDataJSON().require_image).toBe(true);
  await expect(page.locator(".state")).toHaveText("查证完成", {
    timeout: 95_000,
  });
  await expect(page.locator(".answer-text")).toContainText("20");
  await expect(page.locator(".answer-text")).toContainText("healthy");
  await page
    .getByRole("button", { name: /查看来源/ })
    .first()
    .click();
  await expect(page.locator(".evidence-kind")).toHaveText("图片观察");
  const image = page.locator(".image-card img").first();
  await expect(image).toBeVisible();
  await image.evaluate(async (element: HTMLImageElement) => {
    if (!element.complete) await element.decode();
  });
  const directory = resolve(
    process.env.LUME_UI_ARTIFACT_DIR || "test-results/real-model",
  );
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: resolve(directory, "real-model-workbench.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(checkbox).toBeVisible();
  await page.screenshot({
    path: resolve(directory, "real-model-workbench-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.getByLabel("访问令牌").fill(token);
  await page.getByRole("button", { name: "连接工作空间" }).click();
  await expect(
    page.getByRole("checkbox", { name: /核查原图/ }),
  ).not.toBeChecked();
  expect(errors).toEqual([]);
});
