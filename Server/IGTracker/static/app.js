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

// ─── Zmazanie Účtu ────────────────────────────────────────────────────────────
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
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeHistoryModal();
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
