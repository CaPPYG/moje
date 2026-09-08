/* Studio WEB – frontend logika */
"use strict";

/* ── URL prefix (beh pod /cappytools cez Nginx) ── */
function U(p) {
  if (!p || /^(https?:)?\/\//.test(p)) return p;
  return (window.BASE || "") + p;
}
var _fetch = window.fetch;
window.fetch = function (url, opts) {
  if (typeof url === "string") url = U(url);
  return _fetch.call(window, url, opts);
};

/* ── helpers ── */
function showErr(id, msg) { var el = document.getElementById(id); el.textContent = msg; el.classList.remove("hidden"); }
function hideErr(id) { var el = document.getElementById(id); if (el) el.classList.add("hidden"); }

/* ── Taby ── */
document.querySelectorAll(".nav-tab").forEach(function (t) {
  t.addEventListener("click", function () {
    document.querySelectorAll(".nav-tab").forEach(function (x) { x.classList.remove("active"); });
    t.classList.add("active");
    document.querySelectorAll(".tabsec").forEach(function (s) { s.classList.add("hidden"); });
    document.getElementById("tab-" + t.dataset.tab).classList.remove("hidden");
  });
});

/* ── Drop zóny ── */
function bindDrop(dropId, inputId, labelId) {
  var drop = document.getElementById(dropId);
  var input = document.getElementById(inputId);
  var label = labelId ? document.getElementById(labelId) : null;
  if (!drop) return;
  drop.addEventListener("click", function () { input.click(); });
  drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", function () { drop.classList.remove("over"); });
  drop.addEventListener("drop", function (e) {
    e.preventDefault(); drop.classList.remove("over");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      if (label) label.textContent = e.dataTransfer.files[0].name;
    }
  });
  input.addEventListener("change", function () {
    if (label && input.files.length) label.textContent = input.files[0].name;
  });
}
bindDrop("frameDrop", "frameFile", null);
bindDrop("audioDrop", "audioFile", null);
bindDrop("plDrop", "plFile", null);

/* ── Spoofer: jeden súbor alebo celý priečinok ── */
function spoofCollect() {
  var out = [];
  var f = document.getElementById("spoofFile");
  var d = document.getElementById("spoofFolder");
  for (var i = 0; i < f.files.length; i++) out.push(f.files[i]);
  for (var j = 0; j < d.files.length; j++) out.push(d.files[j]);
  return out;
}
function spoofLabel() {
  var files = spoofCollect();
  var el = document.getElementById("spoofName");
  if (!files.length) { el.textContent = "Žiadny súbor"; return; }
  if (files.length === 1) { el.textContent = files[0].webkitRelativePath || files[0].name; return; }
  el.textContent = "📁 " + files.length + " súborov";
}
var spoofDrop = document.getElementById("spoofDrop");
if (spoofDrop) {
  spoofDrop.addEventListener("click", function () { document.getElementById("spoofFile").click(); });
  spoofDrop.addEventListener("dragover", function (e) { e.preventDefault(); spoofDrop.classList.add("over"); });
  spoofDrop.addEventListener("dragleave", function () { spoofDrop.classList.remove("over"); });
  spoofDrop.addEventListener("drop", function (e) {
    e.preventDefault(); spoofDrop.classList.remove("over");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      document.getElementById("spoofFolder").files = e.dataTransfer.files;
      spoofLabel();
    }
  });
}
document.getElementById("spoofFile").addEventListener("change", spoofLabel);
document.getElementById("spoofFolder").addEventListener("change", spoofLabel);

/* ── Spoofer ── */
function filtersAll(v) {
  document.querySelectorAll(".fcard input[type=checkbox]").forEach(function (c) { c.checked = v; });
}
function filtersReset() { location.reload(); }

function runSpoof() {
  var files = spoofCollect();
  if (!files.length) { showErr("spoofErr", "Vyber súbor alebo priečinok."); return; }
  var fd = new FormData();
  files.forEach(function (fl) { fd.append("file", fl, fl.webkitRelativePath || fl.name); });
  fd.append("use_location", document.getElementById("locEnabled").checked ? "1" : "0");
  fd.append("lat", document.getElementById("locLat").value);
  fd.append("lon", document.getElementById("locLon").value);
  fd.append("jitter", document.getElementById("locJitter").value);
  fd.append("copies", document.getElementById("locCopies").value);
  fd.append("orig_enabled", document.getElementById("origEnabled").checked ? "1" : "0");
  fd.append("drive_output", document.getElementById("driveOutput").checked ? "1" : "0");
  document.querySelectorAll(".fcard input[type=checkbox]").forEach(function (c) {
    fd.append(c.id + "_enabled", c.checked ? "1" : "0");
  });
  document.querySelectorAll(".fcard input[type=number]").forEach(function (n) {
    fd.append(n.id, n.value);
  });
  fd.append("fp_enabled", document.getElementById("fpEnabled").checked ? "1" : "0");
  fd.append("fp_mode", document.getElementById("fpMode").value);
  fd.append("fp_device", document.getElementById("fpDevice").value);
  fd.append("fp_days", document.getElementById("fpDays").value);
  fd.append("fp_rand_date", document.getElementById("fpRandDate").checked ? "1" : "0");
  fd.append("fp_rand_uid", document.getElementById("fpRandUid").checked ? "1" : "0");
  fd.append("fp_no_sig", document.getElementById("fpNoSig").checked ? "1" : "0");
  fd.append("fp_title", document.getElementById("fpTitle").value);
  fd.append("fp_artist", document.getElementById("fpArtist").value);
  fd.append("fp_comment", document.getElementById("fpComment").value);

  var btn = document.getElementById("spoofBtn");
  btn.disabled = true;
  hideErr("spoofErr");
  fetch("/api/spoof", { method: "POST", body: fd }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { showErr("spoofErr", d.error); btn.disabled = false; return; }
      pollJob(d.job, "spoofBar", "spoofLog", function (j) {
        btn.disabled = false;
        if (j.result && j.result.download) {
          var n = j.result.files || 1;
          var via = j.result.via === "drive" ? " (cez Google Drive)" : "";
          document.getElementById("spoofLog").textContent +=
            "\n\n✓ Hotovo (" + n + " " + (n === 1 ? "súbor" : "súborov") + ")" + via + " → " + j.result.download;
          var dl = document.getElementById("spoofDl");
          if (dl) {
            dl.href = U(j.result.download);
            dl.textContent = "⬇ Stiahnuť " + (j.result.files ? "všetko (ZIP, " + n + " súborov)" : "súbor");
            dl.style.display = "block";
            setTimeout(function () { dl.click(); }, 400);
          }
        }
      });
    }).catch(function (e) { showErr("spoofErr", String(e)); btn.disabled = false; });
}

/* ── Frames / Audio ── */
function runFrames() {
  var f = document.getElementById("frameFile");
  if (!f.files.length) { showErr("frameErr", "Vyber video."); return; }
  var fd = new FormData();
  fd.append("file", f.files[0]);
  fd.append("mode", document.getElementById("frameMode").value);
  fd.append("value", document.getElementById("frameValue").value);
  fd.append("fmt", document.getElementById("frameFmt").value);
  fd.append("quality", document.getElementById("frameQuality").value);
  var btn = document.getElementById("frameBtn");
  btn.disabled = true; hideErr("frameErr");
  fetch("/api/frames", { method: "POST", body: fd }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { showErr("frameErr", d.error); btn.disabled = false; return; }
      pollJob(d.job, "frameBar", "frameLog", function (j) {
        btn.disabled = false;
        if (j.result && j.result.download) {
          document.getElementById("frameLog").textContent +=
            "\n\n✓ " + j.result.files + " frameov → " + j.result.download;
        }
      });
    }).catch(function (e) { showErr("frameErr", String(e)); btn.disabled = false; });
}

function audioFmtChanged() {
  var lossless = ["wav", "flac"].indexOf(document.getElementById("audioFmt").value) !== -1;
  document.getElementById("audioBitrate").disabled = lossless;
}
function runAudio() {
  var f = document.getElementById("audioFile");
  if (!f.files.length) { showErr("audioErr", "Vyber video."); return; }
  var fd = new FormData();
  fd.append("file", f.files[0]);
  fd.append("fmt", document.getElementById("audioFmt").value);
  fd.append("bitrate", document.getElementById("audioBitrate").value);
  var btn = document.getElementById("audioBtn");
  btn.disabled = true; hideErr("audioErr");
  fetch("/api/audio", { method: "POST", body: fd }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { showErr("audioErr", d.error); btn.disabled = false; return; }
      pollJob(d.job, "audioBar", "audioLog", function (j) {
        btn.disabled = false;
        if (j.result && j.result.download) {
          document.getElementById("audioLog").textContent +=
            "\n\n✓ Hotovo → " + j.result.download;
        }
      });
    }).catch(function (e) { showErr("audioErr", String(e)); btn.disabled = false; });
}

/* ── Job polling ── */
function pollJob(jid, barId, logId, doneCb) {
  var barEl = document.getElementById(barId);
  var logEl = document.getElementById(logId);
  if (barEl && barEl.parentElement) barEl.parentElement.classList.remove("hidden");
  var iv = setInterval(function () {
    fetch("/api/job/" + jid).then(function (r) { return r.json(); }).then(function (j) {
      if (barEl) barEl.style.width = (j.total ? Math.round(j.progress / j.total * 100) : 0) + "%";
      if (logEl && j.log) logEl.textContent = j.log.join("\n");
      if (j.status === "done") {
        clearInterval(iv);
        doneCb(j);
      } else if (j.status === "error") {
        clearInterval(iv);
        if (logEl) logEl.textContent = (logEl.textContent || "") + "\n✗ " + (j.error || "chyba");
        alert("Chyba:\n" + (j.error || "neznáma"));
      }
    }).catch(function () {});
  }, 1000);
}

/* ── Cloaker ── */
var cloakLinks = (window.INIT && window.INIT.cloaker && window.INIT.cloaker.links) || [];
function cloakRender() {
  var el = document.getElementById("cloakList");
  el.innerHTML = "";
  cloakLinks.forEach(function (ln, i) {
    var d = document.createElement("div");
    d.className = "rowline";
    d.innerHTML = "<span class='slug'>" + ln.slug + "</span>" +
      "<span class='src'>" + ln.url + "</span>" +
      "<button class='btn mini ghost' onclick='cloakDel(" + i + ")'>✕</button>";
    el.appendChild(d);
  });
  if (!cloakLinks.length) el.innerHTML = "<div class='hint'>Zatiaľ žiadne odkazy – pridaj nižšie.</div>";
}
function cloakAdd() {
  var s = document.getElementById("cloakSlug").value.trim();
  var u = document.getElementById("cloakUrl").value.trim();
  if (!s || !u) { alert("Vyplň slug aj odkaz."); return; }
  if (/\s|\//.test(s)) { alert("Slug nesmie obsahovať medzery ani lomku."); return; }
  cloakLinks.push({ slug: s, url: u, title: "" });
  document.getElementById("cloakSlug").value = "";
  document.getElementById("cloakUrl").value = "";
  cloakRender();
}
function cloakDel(i) { cloakLinks.splice(i, 1); cloakRender(); }
function cloakSave() {
  var base = document.getElementById("cloakBase").value.trim();
  fetch("/api/cloaker/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_url: base, links: cloakLinks })
  }).then(function (r) { return r.json(); }).then(function (d) {
    if (d.ok) alert("Uložené.");
  });
}
function cloakGenerate() {
  cloakSave();
  fetch("/api/cloaker/generate").then(function (r) { return r.json(); }).then(function (d) {
    var el = document.getElementById("cloakOut");
    el.textContent = d.links.length ? "" : "Žiadne odkazy.";
    d.links.forEach(function (ln) {
      el.textContent += (ln.title ? "# " + ln.title + "\n" : "") + ln.cloak + "  →  " + ln.url + "\n";
    });
  });
}

/* ── Planner ── */
var plVideos = [];
var plDevices = [];
function plRenderVideos() {
  var el = document.getElementById("plVideos");
  el.innerHTML = "";
  plVideos.forEach(function (v, i) {
    var d = document.createElement("div");
    d.className = "rowline";
    d.innerHTML = "<span>🎞 " + v + "</span><button class='btn mini ghost' onclick='plDelVideo(" + i + ")'>✕</button>";
    el.appendChild(d);
  });
  if (!plVideos.length) el.innerHTML = "<div class='hint'>Prázdny vault – nahraj videá.</div>";
}
function plDelVideo(i) { plVideos.splice(i, 1); plRenderVideos(); plSave(); }
function plRenderDevices() {
  var el = document.getElementById("plDevices");
  el.innerHTML = "";
  plDevices.forEach(function (d, i) {
    var row = document.createElement("div");
    row.className = "rowline";
    row.innerHTML = "<span>📱 <b>" + d.name + "</b> · " + d.city + " · " + d.model +
      "</span><button class='btn mini ghost' onclick='plDelDev(" + i + ")'>✕</button>";
    el.appendChild(row);
  });
  if (!plDevices.length) el.innerHTML = "<div class='hint'>Zatiaľ žiadne zariadenia.</div>";
}
function plDelDev(i) { plDevices.splice(i, 1); plRenderDevices(); plSave(); }
function devAdd() {
  var name = document.getElementById("devName").value.trim();
  if (!name) { alert("Zadaj názov zariadenia."); return; }
  plDevices.push({ name: name, city: document.getElementById("devCity").value, model: document.getElementById("devModel").value });
  document.getElementById("devName").value = "";
  plRenderDevices(); plSave();
}
function plUploadFile(file) {
  var fd = new FormData();
  fd.append("file", file);
  fetch("/api/upload/planner", { method: "POST", body: fd }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.file) { plVideos.push(d.file); plRenderVideos(); plSave(); }
    });
}
document.getElementById("plFile").addEventListener("change", function () {
  Array.prototype.forEach.call(this.files, function (f) { plUploadFile(f); });
  this.value = "";
});
document.getElementById("plDrop").addEventListener("drop", function (e) {
  e.preventDefault();
  if (e.dataTransfer.files) Array.prototype.forEach.call(e.dataTransfer.files, function (f) { plUploadFile(f); });
});
function plSave() {
  var st = {
    videos: plVideos, devices: plDevices,
    vmin: document.getElementById("plVmin").value,
    vmax: document.getElementById("plVmax").value,
    start: document.getElementById("plStart").value || new Date().toISOString().slice(0, 10)
  };
  fetch("/api/planner/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(st)
  });
}
function plGenerate() {
  if (!plVideos.length || !plDevices.length) { showErr("plErr", "Pridaj videá aj zariadenia."); return; }
  plSave();
  hideErr("plErr");
  fetch("/api/planner/generate", { method: "POST" }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { showErr("plErr", d.error); return; }
      pollJob(d.job, "plBar", "plLog", function (j) { plShowResult(); });
    });
}
function plShowResult() {
  fetch("/api/planner/status").then(function (r) { return r.json(); }).then(function (d) {
    var el = document.getElementById("plResult");
    if (!d.ready) { el.innerHTML = ""; return; }
    var html = "<div class='card'><h2>📱 Zariadenia – QR / linky</h2><div class='qr-grid'>";
    d.dev_links.forEach(function (dl) {
      var full = d.base_url + dl.url;
      html += "<div class='qr-card'><img src='" + U("/api/qr?url=" + encodeURIComponent(full)) + "'>" +
        "<div class='dname'>" + dl.name + "</div>" +
        "<div class='small' style='font-size:11px;color:#888;word-break:break-all'>" + full + "</div></div>";
    });
    html += "</div></div>";
    if (d.schedule && d.schedule.length) {
      html += "<div class='card'><h2>📅 Rozvrh</h2><div style='overflow-x:auto'><table class='sched'><tr><th>Dátum</th>";
      d.devices.forEach(function (dd) { html += "<th>" + dd.name + "</th>"; });
      html += "</tr>";
      d.schedule.forEach(function (e) {
        html += "<tr><td>" + e.date + "</td>";
        d.devices.forEach(function (dd) {
          var vids = (e.devices && e.devices[dd.name]) || [];
          html += "<td>" + vids.map(function (v) {
            return "<a href='" + U("/device/" + encodeURIComponent(dd.name) + "/" + e.date) + "'>" + v + "</a>";
          }).join("<br>") + "</td>";
        });
        html += "</tr>";
      });
      html += "</table></div></div>";
    }
    el.innerHTML = html;
  });
}

/* ── init ── */
(function () {
  if (window.INIT && window.INIT.planner) {
    plVideos = window.INIT.planner.videos || [];
    plDevices = window.INIT.planner.devices || [];
    if (window.INIT.planner.start) document.getElementById("plStart").value = window.INIT.planner.start;
  }
  if (!document.getElementById("plStart").value) document.getElementById("plStart").value = new Date().toISOString().slice(0, 10);
  plRenderVideos(); plRenderDevices();
  cloakRender();
  audioFmtChanged();
  plShowResult();
  if (window.INIT && window.INIT.is_admin) { loadAdmin(); loadDriveStatus(); }
})();

/* ── Admin ── */
function fmtSize(b) {
  if (b >= 1073741824) return (b / 1073741824).toFixed(2) + " GB";
  if (b >= 1048576) return (b / 1048576).toFixed(1) + " MB";
  if (b >= 1024) return Math.round(b / 1024) + " KB";
  return b + " B";
}
function loadAdmin() {
  fetch("/api/admin/users").then(function (r) { return r.json(); }).then(function (d) {
    document.getElementById("adminTotal").textContent =
      "Celkovo užívateľov: " + d.users.length + " · dáta spolu: " + fmtSize(d.total);
    var el = document.getElementById("adminList");
    el.innerHTML = "";
    d.users.forEach(function (u) {
      var row = document.createElement("div");
      row.className = "rowline";
      var badge = u.role === "admin" ? "<span style='color:#c084fc;font-weight:700'>👑 admin</span>" : "<span style='color:#888'>user</span>";
      row.innerHTML =
        "<span><b>" + u.email + "</b> · " + u.created + " · " + fmtSize(u.size) + " · " + badge + "</span>" +
        "<span>" +
        (u.role !== "admin" ?
          "<button class='btn mini ghost' onclick='adminRole(\"" + u.email + "\",\"admin\")'>Povýšiť</button> " +
          "<button class='btn mini red' onclick='adminDel(\"" + u.email + "\")'>Zmazať</button>" : "") +
        (u.role === "admin" && u.email !== d.admin ?
          "<button class='btn mini ghost' onclick='adminRole(\"" + u.email + "\",\"user\")'>Znížiť</button>" : "") +
        "</span>";
      el.appendChild(row);
    });
  });
}
function adminDel(email) {
  if (!confirm("Naozaj zmazať účet " + email + " aj so všetkými dátami?")) return;
  fetch("/api/admin/users/" + encodeURIComponent(email), { method: "DELETE" })
    .then(function (r) { return r.json(); }).then(function (d) {
      if (d.ok) loadAdmin(); else alert(d.error || "chyba");
    });
}
function adminRole(email, role) {
  fetch("/api/admin/users/" + encodeURIComponent(email) + "/role", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: role })
  }).then(function (r) { return r.json(); }).then(function (d) {
    if (d.ok) loadAdmin(); else alert(d.error || "chyba");
  });
}

/* ── Google Drive (admin) ── */
function loadDriveStatus() {
  fetch("/api/drive/status").then(function (r) { return r.json(); }).then(function (d) {
    var el = document.getElementById("driveStatus");
    if (d.connected) {
      el.innerHTML = "<span style='color:#22c55e'>● Pripojené</span> · užívatelia: " + d.users.length;
    } else if (d.has_creds) {
      el.innerHTML = "⏸ credentials.json je, ale token chýba – klikni „Pripojiť Google Drive“.";
    } else {
      el.innerHTML = "✗ chýba <b>data/credentials.json</b> – pozri návod nižšie.";
    }
  });
}
function driveSync() {
  var el = document.getElementById("driveLog");
  el.textContent = "Spúšťam…";
  fetch("/api/drive/sync", { method: "POST" }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { el.textContent = "✗ " + d.error; return; }
      var out = "";
      for (var k in d.results) out += k + " → " + d.results[k] + "\n";
      el.textContent = out || "hotovo";
    });
}

/* ── Reels Downloader ── */
function runReels() {
  var ta = document.getElementById("reelsUrls");
  var urls = ta.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
  if (!urls.length) { showErr("reelsErr", "Vlož aspoň jeden odkaz."); return; }
  var btn = document.getElementById("reelsBtn");
  btn.disabled = true; hideErr("reelsErr");
  var log = document.getElementById("reelsLog");
  log.textContent = "";
  var linksEl = document.getElementById("reelsLinks");
  if (linksEl) linksEl.innerHTML = "";
  fetch("/api/reels", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls: urls })
  }).then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { showErr("reelsErr", d.error); btn.disabled = false; return; }
      pollJob(d.job, "reelsBar", "reelsLog", function (j) {
        btn.disabled = false;
        if (j.result) {
          var res = j.result;
          var msg = "\n\n✓ Stiahnuté: " + res.ok + " · chyby: " + res.fail;
          if (linksEl) linksEl.innerHTML = "";
          if (res.results && res.results.length) {
            msg += "\nNahrané do Google Drive (AI RAK):";
            res.results.forEach(function (r, idx) {
              msg += "\n  → " + r.drive;
              if (linksEl) {
                var a = document.createElement("a");
                a.href = r.drive;
                a.target = "_blank";
                a.className = "btn green block";
                a.style.textDecoration = "none";
                a.style.marginTop = "6px";
                a.innerHTML = "⬇ Stiahnuť video #" + (idx + 1) + " (Google Drive)";
                linksEl.appendChild(a);
              }
            });
          }
          document.getElementById("reelsLog").textContent += msg;
        }
      });
    }).catch(function (e) { showErr("reelsErr", String(e)); btn.disabled = false; });
}

/* ── Prehľad užívateľov (admin) ── */







