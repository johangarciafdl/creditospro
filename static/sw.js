/* CreditosPro Service Worker v3 */
const CACHE = 'creditospro-v8';
const STATIC = [
  '/', '/dashboard', '/clientes', '/prestamos', '/cobros', '/zonas',
  '/static/manifest.json',
];

// Este mismo archivo se sirve en /sw.js (alcance: todo el sitio) y, por
// compatibilidad con instalaciones viejas, tambien en /static/sw.js. Un
// worker registrado desde /static/ solo controla /static/: no sirve ninguna
// pantalla y encima deja al navegador creyendo que ya hay offline. Si esta
// copia despierta con ese alcance, se da de baja sola.
if (self.registration && self.registration.scope.endsWith('/static/')) {
  self.registration.unregister();
}

self.addEventListener('install', e => {
  // Uno por uno en vez de addAll: addAll es atomico, asi que si una sola URL
  // fallaba (p.ej. /clientes redirige al login cuando aun no hay sesion) se
  // perdia TODO el precacheo, en silencio por el .catch de antes.
  e.waitUntil(caches.open(CACHE).then(c => Promise.allSettled(
    STATIC.map(async u => {
      const res = await fetch(new Request(u, { cache: 'reload' }));
      if (res.ok && !res.redirected) await c.put(u, res);
    })
  )));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  // API calls: network only
  if (url.pathname.startsWith('/auth') || url.pathname.includes('ajax') || url.pathname.includes('nuevo')) return;
  // OJO con ignoreVary: el servidor responde "Vary: Cookie" en todas las
  // paginas, y caches.match() respeta ese encabezado. Como la cookie CSRF
  // cambia al iniciar sesion, la pagina guardada NUNCA coincidia con la
  // peticion y el modo sin señal no servia ni una sola pantalla: el cobrador
  // veia el error de "sin internet" del navegador aunque todo estuviera en
  // el cache. Con ignoreVary la busqueda se hace solo por URL.
  const OPC = { ignoreVary: true };

  // Static assets: cache first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request, OPC).then(r => r || fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone)).catch(()=>{});
        return res;
      }))
    );
    return;
  }
  // Pages: network first, cache fallback
  e.respondWith(
    fetch(e.request).then(res => {
      // No guardar redirecciones (sesion vencida -> login): quedarian
      // cacheadas y sin señal mostrarian el login en vez de la pantalla.
      if (res.ok && !res.redirected) {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone)).catch(()=>{});
      }
      return res;
    }).catch(() => caches.match(e.request, OPC).then(r => r || respuestaSinSeñal()))
  );
});

/** Si no hay nada en cache, al menos una pantalla entendible y no el
 *  error crudo del navegador. */
function respuestaSinSeñal() {
  return new Response(
    `<!doctype html><meta charset="utf-8">
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <style>body{font-family:system-ui,sans-serif;background:#0A0A0A;color:#eee;
     display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
     div{max-width:300px;padding:24px}h1{font-size:18px;margin:0 0 8px}p{font-size:14px;color:#999;line-height:1.6}
     button{margin-top:16px;padding:10px 18px;border:0;border-radius:8px;background:#C8A95A;font-weight:600}</style>
     <div><h1>Sin conexión</h1>
     <p>Esta pantalla todavía no está guardada en el celular. Ábrela una vez con señal y quedará disponible sin internet.</p>
     <button onclick="location.reload()">Reintentar</button></div>`,
    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

// Permite borrar el cache al cerrar sesion: como ahora la busqueda ignora
// la cookie, una pagina guardada por un usuario no debe quedar disponible
// para el siguiente que use el mismo celular.
/** Vuelve a guardar las pantallas principales, ahora CON la sesion iniciada.
 *  El precacheo del install corre cuando el worker se instala, que suele ser
 *  antes del login: ahi /clientes, /cobros, etc. responden con una redireccion
 *  al login y no se guardan. Resultado: el cobrador "preparaba" el celular en
 *  la mañana y en la calle solo tenia offline las pantallas que por casualidad
 *  hubiera abierto. Esto lo dispara pwa.js despues de cada sincronizacion. */
async function precargarPantallas() {
  const c = await caches.open(CACHE);
  await Promise.allSettled(STATIC.map(async u => {
    try {
      const res = await fetch(new Request(u, { cache: 'reload' }), { credentials: 'same-origin' });
      if (res.ok && !res.redirected) await c.put(u, res);
    } catch (e) { /* sin señal: se queda lo que ya hubiera */ }
  }));
}

self.addEventListener('message', e => {
  if (e.data && e.data.type === 'PRECARGAR') {
    e.waitUntil(precargarPantallas());
    return;
  }
  if (e.data && e.data.type === 'LIMPIAR_CACHE') {
    e.waitUntil(caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k)))));
  }
});
/* ─────────────────────────────────────────────────────────────────────
   BACKGROUND SYNC DE COBROS
   pwa.js registra el tag 'sync-cobros' al guardar un cobro sin señal,
   pero aqui no habia ningun listener de 'sync': el navegador disparaba
   el evento y no lo atendia nadie. Resultado: con la app cerrada NO se
   sincronizaba nada, aunque el README lo prometiera.

   No se puede usar Dexie aqui (no esta cargado en el worker), asi que se
   lee el mismo IndexedDB con la API nativa. Tampoco hay document.cookie:
   el token CSRF se saca con cookieStore, que existe en los mismos
   navegadores donde existe Background Sync (Chrome/Android).
   ───────────────────────────────────────────────────────────────────── */

const DB_NAME = 'CreditosProDb';
const STORE_COBROS = 'cobros';

function abrirDb() {
  return new Promise((resolve, reject) => {
    // Sin version: abre la que exista y nunca dispara un upgrade que
    // pudiera pelear con la version que maneja Dexie en la pagina.
    const req = indexedDB.open(DB_NAME);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function cobrosPendientes(db) {
  return new Promise((resolve, reject) => {
    if (!db.objectStoreNames.contains(STORE_COBROS)) return resolve([]);
    const tx = db.transaction(STORE_COBROS, 'readonly');
    const req = tx.objectStore(STORE_COBROS).index('sincronizado').getAll(0);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

function marcarCobro(db, cobro, cambios) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_COBROS, 'readwrite');
    const store = tx.objectStore(STORE_COBROS);
    const req = store.put({ ...cobro, ...cambios });
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

async function csrfToken() {
  try {
    if (typeof cookieStore === 'undefined') return '';
    const c = await cookieStore.get('cp_csrf');
    return c ? c.value : '';
  } catch (e) { return ''; }
}

async function subirCobrosPendientes() {
  const db = await abrirDb();
  const pendientes = await cobrosPendientes(db);
  if (!pendientes.length) return 0;

  const token = await csrfToken();
  let enviados = 0;

  for (const cobro of pendientes) {
    const form = new FormData();
    form.set('cuota_id', String(cobro.cuota_id));
    form.set('valor_cobrado', String(cobro.valor_cobrado));
    form.set('metodo_pago', String(cobro.metodo_pago || 'Efectivo'));
    form.set('observaciones', String(cobro.observaciones || 'Cobro sincronizado sin conexion'));
    form.set('lat', String(cobro.lat || ''));
    form.set('lng', String(cobro.lng || ''));
    if (cobro.idempotency_key) form.set('idempotency_key', String(cobro.idempotency_key));
    if (cobro.foto instanceof Blob) form.set('foto', cobro.foto, 'cobro.jpg');

    let res;
    try {
      res = await fetch('/cobros/registrar', {
        method: 'POST', credentials: 'same-origin',
        headers: token ? { 'X-CSRF-Token': token } : {},
        body: form,
      });
    } catch (e) {
      // Se fue la señal a mitad: se deja pendiente y se reintenta luego.
      // Devolver rechazo hace que el navegador reprograme este sync.
      throw e;
    }

    if (res.ok) {
      await marcarCobro(db, cobro, { sincronizado: 1 });
      enviados++;
    } else if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
      // El servidor lo rechaza y lo va a seguir rechazando (cuota ya pagada,
      // datos invalidos...). Reintentarlo eternamente solo deja el contador
      // de pendientes trabado para siempre: se marca con el motivo para que
      // la app lo muestre en vez de reintentar en un bucle infinito.
      let motivo = 'Rechazado por el servidor';
      try { const d = await res.json(); motivo = d.error || d.detail || motivo; } catch (e) {}
      await marcarCobro(db, cobro, { sincronizado: 2, error_sync: motivo });
    }
    // 5xx / 408 / 429: se deja pendiente tal cual para el proximo intento.
  }

  const clientes = await self.clients.matchAll({ includeUncontrolled: true });
  for (const c of clientes) c.postMessage({ type: 'SYNC_COMPLETE', synced: enviados });
  return enviados;
}

self.addEventListener('sync', e => {
  if (e.tag === 'sync-cobros') e.waitUntil(subirCobrosPendientes());
});
