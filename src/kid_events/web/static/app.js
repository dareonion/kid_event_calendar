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
      sources: checkedValues("sources"),
      branch: form.elements.branch.value,
      hideUnknown: form.elements.hide_unknown.checked,
      sort: form.elements.sort.value,
    };
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
    // Empty source selection means "no source filter" (matches the live app).
    var sourceSet = null;
    if (state.sources.length) {
      sourceSet = {};
      state.sources.forEach(function (s) { sourceSet[s] = true; });
    }

    var matched = events.filter(function (ev) {
      if (desired) {
        var hit = (ev.age_bands || []).some(function (b) { return desired[b]; });
        if (!hit) return false;
      }
      if (miles != null) {
        if (ev.distance_mi == null) {
          if (state.hideUnknown) return false;
        } else if (ev.distance_mi > miles) {
          return false;
        }
      }
      var start = parseLocal(ev.start);
      if (start < windowStart || start > dateTo) return false;
      if (sourceSet && !sourceSet[ev.source_key]) return false;
      if (state.branch && ev.location_name !== state.branch) return false;
      if (state.keyword) {
        var hay = (ev.title + "\n" + (ev.description || "")).toLowerCase();
        if (hay.indexOf(state.keyword) === -1) return false;
      }
      return true;
    });

    matched.sort(function (a, b) {
      if (state.sort === "distance") {
        var au = a.distance_mi == null, bu = b.distance_mi == null;
        if (au !== bu) return au ? 1 : -1;
        var diff = (a.distance_mi || 0) - (b.distance_mi || 0);
        if (diff) return diff;
      }
      return parseLocal(a.start) - parseLocal(b.start);
    });
    return matched;
  }

  // --- list rendering (port of _event_list.html) --------------------------
  function cardHtml(ev, d, groupByDay) {
    var dist = ev.distance_mi != null
      ? '<span class="distance">' + ev.distance_mi.toFixed(1) + " mi</span>" : "";
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
        groups[key] = { city: ev.city || "Unknown location", lat: ev.lat, lon: ev.lon, events: [] };
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
      '<p class="hint">Markers are placed at each city\'s center (events are located by ' +
      "city, not exact address). Click a marker to see its events.</p>" +
      '<div id="map"></div>';

    if (window.initEventMap) {
      window.initEventMap({
        center: data.center,
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

  form.addEventListener("change", render);
  var debounced = debounce(render, 300);
  ["age", "keyword"].forEach(function (name) {
    var el = form.elements[name];
    if (el) el.addEventListener("input", debounced);
  });

  render();
})();
