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
        const form = new URLSearchParams();
        form.set('cuota_id', String(cobro.cuota_id));
        form.set('valor_cobrado', String(cobro.valor_cobrado));
        form.set('metodo_pago', String(cobro.metodo_pago || 'Efectivo'));
        form.set('observaciones', String(cobro.observaciones || 'Cobro sincronizado desde PWA'));
        form.set('lat', String(cobro.lat || ''));
        form.set('lng', String(cobro.lng || ''));
        const response = await fetch('/cobros/registrar', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'X-CSRF-Token': getCookie('cp_csrf'),
          },
          body: form,
        });

        if (response.ok) {
          // Marcar como sincronizado
          await pwaDb.cobros.update(cobro.id, { sincronizado: 1 });
          console.log(`[PWA] Cobro #${cobro.id} sincronizado`);
        }
      } catch (err) {
        console.error(`[PWA] Error sincronizando cobro #${cobro.id}:`, err);
      }
    }
  } catch (err) {
    console.error('[PWA] Error en uploadPendingCobros:', err);
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────────────
// REGISTRO DE COBRO OFFLINE
// ─────────────────────────────────────────────────────────────────────

async function saveCobro(cobroData) {
  console.log('[PWA] Guardando cobro:', cobroData);

  try {
    if (isOnline) {
      // Si está online, enviar directo al servidor
      const form = new URLSearchParams();
      form.set('cuota_id', String(cobroData.cuota_id));
      form.set('valor_cobrado', String(cobroData.valor_cobrado));
      form.set('metodo_pago', String(cobroData.metodo_pago || 'Efectivo'));
      form.set('observaciones', String(cobroData.observaciones || 'Cobro desde PWA'));
      form.set('lat', String(cobroData.lat || ''));
      form.set('lng', String(cobroData.lng || ''));
      const response = await fetch('/cobros/registrar', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
          'X-CSRF-Token': getCookie('cp_csrf'),
        },
        body: form,
      });

      if (!response.ok) {
        throw new Error('Error del servidor');
      }

      return await response.json();
    } else {
      // Si está offline, guardar en IndexedDB
      cobroData.sincronizado = 0;
      cobroData.fecha_registro_offline = new Date().toISOString();

      if (pwaDb.cobros) {
        const id = await pwaDb.cobros.add(cobroData);
        console.log(`[PWA] Cobro guardado offline con ID ${id}`);
        
        // Solicitar sincronización en background
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
          const registration = await navigator.serviceWorker.ready;
          await registration.sync.register('sync-cobros');
        }

        return { id, ok: true, offline: true };
      }
    }
  } catch (err) {
    console.error('[PWA] Error guardando cobro:', err);
    throw err;
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
  isOnline: () => isOnline,
  getDb: () => pwaDb,
};
