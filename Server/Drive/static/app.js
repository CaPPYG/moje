/* ─── Drive Drop Client Application ───────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const filesContainer = document.getElementById('filesContainer');
  const emptyState = document.getElementById('emptyState');
  const searchInput = document.getElementById('searchInput');
  const sortSelect = document.getElementById('sortSelect');
  const btnRefresh = document.getElementById('btnRefresh');
  const progressPanel = document.getElementById('progressPanel');
  const progressFilename = document.getElementById('progressFilename');
  const progressPercent = document.getElementById('progressPercent');
  const progressBarFill = document.getElementById('progressBarFill');
  const statCount = document.getElementById('statCount');
  const statSize = document.getElementById('statSize');

  let allFiles = [];

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

  // ─── Načítanie súborov z API ─────────────────────────────────────────
  async function loadFiles() {
    if (!filesContainer) return;
    if (btnRefresh) btnRefresh.classList.add('spinning');
    try {
      const res = await fetch('api/files');
      if (res.status === 401) {
        window.location.reload();
        return;
      }
      const data = await res.json();
      if (data.status === 'ok') {
        allFiles = data.files || [];
        if (statCount) statCount.textContent = `Počet: ${allFiles.length}`;
        if (statSize) statSize.textContent = `Veľkosť: ${data.total_size_str || '0 B'}`;
        renderFiles();
      } else {
        showToast(data.message || 'Chyba pri načítaní súborov.', 'error');
      }
    } catch (e) {
      console.error(e);
      showToast('Nepodarilo sa spojiť so serverom.', 'error');
    } finally {
      if (btnRefresh) {
        setTimeout(() => btnRefresh.classList.remove('spinning'), 400);
      }
    }
  }

  // ─── Určenie ikony podľa typu súboru ──────────────────────────────────
  function getFileIcon(name, mime) {
    const ext = name.split('.').pop().toLowerCase();
    if (['pdf'].includes(ext)) {
      return { icon: 'fa-file-pdf', cls: 'icon-pdf' };
    }
    if (['doc', 'docx', 'odt', 'rtf', 'txt'].includes(ext)) {
      return { icon: 'fa-file-lines', cls: 'icon-word' };
    }
    if (['xls', 'xlsx', 'csv', 'ods'].includes(ext)) {
      return { icon: 'fa-file-excel', cls: 'icon-excel' };
    }
    if (['ppt', 'pptx', 'odp'].includes(ext)) {
      return { icon: 'fa-file-powerpoint', cls: 'icon-powerpoint' };
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
      return { icon: 'fa-file-zipper', cls: 'icon-archive' };
    }
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext) || mime.startsWith('image/')) {
      return { icon: 'fa-file-image', cls: 'icon-image' };
    }
    if (['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv'].includes(ext) || mime.startsWith('video/')) {
      return { icon: 'fa-file-video', cls: 'icon-video' };
    }
    if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].includes(ext) || mime.startsWith('audio/')) {
      return { icon: 'fa-file-audio', cls: 'icon-audio' };
    }
    if (['py', 'js', 'ts', 'html', 'css', 'json', 'sh', 'bat', 'c', 'cpp', 'java'].includes(ext)) {
      return { icon: 'fa-file-code', cls: 'icon-code' };
    }
    return { icon: 'fa-file', cls: 'icon-generic' };
  }

  // ─── Pekný formát dátumu ──────────────────────────────────────────────
  function formatDate(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return '';
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return 'Práve teraz';
      if (diffMin < 60) return `pred ${diffMin} min`;
      const isToday = d.toDateString() === now.toDateString();
      const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      if (isToday) return `Dnes o ${timeStr}`;
      return `${d.toLocaleDateString()} ${timeStr}`;
    } catch {
      return '';
    }
  }

  // ─── Vykreslenie zoznamu súborov ──────────────────────────────────────
  function renderFiles() {
    if (!filesContainer) return;
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
    const sortBy = sortSelect ? sortSelect.value : 'newest';

    let list = allFiles.filter(f => f.name.toLowerCase().includes(query));

    // Zoradenie
    if (sortBy === 'newest') {
      list.sort((a, b) => new Date(b.modifiedTime || 0) - new Date(a.modifiedTime || 0));
    } else if (sortBy === 'oldest') {
      list.sort((a, b) => new Date(a.modifiedTime || 0) - new Date(b.modifiedTime || 0));
    } else if (sortBy === 'name') {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === 'size') {
      list.sort((a, b) => (b.size || 0) - (a.size || 0));
    }

    if (list.length === 0) {
      filesContainer.innerHTML = '';
      if (emptyState) {
        emptyState.style.display = 'block';
        if (query) {
          emptyState.querySelector('.empty-title').textContent = 'Žiadne výsledky';
          emptyState.querySelector('.empty-desc').textContent = `Pre výraz "${query}" neboli nájdené žiadne súbory.`;
        } else {
          emptyState.querySelector('.empty-title').textContent = 'Priečinok UPLOADED je prázdny';
          emptyState.querySelector('.empty-desc').textContent = 'Nahraj svoj prvý súbor pretiahnutím do zóny vyššie.';
        }
      }
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

    filesContainer.innerHTML = list.map(f => {
      const iconInfo = getFileIcon(f.name, f.mimeType);
      const dateFormatted = formatDate(f.modifiedTime);
      const localBadge = f.is_local ? `<span class="stat-pill" style="color:#fbbf24;border-color:rgba(245,158,11,0.3)">Lokálny server</span>` : '';
      const directDl = f.downloadUrl || `download/${f.id}`;
      const serverDl = f.serverDownloadUrl || `download/${f.id}?proxy=1`;

      return `
        <div class="file-item" data-id="${f.id}" data-name="${encodeURIComponent(f.name)}">
          <div class="file-left">
            <div class="file-type-icon ${iconInfo.cls}">
              <i class="fas ${iconInfo.icon}"></i>
            </div>
            <div class="file-details">
              <div class="file-name" title="${f.name}">${f.name}</div>
              <div class="file-meta">
                <span class="file-meta-item"><i class="fas fa-database"></i> ${f.size_str}</span>
                ${dateFormatted ? `<span class="file-meta-item"><i class="fas fa-clock"></i> ${dateFormatted}</span>` : ''}
                ${localBadge}
              </div>
            </div>
          </div>
          <div class="file-actions">
            <a href="${directDl}" class="btn-action btn-download-direct" target="_blank" rel="noopener" title="Priame rýchle stiahnutie z Google Drive">
              <i class="fas fa-bolt"></i> Stiahnuť
            </a>
            <a href="${serverDl}" class="btn-action btn-download-server" title="Alternatívne proxy stiahnutie cez server (pre blokované siete)">
              <i class="fas fa-download"></i> Server
            </a>
            <button class="btn-action btn-copy-link" onclick="copyLink('${directDl}')" title="Skopírovať priamy odkaz na stiahnutie">
              <i class="fas fa-link"></i> Link
            </button>
            <button class="btn-action btn-delete" onclick="deleteFile('${f.id}', '${encodeURIComponent(f.name)}')" title="Zmazať súbor z Drive">
              <i class="fas fa-trash-alt"></i>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  // ─── Kopírovanie odkazu ───────────────────────────────────────────────
  window.copyLink = function(url) {
    const fullUrl = url.startsWith('http') ? url : window.location.origin + (url.startsWith('/') ? '' : '/') + url;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('Odkaz na stiahnutie bol skopírovaný!', 'success');
      }).catch(() => fallbackCopy(fullUrl));
    } else {
      fallbackCopy(fullUrl);
    }
  };

  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      showToast('Odkaz na stiahnutie bol skopírovaný!', 'success');
    } catch {
      prompt('Skopíruj si odkaz:', text);
    }
    document.body.removeChild(ta);
  }

  // ─── Zmazanie súboru ──────────────────────────────────────────────────
  window.deleteFile = async function(fileId, encodedName) {
    const filename = decodeURIComponent(encodedName);
    if (!confirm(`Naozaj chceš zmazať súbor "${filename}"?`)) return;

    try {
      const res = await fetch(`api/delete/${fileId}`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'ok') {
        showToast(`Súbor "${filename}" bol zmazaný.`, 'success');
        allFiles = allFiles.filter(f => f.id !== fileId);
        renderFiles();
      } else {
        showToast(data.message || 'Nepodarilo sa zmazať súbor.', 'error');
      }
    } catch (e) {
      showToast('Chyba komunikácie pri mazaní.', 'error');
    }
  };

  // ─── Upload spracovanie cez XHR s progressom ─────────────────────────
  async function uploadFiles(files) {
    if (!files || files.length === 0) return;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      await uploadSingleFile(file, i + 1, files.length);
    }

    if (progressPanel) {
      setTimeout(() => { progressPanel.style.display = 'none'; }, 1500);
    }
    loadFiles();
  }

  function uploadSingleFile(file, index, total) {
    return new Promise((resolve) => {
      if (progressPanel) progressPanel.style.display = 'block';
      if (progressFilename) progressFilename.textContent = `[${index}/${total}] ${file.name}`;
      if (progressPercent) progressPercent.textContent = '0%';
      if (progressBarFill) progressBarFill.style.width = '0%';

      const xhr = new XMLHttpRequest();
      const fd = new FormData();
      fd.append('file', file);

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          if (progressPercent) progressPercent.textContent = `${percent}%`;
          if (progressBarFill) progressBarFill.style.width = `${percent}%`;
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.status === 'ok') {
              showToast(`"${file.name}" úspešne nahraný do Drive!`, 'success');
            } else {
              showToast(`Chyba pri nahrávaní "${file.name}".`, 'error');
            }
          } catch {
            showToast(`Súbor "${file.name}" nahraný.`, 'success');
          }
        } else {
          showToast(`Nahrávanie "${file.name}" zlyhalo (${xhr.status}).`, 'error');
        }
        resolve();
      });

      xhr.addEventListener('error', () => {
        showToast(`Chyba siete pri nahrávaní "${file.name}".`, 'error');
        resolve();
      });

      xhr.open('POST', 'api/upload', true);
      xhr.send(fd);
    });
  }

  // ─── Drag & Drop obsluha ──────────────────────────────────────────────
  if (dropzone) {
    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
      }, false);
    });

    dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        uploadFiles(files);
      }
    });

    dropzone.addEventListener('click', (e) => {
      if (e.target.closest('button') || e.target.tagName === 'BUTTON') return;
      if (fileInput) fileInput.click();
    });
  }

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length > 0) {
        uploadFiles(fileInput.files);
        fileInput.value = '';
      }
    });
  }

  // ─── Vkladanie cez Ctrl+V zo schránky ──────────────────────────────────
  window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    const filesToUpload = [];
    for (const item of items) {
      if (item.kind === 'file') {
        const blob = item.getAsFile();
        if (blob) {
          let fname = blob.name;
          if (!fname || fname === 'image.png') {
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            fname = `screenshot_${timestamp}.png`;
          }
          const file = new File([blob], fname, { type: blob.type });
          filesToUpload.push(file);
        }
      }
    }
    if (filesToUpload.length > 0) {
      showToast(`Vložený súbor zo schránky (${filesToUpload.length}x)`, 'info');
      uploadFiles(filesToUpload);
    }
  });

  // ─── Vyhľadávanie a zoradenie ─────────────────────────────────────────
  if (searchInput) searchInput.addEventListener('input', renderFiles);
  if (sortSelect) sortSelect.addEventListener('change', renderFiles);
  if (btnRefresh) btnRefresh.addEventListener('click', loadFiles);

  // ─── Prihlásenie (Login Form) ─────────────────────────────────────────
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pwdInput = document.getElementById('passwordInput');
      const submitBtn = loginForm.querySelector('button[type="submit"]');
      const pwd = pwdInput ? pwdInput.value : '';
      if (!pwd) return;

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Overujem...';
      }

      try {
        const res = await fetch('login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          window.location.reload();
        } else {
          showToast(data.message || 'Nesprávne heslo.', 'error');
          if (pwdInput) {
            pwdInput.value = '';
            pwdInput.focus();
            pwdInput.parentElement.classList.add('shake');
            setTimeout(() => pwdInput.parentElement.classList.remove('shake'), 500);
          }
        }
      } catch (err) {
        showToast('Chyba prihlásenia.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-arrow-right"></i> Prihlásiť sa';
        }
      }
    });
  }

  // Toggle hesla
  const togglePw = document.getElementById('togglePw');
  if (togglePw) {
    togglePw.addEventListener('click', () => {
      const pwdInput = document.getElementById('passwordInput');
      if (!pwdInput) return;
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        togglePw.innerHTML = '<i class="fas fa-eye-slash"></i>';
      } else {
        pwdInput.type = 'password';
        togglePw.innerHTML = '<i class="fas fa-eye"></i>';
      }
    });
  }

  // Automatické načítanie pri štarte (ak je prihlásený)
  if (filesContainer) {
    loadFiles();
  }
});
