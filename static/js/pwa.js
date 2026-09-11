/**
 * PWA LOGIC - IndexedDB + Sincronización
 * Maneja almacenamiento local y sincronización automática
 */

let pwaDb = null;
let isOnline = navigator.onLine;

// ─────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN DEXIE (IndexedDB)
// ─────────────────────────────────────────────────────────────────────

async function initPwaDb() {
  try {
    // Dinámicamente cargar/crear Dexie
    if (typeof Dexie === 'undefined') {
      // Si no está disponible, usar localStorage como fallback
      console.log('[PWA] IndexedDB no disponible, usando localStorage');
      return createLocalStorageDb();
    }

    pwaDb = new Dexie('CreditosProDb');
    pwaDb.version(1).stores({
      clientes: 'id, empresa_id, cedula',
      prestamos: 'id, cliente_id, empresa_id, estado',
      cuotas: 'id, prestamo_id, empresa_id, estado',
      cobros: '++id, prestamo_id, empresa_id, fecha, sincronizado',
      sincronizacion: 'id'
    });
    // v2: se agrega "zonas" para poder mostrar el nombre de la zona
    // (no solo el zona_id) en Clientes/Préstamos sin conexión.
    pwaDb.version(2).stores({
      clientes: 'id, empresa_id, cedula',
      prestamos: 'id, cliente_id, empresa_id, estado',
      cuotas: 'id, prestamo_id, empresa_id, estado',
      cobros: '++id, prestamo_id, empresa_id, fecha, sincronizado',
      sincronizacion: 'id',
      zonas: 'id, empresa_id',
    });

    // Crear tablas si no existen
    await pwaDb.open();
    console.log('[PWA] IndexedDB inicializado correctamente');
    return pwaDb;
  } catch (err) {
    console.error('[PWA] Error inicializando IndexedDB:', err);
    return createLocalStorageDb();
  }
}

function createLocalStorageDb() {
  // Fallback para navegadores sin IndexedDB
  return {
    clientes: { data: {} },
    prestamos: { data: {} },
    cuotas: { data: {} },
    cobros: { data: {} },
  };
}

// ─────────────────────────────────────────────────────────────────────
// SINCRONIZACIÓN DE DATOS
// ─────────────────────────────────────────────────────────────────────

async function syncAllData() {
  if (!isOnline) {
    console.log('[PWA] Offline - No se puede sincronizar');
    updateOnlineStatus(false);
    return;
  }

  console.log('[PWA] Iniciando sincronización...');
  updateOnlineStatus(true);

  try {
    // 1. Descargar datos nuevos del servidor
    await downloadData();

    // 2. Sincronizar cobros pendientes
    await uploadPendingCobros();

    // 3. Marcar como sincronizado
    const syncRecord = {
      id: 1,
      lastSync: new Date().toISOString(),
      success: true,
    };
    
    if (pwaDb.sincronizacion) {
      await pwaDb.sincronizacion.put(syncRecord);
    }

    showSyncNotification('✅ Sincronización completada', 'success');
  } catch (err) {
    console.error('[PWA] Error en sincronización:', err);
    showSyncNotification('⚠️ Error al sincronizar', 'warning');
  }
}

async function downloadData() {
  console.log('[PWA] Descargando datos del servidor...');
  
  try {
    // Descargar clientes
    const clientesRes = await fetch('/clientes/sync', { credentials: 'same-origin' });
    if (clientesRes.ok) {
      const clientes = await clientesRes.json();
      if (pwaDb.clientes && pwaDb.clientes.bulkPut) {
        await pwaDb.clientes.bulkPut(clientes);
      }
      console.log(`[PWA] ${clientes.length} clientes descargados`);
    }

    // Descargar prestamos
    const prestamosRes = await fetch('/prestamos/sync', { credentials: 'same-origin' });
    if (prestamosRes.ok) {
      const prestamos = await prestamosRes.json();
      if (pwaDb.prestamos && pwaDb.prestamos.bulkPut) {
        await pwaDb.prestamos.bulkPut(prestamos);
      }
      console.log(`[PWA] ${prestamos.length} préstamos descargados`);
    }

    // Descargar cuotas
    const cuotasRes = await fetch('/prestamos/sync/cuotas', { credentials: 'same-origin' });
    if (cuotasRes.ok) {
      const cuotas = await cuotasRes.json();
      if (pwaDb.cuotas && pwaDb.cuotas.bulkPut) {
        await pwaDb.cuotas.bulkPut(cuotas);
      }
      console.log(`[PWA] ${cuotas.length} cuotas descargadas`);
    }

    // Descargar zonas (para poder mostrar el nombre de zona sin conexion)
    const zonasRes = await fetch('/zonas/sync', { credentials: 'same-origin' });
    if (zonasRes.ok) {
      const zonas = await zonasRes.json();
      if (pwaDb.zonas && pwaDb.zonas.bulkPut) {
        await pwaDb.zonas.bulkPut(zonas);
      }
      console.log(`[PWA] ${zonas.length} zonas descargadas`);
    }
  } catch (err) {
    console.error('[PWA] Error descargando datos:', err);
    throw err;
  }
}

async function uploadPendingCobros() {
  console.log('[PWA] Sincronizando cobros pendientes...');
  
  try {
    if (!pwaDb.cobros) {
      console.log('[PWA] No hay DB de cobros');
      return;
    }

    // Obtener cobros pendientes de sincronizar
    const cobrosPendientes = await pwaDb.cobros
      .where('sincronizado')
      .equals(0)
      .toArray();

    console.log(`[PWA] ${cobrosPendientes.length} cobros pendientes`);

    for (const cobro of cobrosPendientes) {
      try {
        const form = new FormData();
        form.set('cuota_id', String(cobro.cuota_id));
        form.set('valor_cobrado', String(cobro.valor_cobrado));
        form.set('metodo_pago', String(cobro.metodo_pago || 'Efectivo'));
        form.set('observaciones', String(cobro.observaciones || 'Cobro sincronizado desde PWA'));
        form.set('lat', String(cobro.lat || ''));
        form.set('lng', String(cobro.lng || ''));
        if (cobro.idempotency_key) form.set('idempotency_key', String(cobro.idempotency_key));
        if (cobro.foto instanceof Blob) {
          form.set('foto', cobro.foto, cobro.foto.name || 'cobro.jpg');
        }
        const response = await fetch('/cobros/registrar', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-CSRF-Token': getCookie('cp_csrf') },
          body: form,
        });

        if (response.ok) {
          // Marcar como sincronizado
          await pwaDb.cobros.update(cobro.id, { sincronizado: 1 });
          console.log(`[PWA] Cobro #${cobro.id} sincronizado`);
        } else if (response.status >= 400 && response.status < 500
                   && response.status !== 408 && response.status !== 429) {
          // El servidor lo rechaza de forma definitiva (cuota ya pagada,
          // datos invalidos...). Antes se dejaba como pendiente y se
          // reintentaba en cada sincronizacion para siempre: el cobrador
          // veia "1 cobro sin enviar" eternamente sin forma de resolverlo.
          // Ahora se marca con el motivo (estado 2) y se avisa una vez.
          let motivo = 'Rechazado por el servidor';
          try { const d = await response.json(); motivo = d.error || d.detail || motivo; } catch (e) {}
          await pwaDb.cobros.update(cobro.id, { sincronizado: 2, error_sync: motivo });
          console.warn(`[PWA] Cobro #${cobro.id} rechazado definitivamente: ${motivo}`);
          showSyncNotification(`Un cobro guardado sin señal no se pudo registrar: ${motivo}`, 'error');
        } else {
          // 5xx / timeout / rate limit: es temporal, se reintenta luego.
          console.warn(`[PWA] Cobro #${cobro.id} no se pudo enviar ahora (${response.status}), se reintenta`);
        }
      } catch (err) {
        console.error(`[PWA] Error sincronizando cobro #${cobro.id}:`, err);
      }
    }
    await updatePendingBadge();
  } catch (err) {
    console.error('[PWA] Error en uploadPendingCobros:', err);
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────────────
// REGISTRO DE COBRO OFFLINE
// ─────────────────────────────────────────────────────────────────────

/**
 * Clave unica por cobro, generada en el celular. Viaja con el cobro y se
 * repite en cada reintento: si la respuesta del servidor se pierde a mitad
 * de camino, el reintento NO le cobra dos veces al cliente.
 */
function nuevaClaveCobro() {
  if (self.crypto && self.crypto.randomUUID) return self.crypto.randomUUID();
  return 'c-' + Date.now() + '-' + Math.random().toString(36).slice(2, 12);
}

async function saveCobro(cobroData) {
  console.log('[PWA] Guardando cobro:', cobroData);
  if (!cobroData.idempotency_key) cobroData.idempotency_key = nuevaClaveCobro();

  try {
    if (isOnline) {
      // Si está online, enviar directo al servidor
      const form = new FormData();
      form.set('cuota_id', String(cobroData.cuota_id));
      form.set('valor_cobrado', String(cobroData.valor_cobrado));
      form.set('metodo_pago', String(cobroData.metodo_pago || 'Efectivo'));
      form.set('observaciones', String(cobroData.observaciones || 'Cobro desde PWA'));
      form.set('lat', String(cobroData.lat || ''));
      form.set('lng', String(cobroData.lng || ''));
      form.set('idempotency_key', String(cobroData.idempotency_key));
      if (cobroData.foto instanceof Blob) {
        form.set('foto', cobroData.foto, cobroData.foto.name || 'cobro.jpg');
      }
      const response = await fetch('/cobros/registrar', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': getCookie('cp_csrf') },
        body: form,
      });

      if (!response.ok) {
        throw new Error('Error del servidor');
      }

      return await response.json();
    } else {
      // Si está offline, guardar en IndexedDB (incluida la foto, si hay)
      if (!pwaDb) pwaDb = await initPwaDb();
      cobroData.sincronizado = 0;
      cobroData.fecha_registro_offline = new Date().toISOString();

      if (pwaDb.cobros && pwaDb.cobros.add) {
        const id = await pwaDb.cobros.add(cobroData);
        console.log(`[PWA] Cobro guardado offline con ID ${id}`);
        await updatePendingBadge();

        // Solicitar sincronización en background (no soportado en iOS/Safari;
        // ahi el respaldo es syncAllData() al reabrir la app con señal)
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
          try {
            const registration = await navigator.serviceWorker.ready;
            await registration.sync.register('sync-cobros');
          } catch (e) {
            console.warn('[PWA] Background Sync no disponible:', e);
          }
        }

        return { id, ok: true, offline: true };
      }
      throw new Error('IndexedDB no disponible en este navegador');
    }
  } catch (err) {
    console.error('[PWA] Error guardando cobro:', err);
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────────────
// CONSULTA DE PENDIENTES SIN CONEXIÓN
// ─────────────────────────────────────────────────────────────────────

/**
 * Replica /cobros/pendientes-ajax leyendo de IndexedDB: mismas reglas
 * (estado Pendiente/Vencida/Parcial, vence en <=3 dias, orden por
 * vencimiento, tope 150) para que el cobrador pueda ver a quien cobrar
 * aunque no tenga señal.
 */
async function getPendientesOffline(q, zonaId, fecha) {
  if (!pwaDb) pwaDb = await initPwaDb();
  if (!pwaDb.cuotas || !pwaDb.cuotas.where) return [];

  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const limite = new Date(hoy);
  limite.setDate(limite.getDate() + 3);
  const qLower = (q || '').trim().toLowerCase();
  const zonaNum = zonaId ? Number(zonaId) : null;

  const cuotas = await pwaDb.cuotas.where('estado').anyOf(['Pendiente', 'Vencida', 'Parcial']).toArray();
  const candidatos = [];

  for (const cu of cuotas) {
    if (!cu.fecha_vencimiento) continue;
    const venc = new Date(cu.fecha_vencimiento + 'T00:00:00');
    if (isNaN(venc.getTime()) || venc > limite) continue;

    const prestamo = await pwaDb.prestamos.get(cu.prestamo_id);
    if (!prestamo) continue;
    if (zonaNum && Number(prestamo.zona_id) !== zonaNum) continue;

    const cliente = await pwaDb.clientes.get(prestamo.cliente_id);
    if (!cliente) continue;
    if (qLower) {
      const enNombre = (cliente.nombre || '').toLowerCase().includes(qLower);
      const enCedula = (cliente.cedula || '').toLowerCase().includes(qLower);
      if (!enNombre && !enCedula) continue;
    }

    candidatos.push({ cu, prestamo, cliente, venc });
  }

  candidatos.sort((a, b) => a.venc - b.venc);

  return candidatos.slice(0, 150).map(({ cu, prestamo, cliente, venc }) => ({
    cuota_id: cu.id,
    prestamo_id: prestamo.id,
    cliente_id: cliente.id,
    cliente: cliente.nombre,
    cedula: cliente.cedula,
    whatsapp: cliente.telefono || '',
    cuota_num: cu.numero,
    total_cuotas: prestamo.num_cuotas,
    valor: cu.valor,
    estado: cu.estado,
    vencimiento: venc.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' }),
    dias: Math.round((hoy - venc) / 86400000),
  }));
}

/**
 * Replica /clientes/buscar-ajax leyendo de IndexedDB (clientes+prestamos+
 * zonas ya descargados) para poder seguir consultando clientes sin señal.
 * No pagina (basta con un tope razonable para consulta en campo).
 */
async function getClientesOffline(q, zonaId) {
  if (!pwaDb) pwaDb = await initPwaDb();
  if (!pwaDb.clientes || !pwaDb.clientes.toArray) return [];

  const qLower = (q || '').trim().toLowerCase();
  const zonaNum = zonaId ? Number(zonaId) : null;
  if (!qLower && !zonaNum) return [];

  const [clientes, prestamos, zonas] = await Promise.all([
    pwaDb.clientes.toArray(),
    pwaDb.prestamos.toArray(),
    (pwaDb.zonas && pwaDb.zonas.toArray) ? pwaDb.zonas.toArray() : Promise.resolve([]),
  ]);
  const zonasPorId = new Map(zonas.map(z => [z.id, z.nombre]));
  const estadosActivos = ['Activo', 'activo', 'Atrasado', 'atrasado'];
  const prestamoPorCliente = new Map();
  for (const p of prestamos) {
    if (!estadosActivos.includes(p.estado)) continue;
    if (!prestamoPorCliente.has(p.cliente_id)) prestamoPorCliente.set(p.cliente_id, p);
  }

  return clientes
    .filter(c => {
      if (zonaNum && Number(c.zona_id) !== zonaNum) return false;
      if (qLower) {
        const enNombre = (c.nombre || '').toLowerCase().includes(qLower);
        const enCedula = (c.cedula || '').toLowerCase().includes(qLower);
        if (!enNombre && !enCedula) return false;
      }
      return true;
    })
    .sort((a, b) => (a.nombre || '').localeCompare(b.nombre || ''))
    .slice(0, 100)
    .map(c => {
      const p = prestamoPorCliente.get(c.id);
      return {
        id: c.id,
        cedula: c.cedula,
        nombre: c.nombre,
        telefono: c.telefono || '',
        whatsapp: c.telefono || '',
        zona: zonasPorId.get(c.zona_id) || '—',
        zona_id: c.zona_id,
        tipo_cliente: c.tipo_cliente || 'Regular',
        foto_path: '',
        prestamo: p ? {
          id: p.id,
          capital: Number(p.capital) || 0,
          total: Number(p.total_pagar || p.capital) || 0,
          saldo: Number(p.total_pagar || p.capital) || 0,
          num_cuotas: p.num_cuotas || 0,
          estado: p.estado || 'Activo',
        } : null,
      };
    });
}

/**
 * Replica /prestamos/buscar-ajax leyendo de IndexedDB para poder seguir
 * consultando la lista de prestamos sin señal.
 */
async function getPrestamosOffline(q, estado, zonaId) {
  if (!pwaDb) pwaDb = await initPwaDb();
  if (!pwaDb.prestamos || !pwaDb.prestamos.toArray) return [];

  const qLower = (q || '').trim().toLowerCase();
  const estadoLower = (estado || '').trim().toLowerCase();
  const zonaNum = zonaId ? Number(zonaId) : null;
  if (!qLower && !estadoLower && !zonaNum) return [];

  const [prestamos, clientes, zonas] = await Promise.all([
    pwaDb.prestamos.toArray(),
    pwaDb.clientes.toArray(),
    (pwaDb.zonas && pwaDb.zonas.toArray) ? pwaDb.zonas.toArray() : Promise.resolve([]),
  ]);
  const clientesPorId = new Map(clientes.map(c => [c.id, c]));
  const zonasPorId = new Map(zonas.map(z => [z.id, z.nombre]));

  const formatearFecha = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso + 'T00:00:00');
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  return prestamos
    .filter(p => {
      if (zonaNum && Number(p.zona_id) !== zonaNum) return false;
      if (estadoLower && !(p.estado || '').toLowerCase().includes(estadoLower)) return false;
      if (qLower) {
        const c = clientesPorId.get(p.cliente_id);
        const enNombre = c && (c.nombre || '').toLowerCase().includes(qLower);
        const enCedula = c && (c.cedula || '').toLowerCase().includes(qLower);
        if (!enNombre && !enCedula) return false;
      }
      return true;
    })
    .slice(0, 100)
    .map(p => {
      const c = clientesPorId.get(p.cliente_id) || {};
      return {
        id: p.id,
        cliente: c.nombre || '—',
        cedula: c.cedula || '—',
        cliente_id: p.cliente_id,
        capital: Number(p.capital) || 0,
        total: Number(p.total_pagar || p.capital) || 0,
        saldo: Number(p.total_pagar || p.capital) || 0,
        num_cuotas: p.num_cuotas || 0,
        valor_cuota: Number(p.valor_cuota) || 0,
        estado: p.estado || 'Activo',
        zona: zonasPorId.get(p.zona_id) || '—',
        fecha_inicio: formatearFecha(p.fecha_inicio),
        tipo_cliente: c.tipo_cliente || 'Regular',
      };
    });
}

async function pendingCobrosCount() {
  if (!pwaDb || !pwaDb.cobros || !pwaDb.cobros.where) return 0;
  try {
    return await pwaDb.cobros.where('sincronizado').equals(0).count();
  } catch (e) {
    return 0;
  }
}

async function updatePendingBadge() {
  const el = document.querySelector('[data-pending-count]');
  if (!el) return;
  const n = await pendingCobrosCount();
  if (n > 0) {
    el.textContent = n === 1 ? '1 cobro sin enviar' : `${n} cobros sin enviar`;
    el.style.display = 'inline-block';
  } else {
    el.style.display = 'none';
  }
}

function getCookie(name) {
  const prefix = `${name}=`;
  const item = document.cookie.split('; ').find(value => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : '';
}

// ─────────────────────────────────────────────────────────────────────
// ESTADO ONLINE/OFFLINE
// ─────────────────────────────────────────────────────────────────────

function updateOnlineStatus(online) {
  isOnline = online;
  const indicator = document.querySelector('[data-online-indicator]');
  
  if (indicator) {
    if (online) {
      indicator.textContent = '🟢 Conectado';
      indicator.style.color = '#10b981';
    } else {
      indicator.textContent = '🔴 Offline';
      indicator.style.color = '#ef4444';
    }
  }

  console.log(`[PWA] Estado: ${online ? 'ONLINE' : 'OFFLINE'}`);
}

window.addEventListener('online', () => {
  updateOnlineStatus(true);
  syncAllData();
});

window.addEventListener('offline', () => {
  updateOnlineStatus(false);
});

// ─────────────────────────────────────────────────────────────────────
// NOTIFICACIONES DE SINCRONIZACIÓN
// ─────────────────────────────────────────────────────────────────────

function showSyncNotification(message, type = 'info') {
  if (typeof window.toast === 'function') {
    const tipo = type === 'success' ? 'success' : type === 'warning' ? 'warn' : 'info';
    window.toast(message, tipo);
    return;
  }
  const notification = document.createElement('div');
  notification.className = `pwa-notification pwa-notification-${type}`;
  notification.textContent = message;
  notification.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 8px;
    background: ${type === 'success' ? '#10b981' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
    color: white;
    font-weight: 600;
    z-index: 10000;
    animation: slideInLeft 0.3s ease-out;
  `;

  document.body.appendChild(notification);

  // Remover después de 3 segundos
  setTimeout(() => {
    notification.style.animation = 'fadeOut 0.3s ease-out';
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

// ─────────────────────────────────────────────────────────────────────
// ESCUCHAR MENSAJES DEL SERVICE WORKER
// ─────────────────────────────────────────────────────────────────────

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', (event) => {
    const { type, synced } = event.data;

    if (type === 'SYNC_COMPLETE') {
      showSyncNotification(`✅ ${synced} cobro(s) sincronizado(s)`, 'success');
    }
  });
}

// ─────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN
// ─────────────────────────────────────────────────────────────────────

async function initPwa() {
  console.log('[PWA] Inicializando...');

  try {
    // 1. Registrar Service Worker
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.register('/static/sw.js');
      console.log('[PWA] Service Worker registrado:', registration);
    }

    // 2. Inicializar IndexedDB
    pwaDb = await initPwaDb();
    console.log('[PWA] IndexedDB inicializado');

    // 3. Verificar estado online
    updateOnlineStatus(navigator.onLine);
    await updatePendingBadge();

    // 4. Sincronizar datos iniciales
    if (isOnline) {
      await syncAllData();
    }

    // 5. Sincronizar cada 5 minutos
    setInterval(() => {
      if (isOnline) {
        syncAllData();
      }
    }, 5 * 60 * 1000);

    console.log('[PWA] ✅ PWA completamente inicializado');
  } catch (err) {
    console.error('[PWA] Error en inicialización:', err);
  }
}

// Iniciar cuando el DOM esté listo
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPwa);
} else {
  initPwa();
}

// Exportar para uso externo
window.pwa = {
  saveCobro,
  syncAllData,
  getPendientesOffline,
  getClientesOffline,
  getPrestamosOffline,
  pendingCobrosCount,
  isOnline: () => isOnline,
  getDb: () => pwaDb,
};
