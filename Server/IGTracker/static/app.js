/* ─── IG Analytics Tracker Client Script ─────────────────────────────── */
const PREFIX = window.location.pathname.split('/').filter(Boolean)[0] === 'ig' ? '/ig' : '';

let currentModalAccountId = null;

// ─── Toast Notifikácie ───────────────────────────────────────────────
window.showToast = function(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  let icon = 'info-circle';
  if (type === 'success') icon = 'check-circle';
  if (type === 'error') icon = 'exclamation-circle';
  toast.innerHTML = `<i class="fas fa-${icon}"></i> <span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
};

// ─── Token Modal Metódy ──────────────────────────────────────────────
window.openTokenModal = function(id, username, currentUserId, isLinked) {
  currentModalAccountId = id;
  const modal = document.getElementById('tokenModal');
  const userEl = document.getElementById('modalAccountUsername');
  const tokenInput = document.getElementById('modalAccessToken');
  const userIdInput = document.getElementById('modalUserId');
  const btnUnlink = document.getElementById('btnUnlinkToken');
  const statusBox = document.getElementById('tokenVerifyStatus');

  if (userEl) userEl.textContent = '@' + username;
  if (tokenInput) tokenInput.value = '';
  if (userIdInput) userIdInput.value = currentUserId || '';
  if (statusBox) {
    statusBox.style.display = 'none';
    statusBox.textContent = '';
  }

  if (btnUnlink) {
    btnUnlink.style.display = isLinked ? 'inline-flex' : 'none';
  }

  if (modal) modal.style.display = 'flex';
};

window.closeTokenModal = function() {
  const modal = document.getElementById('tokenModal');
  if (modal) modal.style.display = 'none';
  currentModalAccountId = null;
};

window.saveToken = async function() {
  if (!currentModalAccountId) return;
  const tokenInput = document.getElementById('modalAccessToken');
  const userIdInput = document.getElementById('modalUserId');
  const btnSave = document.getElementById('btnSaveToken');
  const statusBox = document.getElementById('tokenVerifyStatus');

  const token = tokenInput ? tokenInput.value.trim() : '';
  const userId = userIdInput ? userIdInput.value.trim() : '';

  if (!token) {
    showToast('Vložte Meta Access Token.', 'error');
    if (tokenInput) tokenInput.focus();
    return;
  }

  btnSave.disabled = true;
  btnSave.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Overujem...';
  if (statusBox) {
    statusBox.style.display = 'block';
    statusBox.className = 'token-verify-box';
    statusBox.style.background = 'rgba(56, 189, 248, 0.15)';
    statusBox.style.color = '#38bdf8';
    statusBox.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Overujem token cez Meta Graph API...';
  }

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${currentModalAccountId}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: token, ig_user_id: userId })
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      if (statusBox) {
        statusBox.className = 'token-verify-box ok';
        statusBox.style.background = '';
        statusBox.style.color = '';
        statusBox.textContent = '✅ ' + (data.message || 'Token úspešne overený!');
      }
      showToast('Token bol úspešne prepojený!', 'success');
      setTimeout(() => window.location.reload(), 1200);
    } else {
      if (statusBox) {
        statusBox.className = 'token-verify-box err';
        statusBox.style.background = '';
        statusBox.style.color = '';
        statusBox.textContent = '❌ ' + (data.message || 'Chyba overenia tokenu');
      }
      showToast(data.message || 'Chyba overenia tokenu.', 'error');
    }
  } catch (err) {
    console.error(err);
    if (statusBox) {
      statusBox.className = 'token-verify-box err';
      statusBox.style.background = '';
      statusBox.style.color = '';
      statusBox.textContent = '❌ Chyba spojenia so serverom.';
    }
    showToast('Chyba spojenia so serverom.', 'error');
  } finally {
    btnSave.disabled = false;
    btnSave.innerHTML = '<i class="fas fa-check"></i> Overiť a Uložiť';
  }
};

window.unlinkToken = async function() {
  if (!currentModalAccountId) return;
  if (!confirm('Naozaj chcete odpojiť token od tohto účtu?')) return;

  const btnUnlink = document.getElementById('btnUnlinkToken');
  if (btnUnlink) btnUnlink.disabled = true;

  try {
    const res = await fetch(`${PREFIX}/api/ig-tracker/${currentModalAccountId}/token`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      showToast('Token bol úspešne odpojený.', 'info');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.message || 'Chyba pri odpájaní tokenu.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Chyba spojenia.', 'error');
  } finally {
    if (btnUnlink) btnUnlink.disabled = false;
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const addForm = document.getElementById('addAccountForm');
  const usernameInput = document.getElementById('usernameInput');
  const btnAdd = document.getElementById('btnAddAccount');
  const btnSync = document.getElementById('btnSyncAll');
  const syncSpinner = document.getElementById('syncSpinner');

  // Close modal on background click or Escape key
  const modal = document.getElementById('tokenModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeTokenModal();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeTokenModal();
  });

  // ─── Aktualizácia sumárov ────────────────────────────────────────────
  function updateSummaries() {
    fetch(`${PREFIX}/api/ig-tracker`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok') {
          const countEl = document.getElementById('statAccountsCount');
          const followersEl = document.getElementById('statTotalFollowers');
          const viewsEl = document.getElementById('statTotalViews');
          if (countEl) countEl.textContent = data.count;
          if (followersEl) followersEl.textContent = data.total_followers_fmt;
          if (viewsEl) viewsEl.textContent = data.total_views_fmt;
        }
      })
      .catch(err => console.error('Chyba načítania sumárov:', err));
  }

  updateSummaries();

  // ─── Pridanie nového účtu ─────────────────────────────────────────────
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

  // ─── Force-Refresh / Sync ────────────────────────────────────────────
  if (btnSync) {
    btnSync.addEventListener('click', async () => {
      btnSync.disabled = true;
      if (syncSpinner) syncSpinner.classList.add('fa-spin');

      showToast('Prebieha aktualizácia profilov z Instagramu...', 'info');

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

  // ─── Zmazanie účtu ───────────────────────────────────────────────────
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

  // ─── Health Check Trigger ───────────────────────────────────────────
  window.triggerHealthCheck = async function() {
    const btn = document.getElementById('btnHealthCheck');
    const spinner = document.getElementById('healthSpinner');
    if (btn) btn.disabled = true;
    if (spinner) spinner.classList.add('fa-spin');

    showToast('Spúšťam diagnostiku a overenie tokenov cez Meta Graph API...', 'info');

    try {
      const res = await fetch(`${PREFIX}/api/ig-tracker/health-check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        const h = data.healthy_count || 0;
        const w = data.warning_count || 0;
        const e = data.error_count || 0;
        showToast(`Diagnostika dokončená: 🟢 ${h} zdravých, 🟡 ${w} vyžaduje akciu, 🔴 ${e} chýb`, w > 0 || e > 0 ? 'warning' : 'success');
        setTimeout(() => window.location.reload(), 1200);
      } else {
        showToast(data.message || 'Chyba pri diagnostike zdravia účtov.', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Chyba spojenia pri kontrole zdravia.', 'error');
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.classList.remove('fa-spin');
    }
  };

  // ─── Settings & Webhook Modal ───────────────────────────────────────
  window.openSettingsModal = async function() {
    const modal = document.getElementById('settingsModal');
    const statusBox = document.getElementById('settingsStatusBox');
    if (statusBox) statusBox.style.display = 'none';

    try {
      const res = await fetch(`${PREFIX}/api/ig-tracker/settings`);
      const data = await res.json();
      if (res.ok && data.status === 'ok' && data.settings) {
        const s = data.settings;
        const dw = document.getElementById('settingDiscordWebhook');
        const tt = document.getElementById('settingTelegramToken');
        const tc = document.getElementById('settingTelegramChat');
        const gw = document.getElementById('settingGenericWebhook');
        if (dw) dw.value = s.discord_webhook_url || '';
        if (tt) tt.value = s.telegram_bot_token || '';
        if (tc) tc.value = s.telegram_chat_id || '';
        if (gw) gw.value = s.generic_webhook_url || '';
      }
    } catch (err) {
      console.error('Chyba načítania nastavení:', err);
    }

    if (modal) modal.style.display = 'flex';
  };

  window.closeSettingsModal = function() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.style.display = 'none';
  };

  window.saveSettings = async function() {
    const btn = document.getElementById('btnSaveSettings');
    const dw = document.getElementById('settingDiscordWebhook');
    const tt = document.getElementById('settingTelegramToken');
    const tc = document.getElementById('settingTelegramChat');
    const gw = document.getElementById('settingGenericWebhook');
    const statusBox = document.getElementById('settingsStatusBox');

    const payload = {
      discord_webhook_url: dw ? dw.value.trim() : '',
      telegram_bot_token: tt ? tt.value.trim() : '',
      telegram_chat_id: tc ? tc.value.trim() : '',
      generic_webhook_url: gw ? gw.value.trim() : ''
    };

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ukladám...';
    }

    try {
      const res = await fetch(`${PREFIX}/api/ig-tracker/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        showToast('Nastavenia webhookov boli uložené!', 'success');
        if (statusBox) {
          statusBox.style.display = 'block';
          statusBox.className = 'token-verify-box ok';
          statusBox.textContent = '✅ Nastavenia boli úspešne uložené do databázy.';
        }
        setTimeout(() => closeSettingsModal(), 1000);
      } else {
        showToast(data.message || 'Chyba pri ukladaní nastavení.', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Chyba spojenia pri ukladaní nastavení.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-check"></i> Uložiť nastavenia';
      }
    }
  };

  window.testWebhook = async function() {
    const dw = document.getElementById('settingDiscordWebhook');
    const statusBox = document.getElementById('settingsStatusBox');
    const webhookUrl = dw ? dw.value.trim() : '';

    if (statusBox) {
      statusBox.style.display = 'block';
      statusBox.className = 'token-verify-box';
      statusBox.style.background = 'rgba(56, 189, 248, 0.15)';
      statusBox.style.color = '#38bdf8';
      statusBox.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Odosielam testovaciu notifikáciu...';
    }

    try {
      const res = await fetch(`${PREFIX}/api/ig-tracker/settings/test-webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook_url: webhookUrl })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        showToast('Testovací alert bol úspešne odoslaný!', 'success');
        if (statusBox) {
          statusBox.className = 'token-verify-box ok';
          statusBox.style.background = '';
          statusBox.style.color = '';
          statusBox.textContent = '✅ Testovací alert bol odoslaný. Skontrolujte Discord/Telegram kanál.';
        }
      } else {
        showToast(data.message || 'Zlyhalo odoslanie testovacieho webhooku.', 'error');
        if (statusBox) {
          statusBox.className = 'token-verify-box err';
          statusBox.style.background = '';
          statusBox.style.color = '';
          statusBox.textContent = '❌ ' + (data.message || 'Chyba pri odoslaní alertu.');
        }
      }
    } catch (err) {
      console.error(err);
      showToast('Chyba spojenia pri teste webhooku.', 'error');
      if (statusBox) {
        statusBox.className = 'token-verify-box err';
        statusBox.style.background = '';
        statusBox.style.color = '';
        statusBox.textContent = '❌ Chyba spojenia so serverom.';
      }
    }
  };

  // ─── Nastavenie % USA publika ─────────────────────────────────────────
  window.promptSetAudience = async function(accountId, username, currentVal) {
    const defaultVal = (currentVal !== null && currentVal !== undefined) ? currentVal : '';
    const input = prompt(`Zadajte % USA publika pre @${username} (napr. 45 alebo 58.5):`, defaultVal);
    if (input === null) return; // používateľ zrušil

    const trimmed = input.trim();
    const pct = trimmed === '' ? null : parseFloat(trimmed.replace(',', '.'));
    if (pct !== null && (isNaN(pct) || pct < 0 || pct > 100)) {
      alert('Zadajte platné percento od 0 do 100 (alebo nechajte prázdne pre zmazanie).');
      return;
    }

    try {
      const res = await fetch(`${PREFIX}/api/ig-tracker/${accountId}/audience`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usa_audience_pct: pct })
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        if (typeof showToast === 'function') {
          showToast(`% USA publika pre @${username} bolo uložené!`, 'success');
        }
        setTimeout(() => window.location.reload(), 500);
      } else {
        alert(data.message || 'Chyba pri ukladaní.');
      }
    } catch (err) {
      console.error(err);
      alert('Chyba spojenia so serverom.');
    }
  };
});
