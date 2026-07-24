// ========== Global State ==========
const state = {
    connected: false,
    armed: false,
    mode: "UNKNOWN",
    latitude: 0.0,
    longitude: 0.0,
    altitude: 0.0,
    heading: 0,
};

let ws = null;
let map = null;
let droneMarker = null;
let dronePath = [];
let polyline = null;
const INITIAL_LAT = 35.681236;
const INITIAL_LNG = 139.767125;
let reconnectTimer = null;

// ========== Initialize ==========
document.addEventListener("DOMContentLoaded", () => {
    initializeMap();
    setupWebSocket();
    attachEventListeners();
});

// ========== Map Initialization ==========
function initializeMap() {
    map = L.map("map").setView([INITIAL_LAT, INITIAL_LNG], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
            '© OpenStreetMap contributors',
        maxZoom: 19,
    }).addTo(map);

    // Add initial drone marker at Tokyo Station
    droneMarker = L.marker([INITIAL_LAT, INITIAL_LNG], {
        title: "Drone Position",
    }).addTo(map);
    droneMarker.bindPopup(
        `<b>Drone</b><br>Lat: ${INITIAL_LAT.toFixed(6)}<br>Lng: ${INITIAL_LNG.toFixed(
            6
        )}<br>Alt: 0.00m`
    );

    // Initialize polyline
    polyline = L.polyline(dronePath, { color: "red", weight: 2 }).addTo(map);
}

// ========== WebSocket Setup ==========
function setupWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("WebSocket connected");
        addMessage("WebSocketに接続しました");
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        addMessage("WebSocketエラーが発生しました");
    };

    ws.onclose = () => {
        console.log("WebSocket closed, reconnecting in 3s...");
        addMessage("WebSocket切断、3秒後に再接続します");
        clearDronePath();
        reconnectTimer = setTimeout(() => {
            setupWebSocket();
        }, 3000);
    };
}

// ========== Handle WebSocket Messages ==========
function handleMessage(msg) {
    if (msg.type === "state") {
        updateState(msg.state);
    } else if (msg.type === "status") {
        addMessage(msg.message);
    }
}

function updateState(newState) {
    Object.assign(state, newState);
    updateUI();
    updateMapMarker();
}

function updateUI() {
    document.getElementById("connected-status").textContent = state.connected
        ? "接続中"
        : "未接続";
    document.getElementById("armed-status").textContent = state.armed
        ? "アーム中"
        : "未アーム";
    document.getElementById("mode-status").textContent = state.mode;
    document.getElementById("latitude-status").textContent =
        state.latitude.toFixed(6);
    document.getElementById("longitude-status").textContent =
        state.longitude.toFixed(6);
    document.getElementById("altitude-status").textContent =
        state.altitude.toFixed(2) + "m";
    document.getElementById("heading-status").textContent = state.heading + "°";
}

function updateMapMarker() {
    if (state.latitude === 0 && state.longitude === 0) return;

    const position = [state.latitude, state.longitude];

    if (droneMarker) {
        droneMarker.setLatLng(position);
        droneMarker.setPopupContent(
            `<b>Drone</b><br>Lat: ${state.latitude.toFixed(
                6
            )}<br>Lng: ${state.longitude.toFixed(6)}<br>Alt: ${state.altitude.toFixed(
                2
            )}m`
        );
    }

    // Add to path
    if (
        dronePath.length === 0 ||
        (dronePath[dronePath.length - 1][0] !== state.latitude ||
            dronePath[dronePath.length - 1][1] !== state.longitude)
    ) {
        dronePath.push(position);
        polyline.setLatLngs(dronePath);
    }

    // Center map on drone
    map.setView(position);
}

function clearDronePath() {
    dronePath = [];
    polyline.setLatLngs([]);
}

function addMessage(text) {
    const messageBox = document.getElementById("message-box");
    const timestamp = new Date().toLocaleTimeString("ja-JP");
    messageBox.innerHTML =
        `<strong>${timestamp}</strong><br>` + text + "<br>" + messageBox.innerHTML;
    // Keep last 5 messages
    const lines = messageBox.innerHTML.split("<br>");
    if (lines.length > 10) {
        messageBox.innerHTML = lines.slice(0, 10).join("<br>");
    }
}

// ========== Event Listeners ==========
function attachEventListeners() {
    document.getElementById("connect-btn").addEventListener("click", () => {
        sendCommand({ type: "connect" });
    });

    document.getElementById("arm-btn").addEventListener("click", () => {
        sendCommand({ type: "arm" });
    });

    document.getElementById("disarm-btn").addEventListener("click", () => {
        sendCommand({ type: "disarm" });
    });

    document.getElementById("takeoff-btn").addEventListener("click", () => {
        const altitude = parseFloat(
            document.getElementById("takeoff-altitude").value
        );
        if (isNaN(altitude)) {
            addMessage("離陸高度が不正です");
            return;
        }
        sendCommand({ type: "takeoff", altitude });
    });

    document.getElementById("land-btn").addEventListener("click", () => {
        sendCommand({ type: "land" });
    });

    document.getElementById("goto-btn").addEventListener("click", () => {
        const latitude = parseFloat(
            document.getElementById("goto-latitude").value
        );
        const longitude = parseFloat(
            document.getElementById("goto-longitude").value
        );
        const altitude = parseFloat(
            document.getElementById("goto-altitude").value
        );

        if (isNaN(latitude) || isNaN(longitude) || isNaN(altitude)) {
            addMessage("GoTo座標が不正です");
            return;
        }

        sendCommand({
            type: "goto",
            latitude,
            longitude,
            altitude,
        });
    });

    document.getElementById("mode-btn").addEventListener("click", () => {
        const mode = document.getElementById("mode-select").value;
        sendCommand({ type: "mode", mode });
    });
}

// ========== Send Command ==========
function sendCommand(command) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        addMessage("WebSocketが接続されていません");
        return;
    }
    console.log("Sending command:", command);
    ws.send(JSON.stringify(command));
}
