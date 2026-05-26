# Static Assets Documentation

## JavaScript Files

### `pwa.js` - Progressive Web App Logic
**Purpose:** Handles offline functionality, IndexedDB sync, and data synchronization

**Main Functions:**
- `initPwaDb()` - Initialize IndexedDB with Dexie
- `syncAllData()` - Full data synchronization
- `saveCobro(cobroData)` - Smart save (online/offline aware)
- `downloadData()` - Download all data from server
- `uploadPendingCobros()` - Sync offline cobros
- `updateOnlineStatus(online)` - Update UI indicator

**Usage:**
```javascript
// Automatically initialized on page load
// To manually trigger sync:
await window.pwa.syncAllData();

// To save a cobro (works online/offline):
const result = await window.pwa.saveCobro({
  prestamo_id: 123,
  monto: 50000,
  fecha: '2024-05-06'
});
```

**Features:**
- Automatic sync every 5 minutes (when online)
- Background sync on reconnection
- IndexedDB for offline storage
- Automatic fallback to localStorage
- Real-time online/offline detection

---

### `animations.js` - Animation Controller
**Purpose:** Micro-interactions and smooth animations for modern UI

**Exported Functions:**
```javascript
window.animations.fadeOut(element, duration)
window.animations.fadeIn(element, duration)
window.animations.slideUp(element, duration)
window.animations.slideDown(element, duration)
window.animations.openModal(modal)
window.animations.closeModal(modal)
window.animations.showToast(message, type, duration)
window.animations.createLoadingSpinner()
window.animations.openMenu(menu)
window.animations.closeMenu(menu)
window.animations.toggleHamburgerMenu(hamburger, menu)
window.animations.addPulseEffect(element)
window.animations.removePulseEffect(element)
window.animations.AnimatedCounter(element, target, duration)
```

**Usage:**
```javascript
// Toast notification
window.animations.showToast('Operación exitosa', 'success', 3000);

// Modal opening with animation
const modal = document.getElementById('myModal');
window.animations.openModal(modal);

// Fade out element
await window.animations.fadeOut(element, 300);

// Animated counter
const counter = new window.animations.AnimatedCounter(
  document.getElementById('count'),
  1000,
  2000
);
counter.start();
```

**Animation Types:**
- `fadeIn` / `fadeOut` - Opacity transitions (0.3s)
- `slideUp` / `slideDown` - Vertical transitions (0.4s)
- `pulse` - Breathing animation (2s infinite)
- `bounce` - Bounce effect
- `ripple` - Click ripple effect

---

## CSS Files

### `modern-design.css` - Design System
**Purpose:** Modern Black & Gold design system with responsive layout

**Key Features:**

**Color Variables:**
```css
--primary-black: #0F0F0F;      /* Deepest black */
--dark-black: #1A1A1A;         /* Dark black */
--medium-black: #2A2A2A;       /* Medium black */
--primary-gold: #D4AF37;       /* Main gold */
--dark-gold: #C9A961;          /* Dark gold */
--light-gold: #E6C847;         /* Light gold */
--success: #10B981;
--warning: #F59E0B;
--error: #EF4444;
```

**Components:**
- `.card` - Elevated cards with hover effects
- `.btn` / `.btn-primary` - Buttons with ripple effects
- `.input-field` - Form inputs with gold focus state
- `.badge` / `.badge-success` - Colored badges
- `.modal` / `.modal-content` - Modals with backdrop blur

**Responsive Breakpoints:**
- Mobile: `(max-width: 480px)`
- Tablet: `(max-width: 768px)`
- Desktop: `(max-width: 1024px)`
- Large: `(max-width: 1200px)`

**Usage in HTML:**
```html
<!-- Card -->
<div class="card">
  <h3>Title</h3>
  <p>Content</p>
</div>

<!-- Button -->
<button class="btn btn-primary">Save</button>

<!-- Badge -->
<span class="badge badge-success">Pagado</span>

<!-- Input -->
<input type="text" class="input-field" placeholder="Search...">
```

---

## Service Worker

### `sw.js` - Service Worker
**Purpose:** Caching strategy, offline fallback, background sync

**Caching Strategy:**
- **Network-first** for API calls (`/api/*`, `/cobros/*`)
- **Cache-first** for static assets (`/static/*`)
- **Offline fallback** for HTML pages

**Cache Versions:**
- `creditospro-v1` - Static assets
- `creditospro-api-v1` - API responses

**Installation:**
Automatically registered in `base.html`:
```javascript
navigator.serviceWorker.register('/static/sw.js')
```

---

## Web App Manifest

### `manifest.json` - PWA Installation Metadata
**Purpose:** Enables "Add to home screen" on mobile devices

**Key Properties:**
```json
{
  "name": "CreditosPro - Sistema de Gestión de Créditos",
  "short_name": "CreditosPro",
  "theme_color": "#D4AF37",        // Gold
  "background_color": "#0F0F0F",   // Black
  "display": "standalone",
  "start_url": "/"
}
```

**Referenced in:** `base.html` as:
```html
<link rel="manifest" href="/static/manifest.json">
```

---

## Loading Order

1. **HTML** loads first
2. **CSS** (inline + modern-design.css) - Blocks rendering
3. **JavaScript:**
   - PWA registration script (async)
   - Dexie CDN (async, onload callback)
   - `pwa.js` (defer) - Waits for DOM
   - `animations.js` (defer) - Waits for DOM

This ensures:
- Styling is applied immediately
- PWA starts registration early
- Scripts run after DOM is ready
- No layout shift

---

## Browser Compatibility

| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| Service Worker | ✅ | ✅ | ✅ | ✅ |
| IndexedDB | ✅ | ✅ | ✅ | ✅ |
| CSS Grid | ✅ | ✅ | ✅ | ✅ |
| Animations | ✅ | ✅ | ✅ | ✅ |
| PWA Install | ✅ | ⚠️ | ⚠️ | ✅ |
| Background Sync | ✅ | ❌ | ❌ | ✅ |

---

## Performance Notes

- All CSS variables are GPU-accelerated (`transform`, `opacity`)
- Animations use `requestAnimationFrame`
- Debounced event listeners for scroll/resize
- Intersection Observer for entrance animations
- Lazy-loaded scripts with `defer` attribute

---

## Debugging

### View Service Worker
1. Open DevTools (F12)
2. Application tab → Service Workers
3. Check registration status and cache contents

### View IndexedDB
1. Open DevTools (F12)
2. Application tab → IndexedDB → CreditosProDb
3. View tables: clientes, prestamos, cuotas, cobros

### View Network Cache
1. Open DevTools (F12)
2. Application tab → Cache Storage
3. View cached static assets

### Check Online Status
```javascript
// In console:
navigator.onLine          // true/false
window.pwa.isOnline()     // true/false
```

---

## Version History

- **1.0.0** (2024-05-06) - Initial PWA implementation with animations
  - Service Worker caching
  - IndexedDB sync
  - Modern design system
  - Animation controller

---

Last Updated: 2024-05-06
