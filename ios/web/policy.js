export function connection(value, room = "") {
  const url = new URL(value.trim());
  const host = url.hostname.toLowerCase();
  const parts = host.split(".").map(Number);
  const local =
    host.endsWith(".local") ||
    (parts.length === 4 &&
      parts.every((n) => Number.isInteger(n) && n >= 0 && n <= 255) &&
      (parts[0] === 10 ||
        (parts[0] === 192 && parts[1] === 168) ||
        (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)));
  if (
    url.username ||
    url.password ||
    !["http:", "https:"].includes(url.protocol) ||
    (url.protocol === "http:" && !local)
  )
    throw new Error("请使用 HTTPS 或局域网 HTTP 地址");
  const code = (url.searchParams.get("room") || room).trim().toUpperCase();
  if (!/^[A-Z0-9]{4,12}$/.test(code)) throw new Error("请输入有效房间码");
  if (!["/", "/m.html", "/tv.html"].includes(url.pathname))
    throw new Error("请输入服务器根地址");
  return { server: url.origin, room: code };
}
export function allowedPath(path, method) {
  return method === "GET"
    ? /^\/api\/(songs\?[^#]*|rooms\/[A-Z0-9]{4,12})$/.test(path)
    : method === "POST" &&
        (/^\/api\/rooms\/[A-Z0-9]{4,12}\/(queue|play|skip|mix)$/.test(path) ||
          path === "/api/remote/reports");
}
