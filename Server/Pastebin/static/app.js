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

  let activeTab = 'text'; // 'text' | 'image'
  let selectedFile = null;

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

  // ─── Podpora TAB klávesy v editore ────────────────────────────────────
  if (pasteTextarea) {
    pasteTextarea.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = pasteTextarea.selectionStart;
        const end = pasteTextarea.selectionEnd;
        pasteTextarea.value = pasteTextarea.value.substring(0, start) + '  ' + pasteTextarea.value.substring(end);
        pasteTextarea.selectionStart = pasteTextarea.selectionEnd = start + 2;
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
    // Ak píše do textarea a ide o bežný text, nevytvárame obrázok
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
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Vytváram...';
      }

      try {
        const res = await fetch('api/paste', {
          method: 'POST',
          body: fd
        });

        const data = await res.json();
        if (res.status === 201 && data.status === 'ok') {
          showToast('Paste úspešne vytvorený!', 'success');
          if (generatedUrlInput) generatedUrlInput.value = data.url;
          if (successModal) {
            successModal.style.display = 'block';
            successModal.scrollIntoView({ behavior: 'smooth' });
          }

          // Vyčistiť polia
          if (pasteTextarea) pasteTextarea.value = '';
          resetImage();
        } else {
          showToast(data.message || 'Chyba pri vytváraní paste.', 'error');
        }
      } catch (err) {
        console.error(err);
        showToast('Chyba komunikácie so serverom.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-lock"></i> Vytvoriť bezpečný odkaz';
        }
      }
    });
  }

  // ─── Kopírovanie vygenerovanej URL ─────────────────────────────────────
  if (btnCopyUrl && generatedUrlInput) {
    btnCopyUrl.addEventListener('click', () => {
      const url = generatedUrlInput.value;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => {
          showToast('Odkaz skopírovaný do schránky!', 'success');
        });
      } else {
        generatedUrlInput.select();
        document.execCommand('copy');
        showToast('Odkaz skopírovaný!', 'success');
      }
    });
  }

  // ─── Kopírovanie kódu vo vieweri ──────────────────────────────────────
  const btnCopyContent = document.getElementById('btnCopyContent');
  if (btnCopyContent) {
    btnCopyContent.addEventListener('click', () => {
      const codeEl = document.querySelector('pre code');
      if (codeEl) {
        const text = codeEl.innerText;
        navigator.clipboard.writeText(text).then(() => {
          showToast('Obsah skopírovaný!', 'success');
        });
      }
    });
  }
});
