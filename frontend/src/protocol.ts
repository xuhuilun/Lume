type RecordValue = Record<string, unknown>;
function object(value: unknown): value is RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function strings(value: unknown): boolean {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}
function message(value: unknown): boolean {
  return (
    object(value) &&
    typeof value.message_id === "string" &&
    typeof value.source_id === "string" &&
    typeof value.text === "string" &&
    typeof value.author === "string" &&
    typeof value.sent_at === "string" &&
    typeof value.version === "number" &&
    Array.isArray(value.images) &&
    value.images.every(
      (i) =>
        object(i) &&
        typeof i.id === "string" &&
        typeof i.filename === "string" &&
        typeof i.status === "string" &&
        typeof i.ocr_text === "string",
    )
  );
}

/** Check the fields consumed by the workbench, independently of erased TS annotations. */
export function validateResponse(
  path: string,
  method: string,
  data: unknown,
): void {
  let valid = object(data) || Array.isArray(data);
  if (path === "/me") valid = object(data) && typeof data.name === "string";
  else if (path === "/spaces")
    valid =
      Array.isArray(data) &&
      data.every(
        (s) =>
          object(s) &&
          typeof s.id === "string" &&
          typeof s.name === "string" &&
          typeof s.read === "boolean" &&
          typeof s.maintain === "boolean" &&
          typeof s.message_count === "number",
      );
  else if (path === "/tasks" && method === "GET")
    valid =
      Array.isArray(data) &&
      data.every(
        (t) =>
          object(t) &&
          typeof t.id === "string" &&
          typeof t.question === "string" &&
          typeof t.state === "string",
      );
  else if (path.endsWith("/events"))
    valid =
      Array.isArray(data) &&
      data.every(
        (e) =>
          object(e) && typeof e.id === "number" && typeof e.kind === "string",
      );
  else if (path.startsWith("/answers/"))
    valid =
      object(data) &&
      typeof data.id === "string" &&
      typeof data.text === "string" &&
      strings(data.citation_ids) &&
      Array.isArray(data.dependencies);
  else if (path.startsWith("/observations/"))
    valid =
      object(data) &&
      typeof data.id === "string" &&
      typeof data.kind === "string" &&
      object(data.content) &&
      (!("messages" in data.content) ||
        (Array.isArray(data.content.messages) &&
          data.content.messages.every(message))) &&
      (!("text" in data.content) || typeof data.content.text === "string");
  else if (path.startsWith("/tasks"))
    valid =
      object(data) &&
      typeof data.id === "string" &&
      typeof data.state === "string";
  if (!valid) throw new Error("服务响应结构异常，请重新连接或稍后重试");
}
