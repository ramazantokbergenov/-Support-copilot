import { expect, test } from "@playwright/test";

async function signInIfRequired(page: import("@playwright/test").Page) {
  await page.goto("/");
  const localUsername = page.getByLabel("Имя оператора");
  const supabaseEmail = page.getByLabel("Рабочая почта");
  const loginField = await localUsername.isVisible().catch(() => false)
    ? localUsername
    : supabaseEmail;
  if (!await loginField.isVisible().catch(() => false)) return;

  const username = process.env.SUPPORT_COPILOT_OPERATOR_USERNAME;
  const password = process.env.SUPPORT_COPILOT_OPERATOR_PASSWORD;
  if (!username || !password) {
    throw new Error("Set operator credentials in the environment before running E2E tests.");
  }
  await loginField.fill(username);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Backend подключён")).toBeVisible();
}

test("operator can create, analyze, update, and save a ticket draft", async ({ page }) => {
  const playerId = `e2e-player-${Date.now()}`;
  const message = "Прошу проверить блокировку моего аккаунта, не могу войти.";
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await signInIfRequired(page);
  await expect(page.getByText("Backend подключён")).toBeVisible();
  await page.getByRole("button", { name: "Новое обращение" }).click();
  await page.getByPlaceholder("Укажите ID игрока").fill(playerId);
  await page.getByPlaceholder("Текст обращения игрока").fill(message);
  await page.getByRole("button", { name: "Создать обращение" }).click();
  await expect(page).toHaveURL(/\/tickets\/[^/]+$/);
  await expect(page.getByText(message)).toBeVisible();

  await page.getByRole("button", { name: "Анализировать" }).click();
  await expect(page.getByText("Требуется проверка оператором", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Язык: ru")).toBeVisible();
  await page.getByRole("combobox", { name: "Изменить статус обращения" }).selectOption("Processing");
  await expect(page.getByText("В работе")).toBeVisible();

  const ticketId = decodeURIComponent(new URL(page.url()).pathname.split("/").at(-1) ?? "");
  await page.goto("/drafts");
  const editor = page.getByLabel("Редактор текста ответа");
  await expect(editor).toBeVisible();
  await editor.fill("Оператор проверит обращение. Это черновик для проверки оператором.");
  await page.getByRole("button", { name: "Сохранить изменения" }).click();
  await expect(page.getByText("Черновик сохранён в Backend.")).toBeVisible();
  await page.getByRole("button", { name: "Отметить проверенным" }).click();
  await expect(page.getByText("Проверка записана.")).toBeVisible();

  const accessToken = await page.evaluate(() => sessionStorage.getItem("support-copilot.local-access-token"));
  expect(accessToken).toBeTruthy();
  const detailsResponse = await page.request.get(
    `http://127.0.0.1:8000/tickets/${encodeURIComponent(ticketId)}`,
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  expect(detailsResponse.ok()).toBeTruthy();
  const details = await detailsResponse.json();
  expect(details.player_id).toBe(playerId);
  expect(details.status).toBe("Processing");
  expect(details.draft_reply).toContain("Оператор проверит обращение");
  expect(details.draft_status).toBe("reviewed");
  expect(details.operator_notes).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("knowledge base displays an empty state instead of fabricated citations", async ({ page }) => {
  await signInIfRequired(page);
  await page.goto("/knowledge");
  await expect(page.getByText("В базе нет активных правил")).toBeVisible();
  await expect(page.getByText("Показываются только опубликованные правила с проверенным источником.")).toBeVisible();
});