import { expect, test } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const cases = [
  {
    name: "fact",
    question:
      "BROWSER_CONN_47在browser-stage-r1已验证的max_connections是多少？",
    state: "查证完成",
    expected: "18",
    requireImage: false,
  },
  {
    name: "insufficient",
    question: "browser-stage-r1允许的单文件容量上限是多少GiB？",
    state: "依据不足",
    expected: "当前已读资料不足",
    requireImage: false,
  },
  {
    name: "image",
    question:
      "请核查BROWSER_CONN_47的浏览器联调示意图，图里展示了哪些连接池字段？",
    state: "查证完成",
    expected: "图像观察",
    requireImage: true,
  },
] as const;

for (const item of cases) {
  test(`reviewed workbench ${item.name} through real HTTP and worker`, async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    test.skip(
      process.env.LUME_UI_REAL_MODELS !== "1" ||
        !process.env.LUME_UI_TOKEN_FILE,
      "Use the isolated browser_validation harness with local real models",
    );
    expect((await (await request.get("/api/health")).json()).provider).toBe(
      "ollama",
    );
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
    if (item.requireImage) await checkbox.check();
    await page.getByLabel("查证问题").fill(item.question);
    const submitted = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/tasks") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "开始查证" }).click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    expect(response.request().postDataJSON().require_image).toBe(
      item.requireImage,
    );
    const taskId = (await response.json()).id as string;
    await expect(page.locator(".state")).toHaveText(item.state, {
      timeout: 95_000,
    });
    await expect(page.locator(".answer-text")).toContainText(item.expected);
    const status = await request.get(`/api/tasks/${taskId}`, {
      headers: { Authorization: "Bearer " + token },
    });
    expect(status.ok()).toBe(true);
    const task = await status.json();
    const answerResponse = await request.get(`/api/answers/${task.answer_id}`, {
      headers: { Authorization: "Bearer " + token },
    });
    expect(answerResponse.ok()).toBe(true);
    const answer = await answerResponse.json();
    if (item.name === "insufficient") {
      expect(task.state).toBe("insufficient");
      expect(answer.citation_ids).toEqual([]);
      await expect(page.getByRole("button", { name: /查看来源/ })).toHaveCount(
        0,
      );
    } else {
      expect(task.state).toBe("completed");
      expect(answer.citation_ids.length).toBeGreaterThan(0);
      // Every offered citation is fetched through the real authorized endpoint.
      const observations = [];
      for (const id of answer.citation_ids as string[]) {
        const evidence = await request.get(`/api/observations/${id}`, {
          headers: { Authorization: "Bearer " + token },
        });
        expect(evidence.ok()).toBe(true);
        observations.push(await evidence.json());
      }
      expect(observations.every((o) => o.kind !== "support_review")).toBe(true);
      const target = item.requireImage
        ? observations.find((o) => o.kind === "image_observation")
        : observations.find((o) => o.kind === "message_context");
      expect(target).toBeTruthy();
      const index = (answer.citation_ids as string[]).indexOf(target.id);
      await page
        .getByRole("button", { name: /查看来源/ })
        .nth(index)
        .click();
      if (item.requireImage) {
        expect(target.content.semantic).toBe(true);
        expect(target.content.text.trim().length).toBeGreaterThan(0);
        await expect(page.locator(".evidence-kind")).toHaveText("图片观察");
        const image = page.locator(".image-card img").first();
        await expect(image).toBeVisible();
        const width = await image.evaluate(
          async (element: HTMLImageElement) => {
            if (!element.complete) await element.decode();
            return element.naturalWidth;
          },
        );
        expect(width).toBeGreaterThan(0);
      } else {
        await expect(page.locator(".source-card").first()).toBeVisible();
        await expect(page.locator(".evidence-content")).toContainText(
          "browser-stage-r1",
        );
      }
    }
    const directory = resolve(
      process.env.LUME_UI_ARTIFACT_DIR || "test-results/reviewed-browser",
    );
    await mkdir(directory, { recursive: true });
    await page.screenshot({
      path: resolve(directory, `${item.name}-desktop.png`),
      fullPage: true,
    });
    if (item.requireImage) {
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(page.getByLabel("查证问题")).toBeVisible();
      await expect(page.locator(".image-card img").first()).toBeVisible();
      await page.screenshot({
        path: resolve(directory, "image-mobile.png"),
        fullPage: true,
      });
    }
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await page.getByLabel("访问令牌").fill(token);
    await page.getByRole("button", { name: "连接工作空间" }).click();
    await expect(
      page.getByRole("checkbox", { name: /核查原图/ }),
    ).not.toBeChecked();
    expect(errors).toEqual([]);
  });
}
