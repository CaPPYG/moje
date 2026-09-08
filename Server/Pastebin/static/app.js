/* ─── PasteBin Client Script ─────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const tabTextBtn = document.getElementById('tabTextBtn');
  const tabImageBtn = document.getElementById('tabImageBtn');
  const textContentSection = document.getElementById('textContentSection');
  const imageContentSection = document.getElementById('imageContentSection');
  const pasteTextarea = document.getElementById('pasteTextarea');
  const imageDropzone = document.getElementById('imageDropzone');
  const imageFileInput = document.getElementById('imageFileInput');
  const imagePreviewContainer = document.getElementById('imagePreviewContainer');
  const imagePreviewImg = document.getElementById('imagePreviewImg');
  const imagePreviewInfo = document.getElementById('imagePreviewInfo');
  const pasteForm = document.getElementById('pasteForm');
  const submitBtn = document.getElementById('submitBtn');
  const successModal = document.getElementById('successModal');
  const generatedUrlInput = document.getElementById('generatedUrlInput');
  const btnCopyUrl = document.getElementById('btnCopyUrl');

  // Clipboard elements
  const clipboardSection = document.getElementById('clipboardSection');
  const pastesContainer = document.getElementById('pastesContainer');
  const emptyState = document.getElementById('emptyState');
  const activeCountBadge = document.getElementById('activeCountBadge');
  const pasteSearchInput = document.getElementById('pasteSearchInput');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  const btnRefreshPastes = document.getElementById('btnRefreshPastes');
  const filterBtns = document.querySelectorAll('.filter-btn');

  // QR Modal elements
  const qrModal = document.getElementById('qrModal');
  const qrCodeContainer = document.getElementById('qrCodeContainer');
  const qrUrlInput = document.getElementById('qrUrlInput');
  const btnCopyQrUrl = document.getElementById('btnCopyQrUrl');
  const btnOpenQrUrl = document.getElementById('btnOpenQrUrl');
  const closeQrModal = document.getElementById('closeQrModal');
  const btnCloseQrModal = document.getElementById('btnCloseQrModal');

  let activeTab = 'text'; // 'text' | 'image'
  let selectedFile = null;
  let allPastes = [];
  let currentFilter = 'all'; // 'all' | 'text' | 'image'
  let searchQuery = '';
  let qrCodeInstance = null;

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

  // ─── Pomocné funkcie ─────────────────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatTimeAgo(isoString) {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSec = Math.floor((now - date) / 1000);

      if (diffSec < 45) return 'práve teraz';
      if (diffSec < 90) return 'pred 1 min';
      if (diffSec < 3600) return `pred ${Math.floor(diffSec / 60)} min`;
      if (diffSec < 86400) return `pred ${Math.floor(diffSec / 3600)} hod`;
      if (diffSec < 172800) return 'včera';
      return date.toLocaleDateString('sk-SK', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (e) {
      return '';
    }
  }

  function formatTtl(expiresAt) {
    if (!expiresAt) return null;
    try {
      const expDate = new Date(expiresAt);
      const now = new Date();
      const diffSec = Math.floor((expDate - now) / 1000);

      if (diffSec <= 0) return 'vypršané';
      if (diffSec < 60) return `vyprší o ${diffSec}s`;
      if (diffSec < 3600) return `vyprší o ${Math.round(diffSec / 60)} min`;
      if (diffSec < 86400) return `vyprší o ${Math.round(diffSec / 3600)} hod`;
      return `vyprší o ${Math.round(diffSec / 86400)} dní`;
    } catch (e) {
      return null;
    }
  }

  function copyTextToClipboard(text, onSuccess, onError) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(onSuccess).catch(err => {
        fallbackCopyText(text, onSuccess, onError);
      });
    } else {
      fallbackCopyText(text, onSuccess, onError);
    }
  }

  function fallbackCopyText(text, onSuccess, onError) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(ta);
      if (successful && onSuccess) onSuccess();
      else if (!successful && onError) onError();
    } catch (err) {
      if (onError) onError(err);
    }
  }

  // ─── Prepínanie kariet (Text / Obrázok) ───────────────────────────────
  if (tabTextBtn && tabImageBtn) {
    tabTextBtn.addEventListener('click', () => {
      activeTab = 'text';
      tabTextBtn.classList.add('active');
      tabImageBtn.classList.remove('active');
      if (textContentSection) textContentSection.style.display = 'block';
      if (imageContentSection) imageContentSection.style.display = 'none';
      if (pasteTextarea) pasteTextarea.focus();
    });

    tabImageBtn.addEventListener('click', () => {
      activeTab = 'image';
      tabImageBtn.classList.add('active');
      tabTextBtn.classList.remove('active');
      if (imageContentSection) imageContentSection.style.display = 'block';
      if (textContentSection) textContentSection.style.display = 'none';
    });
  }

  // ─── Podpora TAB klávesy a Ctrl+Enter v editore ────────────────────────
  if (pasteTextarea) {
    pasteTextarea.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = pasteTextarea.selectionStart;
        const end = pasteTextarea.selectionEnd;
        pasteTextarea.value = pasteTextarea.value.substring(0, start) + '  ' + pasteTextarea.value.substring(end);
        pasteTextarea.selectionStart = pasteTextarea.selectionEnd = start + 2;
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (pasteForm) {
          pasteForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
        }
      }
    });
  }

  // ─── Spracovanie zvoleného obrázka ────────────────────────────────────
  function handleImageFile(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      showToast('Vyberte platný súbor obrázka (PNG, JPG, WEBP, GIF).', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast('Maximálna povolená veľkosť obrázka je 10 MB.', 'error');
      return;
    }

    selectedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
      if (imagePreviewImg) imagePreviewImg.src = e.target.result;
      if (imagePreviewInfo) {
        const sz = (file.size / (1024 * 1024)).toFixed(2);
        imagePreviewInfo.textContent = `${file.name} (${sz} MB)`;
      }
      if (imagePreviewContainer) imagePreviewContainer.style.display = 'block';
      if (imageDropzone) imageDropzone.style.display = 'none';
    };
    reader.readAsDataURL(file);

    // Automaticky prepneme na tab obrázok ak sme vložili Ctrl+V
    if (activeTab !== 'image' && tabImageBtn) {
      tabImageBtn.click();
    }
  }

  window.resetImage = function() {
    selectedFile = null;
    if (imageFileInput) imageFileInput.value = '';
    if (imagePreviewContainer) imagePreviewContainer.style.display = 'none';
    if (imageDropzone) imageDropzone.style.display = 'block';
  };

  // ─── Drag & Drop ──────────────────────────────────────────────────────
  if (imageDropzone) {
    imageDropzone.addEventListener('click', () => {
      if (imageFileInput) imageFileInput.click();
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      imageDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        imageDropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      imageDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        imageDropzone.classList.remove('dragover');
      });
    });

    imageDropzone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        handleImageFile(files[0]);
      }
    });
  }

  if (imageFileInput) {
    imageFileInput.addEventListener('change', () => {
      if (imageFileInput.files && imageFileInput.files.length > 0) {
        handleImageFile(imageFileInput.files[0]);
      }
    });
  }

  // ─── Ctrl+V Vloženie zo schránky ──────────────────────────────────────
  window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          showToast('Obrázok vložený zo schránky!', 'info');
          handleImageFile(file);
          break;
        }
      }
    }
  });

  // ─── Odoslanie formulára (Create Paste) ────────────────────────────────
  if (pasteForm) {
    pasteForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const ttl = document.getElementById('ttlSelect').value;
      const burn = document.getElementById('burnCheck').checked ? '1' : '0';
      const password = document.getElementById('passwordInput').value;

      const fd = new FormData();
      fd.append('ttl', ttl);
      fd.append('burn_after_reading', burn);
      if (password) fd.append('password', password);

      if (activeTab === 'image') {
        if (!selectedFile) {
          showToast('Najprv vyberte alebo pretiahnite obrázok.', 'error');
          return;
        }
        fd.append('type', 'image');
        fd.append('file', selectedFile);
      } else {
        const text = pasteTextarea.value.trim();
        if (!text) {
          showToast('Zadajte text alebo kód.', 'error');
          return;
        }
        fd.append('type', 'text');
        fd.append('content', text);
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ukladám...';
      }

      try {
        const res = await fetch('api/paste', {
          method: 'POST',
          body: fd
        });

        const data = await res.json();
        if (res.status === 201 && data.status === 'ok') {
          showToast('Uložené! Záznam je pripravený v schránke.', 'success');
          if (generatedUrlInput) generatedUrlInput.value = data.url;
          if (successModal) {
            successModal.style.display = 'block';
            successModal.scrollIntoView({ behavior: 'smooth' });
          }

          // Vyčistiť polia
          if (pasteTextarea) pasteTextarea.value = '';
          resetImage();

          // Okamžite načítať a zobraziť nový zoznam v schránke
          loadPastes(true);
        } else {
          showToast(data.message || 'Chyba pri vytváraní paste.', 'error');
        }
      } catch (err) {
        console.error(err);
        showToast('Chyba komunikácie so serverom.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Vytvoriť & Uložiť do schránky';
        }
      }
    });
  }

  // ─── Kopírovanie vygenerovanej URL z modalu ───────────────────────────
  if (btnCopyUrl && generatedUrlInput) {
    btnCopyUrl.addEventListener('click', () => {
      const url = generatedUrlInput.value;
      copyTextToClipboard(url, () => {
        showToast('Odkaz skopírovaný do schránky!', 'success');
      });
    });
  }

  // ─── Rýchly Clipboard & História Liniek ────────────────────────────────
  async function loadPastes(silent = false) {
    if (!pastesContainer) return;

    if (!silent && btnRefreshPastes) {
      btnRefreshPastes.classList.add('spinning');
    }

    try {
      const res = await fetch('api/pastes');
      if (res.status === 401) {
        return; // Neautentifikovaný
      }
      const data = await res.json();
      if (data.status === 'ok' && Array.isArray(data.pastes)) {
        allPastes = data.pastes;
        if (activeCountBadge) {
          activeCountBadge.textContent = `${allPastes.length} ${getSlovakItemWord(allPastes.length)}`;
        }
        renderPastes();
      }
    } catch (err) {
      console.error('Chyba pri načítaní záznamov schránky:', err);
    } finally {
      if (btnRefreshPastes) {
        btnRefreshPastes.classList.remove('spinning');
      }
    }
  }

  function getSlovakItemWord(count) {
    if (count === 1) return 'položka';
    if (count >= 2 && count <= 4) return 'položky';
    return 'položiek';
  }

  function renderPastes() {
    if (!pastesContainer) return;

    // Aplikujeme filter a vyhľadávanie
    const q = searchQuery.toLowerCase().trim();
    const filtered = allPastes.filter(p => {
      // Filter podľa typu
      if (currentFilter === 'text' && p.type !== 'text') return false;
      if (currentFilter === 'image' && p.type !== 'image') return false;

      // Filter podľa textu vyhľadávania
      if (q) {
        const matchId = (p.id || '').toLowerCase().includes(q);
        const matchContent = (p.content || '').toLowerCase().includes(q);
        return matchId || matchContent;
      }
      return true;
    });

    if (allPastes.length === 0) {
      pastesContainer.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      return;
    }

    if (filtered.length === 0) {
      if (emptyState) emptyState.style.display = 'none';
      pastesContainer.innerHTML = `
        <div style="text-align: center; padding: 30px; color: var(--text-dim); background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-color);">
          <i class="fas fa-search" style="font-size: 1.5em; margin-bottom: 8px; display: block;"></i>
          Nenašli sa žiadne položky zodpovedajúce filtru "<b>${escapeHtml(searchQuery)}</b>".
        </div>
      `;
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

    let html = '';
    filtered.forEach(p => {
      const isText = p.type === 'text';
      const timeAgo = formatTimeAgo(p.created_at);
      const ttlText = formatTtl(p.expires_at);
      const isBurn = Boolean(p.burn_after_reading);
      const isLock = Boolean(p.has_password);
      const views = p.views_count || 0;

      // Status pills
      let statusPillsHtml = '';
      if (isBurn) {
        statusPillsHtml += `<span class="status-pill pill-burn"><i class="fas fa-fire"></i> 1x Burn</span>`;
      }
      if (isLock) {
        statusPillsHtml += `<span class="status-pill pill-lock"><i class="fas fa-lock"></i> Heslo</span>`;
      }
      if (ttlText) {
        statusPillsHtml += `<span class="status-pill pill-ttl"><i class="fas fa-clock"></i> ${ttlText}</span>`;
      } else if (!isBurn) {
        statusPillsHtml += `<span class="status-pill pill-never"><i class="fas fa-infinity"></i> Trvalý</span>`;
      }
      statusPillsHtml += `<span class="status-pill pill-views" title="Počet zobrazení"><i class="fas fa-eye"></i> ${views}</span>`;

      // Content area
      let contentHtml = '';
      if (isText) {
        const rawContent = p.content || '';
        const lineCount = (rawContent.match(/\n/g) || []).length + 1;
        const needsExpand = lineCount > 4 || rawContent.length > 250;

        contentHtml = `
          <div class="quick-copy-bar">
            <span class="quick-copy-title"><i class="fas fa-bolt" style="color: var(--accent-fire);"></i> Rýchla schránka</span>
            <button type="button" class="btn-fast-copy" data-id="${p.id}" title="Okamžite skopírovať celý text do schránky zariadenia">
              <i class="fas fa-copy"></i> Kopírovať do schránky
            </button>
          </div>
          <div class="snippet-box" id="snippet-${p.id}">${escapeHtml(rawContent)}</div>
          ${needsExpand ? `<button type="button" class="btn-toggle-expand" data-target="snippet-${p.id}"><i class="fas fa-chevron-down"></i> Rozbaliť celé (${lineCount} riadkov)</button>` : ''}
        `;
      } else {
        const rawImgUrl = p.raw_url || `p/${p.id}/raw`;
        const viewUrl = p.url || `p/${p.id}`;
        contentHtml = `
          <div class="image-item-preview">
            <a href="${viewUrl}" target="_blank" class="image-thumb-link" title="Zobraziť obrázok">
              <img src="${rawImgUrl}" alt="Náhľad ${p.id}" loading="lazy">
            </a>
            <div class="image-item-details">
              <div class="image-item-title"><i class="fas fa-image" style="color: #fb923c;"></i> Zdieľaný obrázok #${p.id}</div>
              <div class="image-item-meta">${p.file_mime || 'image/png'}</div>
              <div style="display: flex; gap: 8px;">
                <a href="${rawImgUrl}" target="_blank" class="btn-card-action" style="font-size: 0.82em;">
                  <i class="fas fa-external-link-alt"></i> Zobraziť plnú veľkosť
                </a>
                <a href="${rawImgUrl}" download="paste_${p.id}" class="btn-card-action" style="font-size: 0.82em;">
                  <i class="fas fa-download"></i> Stiahnuť
                </a>
              </div>
            </div>
          </div>
        `;
      }

      // Card item
      html += `
        <div class="paste-card-item" id="paste-item-${p.id}">
          <div class="paste-card-top">
            <div class="paste-meta-left">
              <span class="badge-item-type ${isText ? 'type-text' : 'type-image'}">
                <i class="fas ${isText ? 'fa-file-code' : 'fa-image'}"></i> ${isText ? 'Text' : 'Obrázok'}
              </span>
              <a href="${p.url}" target="_blank" class="paste-id-tag" title="Otvoriť verejný odkaz">#${p.id}</a>
              <span class="paste-time-ago" title="${p.created_at || ''}"><i class="far fa-clock"></i> ${timeAgo}</span>
            </div>
            <div class="paste-meta-right">
              ${statusPillsHtml}
            </div>
          </div>

          <div class="paste-card-content">
            ${contentHtml}
          </div>

          <div class="paste-card-footer">
            <div class="paste-actions-left">
              <button type="button" class="btn-card-action" data-action="copy-link" data-url="${p.url}" title="Kopírovať verejný web odkaz">
                <i class="fas fa-link"></i> Kopírovať odkaz
              </button>
              <button type="button" class="btn-card-action" data-action="qr" data-url="${p.url}" title="Zobraziť QR kód pre skenovanie mobilom">
                <i class="fas fa-qrcode"></i> QR Kód
              </button>
              <a href="${p.url}" target="_blank" class="btn-card-action" title="Otvoriť v novej karte">
                <i class="fas fa-external-link-alt"></i> Otvoriť
              </a>
            </div>
            <button type="button" class="btn-card-delete" data-id="${p.id}" title="Natrvalo zmazať záznam">
              <i class="fas fa-trash-can"></i> Zmazať
            </button>
          </div>
        </div>
      `;
    });

    pastesContainer.innerHTML = html;
  }

  // ─── Event Delegation pre položky v zozname ────────────────────────────
  if (pastesContainer) {
    pastesContainer.addEventListener('click', async (e) => {
      // 1. Rýchle kopírovanie textu do schránky
      const copyBtn = e.target.closest('.btn-fast-copy');
      if (copyBtn) {
        const pasteId = copyBtn.dataset.id;
        const pasteObj = allPastes.find(p => p.id === pasteId);
        if (pasteObj && pasteObj.content) {
          copyTextToClipboard(pasteObj.content, () => {
            copyBtn.classList.add('copied');
            const origHtml = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Skopírované!';
            showToast('Text bol skopírovaný do schránky zariadenia!', 'success');
            setTimeout(() => {
              copyBtn.classList.remove('copied');
              copyBtn.innerHTML = origHtml;
            }, 2000);
          }, () => {
            showToast('Nepodarilo sa skopírovať do schránky.', 'error');
          });
        }
        return;
      }

      // 2. Kopírovanie linku
      const copyLinkBtn = e.target.closest('[data-action="copy-link"]');
      if (copyLinkBtn) {
        const url = copyLinkBtn.dataset.url;
        copyTextToClipboard(url, () => {
          copyLinkBtn.classList.add('copied');
          const origHtml = copyLinkBtn.innerHTML;
          copyLinkBtn.innerHTML = '<i class="fas fa-check"></i> Odkaz skopírovaný!';
          showToast('Odkaz skopírovaný do schránky!', 'success');
          setTimeout(() => {
            copyLinkBtn.classList.remove('copied');
            copyLinkBtn.innerHTML = origHtml;
          }, 2000);
        });
        return;
      }

      // 3. QR Kód
      const qrBtn = e.target.closest('[data-action="qr"]');
      if (qrBtn) {
        const url = qrBtn.dataset.url;
        openQrModalDialog(url);
        return;
      }

      // 4. Zmazať záznam
      const delBtn = e.target.closest('.btn-card-delete');
      if (delBtn) {
        const pasteId = delBtn.dataset.id;
        if (confirm(`Naozaj chcete natrvalo zmazať záznam #${pasteId}?`)) {
          delBtn.disabled = true;
          delBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
          try {
            const res = await fetch(`api/paste/${pasteId}`, { method: 'DELETE' });
            const resData = await res.json();
            if (res.status === 200 && resData.status === 'ok') {
              showToast(`Záznam #${pasteId} bol úspešne zmazaný.`, 'info');
              allPastes = allPastes.filter(p => p.id !== pasteId);
              if (activeCountBadge) {
                activeCountBadge.textContent = `${allPastes.length} ${getSlovakItemWord(allPastes.length)}`;
              }
              renderPastes();
            } else {
              showToast(resData.message || 'Chyba pri mazaní záznamu.', 'error');
              delBtn.disabled = false;
              delBtn.innerHTML = '<i class="fas fa-trash-can"></i> Zmazať';
            }
          } catch (err) {
            console.error(err);
            showToast('Chyba komunikácie so serverom pri mazaní.', 'error');
            delBtn.disabled = false;
            delBtn.innerHTML = '<i class="fas fa-trash-can"></i> Zmazať';
          }
        }
        return;
      }

      // 5. Rozbalenie / Zbalenie snippetu
      const expandBtn = e.target.closest('.btn-toggle-expand');
      if (expandBtn) {
        const targetId = expandBtn.dataset.target;
        const box = document.getElementById(targetId);
        if (box) {
          const isExpanded = box.classList.toggle('expanded');
          expandBtn.innerHTML = isExpanded
            ? '<i class="fas fa-chevron-up"></i> Zbaliť'
            : '<i class="fas fa-chevron-down"></i> Rozbaliť celé';
        }
        return;
      }
    });
  }

  // ─── Vyhľadávanie a Filtre ────────────────────────────────────────────
  if (pasteSearchInput) {
    pasteSearchInput.addEventListener('input', () => {
      searchQuery = pasteSearchInput.value;
      if (clearSearchBtn) {
        clearSearchBtn.style.display = searchQuery ? 'block' : 'none';
      }
      renderPastes();
    });
  }

  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      if (pasteSearchInput) pasteSearchInput.value = '';
      searchQuery = '';
      clearSearchBtn.style.display = 'none';
      renderPastes();
      if (pasteSearchInput) pasteSearchInput.focus();
    });
  }

  if (filterBtns && filterBtns.length > 0) {
    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter || 'all';
        renderPastes();
      });
    });
  }

  if (btnRefreshPastes) {
    btnRefreshPastes.addEventListener('click', () => {
      loadPastes(false);
      showToast('Schránka obnovená.', 'info');
    });
  }

  // ─── QR Kód Modálne Okno ──────────────────────────────────────────────
  function openQrModalDialog(url) {
    if (!qrModal || !qrCodeContainer) return;

    qrCodeContainer.innerHTML = '';
    if (typeof QRCode !== 'undefined') {
      try {
        qrCodeInstance = new QRCode(qrCodeContainer, {
          text: url,
          width: 190,
          height: 190,
          colorDark: '#0b0f19',
          colorLight: '#ffffff',
          correctLevel: QRCode.CorrectLevel.M
        });
      } catch (e) {
        console.error('Chyba QRCode knižnice:', e);
        qrCodeContainer.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(url)}" alt="QR Kód" width="190" height="190">`;
      }
    } else {
      qrCodeContainer.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(url)}" alt="QR Kód" width="190" height="190">`;
    }

    if (qrUrlInput) qrUrlInput.value = url;
    if (btnOpenQrUrl) btnOpenQrUrl.href = url;

    qrModal.style.display = 'flex';
  }

  function closeQrModalDialog() {
    if (qrModal) qrModal.style.display = 'none';
  }

  if (closeQrModal) closeQrModal.addEventListener('click', closeQrModalDialog);
  if (btnCloseQrModal) btnCloseQrModal.addEventListener('click', closeQrModalDialog);

  if (qrModal) {
    qrModal.addEventListener('click', (e) => {
      if (e.target === qrModal) closeQrModalDialog();
    });
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && qrModal && qrModal.style.display === 'flex') {
      closeQrModalDialog();
    }
  });

  if (btnCopyQrUrl && qrUrlInput) {
    btnCopyQrUrl.addEventListener('click', () => {
      copyTextToClipboard(qrUrlInput.value, () => {
        showToast('Odkaz skopírovaný!', 'success');
      });
    });
  }

  // ─── Automatická synchronizácia schránky ─────────────────────────────
  // 1. Inicializácia po štarte (okamžite z SSR ak je dostupné, inak cez API)
  if (Array.isArray(window.__INITIAL_PASTES__) && window.__INITIAL_PASTES__.length > 0) {
    const baseUrl = window.__BASE_URL__ || window.location.origin;
    allPastes = window.__INITIAL_PASTES__.map(p => ({
      ...p,
      url: p.url || `${baseUrl}/p/${p.id}`,
      raw_url: p.raw_url || `${baseUrl}/p/${p.id}/raw`
    }));
    if (activeCountBadge) {
      activeCountBadge.textContent = `${allPastes.length} ${getSlovakItemWord(allPastes.length)}`;
    }
    renderPastes();
  } else if (pastesContainer) {
    loadPastes(true);
  }

  // 2. Pravidelný interval (každých 10 sekúnd na pozadí)
  setInterval(() => {
    if (document.visibilityState === 'visible') {
      loadPastes(true);
    }
  }, 10000);

  // 3. Obnova pri návrate do záložky alebo okna (cross-device okamžitý sync)
  window.addEventListener('focus', () => {
    loadPastes(true);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      loadPastes(true);
    }
  });

  // ─── Kopírovanie kódu vo vieweri ──────────────────────────────────────
  const btnCopyContent = document.getElementById('btnCopyContent');
  if (btnCopyContent) {
    btnCopyContent.addEventListener('click', () => {
      const codeEl = document.querySelector('pre code');
      if (codeEl) {
        copyTextToClipboard(codeEl.innerText, () => {
          showToast('Obsah skopírovaný do schránky!', 'success');
        });
      }
    });
  }
});
