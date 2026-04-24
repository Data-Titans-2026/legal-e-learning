(function() {
  let confirmCallback = null;

  function ensureToastContainer() {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function ensureConfirmModal() {
    let overlay = document.getElementById('confirmOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'confirmOverlay';
      overlay.className = 'confirm-overlay hidden';
      overlay.innerHTML = `
        <div class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
          <h3 id="confirmTitle">Please confirm</h3>
          <p id="confirmMessage"></p>
          <div class="confirm-actions">
            <button type="button" class="confirm-btn cancel" id="confirmCancelBtn">Cancel</button>
            <button type="button" class="confirm-btn confirm" id="confirmOkBtn">Confirm</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function(event) {
        if (event.target === overlay) {
          resolveConfirm(false);
        }
      });

      overlay.querySelector('#confirmCancelBtn').addEventListener('click', function() {
        resolveConfirm(false);
      });

      overlay.querySelector('#confirmOkBtn').addEventListener('click', function() {
        resolveConfirm(true);
      });
    }

    return overlay;
  }

  function resolveConfirm(confirmed) {
    const overlay = document.getElementById('confirmOverlay');
    if (overlay) {
      overlay.classList.add('hidden');
    }

    const callback = confirmCallback;
    confirmCallback = null;
    if (typeof callback === 'function') {
      callback(confirmed);
    }
  }

  document.addEventListener('keydown', function(event) {
    const overlay = document.getElementById('confirmOverlay');
    if (!overlay || overlay.classList.contains('hidden')) {
      return;
    }

    if (event.key === 'Escape') {
      resolveConfirm(false);
    }
  });

  window.showToast = function(message, type) {
    const container = ensureToastContainer();
    const toast = document.createElement('div');
    toast.className = 'toast ' + (type || 'info');
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(function() {
      toast.classList.add('show');
    });

    setTimeout(function() {
      toast.classList.remove('show');
      setTimeout(function() {
        toast.remove();
      }, 220);
    }, 3000);
  };

  window.showConfirm = function(message, callback) {
    const overlay = ensureConfirmModal();
    overlay.querySelector('#confirmMessage').textContent = message;
    confirmCallback = callback;
    overlay.classList.remove('hidden');
    overlay.querySelector('#confirmOkBtn').focus();
  };

  window.startButtonLoading = function(button, loadingText) {
    if (!button) {
      return;
    }

    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent;
    }

    button.disabled = true;
    button.classList.add('is-loading');
    button.textContent = loadingText || 'Loading...';
  };

  window.stopButtonLoading = function(button, nextText) {
    if (!button) {
      return;
    }

    button.disabled = false;
    button.classList.remove('is-loading');
    button.textContent = nextText || button.dataset.originalText || button.textContent;
  };
})();
