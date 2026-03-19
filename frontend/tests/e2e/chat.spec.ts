/**
 * E2E tests for the TokenFounder chat interface.
 *
 * All backend API calls are intercepted via page.route() — no real server needed.
 * SSE responses are constructed as plain text bodies with Content-Type:
 * text/event-stream; the frontend's fetch().body.getReader() loop consumes
 * the entire body as one chunk and parses events correctly.
 *
 * Test groups:
 *   1. 页面初始状态        (2)
 *   2. 发送消息·正常对话轮  (4)
 *   3. 偏题重定向          (2)
 *   4. 完整对话流→画布弹窗  (4)
 *   5. 画布弹窗交互        (2)
 *   6. 多轮对话            (1)
 */

import { test, expect, Page } from "@playwright/test";

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Serialise an array of SSE events into a text/event-stream body. */
function sse(events: Array<{ type: string; data: object }>): string {
  return events
    .map((e) => `data: ${JSON.stringify({ type: e.type, data: e.data })}\n\n`)
    .join("");
}

/** Intercept the next POST to /api/chat and respond with the given SSE body. */
async function mockChat(
  page: Page,
  events: Array<{ type: string; data: object }>
): Promise<void> {
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
      body: sse(events),
    })
  );
}

/** BMC-progress event helper. */
const bmcEv = (
  covered: number,
  stage = "Empathize",
  missing = ["渠道通路", "成本结构"]
) => ({
  type: "bmc_progress",
  data: { covered_count: covered, total: 9, missing_items: missing, current_stage: stage },
});

/** Complete BusinessCanvas payload with one inferred section. */
const CANVAS_DATA = {
  project_name: "SalesMind AI",
  tagline: "让每封销售邮件都像手写一样个性化",
  canvas: {
    customer_segments:    { content: ["B2B销售团队"], is_inferred: false },
    value_propositions:   { content: ["回复率提升3倍"], is_inferred: false },
    channels:             { content: ["Salesforce集成"], is_inferred: false },
    customer_relationships: { content: ["CSM服务"], is_inferred: false },
    revenue_streams:      { content: ["$99/月/席位"], is_inferred: false },
    key_resources:        { content: ["训练数据集"], is_inferred: false },
    key_activities:       { content: ["模型训练"], is_inferred: false },
    key_partnerships:     { content: ["数据供应商"], is_inferred: true },   // inferred
    cost_structure:       { content: ["API调用成本"], is_inferred: false },
  },
  next_steps: ["招募10名Beta用户", "开发MVP"],
};

/** Sends a message through the chat UI (fills textarea, clicks Send). */
async function sendMessage(page: Page, text: string): Promise<void> {
  await page.getByTestId("chat-input").fill(text);
  await page.getByTestId("send-btn").click();
}

// ── 1. 页面初始状态 ────────────────────────────────────────────────────────────

test.describe("页面初始状态", () => {
  test("页面加载显示欢迎消息", async ({ page }) => {
    await page.goto("/");

    // Header title
    await expect(page.getByRole("heading", { name: "TokenFounder" })).toBeVisible();

    // Welcome assistant message
    const welcomeBubble = page.locator('[data-testid="message-bubble"][data-role="assistant"]').first();
    await expect(welcomeBubble).toBeVisible();
    await expect(welcomeBubble).toContainText("TokenFounder");

    // Input enabled, no canvas modal
    await expect(page.getByTestId("chat-input")).toBeEnabled();
    await expect(page.getByTestId("canvas-modal")).not.toBeVisible();
  });

  test("无 bmc_progress 前不显示进度条", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("progress-bar")).not.toBeVisible();
  });
});

// ── 2. 发送消息·正常对话轮 ─────────────────────────────────────────────────────

test.describe("发送消息·正常对话轮", () => {
  test("用户消息立即出现在消息列表", async ({ page }) => {
    await mockChat(page, [bmcEv(1)]);
    await page.goto("/");

    await sendMessage(page, "我想做一个AI销售助理");

    // User bubble with correct text
    const userBubble = page.locator('[data-testid="message-bubble"][data-role="user"]').first();
    await expect(userBubble).toContainText("我想做一个AI销售助理");
  });

  test("发送时显示加载指示器，完成后消失", async ({ page }) => {
    // Delay the response so we can observe the loading state
    await page.route("**/api/chat", async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sse([bmcEv(1)]),
      });
    });

    await page.goto("/");
    await page.getByTestId("chat-input").fill("测试加载状态");
    await page.getByTestId("send-btn").click();

    // Loading indicator must appear
    await expect(page.getByTestId("loading-indicator")).toBeVisible();

    // Then disappear once stream finishes
    await expect(page.getByTestId("loading-indicator")).not.toBeVisible();
  });

  test("助手回复文本正确渲染", async ({ page }) => {
    await mockChat(page, [
      { type: "text", data: { chunk: "你好！" } },
      { type: "text", data: { chunk: "说说你的想法。" } },
      bmcEv(1),
    ]);
    await page.goto("/");

    await sendMessage(page, "你好");

    // The last assistant bubble should contain the concatenated reply
    const assistantBubbles = page.locator('[data-testid="message-bubble"][data-role="assistant"]');
    const last = assistantBubbles.last();
    await expect(last).toContainText("你好！说说你的想法。");
  });

  test("bmc_progress 触发进度条出现并显示正确数值", async ({ page }) => {
    await mockChat(page, [
      { type: "text", data: { chunk: "继续" } },
      bmcEv(2, "Define"),
    ]);
    await page.goto("/");

    await sendMessage(page, "我的用户是销售人员");

    // Progress bar should appear
    await expect(page.getByTestId("progress-bar")).toBeVisible();
    await expect(page.getByTestId("progress-text")).toContainText("2/9");

    // Stage label updated
    await expect(page.getByTestId("stage-label")).toContainText("定义");
  });
});

// ── 3. 偏题重定向 ──────────────────────────────────────────────────────────────

test.describe("偏题重定向", () => {
  test("redirect 事件替换助手消息内容", async ({ page }) => {
    const redirectMsg = "偏题了！我们继续聊你的 Agent 创业想法吧。";
    await mockChat(page, [
      { type: "redirect", data: { message: redirectMsg } },
    ]);
    await page.goto("/");

    await sendMessage(page, "今天天气怎么样？");

    const assistantBubbles = page.locator('[data-testid="message-bubble"][data-role="assistant"]');
    await expect(assistantBubbles.last()).toContainText("偏题了");
  });

  test("redirect 后不显示进度条", async ({ page }) => {
    await mockChat(page, [
      { type: "redirect", data: { message: "请继续聊创业。" } },
    ]);
    await page.goto("/");

    await sendMessage(page, "给我讲个笑话");

    // No bmc_progress event → progress bar must not appear
    await expect(page.getByTestId("progress-bar")).not.toBeVisible();
  });
});

// ── 4. 完整对话流 → 画布弹窗 ──────────────────────────────────────────────────

test.describe("完整对话流→画布弹窗", () => {
  /** Events that trigger the full canvas flow. */
  const fullCanvasEvents = () => [
    { type: "text", data: { chunk: "很好，商业模式已完整！" } },
    bmcEv(7, "Validate", []),
    { type: "canvas_start", data: { message: "🎉 正在为你生成商业画布，请稍候..." } },
    { type: "canvas_complete", data: CANVAS_DATA },
  ];

  test("canvas_start 消息作为助手消息展示", async ({ page }) => {
    await mockChat(page, fullCanvasEvents());
    await page.goto("/");

    await sendMessage(page, "我们的商业模式很完整了");

    const assistantBubbles = page.locator('[data-testid="message-bubble"][data-role="assistant"]');
    // The canvas_start message should appear as an extra assistant bubble
    await expect(assistantBubbles.last()).toContainText("🎉");
  });

  test("canvas_complete 触发画布弹窗打开，显示项目名和标语", async ({ page }) => {
    await mockChat(page, fullCanvasEvents());
    await page.goto("/");

    await sendMessage(page, "我们的商业模式很完整了");

    await expect(page.getByTestId("canvas-modal")).toBeVisible();
    await expect(page.getByTestId("canvas-project-name")).toHaveText("SalesMind AI");
    await expect(page.getByTestId("canvas-tagline")).toContainText("让每封销售邮件");
  });

  test("画布弹窗显示 9 个 canvas cell", async ({ page }) => {
    await mockChat(page, fullCanvasEvents());
    await page.goto("/");

    await sendMessage(page, "触发画布");

    await expect(page.getByTestId("canvas-modal")).toBeVisible();
    await expect(page.getByTestId("canvas-cell")).toHaveCount(9);
  });

  test("推断项显示黄色推断标记", async ({ page }) => {
    await mockChat(page, fullCanvasEvents());
    await page.goto("/");

    await sendMessage(page, "触发画布");

    // key_partnerships has is_inferred=true → exactly one inferred badge
    await expect(page.getByTestId("inferred-badge")).toHaveCount(1);
    await expect(page.getByTestId("inferred-badge").first()).toContainText("推断补全");
  });
});

// ── 5. 画布弹窗交互 ────────────────────────────────────────────────────────────

test.describe("画布弹窗交互", () => {
  const openCanvas = async (page: Page) => {
    await mockChat(page, [
      { type: "text", data: { chunk: "好" } },
      bmcEv(7, "Validate", []),
      { type: "canvas_start", data: { message: "🎉 生成中" } },
      { type: "canvas_complete", data: CANVAS_DATA },
    ]);
    await page.goto("/");
    await sendMessage(page, "完整商业模式");
    await expect(page.getByTestId("canvas-modal")).toBeVisible();
  };

  test("点击关闭按钮隐藏弹窗", async ({ page }) => {
    await openCanvas(page);

    await page.getByTestId("canvas-close").click();
    await expect(page.getByTestId("canvas-modal")).not.toBeVisible();
  });

  test("下一步建议列表正确渲染", async ({ page }) => {
    await openCanvas(page);

    const nextSteps = page.getByTestId("canvas-next-steps");
    await expect(nextSteps).toBeVisible();
    // CANVAS_DATA.next_steps has 2 items
    await expect(nextSteps.locator("li")).toHaveCount(2);
    await expect(nextSteps.locator("li").first()).toContainText("Beta用户");
  });
});

// ── 6. 多轮对话 ────────────────────────────────────────────────────────────────

test.describe("多轮对话", () => {
  test("第二轮消息追加到消息列表", async ({ page }) => {
    // First call returns a simple text reply + progress
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sse([
          { type: "text", data: { chunk: "明白了。" } },
          bmcEv(1),
        ]),
      })
    );

    await page.goto("/");

    // First turn
    await sendMessage(page, "第一轮消息");
    // Wait for assistant to reply
    await expect(page.getByTestId("loading-indicator")).not.toBeVisible();

    // Re-route for second turn
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sse([
          { type: "text", data: { chunk: "继续聊。" } },
          bmcEv(2),
        ]),
      })
    );

    // Second turn
    await sendMessage(page, "第二轮消息");
    await expect(page.getByTestId("loading-indicator")).not.toBeVisible();

    // Should have: 1 welcome + 1 user + 1 assistant + 1 user + 1 assistant = 5 bubbles
    const bubbles = page.getByTestId("message-bubble");
    await expect(bubbles).toHaveCount(5);

    // Second user message is present
    const userBubbles = page.locator('[data-testid="message-bubble"][data-role="user"]');
    await expect(userBubbles).toHaveCount(2);
    await expect(userBubbles.last()).toContainText("第二轮消息");
  });
});
