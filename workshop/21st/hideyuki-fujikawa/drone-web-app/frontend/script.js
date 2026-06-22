"use strict";

// ---- 地図初期化 -----------------------------------------------------------
// ローカル同梱した Leaflet のマーカー画像パスを明示（オフラインでも表示）
L.Icon.Default.imagePath = "/static/leaflet/images/";

const TOKYO_STATION = [35.681236, 139.767125];

const map = L.map("map").setView(TOKYO_STATION, 16);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

let marker = L.marker(TOKYO_STATION).addTo(map);
let track = L.polyline([], { color: "#1565c0", weight: 3 }).addTo(map);
let trackPoints = [];
let hasFix = false; // 有効な位置を受信したか

// ---- DOM 参照 -------------------------------------------------------------
const el = (id) => document.getElementById(id);
const wsIndicator = el("ws-indicator");
const logBox = el("log");

function log(message) {
  const line = document.createElement("div");
  const ts = new Date().toLocaleTimeString();
  line.textContent = `[${ts}] ${message}`;
  logBox.appendChild(line);
  logBox.scrollTop = logBox.scrollHeight;
}

// ---- WebSocket ------------------------------------------------------------
let ws = null;

function connectWebSocket() {
  ws = new WebSocket(`ws://${window.location.host}/ws`);

  ws.onopen = () => {
    wsIndicator.textContent = "サーバー接続中";
    wsIndicator.className = "badge badge-on";
    // 再接続時は飛行軌跡をクリア
    clearTrack();
    log("サーバーに接続しました");
  };

  ws.onclose = () => {
    wsIndicator.textContent = "サーバー未接続";
    wsIndicator.className = "badge badge-off";
    log("サーバーから切断されました。3秒後に再接続します");
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => {
    log("WebSocket エラーが発生しました");
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }
    if (msg.type === "state") {
      updateState(msg.state);
    } else if (msg.type === "status") {
      log(msg.message);
    }
  };
}

function send(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    log("サーバー未接続のため送信できません");
    return;
  }
  ws.send(JSON.stringify(obj));
}

// ---- 状態表示の更新 -------------------------------------------------------
function updateState(state) {
  el("st-connected").textContent = state.connected ? "接続済み" : "未接続";
  el("st-armed").textContent = state.armed ? "ARMED" : "DISARMED";
  el("st-mode").textContent = state.mode;
  el("st-lat").textContent = state.latitude.toFixed(6);
  el("st-lon").textContent = state.longitude.toFixed(6);
  el("st-alt").textContent = state.altitude.toFixed(2);
  el("st-hdg").textContent = Math.round(state.heading);

  updateMap(state);
}

function updateMap(state) {
  const lat = state.latitude;
  const lon = state.longitude;
  // 0,0 など無効な位置はスキップ
  if (!state.connected || (lat === 0 && lon === 0)) {
    return;
  }

  const pos = [lat, lon];
  marker.setLatLng(pos);
  marker.bindPopup(
    `緯度: ${lat.toFixed(6)}<br>` +
      `経度: ${lon.toFixed(6)}<br>` +
      `高度: ${state.altitude.toFixed(2)} m`
  );

  trackPoints.push(pos);
  track.setLatLngs(trackPoints);
  map.setView(pos);
  hasFix = true;
}

function clearTrack() {
  trackPoints = [];
  track.setLatLngs([]);
  hasFix = false;
}

// ---- ボタンイベント -------------------------------------------------------
// 要素が見つからなくても 1 か所の失敗で全体が止まらないよう null ガードする
function bind(id, handler) {
  const node = el(id);
  if (node) {
    node.addEventListener("click", handler);
  } else {
    console.warn(`要素が見つかりません: #${id}`);
  }
}

function bindControls() {
  bind("btn-connect", () => send({ type: "connect" }));
  bind("btn-arm", () => send({ type: "arm" }));
  bind("btn-disarm", () => send({ type: "disarm" }));
  bind("btn-land", () => send({ type: "land" }));

  bind("btn-takeoff", () => {
    const altitude = parseFloat(el("in-takeoff-alt").value);
    send({ type: "takeoff", altitude });
  });

  bind("btn-goto", () => {
    send({
      type: "goto",
      latitude: parseFloat(el("in-goto-lat").value),
      longitude: parseFloat(el("in-goto-lon").value),
      altitude: parseFloat(el("in-goto-alt").value),
    });
  });

  bind("btn-mode", () => {
    send({ type: "mode", mode: el("sel-mode").value });
  });
}

// ---- 起動 -----------------------------------------------------------------
// ボタン束縛で失敗しても WebSocket 接続は必ず開始する
try {
  bindControls();
} catch (e) {
  console.error("コントロールの初期化に失敗:", e);
}
connectWebSocket();
