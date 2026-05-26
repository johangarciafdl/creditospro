/**
 * ANIMATIONS - Micro-interacciones optimizadas
 * Solo animaciones esenciales para no hacer lag
 */

// Minimalist animations - Solo lo necesario

// ─────────────────────────────────────────────────────────────────────
// RIPPLE EFFECT - Click ripple en buttons (OPTIMIZADO)
// ─────────────────────────────────────────────────────────────────────

function createRipple(event) {
  const button = event.currentTarget;
  const ripple = document.createElement('span');
  const rect = button.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const x = event.clientX - rect.left - size / 2;
  const y = event.clientY - rect.top - size / 2;

  ripple.style.width = ripple.style.height = size + 'px';
  ripple.style.left = x + 'px';
  ripple.style.top = y + 'px';
  ripple.classList.add('ripple');

  // Remover ripple anterior si existe
  const existingRipple = button.querySelector('.ripple');
  if (existingRipple) {
    existingRipple.remove();
  }

  button.appendChild(ripple);

  // Remover después de la animación
  setTimeout(() => ripple.remove(), 400);
}

// Aplicar ripple a botones principales (no todos)
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.btn-primary, .btn-danger').forEach(btn => {
    btn.addEventListener('click', createRipple);
  });
});

// ─────────────────────────────────────────────────────────────────────
// TOAST NOTIFICATIONS (SIN EXCESOS)
// ─────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 3000) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 6px;
    background: ${
      type === 'success' ? '#10b981' :
      type === 'error' ? '#ef4444' :
      type === 'warning' ? '#f59e0b' :
      '#3b82f6'
    };
    color: white;
    font-weight: 600;
    z-index: 10000;
    font-size: 14px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    opacity: 0;
    transition: opacity 200ms ease-out;
  `;

  document.body.appendChild(toast);
  
  // Fade in
  setTimeout(() => toast.style.opacity = '1', 10);

  // Fade out
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

// ─────────────────────────────────────────────────────────────────────
// ANIMATED COUNTERS - Contadores de números animados
// ─────────────────────────────────────────────────────────────────────

class AnimatedCounter {
  constructor(element, targetValue, duration = 2000) {
    this.element = element;
    this.target = parseInt(targetValue) || 0;
    this.duration = duration;
    this.current = 0;
    this.isRunning = false;
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;

    const startTime = Date.now();
    const self = this;

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / this.duration, 1);

      // Easing: cubic-in-out
      const eased = progress < 0.5
        ? 4 * progress ** 3
        : 1 - (-2 * progress + 2) ** 3 / 2;

      self.current = Math.floor(self.target * eased);
      self.element.textContent = self.formatNumber(self.current);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        self.element.textContent = self.formatNumber(self.target);
        self.isRunning = false;
      }
    };

    requestAnimationFrame(animate);
  }

  formatNumber(num) {
    return num.toLocaleString('es-ES');
  }
}

function initCounters() {
  document.querySelectorAll('[data-counter]').forEach(element => {
    const target = element.dataset.counter;
    const counter = new AnimatedCounter(element, target);

    // Iniciar cuando sea visible
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        counter.start();
        observer.unobserve(element);
      }
    });

    observer.observe(element);
  });
}

document.addEventListener('DOMContentLoaded', initCounters);

// ─────────────────────────────────────────────────────────────────────
// SKELETON LOADING - Animación de carga
// ─────────────────────────────────────────────────────────────────────

function showSkeleton(container) {
  const skeleton = document.createElement('div');
  skeleton.className = 'skeleton-loading';
  skeleton.innerHTML = `
    <div class="skeleton-card">
      <div class="skeleton-header"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
  `;
  
  container.appendChild(skeleton);
  return skeleton;
}

function hideSkeleton(skeleton) {
  skeleton.style.animation = 'fadeOut 0.3s ease-out';
  setTimeout(() => skeleton.remove(), 300);
}

// ─────────────────────────────────────────────────────────────────────
// TRANSITION HELPERS - Transiciones suaves
// ─────────────────────────────────────────────────────────────────────

async function fadeOut(element, duration = 300) {
  element.style.animation = `fadeOut ${duration}ms ease-out`;
  await new Promise(resolve => setTimeout(resolve, duration));
  element.remove();
}

async function fadeIn(element, duration = 300) {
  element.style.animation = `fadeIn ${duration}ms ease-out`;
  return new Promise(resolve => setTimeout(resolve, duration));
}

async function slideUp(element, duration = 400) {
  element.style.animation = `slideUp ${duration}ms cubic-bezier(0.4, 0, 0.2, 1)`;
  return new Promise(resolve => setTimeout(resolve, duration));
}

async function slideDown(element, duration = 400) {
  element.style.animation = `slideDown ${duration}ms cubic-bezier(0.4, 0, 0.2, 1)`;
  return new Promise(resolve => setTimeout(resolve, duration));
}

// ─────────────────────────────────────────────────────────────────────
// MODAL ANIMATIONS
// ─────────────────────────────────────────────────────────────────────

function openModal(modal) {
  modal.style.display = 'flex';
  modal.style.animation = 'fadeIn 0.3s ease-out';
  
  const modalContent = modal.querySelector('.modal-content');
  if (modalContent) {
    modalContent.style.animation = 'slideUp 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
  }

  // Prevenir scroll en fondo
  document.body.style.overflow = 'hidden';
}

function closeModal(modal) {
  const modalContent = modal.querySelector('.modal-content');
  if (modalContent) {
    modalContent.style.animation = 'slideDown 0.3s ease-in';
  }

  setTimeout(() => {
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
  }, 300);
}

// ─────────────────────────────────────────────────────────────────────
// BUTTON SCALE ANIMATION
// ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('button, .btn').forEach(btn => {
    btn.addEventListener('mouseenter', function() {
      this.style.transform = 'scale(1.05)';
    });

    btn.addEventListener('mouseleave', function() {
      this.style.transform = 'scale(1)';
    });

    btn.addEventListener('mousedown', function() {
      this.style.transform = 'scale(0.98)';
    });

    btn.addEventListener('mouseup', function() {
      this.style.transform = 'scale(1.05)';
    });
  });
});

// ─────────────────────────────────────────────────────────────────────
// INPUT FOCUS ANIMATIONS
// ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input, textarea, select').forEach(input => {
    input.addEventListener('focus', function() {
      const wrapper = this.closest('.form-group') || this.parentElement;
      if (wrapper) {
        wrapper.classList.add('focused');
      }
    });

    input.addEventListener('blur', function() {
      const wrapper = this.closest('.form-group') || this.parentElement;
      if (wrapper && !this.value) {
        wrapper.classList.remove('focused');
      }
    });
  });
});

// ─────────────────────────────────────────────────────────────────────
// SEARCH INPUT ANIMATION
// ─────────────────────────────────────────────────────────────────────

function animateSearchInput(inputElement) {
  inputElement.addEventListener('focus', function() {
    this.parentElement.style.transform = 'scale(1.02)';
    this.parentElement.style.boxShadow = '0 0 0 3px rgba(212, 175, 55, 0.2)';
  });

  inputElement.addEventListener('blur', function() {
    this.parentElement.style.transform = 'scale(1)';
    this.parentElement.style.boxShadow = 'none';
  });
}

// ─────────────────────────────────────────────────────────────────────
// PULSE ANIMATION TRIGGER
// ─────────────────────────────────────────────────────────────────────

function addPulseEffect(element) {
  element.classList.add('pulse');
}

function removePulseEffect(element) {
  element.classList.remove('pulse');
}

// ─────────────────────────────────────────────────────────────────────
// BADGE ANIMATIONS
// ─────────────────────────────────────────────────────────────────────

function animateBadge(badge) {
  badge.style.animation = 'slideUp 0.3s ease-out';
}

// ─────────────────────────────────────────────────────────────────────
// TABLE ROW ANIMATIONS
// ─────────────────────────────────────────────────────────────────────

function animateNewTableRow(row) {
  row.style.animation = 'slideUp 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
}

function animateRemoveTableRow(row, duration = 300) {
  row.style.animation = `fadeOut ${duration}ms ease-out`;
  return new Promise(resolve => {
    setTimeout(() => {
      row.remove();
      resolve();
    }, duration);
  });
}

// ─────────────────────────────────────────────────────────────────────
// MENU ANIMATIONS
// ─────────────────────────────────────────────────────────────────────

function openMenu(menu) {
  menu.style.display = 'block';
  menu.style.animation = 'slideUp 0.3s ease-out';
}

function closeMenu(menu) {
  menu.style.animation = 'slideDown 0.2s ease-in';
  setTimeout(() => menu.style.display = 'none', 200);
}

// ─────────────────────────────────────────────────────────────────────
// HAMBURGER MENU ANIMATION
// ─────────────────────────────────────────────────────────────────────

function toggleHamburgerMenu(hamburger, menu) {
  hamburger.addEventListener('click', () => {
    hamburger.classList.toggle('active');
    if (hamburger.classList.contains('active')) {
      openMenu(menu);
    } else {
      closeMenu(menu);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────
// LOADING SPINNER
// ─────────────────────────────────────────────────────────────────────

function createLoadingSpinner() {
  const spinner = document.createElement('div');
  spinner.className = 'loading-spinner';
  spinner.innerHTML = `
    <div class="spinner-inner"></div>
    <p>Cargando...</p>
  `;
  return spinner;
}

// ─────────────────────────────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 3000) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 16px 24px;
    border-radius: 8px;
    background: ${
      type === 'success' ? '#10b981' :
      type === 'error' ? '#ef4444' :
      type === 'warning' ? '#f59e0b' :
      '#3b82f6'
    };
    color: white;
    font-weight: 600;
    z-index: 10000;
    animation: slideUp 0.3s ease-out;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
  `;

  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'fadeOut 0.3s ease-out';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


// ─────────────────────────────────────────────────────────────────────
// EXPORT - Funciones esenciales
// ─────────────────────────────────────────────────────────────────────

window.animations = {
  showToast,
  createRipple,
};

