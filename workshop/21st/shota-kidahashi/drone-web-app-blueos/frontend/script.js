const connectionStatus = document.getElementById('connectionStatus');
const armedStatus = document.getElementById('armedStatus');
const modeStatus = document.getElementById('modeStatus');
const latitudeStatus = document.getElementById('latitudeStatus');
const longitudeStatus = document.getElementById('longitudeStatus');
const altitudeStatus = document.getElementById('altitudeStatus');
const batteryStatus = document.getElementById('batteryStatus');

const connectBtn = document.getElementById('connectBtn');
const armBtn = document.getElementById('armBtn');
const takeoffBtn = document.getElementById('takeoffBtn');
const landBtn = document.getElementById('landBtn');
const gotoBtn = document.getElementById('gotoBtn');
const setModeBtn = document.getElementById('setModeBtn');

const takeoffAltitudeInput = document.getElementById('takeoffAltitude');
const gotoLatitudeInput = document.getElementById('gotoLatitude');
const gotoLongitudeInput = document.getElementById('gotoLongitude');
const gotoAltitudeInput = document.getElementById('gotoAltitude');
const modeSelect = document.getElementById('modeSelect');

let ws;
let map;
let droneMarker;
let targetMarker = null;
let flightPath = [];
let flightPathPolyline;

const droneIcon = L.divIcon({
    className: "drone-icon",
    html: `<div class="drone-arrow"></div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20]
});

function initMap() {
    map = L.map('map').setView([35.0, 135.0], 6);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    droneMarker = L.marker([35.0, 135.0], { icon: droneIcon }).addTo(map);

    flightPathPolyline = L.polyline(flightPath, {color: 'red'}).addTo(map);

    map.on("click", (e) => {
        const lat = e.latlng.lat;
        const lon = e.latlng.lng;
        const alt = parseFloat(gotoAltitudeInput.value || "20");

        gotoLatitudeInput.value = lat.toFixed(7);
        gotoLongitudeInput.value = lon.toFixed(7);

        if (targetMarker) map.removeLayer(targetMarker);

        targetMarker = L.marker([lat, lon], {
            icon: L.divIcon({
                className: "target-icon",
                html: `<div class="target-dot"></div>`,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            })
        }).addTo(map);

        ws.send(JSON.stringify({
            type: "goto",
            latitude: lat,
            longitude: lon,
            altitude: alt
        }));
    });
}

function connectWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws`);

    ws.onopen = () => {
        connectionStatus.textContent = '接続済み';
        ws.send(JSON.stringify({ type: 'connect' }));
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'status') return;

        armedStatus.textContent = data.armed ? 'アーム済み' : '未アーム';
        modeStatus.textContent = data.mode;
        latitudeStatus.textContent = data.latitude.toFixed(6);
        longitudeStatus.textContent = data.longitude.toFixed(6);
        altitudeStatus.textContent = data.altitude.toFixed(2);
        batteryStatus.textContent = data.battery?.toFixed(2) || "0.0";

        const newLatLng = new L.LatLng(data.latitude, data.longitude);
        droneMarker.setLatLng(newLatLng);
        map.panTo(newLatLng);

        const arrow = droneMarker.getElement().querySelector(".drone-arrow");
        arrow.style.transform = `rotate(${data.heading}deg)`;

        flightPath.push(newLatLng);
        flightPathPolyline.setLatLngs(flightPath);
    };

    ws.onclose = () => {
        connectionStatus.textContent = '切断';
        setTimeout(connectWebSocket, 3000);
    };
}

connectBtn.onclick = () => ws.send(JSON.stringify({ type: 'connect' }));
armBtn.onclick = () => ws.send(JSON.stringify({ type: 'arm' }));
landBtn.onclick = () => ws.send(JSON.stringify({ type: 'land' }));

takeoffBtn.onclick = () => {
    ws.send(JSON.stringify({
        type: 'takeoff',
        altitude: parseFloat(takeoffAltitudeInput.value)
    }));
};

gotoBtn.onclick = () => {
    ws.send(JSON.stringify({
        type: 'goto',
        latitude: parseFloat(gotoLatitudeInput.value),
        longitude: parseFloat(gotoLongitudeInput.value),
        altitude: parseFloat(gotoAltitudeInput.value)
    }));
};

setModeBtn.onclick = () => {
    ws.send(JSON.stringify({
        type: 'mode',
        mode_name: modeSelect.value
    }));
};

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    connectWebSocket();
});

