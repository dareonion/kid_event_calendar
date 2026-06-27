/* Client-side filtering for the static (published) Kid Event Calendar page.
   Mirrors the server-side logic in filters.py / ages.py so the no-server page
   behaves like the live HTMX app. Reads the event set + config embedded by
   build.py from <script id="events-data">, then re-renders the list or map
   whenever a filter changes. */
(function () {
  "use strict";

  var dataEl = document.getElementById("events-data");
  var form = document.getElementById("filters");
  var results = document.getElementById("results");
  if (!dataEl || !form || !results) return;

  var data = JSON.parse(dataEl.textContent);
  var events = data.events || [];

  // value -> label, value -> {min,max,is_kid}, for badges and age->band mapping.
  var bandLabel = {};
  var bandMeta = {};
  (data.bands || []).forEach(function (b) {
    bandLabel[b.value] = b.label;
    bandMeta[b.value] = b;
  });

  var radiusByKey = {};
  (data.radius_presets || []).forEach(function (p) {
    radiusByKey[p.key] = p.miles;
  });

  // --- active center + distance (recomputed client-side) ------------------
  // distance_mi is baked from the default center at build time; we recompute it
  // from whatever center the user picks, so it stays correct after recentering.
  function lsGet(key) {
    try { var v = window.localStorage.getItem(key); return v ? JSON.parse(v) : null; }
    catch (e) { return null; }
  }
  function lsSet(key, val) {
    try { window.localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }
  var CENTER_KEY = "kec:center", ADDR_KEY = "kec:addresses", UNITS_KEY = "kec:units";

  var defaultCenter = data.center || { name: "Mountain View", lat: 37.3894, lon: -122.0819 };
  var activeCenter = defaultCenter;
  var savedAddresses = lsGet(ADDR_KEY) || []; // [{label,lat,lon}]
  var units = lsGet(UNITS_KEY) === "km" ? "km" : "mi";

  var EARTH_RADIUS_MI = 3958.7613;
  function haversineMiles(lat1, lon1, lat2, lon2) {
    function rad(deg) { return (deg * Math.PI) / 180; }
    var dphi = rad(lat2 - lat1), dlambda = rad(lon2 - lon1);
    var a = Math.sin(dphi / 2) * Math.sin(dphi / 2) +
      Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dlambda / 2) * Math.sin(dlambda / 2);
    return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  function distanceOf(ev) {
    if (ev.lat == null || ev.lon == null) return null;
    return haversineMiles(activeCenter.lat, activeCenter.lon, ev.lat, ev.lon);
  }
  function formatDistance(mi) {
    if (mi == null) return "";
    return units === "km" ? (mi * 1.609344).toFixed(1) + " km" : mi.toFixed(1) + " mi";
  }
  function radiusLabel(miles) {
    if (miles == null) return "Any distance";
    return units === "km" ? "Within ~" + Math.round(miles * 1.609344) + " km" : "Within ~" + miles + " mi";
  }
  function syncRadiusLabels() {
    Array.prototype.forEach.call(form.elements.radius.options, function (opt) {
      var miles = radiusByKey[opt.value];
      opt.textContent = radiusLabel(miles === undefined ? null : miles);
    });
  }

  // --- date/time helpers --------------------------------------------------
  // Event timestamps are already localized (Pacific) with an offset, e.g.
  // "2026-06-22T10:30:00-07:00". We display the wall-clock part verbatim,
  // independent of the viewer's timezone, by rebuilding it as a UTC instant.
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function parseLocal(iso) {
    var m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return new Date(NaN);
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
  }
  function dayLabel(d) {
    return DAYS[d.getUTCDay()] + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCDate();
  }
  function timeLabel(d) {
    var h = d.getUTCHours();
    var m = d.getUTCMinutes();
    var ampm = h < 12 ? "AM" : "PM";
    var h12 = h % 12 === 0 ? 12 : h % 12;
    return h12 + ":" + (m < 10 ? "0" + m : m) + " " + ampm;
  }
  function whenLabel(d) {
    return dayLabel(d) + ", " + timeLabel(d);
  }
  function dateKey(d) {
    return d.getUTCFullYear() + "-" + d.getUTCMonth() + "-" + d.getUTCDate();
  }

  // --- age parsing (port of ages.parse_age_to_months / child_age_to_bands)-
  function parseAgeToMonths(text) {
    if (!text) return null;
    var m = text.trim().match(/(\d+(?:\.\d+)?)\s*(months?|mos?|mths?|m|years?|yrs?|y)?/i);
    if (!m) return null;
    var value = parseFloat(m[1]);
    var unit = (m[2] || "").toLowerCase();
    return unit.charAt(0) === "m" ? Math.round(value) : Math.round(value * 12);
  }
  function childAgeToBands(months) {
    var set = {};
    (data.bands || []).forEach(function (b) {
      if (b.is_kid && b.min <= months && months <= b.max) set[b.value] = true;
    });
    set.all_ages = true;
    return set;
  }

  // --- text helpers -------------------------------------------------------
  function esc(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : value;
    return div.innerHTML;
  }
  function truncate(s, length) {
    if (s.length <= length + 5) return s;
    var sub = s.slice(0, length);
    var lastSpace = sub.lastIndexOf(" ");
    if (lastSpace > 0) sub = sub.slice(0, lastSpace);
    return sub + "…";
  }

  // --- read the current filter state from the form ------------------------
  function checkedValues(name) {
    return Array.prototype.slice
      .call(form.querySelectorAll('input[name="' + name + '"]:checked'))
      .map(function (el) { return el.value; });
  }
  function readState() {
    var viewEl = form.querySelector('input[name="view"]:checked');
    return {
      view: viewEl ? viewEl.value : "list",
      age: form.elements.age.value,
      bands: checkedValues("bands"),
      radius: form.elements.radius.value,
      days: parseInt(form.elements.days.value, 10) || data.default_days,
      keyword: form.elements.keyword.value.trim().toLowerCase(),
      libs: checkedValues("libs"),
      hideUnknown: form.elements.hide_unknown.checked,
      sort: form.elements.sort.value,
    };
  }

  // System-scoped key matching build.py's branch_key(); events with no named
  // location share a per-system "other" bucket.
  function branchKey(ev) {
    return ev.source_key + "::" + (ev.location_name || "__other__");
  }

  function desiredBands(state) {
    var months = parseAgeToMonths(state.age);
    if (months != null) return childAgeToBands(months);
    if (state.bands.length) {
      var set = {};
      state.bands.forEach(function (b) { set[b] = true; });
      set.all_ages = true;
      return set;
    }
    return null; // no age filter
  }

  // --- filtering (port of filters._matches / apply_filters) ---------------
  function filterEvents(state) {
    var desired = desiredBands(state);
    var miles = radiusByKey[state.radius]; // undefined for "any" -> no limit
    if (miles === undefined) miles = null;
    var windowStart = parseLocal(data.window_start);
    var dateTo = new Date(windowStart.getTime() + state.days * 86400000);
    // Pure set membership: every event has a branch key, every key has a box.
    var libSet = {};
    state.libs.forEach(function (k) { libSet[k] = true; });

    var matched = events.filter(function (ev) {
      if (desired) {
        var hit = (ev.age_bands || []).some(function (b) { return desired[b]; });
        if (!hit) return false;
      }
      if (miles != null) {
        var dist = distanceOf(ev);
        if (dist == null) {
          if (state.hideUnknown) return false;
        } else if (dist > miles) {
          return false;
        }
      }
      var start = parseLocal(ev.start);
      if (start < windowStart || start > dateTo) return false;
      if (!libSet[branchKey(ev)]) return false;
      if (state.keyword) {
        var hay = (ev.title + "\n" + (ev.description || "")).toLowerCase();
        if (hay.indexOf(state.keyword) === -1) return false;
      }
      return true;
    });

    matched.sort(function (a, b) {
      if (state.sort === "distance") {
        var da = distanceOf(a), db = distanceOf(b);
        var au = da == null, bu = db == null;
        if (au !== bu) return au ? 1 : -1;
        var diff = (da || 0) - (db || 0);
        if (diff) return diff;
      }
      return parseLocal(a.start) - parseLocal(b.start);
    });
    return matched;
  }

  // --- list rendering (port of _event_list.html) --------------------------
  function cardHtml(ev, d, groupByDay) {
    var distVal = distanceOf(ev);
    var dist = distVal != null
      ? '<span class="distance">' + formatDistance(distVal) + "</span>" : "";
    var dayInTime = groupByDay ? "" : '<span class="muted">' + dayLabel(d) + "</span>";
    var title = ev.url
      ? '<a href="' + esc(ev.url) + '" target="_blank" rel="noopener">' + esc(ev.title) + "</a>"
      : esc(ev.title);

    var meta = esc(ev.source);
    if (ev.location_name) meta += " · " + esc(ev.location_name);
    if (ev.city) meta += " · " + esc(ev.city);
    if (ev.registration_required) meta += ' · <span class="reg">registration</span>';

    var badges = (ev.age_bands || []).map(function (b) {
      return '<span class="badge">' + esc(bandLabel[b] || b) + "</span>";
    }).join("");
    if (ev.age_inferred) {
      badges += '<span class="badge inferred" title="Age inferred from title/description">~age</span>';
    }
    var desc = ev.description
      ? '<p class="desc">' + esc(truncate(ev.description, 220)) + "</p>" : "";

    return '<article class="card">' +
      '<div class="card-time"><span class="time">' + timeLabel(d) + "</span>" + dayInTime + dist + "</div>" +
      '<div class="card-body"><h3>' + title + "</h3>" +
      '<p class="meta">' + meta + "</p>" +
      '<div class="badges">' + badges + "</div>" + desc +
      "</div></article>";
  }

  function renderList(matched, groupByDay) {
    var n = matched.length;
    var html = '<p class="count">' + n + " event" + (n === 1 ? "" : "s") + "</p>";
    if (n === 0) {
      html += '<p class="empty">No events match these filters. ' +
        "Try widening the distance or age range.</p>";
    }
    var lastKey = null;
    matched.forEach(function (ev) {
      var d = parseLocal(ev.start);
      if (groupByDay) {
        var key = dateKey(d);
        if (key !== lastKey) {
          html += '<h2 class="day-heading">' + dayLabel(d) + "</h2>";
          lastKey = key;
        }
      }
      html += cardHtml(ev, d, groupByDay);
    });
    results.innerHTML = html;
  }

  // --- map rendering (port of _map_payload + map.js call) -----------------
  function round5(x) { return Math.round(x * 100000) / 100000; }

  function renderMap(matched, miles) {
    var groups = {};
    var order = [];
    var unknown = 0;
    matched.forEach(function (ev) {
      if (ev.lat == null || ev.lon == null) { unknown++; return; }
      var key = round5(ev.lat) + "," + round5(ev.lon);
      if (!groups[key]) {
        groups[key] = {
          city: ev.location_name || ev.city || "Unknown location",
          lat: ev.lat, lon: ev.lon, events: [],
        };
        order.push(key);
      }
      groups[key].events.push(ev);
    });

    var locations = order.map(function (key) {
      var g = groups[key];
      var ordered = g.events.slice().sort(function (a, b) {
        return parseLocal(a.start) - parseLocal(b.start);
      });
      var shown = ordered.slice(0, 25);
      return {
        city: g.city, lat: g.lat, lon: g.lon,
        count: ordered.length, more: ordered.length - shown.length,
        events: shown.map(function (e) {
          return { title: e.title, when: whenLabel(parseLocal(e.start)), url: e.url };
        }),
      };
    });
    locations.sort(function (a, b) { return b.count - a.count; });

    var n = matched.length;
    var locN = locations.length;
    var line = n + " event" + (n === 1 ? "" : "s") + " · " +
      locN + " location" + (locN === 1 ? "" : "s") +
      (unknown ? " · " + unknown + " without a mappable location" : "");
    results.innerHTML =
      '<p class="count">' + line + "</p>" +
      '<p class="hint">Each marker is a branch (or city center); distances are from ' +
      esc(activeCenter.name) + ". Click a marker to see its events.</p>" +
      '<div id="map"></div>';

    if (window.initEventMap) {
      window.initEventMap({
        center: activeCenter,
        radius_miles: miles,
        locations: locations,
        unknown: unknown,
      });
    }
  }

  // --- glue ---------------------------------------------------------------
  function render() {
    var state = readState();
    var matched = filterEvents(state);
    if (state.view === "map") {
      var miles = radiusByKey[state.radius];
      renderMap(matched, miles === undefined ? null : miles);
    } else {
      renderList(matched, state.sort === "date");
    }
  }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      if (t) clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }

  // --- favorites + library picker -----------------------------------------
  var FAV_KEY = "kec:favorites";
  var libBoxes = Array.prototype.slice.call(form.querySelectorAll('input[name="libs"]'));
  var allLibKeys = libBoxes.map(function (b) { return b.value; });
  var favBtn = document.getElementById("lib-fav-btn");

  var favorites = {};
  (function loadFavorites() {
    try {
      var raw = window.localStorage.getItem(FAV_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      if (Array.isArray(arr)) arr.forEach(function (k) { favorites[k] = true; });
    } catch (e) { /* localStorage unavailable — favorites just won't persist */ }
  })();
  function saveFavorites() {
    try {
      window.localStorage.setItem(FAV_KEY, JSON.stringify(Object.keys(favorites)));
    } catch (e) { /* ignore */ }
  }
  // Only favorites that still exist in today's data.
  function favoritesInData() {
    return allLibKeys.filter(function (k) { return favorites[k]; });
  }

  function setChecked(keys) {
    var want = {};
    keys.forEach(function (k) { want[k] = true; });
    libBoxes.forEach(function (b) { b.checked = !!want[b.value]; });
    syncGroups();
  }
  function syncGroups() {
    form.querySelectorAll(".lib-group").forEach(function (group) {
      var boxes = group.querySelectorAll('input[name="libs"]');
      var on = 0;
      boxes.forEach(function (b) { if (b.checked) on++; });
      var head = group.querySelector(".lib-group-check");
      head.checked = on === boxes.length;
      head.indeterminate = on > 0 && on < boxes.length;
    });
  }
  function syncStars() {
    form.querySelectorAll(".star").forEach(function (s) {
      var fav = !!favorites[s.dataset.key];
      s.textContent = fav ? "★" : "☆";
      s.classList.toggle("is-fav", fav);
      s.setAttribute("aria-pressed", fav ? "true" : "false");
    });
    if (favBtn) favBtn.disabled = favoritesInData().length === 0;
  }

  // A change to any filter re-renders; library checkboxes also keep the group
  // header (and a group header toggles its branches) in sync first.
  form.addEventListener("change", function (e) {
    var t = e.target;
    if (t.classList && t.classList.contains("lib-group-check")) {
      t.closest(".lib-group")
        .querySelectorAll('input[name="libs"]')
        .forEach(function (b) { b.checked = t.checked; });
    }
    if (t.name === "libs" || (t.classList && t.classList.contains("lib-group-check"))) {
      syncGroups();
    }
    if (t.name === "units") {
      units = t.value === "km" ? "km" : "mi";
      lsSet(UNITS_KEY, units);
      syncRadiusLabels();
    }
    render();
  });

  // All / None / Favorites buttons and the per-branch star toggles.
  form.addEventListener("click", function (e) {
    var action = e.target.closest("[data-lib-action]");
    if (action) {
      var which = action.getAttribute("data-lib-action");
      if (which === "all") setChecked(allLibKeys);
      else if (which === "none") setChecked([]);
      else if (which === "favorites") setChecked(favoritesInData());
      render();
      return;
    }
    var star = e.target.closest(".star");
    if (star) {
      var key = star.dataset.key;
      if (favorites[key]) delete favorites[key];
      else favorites[key] = true;
      saveFavorites();
      syncStars();
      // Starring sets the default for next visit; it doesn't change the current view.
    }
  });

  var debounced = debounce(render, 300);
  ["age", "keyword"].forEach(function (name) {
    var el = form.elements[name];
    if (el) el.addEventListener("input", debounced);
  });

  // --- center location control --------------------------------------------
  var centerName = document.getElementById("center-name");
  var subtitleCenter = document.getElementById("subtitle-center");
  var centerStatus = document.getElementById("center-status");
  var centerInput = document.getElementById("center-address");
  var centerList = document.getElementById("center-list");

  function shortName(name) {
    name = String(name || "");
    return name.length > 42 ? name.slice(0, 40) + "…" : name;
  }
  function sameSpot(a, b) {
    return Math.abs(a.lat - b.lat) < 1e-6 && Math.abs(a.lon - b.lon) < 1e-6;
  }
  function applyCenterLabels() {
    if (centerName) centerName.textContent = shortName(activeCenter.name);
    if (subtitleCenter) subtitleCenter.textContent = shortName(activeCenter.name);
  }
  function setStatus(msg, isError) {
    if (!centerStatus) return;
    centerStatus.textContent = msg || "";
    centerStatus.classList.toggle("error", !!isError);
  }
  function setCenter(center) {
    activeCenter = center;
    lsSet(CENTER_KEY, center);
    applyCenterLabels();
    renderSavedAddresses();
    render();
  }
  function renderSavedAddresses() {
    if (!centerList) return;
    centerList.innerHTML = "";
    savedAddresses.forEach(function (addr, i) {
      var row = document.createElement("div");
      row.className = "center-row";
      var pick = document.createElement("button");
      pick.type = "button";
      pick.className = "pick" + (sameSpot(addr, activeCenter) ? " active" : "");
      pick.textContent = addr.label;
      pick.addEventListener("click", function () {
        setCenter({ name: addr.label, lat: addr.lat, lon: addr.lon });
      });
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "remove";
      rm.title = "Remove";
      rm.textContent = "×";
      rm.addEventListener("click", function () {
        savedAddresses.splice(i, 1);
        lsSet(ADDR_KEY, savedAddresses);
        renderSavedAddresses();
      });
      row.appendChild(pick);
      row.appendChild(rm);
      centerList.appendChild(row);
    });
  }

  function geocode() {
    var q = (centerInput.value || "").trim();
    if (!q) return;
    setStatus("Searching…", false);
    var url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=ca,us&q=" +
      encodeURIComponent(q);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (list) {
        if (!list || !list.length) { setStatus("No match for that address.", true); return; }
        setStatus("", false);
        setCenter({ name: list[0].display_name || q, lat: +list[0].lat, lon: +list[0].lon });
      })
      .catch(function () { setStatus("Address lookup failed — try again.", true); });
  }
  function useMyLocation() {
    if (!navigator.geolocation) { setStatus("Geolocation isn't available here.", true); return; }
    setStatus("Locating…", false);
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        setStatus("", false);
        setCenter({ name: "My location", lat: pos.coords.latitude, lon: pos.coords.longitude });
      },
      function () { setStatus("Couldn't get your location.", true); },
      { timeout: 10000 }
    );
  }
  function saveCurrentCenter() {
    if (sameSpot(activeCenter, defaultCenter)) { setStatus("Set a location first, then Save.", true); return; }
    if (savedAddresses.some(function (a) { return sameSpot(a, activeCenter); })) {
      setStatus("Already saved.", false);
      return;
    }
    savedAddresses.push({ label: shortName(activeCenter.name), lat: activeCenter.lat, lon: activeCenter.lon });
    lsSet(ADDR_KEY, savedAddresses);
    renderSavedAddresses();
    setStatus("Saved on this device.", false);
  }

  document.getElementById("center-set").addEventListener("click", geocode);
  centerInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); geocode(); }
  });
  document.getElementById("center-geo").addEventListener("click", useMyLocation);
  document.getElementById("center-reset").addEventListener("click", function () { setCenter(defaultCenter); });
  document.getElementById("center-save").addEventListener("click", saveCurrentCenter);

  // --- initial state ------------------------------------------------------
  // Library selection: your favorites if you have any (in today's data), else all.
  var startFavs = favoritesInData();
  setChecked(startFavs.length ? startFavs : allLibKeys);
  syncStars();

  // Center + units: reopen on your last-used center, in your last-used unit.
  var persistedCenter = lsGet(CENTER_KEY);
  if (persistedCenter && typeof persistedCenter.lat === "number") activeCenter = persistedCenter;
  applyCenterLabels();
  renderSavedAddresses();
  var unitsRadio = form.querySelector('input[name="units"][value="' + units + '"]');
  if (unitsRadio) unitsRadio.checked = true;
  syncRadiusLabels();

  render();
})();
