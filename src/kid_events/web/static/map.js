/* Renders the filtered events on a Leaflet map. One marker per location
   (city centroid), sized by event count, with a popup listing its events. */
function initEventMap(payload) {
  if (window._eventMap) {
    try {
      window._eventMap.remove();
    } catch (e) {
      /* container was already replaced by an htmx swap */
    }
    window._eventMap = null;
  }
  var mapEl = document.getElementById("map");
  if (!mapEl || typeof L === "undefined") return;

  var map = L.map("map", { scrollWheelZoom: true });
  window._eventMap = map;
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  function esc(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : value;
    return div.innerHTML;
  }

  var points = [];
  var center = payload.center;
  if (center) {
    L.circleMarker([center.lat, center.lon], {
      radius: 7,
      color: "#b91c1c",
      weight: 2,
      fillColor: "#ef4444",
      fillOpacity: 1,
    })
      .addTo(map)
      .bindPopup("<b>" + esc(center.name) + "</b><br>(center)");
    points.push([center.lat, center.lon]);
    if (payload.radius_miles) {
      L.circle([center.lat, center.lon], {
        radius: payload.radius_miles * 1609.34,
        color: "#2563eb",
        weight: 1,
        fill: false,
        dashArray: "5,5",
      }).addTo(map);
    }
  }

  (payload.locations || []).forEach(function (loc) {
    var marker = L.circleMarker([loc.lat, loc.lon], {
      radius: Math.min(9 + Math.sqrt(loc.count) * 2.4, 26),
      color: "#1d4ed8",
      weight: 1,
      fillColor: "#3b82f6",
      fillOpacity: 0.55,
    }).addTo(map);

    var html =
      "<b>" + esc(loc.city) + "</b> — " + loc.count + " event" + (loc.count === 1 ? "" : "s");
    html += '<ul class="map-popup">';
    (loc.events || []).forEach(function (ev) {
      var title = ev.url
        ? '<a href="' + encodeURI(ev.url) + '" target="_blank" rel="noopener">' + esc(ev.title) + "</a>"
        : esc(ev.title);
      html += '<li><span class="when">' + esc(ev.when) + "</span> " + title + "</li>";
    });
    if (loc.more > 0) {
      html += "<li>…and " + loc.more + " more</li>";
    }
    html += "</ul>";
    marker.bindPopup(html, { maxHeight: 260, maxWidth: 320 });
    points.push([loc.lat, loc.lon]);
  });

  if (points.length > 1) {
    map.fitBounds(points, { padding: [30, 30], maxZoom: 12 });
  } else if (points.length === 1) {
    map.setView(points[0], 11);
  } else {
    map.setView([center ? center.lat : 37.39, center ? center.lon : -122.08], 10);
  }
  // The container may have just been inserted by htmx; recompute its size.
  setTimeout(function () {
    map.invalidateSize();
  }, 60);
}
