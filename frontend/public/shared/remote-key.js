// Web account page only. The dedicated iOS bundle does not include this module.
const panel = document.getElementById("remote-key-panel");
const info = document.getElementById("remote-key-info");
const secret = document.getElementById("remote-key-secret");
const create = document.getElementById("remote-key-create");
const revoke = document.getElementById("remote-key-revoke");
async function request(method = "GET") {
  const response = await fetch("/api/account/remote-key", {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "暂时无法管理 API key");
  return data;
}
async function load() {
  const data = await request();
  panel.hidden = false;
  create.disabled = !data.eligible;
  create.textContent = data.key ? "重新生成 API key" : "申请 API key";
  revoke.hidden = !data.key;
  info.textContent = data.key
    ? `已保存 ${data.key.prefix}…（${new Date(data.key.created_at).toLocaleString()}）。完整 key 仅生成时显示。`
    : data.eligible
      ? "可申请用于官方遥控服务的 API key。"
      : "有效会员可申请 API key。";
}
async function action(work) {
  create.disabled = true;
  revoke.disabled = true;
  try {
    await work();
  } catch (error) {
    info.textContent = error.message;
  } finally {
    revoke.disabled = false;
  }
}
create.onclick = () =>
  action(async () => {
    if (!confirm("生成新 key 会立即使旧 key 失效，是否继续？")) {
      await load();
      return;
    }
    secret.textContent = "";
    const data = await request("POST");
    secret.textContent = data.api_key;
    await load();
  });
revoke.onclick = () =>
  action(async () => {
    if (!confirm("吊销后，使用此 key 的设备将断开官方服务，是否继续？")) {
      await load();
      return;
    }
    await request("DELETE");
    secret.textContent = "";
    await load();
  });
load().catch(() => {});
