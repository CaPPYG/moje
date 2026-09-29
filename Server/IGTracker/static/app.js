/* ─── IG Analytics Tracker Client Script (v2.0) ─────────────────────────── */
const PREFIX = window.location.pathname.split('/').filter(Boolean)[0] === 'ig' ? '/ig' : '';

// ─── Toast Notifikácie ────────────────────────────────────────────────────────
window.showToast = function(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  let icon = 'info-circle';
  if (type === 'success') icon = 'check-circle';
  if (type === 'error') icon = 'exclamation-circle';
  if (type === 'warning') icon = 'triangle-exclamation';
  toast.innerHTML = `<i class="fas fa-${icon}"></i> <span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
};

// ─── Prepínanie Pohľadov (Tabuľka vs Porovnanie) ──────────────────────────────
window.switchView = function(viewName) {
  const tabTableBtn = document.getElementById('tabTableBtn');
  const tabCompareBtn = document.getElementById('tabCompareBtn');
  const tableView = document.getElementById('tableView');
  const compareView = document.getElementById('compareView');

  if (viewName === 'compare') {
    if (tabTableBtn) tabTableBtn.classList.remove('active');
    if (tabCompareBtn) tabCompareBtn.classList.add('active');
    if (tableView) tableView.style.display = 'none';
    if (compareView) compareView.style.display = 'block';
    renderComparison();
  } else {
    if (tabCompareBtn) tabCompareBtn.classList.remove('active');
    if (tabTableBtn) tabTableBtn.classList.add('active');
    if (compareView) compareView.style.display = 'none';
    if (tableView) tableView.style.display = 'block';
  }
};

// ─── Vykreslenie Porovnania Progressu (Leaderboards) ──────────────────────────
async function renderComparison() {
  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/compare`);
    const data = await res.json();
    if (!res.ok || data.status !== 'ok' || !data.comparison) return;

    const c = data.comparison;
    renderLeaderboardList('compareFollowerGrowthList', c.by_follower_growth, a => {
      const d = a.delta_followers || 0;
      return {
        valNum: Math.max(0, d),
        valText: d > 0 ? `+${d}` : `${d}`,
        badgeClass: d > 0 ? 'color: #34d399;' : (d < 0 ? 'color: #f87171;' : 'color: #94a3b8;')
      };
    });

    renderLeaderboardList('compareViewsList', c.by_views, a => {
      const v = a.total_views || 0;
      return {
        valNum: v,
        valText: a.total_views_fmt || '0',
        badgeClass: 'color: #38bdf8;'
      };
    });

    renderLeaderboardList('compareEngagementList', c.by_engagement, a => {
      const e = a.engagement_rate || 0;
      return {
        valNum: e,
        valText: `${e} %`,
        badgeClass: 'color: #fbbf24;'
      };
    });

    renderLeaderboardList('compareAvgViewsList', c.by_avg_views, a => {
      const av = a.avg_views || 0;
      return {
        valNum: av,
        valText: a.avg_views_fmt || '0',
        badgeClass: 'color: #ec4899;'
      };
    });

  } catch (err) {
    console.error('Chyba pri načítaní porovnania:', err);
  }
}

function renderLeaderboardList(containerId, list, valExtractor) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!list || list.length === 0) {
    container.innerHTML = '<div style="color: #64748b; font-size: 0.85rem; padding: 12px; text-align: center;">Žiadne dáta na porovnanie. Pridajte profily.</div>';
    return;
  }

  const maxVal = Math.max(...list.map(a => valExtractor(a).valNum), 1);
  let html = '';

  list.forEach((acc, idx) => {
    const rank = idx + 1;
    const rankClass = rank === 1 ? 'rank-1' : (rank === 2 ? 'rank-2' : (rank === 3 ? 'rank-3' : ''));
    const meta = valExtractor(acc);
    const pct = Math.max(5, Math.min(100, Math.round((meta.valNum / maxVal) * 100)));

    html += `
      <div class="compare-item">
        <div class="compare-rank ${rankClass}">${rank}</div>
        <img src="${acc.avatar_url}" alt="@${acc.username}" class="compare-avatar" onerror="this.src='https://ui-avatars.com/api/?name=${acc.username}&background=random'">
        <div class="compare-info">
          <div class="compare-top-line">
            <span class="compare-name">@${acc.username}</span>
            <span class="compare-value" style="${meta.badgeClass}">${meta.valText}</span>
          </div>
          <div class="compare-bar-track">
            <div class="compare-bar-fill" style="width: ${pct}%;"></div>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

// ─── Aktualizácia Sumárov v Hlavičke ───────────────────────────────────────────
function updateSummaries() {
  fetch(`${PREFIX}/api/ig-tracker`)
    .then(res => res.json())
    .then(data => {
      if (data.status === 'ok') {
        const countEl = document.getElementById('statAccountsCount');
        const followersEl = document.getElementById('statTotalFollowers');
        const viewsEl = document.getElementById('statTotalViews');
        if (countEl) countEl.textContent = data.count;
        if (followersEl) followersEl.textContent = data.total_followers_fmt || '--';
        if (viewsEl) viewsEl.textContent = data.total_views_fmt || '--';

        const topViewsEl = document.getElementById('statTopReelViews');
        const topMetaEl = document.getElementById('statTopReelMeta');
        if (topViewsEl && data.top_farm_reel) {
          topViewsEl.textContent = data.top_farm_reel.views_fmt || '--';
          if (topMetaEl) {
            topMetaEl.href = data.top_farm_reel.url;
            topMetaEl.innerHTML = `<span>@${data.top_farm_reel.username}</span><span style="color: #f43f5e; margin-left: 4px;"><i class="fas fa-heart"></i> ${data.top_farm_reel.likes_fmt}</span> <i class="fas fa-arrow-up-right-from-square" style="font-size: 0.72em; margin-left: 3px;"></i>`;
          }
        }

        const latestViewsEl = document.getElementById('statLatestReelViews');
        const latestMetaEl = document.getElementById('statLatestReelMeta');
        if (latestViewsEl && data.latest_farm_reel) {
          latestViewsEl.textContent = data.latest_farm_reel.views_fmt || '--';
          if (latestMetaEl) {
            latestMetaEl.href = data.latest_farm_reel.url;
            const perfBadge = data.latest_farm_reel.perf && data.latest_farm_reel.perf.status !== 'none'
              ? `<span class="perf-badge-mini ${data.latest_farm_reel.perf.badge_class}" style="margin-left: 4px;"><i class="${data.latest_farm_reel.perf.icon}"></i> ${data.latest_farm_reel.perf.label}</span>`
              : '';
            latestMetaEl.innerHTML = `<span>@${data.latest_farm_reel.username}</span><span class="post-sep">·</span><span style="color: #94a3b8;">${data.latest_farm_reel.date}</span>${perfBadge} <i class="fas fa-arrow-up-right-from-square" style="font-size: 0.72em; margin-left: 3px;"></i>`;
          }
        }
      }
    })
    .catch(err => console.error('Chyba načítania sumárov:', err));
}

// ─── História Snapshotov Modal ────────────────────────────────────────────────
window.openHistoryModal = async function(id, username) {
  const modal = document.getElementById('historyModal');
  const userEl = document.getElementById('historyModalUsername');
  const tbody = document.getElementById('historyModalTbody');

  if (userEl) userEl.textContent = '@' + username;
  if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #94a3b8; padding: 20px;"><i class="fas fa-spinner fa-spin"></i> Načítavam históriu...</td></tr>';
  if (modal) modal.style.display = 'flex';

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${id}/history?limit=30`);
    const data = await res.json();
    if (res.ok && data.status === 'ok' && data.snapshots) {
      if (data.snapshots.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #64748b; padding: 20px;">Zatiaľ nie sú zaznamenané žiadne snapshoty pre tento účet.</td></tr>';
        return;
      }

      let rowsHtml = '';
      data.snapshots.forEach(s => {
        const dt = s.timestamp ? new Date(s.timestamp).toLocaleString('sk-SK', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
        rowsHtml += `
          <tr>
            <td style="color: #94a3b8; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">${dt}</td>
            <td style="font-weight: 600; color: #fff;">${Number(s.followers || 0).toLocaleString()}</td>
            <td style="color: #38bdf8; font-weight: 600;">${Number(s.total_views || 0).toLocaleString()}</td>
            <td style="color: #cbd5e1;">${Number(s.avg_views || 0).toLocaleString()}</td>
            <td style="color: #fbbf24;">${s.engagement_rate ? s.engagement_rate + ' %' : '-'}</td>
          </tr>
        `;
      });
      tbody.innerHTML = rowsHtml;
    } else {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 20px;">Nepodarilo sa načítať históriu.</td></tr>';
    }
  } catch (err) {
    console.error(err);
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 20px;">Chyba spojenia.</td></tr>';
  }
};

window.closeHistoryModal = function() {
  const modal = document.getElementById('historyModal');
  if (modal) modal.style.display = 'none';
};

// ─── Reels & AI Analýza Modal ────────────────────────────────────────────────
let currentReelsAccountId = null;
let currentReelsUsername = '';
let currentReelsList = [];
let currentSortBy = 'taken_at';

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatStatNum(val) {
  if (val === null || val === undefined) return '0';
  const n = Number(val);
  if (isNaN(n)) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return n.toLocaleString();
}

window.openReelsModal = async function(id, username) {
  currentReelsAccountId = id;
  currentReelsUsername = username;
  currentSortBy = 'taken_at';

  const modal = document.getElementById('reelsModal');
  const userEl = document.getElementById('reelsModalUsername');
  const fullEl = document.getElementById('reelsModalFullName');
  const avatarEl = document.getElementById('reelsModalAvatar');
  const grid = document.getElementById('reelsGrid');
  const searchInput = document.getElementById('reelsSearchInput');

  if (userEl) userEl.textContent = '@' + username;
  if (fullEl) fullEl.textContent = 'Načítavam...';
  if (avatarEl) avatarEl.src = `https://ui-avatars.com/api/?name=${username}&background=random`;
  if (searchInput) searchInput.value = '';
  if (grid) {
    grid.innerHTML = `
      <div class="reels-loading-state" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #94a3b8;">
        <i class="fas fa-spinner fa-spin fa-2x ig-gradient-text" style="margin-bottom: 12px; display: inline-block;"></i>
        <p>Načítavam Reels a AI Content Taxonomy pre @${username}...</p>
      </div>
    `;
  }

  // Reset sort buttons
  document.querySelectorAll('.reels-sort-group .sort-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sort === 'taken_at');
  });

  if (modal) modal.style.display = 'flex';
  await loadAccountReels(id, 'taken_at');
};

window.closeReelsModal = function() {
  const modal = document.getElementById('reelsModal');
  if (modal) modal.style.display = 'none';
};

async function loadAccountReels(id, sortBy = 'taken_at') {
  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${id}/reels?sort_by=${sortBy}`);
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      currentReelsList = data.reels || [];

      // Update Header Info
      const fullEl = document.getElementById('reelsModalFullName');
      const avatarEl = document.getElementById('reelsModalAvatar');
      if (data.account) {
        if (fullEl) fullEl.textContent = data.account.full_name || `@${data.account.username}`;
        if (avatarEl && data.account.avatar_url) avatarEl.src = data.account.avatar_url;
      }

      // Update Summary Strip
      const s = data.summary || {};
      const countEl = document.getElementById('reelsCountVal');
      const totalViewsEl = document.getElementById('reelsTotalViewsVal');
      const avgViewsEl = document.getElementById('reelsAvgViewsVal');
      const topViewsEl = document.getElementById('reelsTopViewsVal');

      if (countEl) countEl.textContent = s.reels_count || data.count || 0;
      if (totalViewsEl) totalViewsEl.textContent = s.total_views_fmt || '0';
      if (avgViewsEl) avgViewsEl.textContent = s.avg_views_fmt || '0';
      if (topViewsEl) {
        topViewsEl.textContent = (s.top_reel && s.top_reel.views_fmt) ? s.top_reel.views_fmt : '0';
      }

      renderReelsList();
    } else {
      const grid = document.getElementById('reelsGrid');
      if (grid) {
        grid.innerHTML = `
          <div class="reels-error-state" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ef4444;">
            <i class="fas fa-exclamation-triangle fa-2x" style="margin-bottom: 12px; display: inline-block;"></i>
            <p>${escapeHtml(data.message || 'Nepodarilo sa načítať reels.')}</p>
          </div>
        `;
      }
    }
  } catch (err) {
    console.error(err);
    const grid = document.getElementById('reelsGrid');
    if (grid) {
      grid.innerHTML = `
        <div class="reels-error-state" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ef4444;">
          <i class="fas fa-wifi fa-2x" style="margin-bottom: 12px; display: inline-block;"></i>
          <p>Chyba komunikácie so serverom.</p>
        </div>
      `;
    }
  }
}

window.renderReelsList = function(filterQuery = '') {
  const grid = document.getElementById('reelsGrid');
  if (!grid) return;

  const q = (filterQuery || (document.getElementById('reelsSearchInput')?.value || '')).trim().toLowerCase();

  let list = currentReelsList;
  if (q) {
    list = list.filter(r => {
      const cap = (r.caption || '').toLowerCase();
      const ai = (r.accessibility_caption || '').toLowerCase();
      const topStr = Array.isArray(r.topics) ? r.topics.join(' ').toLowerCase() : '';
      const mus = ((r.music_title || '') + ' ' + (r.music_artist || '')).toLowerCase();
      return cap.includes(q) || ai.includes(q) || topStr.includes(q) || mus.includes(q);
    });
  }

  if (list.length === 0) {
    if (q) {
      grid.innerHTML = `
        <div class="reels-empty-state" style="grid-column: 1 / -1; text-align: center; padding: 50px 20px; color: #94a3b8;">
          <i class="fas fa-filter-circle-xmark fa-2x" style="color: #64748b; margin-bottom: 10px; display: inline-block;"></i>
          <p>Žiadne Reels nevyhovujú filtru „${escapeHtml(q)}“.</p>
          <button class="btn-refresh" style="margin-top: 12px;" onclick="document.getElementById('reelsSearchInput').value=''; renderReelsList();">Zrušiť filter</button>
        </div>
      `;
    } else {
      grid.innerHTML = `
        <div class="reels-empty-state" style="grid-column: 1 / -1; text-align: center; padding: 50px 20px; color: #94a3b8;">
          <div class="empty-icon ig-gradient-text" style="font-size: 2.5rem; margin-bottom: 12px;"><i class="fas fa-film"></i></div>
          <h3 style="color: #fff; font-size: 1.15rem; margin-bottom: 8px;">Zatiaľ žiadne uložené Reels pre tento profil</h3>
          <p style="font-size: 0.9rem; max-width: 480px; margin: 0 auto; color: #94a3b8;">Spusťte rýchlu synchronizáciu cez HTML alebo stiahnite celú históriu profilu cez Apify.</p>
          <div style="display: flex; gap: 12px; margin-top: 20px; justify-content: center; flex-wrap: wrap;">
            <button class="btn-sync-fast" onclick="syncCurrentReelsFast()"><i class="fas fa-bolt"></i> Rýchla synchronizácia (HTML)</button>
            <button class="btn-sync-full" onclick="syncCurrentReelsFull()"><i class="fas fa-cloud-arrow-down"></i> Stiahnuť históriu (Apify)</button>
          </div>
        </div>
      `;
    }
    return;
  }

  let html = '';
  list.forEach(r => {
    const shortcode = escapeHtml(r.shortcode || '');
    const url = r.url || `https://www.instagram.com/reel/${shortcode}/`;
    const views = r.views_fmt || formatStatNum(r.views_count || 0);
    const likes = r.likes_fmt || formatStatNum(r.likes_count || 0);
    const comments = r.comments_fmt || formatStatNum(r.comments_count || 0);
    const relDate = r.taken_at_relative || 'Aktuálne';
    const thumb = r.thumbnail_url || '';
    const caption = escapeHtml(r.caption || '');
    const aiCaption = (r.accessibility_caption || '').trim();
    const topics = Array.isArray(r.topics) ? r.topics.filter(t => !String(t).startsWith('#')) : [];

    // Hashtags extracted from caption
    let hashtagsHtml = '';
    if (caption) {
      const hts = caption.match(/#[A-Za-z0-9_áčďéíĺľňóôŕšťúýžÁČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]+/g);
      if (hts && hts.length > 0) {
        hashtagsHtml = `<div class="reel-hashtags-row"><span class="hashtags-label">Hashtagy:</span> ` + 
          hts.slice(0, 5).map(h => `<span class="hashtag-pill">${escapeHtml(h)}</span>`).join(' ') + `</div>`;
      }
    }

    // AI Topics pills (Real Meta Content Taxonomy)
    let topicsHtml = '';
    if (topics.length > 0) {
      topics.forEach(t => {
        const cleanT = escapeHtml(String(t));
        topicsHtml += `<span class="topic-pill" title="Oficiálna tematická kategória Instagramu (FYP Algoritmus)"><i class="fas fa-tag"></i> ${cleanT}</span>`;
      });
    }

    // Music info
    let musicHtml = '';
    if (r.music_title) {
      const mText = escapeHtml(r.music_artist ? `${r.music_artist} – ${r.music_title}` : r.music_title);
      musicHtml = `<div class="reel-music-info" title="Hudba / Zvuk: ${mText}"><i class="fas fa-music"></i> <span>${mText}</span></div>`;
    }

    // AI Caption Box
    let aiBoxHtml = '';
    if (aiCaption || topicsHtml) {
      aiBoxHtml = `
        <div class="reel-ai-box">
          ${aiCaption ? `
            <div class="ai-box-header">
              <span class="ai-box-title"><i class="fas fa-robot ig-gradient-text"></i> Čo vidí AI (Meta Computer Vision):</span>
            </div>
            <div class="ai-caption-text">"${escapeHtml(aiCaption)}"</div>
          ` : ''}
          ${topicsHtml ? `
            <div class="ai-topics-container">
              <div class="ai-topics-title"><i class="fas fa-bullseye ig-gradient-text"></i> Instagram AI Kategórie (FYP):</div>
              <div class="ai-topics-list">${topicsHtml}</div>
            </div>
          ` : ''}
          ${!aiCaption || !topicsHtml ? `
            <div class="ai-box-actions" style="margin-top: 4px; text-align: right;">
              <button type="button" class="btn-enrich-single" onclick="enrichSingleReel('${shortcode}', this)" title="Donačítať detailnú AI analýzu pre toto video"><i class="fas fa-wand-magic-sparkles"></i> Doplniť AI</button>
            </div>
          ` : ''}
        </div>
      `;
    } else {
      aiBoxHtml = `
        <div class="reel-ai-box ai-box-empty">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <span class="ai-empty-text"><i class="fas fa-brain" style="opacity: 0.6;"></i> AI analýza zatiaľ nenačítaná.</span>
            <button type="button" class="btn-enrich-single" onclick="enrichSingleReel('${shortcode}', this)" title="Stiahnuť Meta AI popis a tematické kategórie"><i class="fas fa-wand-magic-sparkles"></i> Načítať AI</button>
          </div>
        </div>
      `;
    }

    html += `
      <div class="reel-card" data-shortcode="${shortcode}">
        <div class="reel-thumbnail-wrap">
          ${thumb ? `<img src="${thumb}" class="reel-thumbnail" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">` : ''}
          <div class="reel-thumb-fallback" style="${thumb ? 'display: none;' : 'display: flex;'}">
            <i class="fas fa-film fa-2x ig-gradient-text"></i>
          </div>
          <div class="reel-badge-top-left">
            <span class="badge-views"><i class="fas fa-play"></i> ${views}</span>
          </div>
          <div class="reel-badge-top-right">
            <a href="${url}" target="_blank" rel="noopener noreferrer" class="reel-link-btn" title="Otvoriť Reel na Instagrame">
              <i class="fas fa-arrow-up-right-from-square"></i>
            </a>
          </div>
        </div>

        <div class="reel-content">
          <div class="reel-stats-bar">
            <span class="reel-stat-item stat-likes" title="Lajky"><i class="fas fa-heart"></i> ${likes}</span>
            <span class="reel-stat-item stat-comments" title="Komentáre"><i class="fas fa-comment"></i> ${comments}</span>
            <span class="reel-stat-item stat-date" title="Dátum publikovania"><i class="fas fa-clock"></i> ${relDate}</span>
          </div>

          ${musicHtml}

          ${caption ? `<div class="reel-caption">${caption}</div>` : ''}
          ${hashtagsHtml}

          ${aiBoxHtml}

          <div class="reel-card-footer">
            <a href="${url}" target="_blank" rel="noopener noreferrer" class="btn-open-reel">
              <i class="fab fa-instagram"></i> Otvoriť Reel na Instagrame
            </a>
          </div>
        </div>
      </div>
    `;
  });

  grid.innerHTML = html;
};

window.filterReelsList = function() {
  const query = document.getElementById('reelsSearchInput')?.value || '';
  renderReelsList(query);
};

window.sortReels = function(sortKey, btn) {
  currentSortBy = sortKey;
  document.querySelectorAll('.reels-sort-group .sort-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  if (sortKey === 'views_count') {
    currentReelsList.sort((a, b) => (b.views_count || 0) - (a.views_count || 0));
  } else if (sortKey === 'likes_count') {
    currentReelsList.sort((a, b) => (b.likes_count || 0) - (a.likes_count || 0));
  } else if (sortKey === 'comments_count') {
    currentReelsList.sort((a, b) => (b.comments_count || 0) - (a.comments_count || 0));
  } else {
    currentReelsList.sort((a, b) => {
      const pinDiff = (b.is_pinned || 0) - (a.is_pinned || 0);
      if (pinDiff !== 0) return pinDiff;
      const timeA = a.taken_at ? new Date(a.taken_at).getTime() : 0;
      const timeB = b.taken_at ? new Date(b.taken_at).getTime() : 0;
      return timeB - timeA;
    });
  }

  renderReelsList();
};

window.syncCurrentReelsFast = async function() {
  if (!currentReelsAccountId) return;
  const btn = document.getElementById('btnSyncReelsFast');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rýchla synchronizácia...';
  }

  showToast(`Sťahujem najnovšie Reels pre @${currentReelsUsername} cez HTML...`, 'info');

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${currentReelsAccountId}/sync-reels-fast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast(data.message || 'Reels úspešne synchronizované!', 'success');
      await loadAccountReels(currentReelsAccountId, currentSortBy);
      updateSummaries();
      renderComparison();
    } else {
      showToast(data.message || 'Upozornenie pri synchronizácii.', 'warning');
      await loadAccountReels(currentReelsAccountId, currentSortBy);
      updateSummaries();
      renderComparison();
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba spojenia pri rýchlej synchronizácii.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-bolt"></i> Rýchla synchronizácia (HTML)';
    }
  }
};

window.syncCurrentReelsFull = async function() {
  if (!currentReelsAccountId) return;
  const btn = document.getElementById('btnSyncReelsFull');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sťahujem históriu (Apify)...';
  }

  showToast(`Spúšťam plné sťahovanie histórie Reels pre @${currentReelsUsername} cez Apify...`, 'info');

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${currentReelsAccountId}/sync-reels-full`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit: 100 })
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast(data.message || 'História úspešne stiahnutá!', 'success');
      await loadAccountReels(currentReelsAccountId, currentSortBy);
      updateSummaries();
      renderComparison();
    } else {
      showToast(data.message || 'Chyba pri sťahovaní cez Apify.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba spojenia pri Apify synchronizácii.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-cloud-arrow-down"></i> Stiahnuť históriu (Apify)';
    }
  }
};

window.enrichSingleReel = async function(shortcode, btn) {
  if (!shortcode) return;
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI...';
  }

  showToast(`Sťahujem Meta AI analýzu pre video ${shortcode}...`, 'info');

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/reel/${encodeURIComponent(shortcode)}/enrich-ai`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast(data.message || 'AI analýza úspešne načítaná!', 'success');
      await loadAccountReels(currentReelsAccountId, currentSortBy);
    } else {
      showToast(data.message || 'Nepodarilo sa stiahnuť AI dáta.', 'warning');
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba spojenia pri AI analýze.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
};

window.enrichAllCurrentReelsAI = async function() {
  if (!currentReelsAccountId) return;
  const btn = document.getElementById('btnEnrichAllAI');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzujem všetky...';
  }

  showToast(`Sťahujem Meta AI popis a kategórie pre všetky videá...`, 'info');

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${currentReelsAccountId}/enrich-all-ai`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast(data.message || 'AI analýza dokončená!', 'success');
      await loadAccountReels(currentReelsAccountId, currentSortBy);
    } else {
      showToast(data.message || 'Chyba pri hromadnej AI analýze.', 'warning');
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba spojenia pri AI analýze.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-brain"></i> Analyzovať AI';
    }
  }
};

// ─── Inicializácia Formularov a Event Listenerov ──────────────────────────────
window.deleteAccount = async function(id, username) {
  if (!confirm(`Naozaj chcete odstrániť účet @${username} zo sledovania?`)) {
    return;
  }

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${id}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast(`Účet @${username} bol zmazaný.`, 'info');
      const row = document.getElementById(`row-${id}`);
      if (row) {
        row.style.opacity = '0';
        row.style.transform = 'translateX(20px)';
        row.style.transition = 'all 0.3s ease';
        setTimeout(() => {
          row.remove();
          updateSummaries();
          renderComparison();
          const tbody = document.getElementById('accountsTbody');
          if (tbody && tbody.children.length === 0) {
            window.location.reload();
          }
        }, 300);
      }
    } else {
      showToast(data.message || 'Chyba pri mazaní účtu.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba komunikácie pri mazaní.', 'error');
  }
};

// ─── Inicializácia Formularov a Event Listenerov ──────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const addForm = document.getElementById('addAccountForm');
  const usernameInput = document.getElementById('usernameInput');
  const btnAdd = document.getElementById('btnAddAccount');
  const btnSync = document.getElementById('btnSyncAll');
  const syncSpinner = document.getElementById('syncSpinner');

  // Close modals on click outside or Escape
  const historyModal = document.getElementById('historyModal');
  if (historyModal) {
    historyModal.addEventListener('click', (e) => {
      if (e.target === historyModal) closeHistoryModal();
    });
  }
  const reelsModal = document.getElementById('reelsModal');
  if (reelsModal) {
    reelsModal.addEventListener('click', (e) => {
      if (e.target === reelsModal) closeReelsModal();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeHistoryModal();
      closeReelsModal();
    }
  });

  // Pridanie profilu
  if (addForm) {
    addForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const uname = usernameInput.value.trim().replace(/^@/, '');
      if (!uname) return;

      btnAdd.disabled = true;
      btnAdd.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Hľadám...';

      try {
        const res = await fetch(`${PREFIX}/api/ig-tracker/add`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: uname })
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
          showToast(data.message || `Účet @${uname} bol pridaný!`, 'success');
          usernameInput.value = '';
          setTimeout(() => window.location.reload(), 600);
        } else {
          showToast(data.message || 'Chyba pri pridávaní účtu.', 'error');
        }
      } catch (err) {
        console.error(err);
        showToast('Chyba komunikácie so serverom.', 'error');
      } finally {
        btnAdd.disabled = false;
        btnAdd.innerHTML = '<i class="fas fa-plus"></i> Sledovať profil';
      }
    });
  }

  // Manuálna synchronizácia cez Sync button
  if (btnSync) {
    btnSync.addEventListener('click', async () => {
      btnSync.disabled = true;
      if (syncSpinner) syncSpinner.classList.add('fa-spin');

      showToast('Prebieha manuálna synchronizácia profilov z Instagramu...', 'info');

      try {
        const res = await fetch(`${PREFIX}/api/ig-tracker/sync`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
          showToast(data.message || 'Dáta boli úspešne obnovené!', 'success');
          setTimeout(() => window.location.reload(), 800);
        } else {
          showToast(data.message || 'Chyba synchronizácie.', 'error');
        }
      } catch (err) {
        console.error(err);
        showToast('Chyba spojenia pri synchronizácii.', 'error');
      } finally {
        btnSync.disabled = false;
        if (syncSpinner) syncSpinner.classList.remove('fa-spin');
      }
    });
  }

  // ─── Automatická synchronizácia pri otvorení webu ─────────────────────────
  async function checkAndAutoSyncOnOpen() {
    const lastSyncTime = parseInt(localStorage.getItem('ig_last_auto_sync_ts') || '0', 10);
    const now = Date.now();
    // Ak od poslednej synchronizácie ubehlo viac ako 3 minúty (alebo prvé otvorenie)
    if (now - lastSyncTime > 3 * 60 * 1000) {
      localStorage.setItem('ig_last_auto_sync_ts', now.toString());
      if (btnSync) btnSync.disabled = true;
      if (syncSpinner) syncSpinner.classList.add('fa-spin');
      showToast('Otvorenie webu: Načítavam najnovšie čísla z Instagramu...', 'info');

      try {
        const res = await fetch(`${PREFIX}/api/ig-tracker/sync`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
          showToast('Najnovšie čísla boli úspešne stiahnuté!', 'success');
          setTimeout(() => window.location.reload(), 900);
        }
      } catch (err) {
        console.error('Chyba auto-syncu pri štarte:', err);
      } finally {
        if (btnSync) btnSync.disabled = false;
        if (syncSpinner) syncSpinner.classList.remove('fa-spin');
      }
    }
  }

  // Načítanie sumárov a porovnania pri štarte
  updateSummaries();
  renderComparison();
  checkAndAutoSyncOnOpen();
});
