if(!window.anime){window.anime=(opts)=>{const raw=opts.targets;const targets=typeof raw==='string'?document.querySelectorAll(raw):raw&&raw.length!==undefined?raw:[raw];Array.from(targets||[]).forEach(el=>{if(el&&el.style){el.style.opacity='1';el.style.removeProperty('transform');}});if(opts.complete)opts.complete();return {add(){return this}}};anime.stagger=()=>0;}
// ── SIDEBAR ──
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('backdrop').classList.toggle('open')}
function closeSidebar(){document.getElementById('sidebar').classList.remove('open');document.getElementById('backdrop').classList.remove('open')}

// ── CLOCK ──
function tick(){const el=document.getElementById('fecha-hora');if(el)el.textContent=new Date().toLocaleString('es-CO',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})}
tick();setInterval(tick,30000);

// ── TOAST (seguro contra XSS) ──
function toast(msg,tipo='success',ms=null){
  const t=document.getElementById('toast');
  // Los errores se leen mas despacio que un "guardado ✓"
  if(ms===null) ms = (tipo==='error') ? 5200 : 3200;
  // Construir DOM con createElement para evitar que 'msg' se interprete como HTML
  while(t.firstChild)t.removeChild(t.firstChild);
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('width','14');svg.setAttribute('height','14');
  svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');
  svg.setAttribute('stroke-width','2.5');svg.setAttribute('viewBox','0 0 24 24');
  if(tipo==='success'){
    const p=document.createElementNS(ns,'polyline');
    p.setAttribute('points','20 6 9 17 4 12');svg.appendChild(p);
  }else if(tipo==='error'){
    // Triangulo de advertencia, NO una "X": una X se lee como boton de cerrar
    // y la gente le hace clic esperando que el aviso desaparezca.
    const p=document.createElementNS(ns,'path');
    p.setAttribute('d','M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z');
    const l1=document.createElementNS(ns,'line');
    l1.setAttribute('x1','12');l1.setAttribute('y1','9');l1.setAttribute('x2','12');l1.setAttribute('y2','13');
    const l2=document.createElementNS(ns,'line');
    l2.setAttribute('x1','12');l2.setAttribute('y1','17');l2.setAttribute('x2','12.01');l2.setAttribute('y2','17');
    svg.appendChild(p);svg.appendChild(l1);svg.appendChild(l2);
  }else{
    const c=document.createElementNS(ns,'circle');c.setAttribute('cx','12');c.setAttribute('cy','12');c.setAttribute('r','10');
    const l1=document.createElementNS(ns,'line');l1.setAttribute('x1','12');l1.setAttribute('y1','8');l1.setAttribute('x2','12');l1.setAttribute('y2','12');
    const l2=document.createElementNS(ns,'line');l2.setAttribute('x1','12');l2.setAttribute('y1','16');l2.setAttribute('x2','12.01');l2.setAttribute('y2','16');
    svg.appendChild(c);svg.appendChild(l1);svg.appendChild(l2);
  }
  t.appendChild(svg);
  // textContent NO interpreta HTML: previene XSS incluso si 'msg' trae tags
  t.appendChild(document.createTextNode(' '+msg));
  t.className=tipo;t.style.display='flex';t.style.opacity='1';
  clearTimeout(t._t);
  // Cerrar con clic: la gente igual intenta hacerle clic al aviso, sobre todo
  // cuando trae un icono. Mejor que responda a que parezca congelado.
  t.style.cursor='pointer';t.title='Clic para cerrar';
  t.onclick=()=>{clearTimeout(t._t);t.style.display='none';};
  
  // Intentar usar Anime.js
  if(window.anime&&typeof anime==='function'){
    try{
      anime({targets:t,translateY:[12,0],opacity:[0,1],duration:350,easing:'easeOutBack'});
    }catch(e){
      t.style.transform='translateY(0)';
    }
  }
  
  t._t=setTimeout(()=>{
    if(window.anime&&typeof anime==='function'){
      try{
        anime({targets:t,translateY:[0,8],opacity:[1,0],duration:250,easing:'easeInQuad',complete:()=>{t.style.display='none'}});
        return;
      }catch(e){}
    }
    t.style.display='none';
  },ms);
}

// ── FORMAT COP ──
function cop(n){return new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',minimumFractionDigits:0,maximumFractionDigits:0}).format(n||0)}
function fmt(n){return new Intl.NumberFormat('es-CO').format(Math.round(n||0))}

// ── MODAL GENERICO (abrirModal/cerrarModal) ──
// Usado por paginas que arman el contenido del modal dinamicamente
// (ej. zonas.html, whatsapp.html). titulo/cuerpo/pie ya vienen escapados
// por quien llama (esc()/attr()) antes de interpolarse en el HTML.
function abrirModal(titulo,cuerpoHtml,pieHtml){
  let modal=document.getElementById('modal-generico');
  if(!modal){
    modal=document.createElement('div');
    modal.id='modal-generico';
    modal.className='modal-overlay';
    modal.innerHTML='<div class="modal" onclick="event.stopPropagation()">'
      +'<div class="modal-header">'
        +'<div class="modal-title" id="modal-generico-titulo"></div>'
        +'<button class="btn btn-ghost btn-icon" onclick="cerrarModal()">✕</button>'
      +'</div>'
      +'<div class="modal-body" id="modal-generico-cuerpo"></div>'
      +'<div class="modal-footer" id="modal-generico-pie"></div>'
    +'</div>';
    document.body.appendChild(modal);
    if(typeof observer!=='undefined')observer.observe(modal,{attributes:true,attributeFilter:['class']});
  }
  document.getElementById('modal-generico-titulo').innerHTML=titulo||'';
  document.getElementById('modal-generico-cuerpo').innerHTML=cuerpoHtml||'';
  document.getElementById('modal-generico-pie').innerHTML=pieHtml||'';
  modal.classList.add('open');
}
function cerrarModal(){
  const modal=document.getElementById('modal-generico');
  if(modal)modal.classList.remove('open');
}

// ── MODAL CLOSE ON ESC ──
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.modal-overlay.open').forEach(m=>m.classList.remove('open'))});

// ── MODAL OPEN ANIMATION ──
document.addEventListener('click',e=>{
  const overlay=e.target.closest('.modal-overlay');
  if(overlay&&overlay.classList.contains('open')){
    const modal=overlay.querySelector('.modal');
    if(modal&&!modal.contains(e.target))overlay.classList.remove('open');
  }
});
const observer=new MutationObserver(mutations=>{
  mutations.forEach(m=>{
    if(m.target.classList.contains('modal-overlay')&&m.target.classList.contains('open')){
      const modal=m.target.querySelector('.modal');
      if(modal){
        if(window.anime&&typeof anime==='function'){
          try{
            anime({targets:modal,translateY:[-20,0],opacity:[0,1],scale:[.96,1],duration:380,easing:'easeOutBack'});
          }catch(e){
            modal.style.opacity='1';
            modal.style.transform='scale(1) translateY(0)';
          }
        }else{
          modal.style.opacity='1';
          modal.style.transform='scale(1) translateY(0)';
        }
      }
    }
  });
});
document.querySelectorAll('.modal-overlay').forEach(el=>observer.observe(el,{attributes:true,attributeFilter:['class']}));

// ── PAGE TRANSITION ──
function navigateTo(url){ window.location.href=url; }
// Subtle fade on nav items only - no blocking transition
document.addEventListener('click',e=>{
  const a=e.target.closest('.nav-item');
  if(a&&a.href&&a.origin===location.origin&&!e.ctrlKey&&!e.metaKey){
    document.querySelectorAll('.nav-item').forEach(n=>n.style.opacity='.5');
  }
});

// ── SIDEBAR ANIMATION ON LOAD ──
document.addEventListener('DOMContentLoaded',()=>{
  // Fallback de seguridad: si Anime no funciona, mostrar después de 1.5s
  setTimeout(()=>{
    document.querySelectorAll('#nav .nav-item, .stat-card, .card-anim, #page-content').forEach(el=>{
      if(el.style.opacity==='0'||el.style.opacity===''){
        el.style.opacity='1';
        el.style.removeProperty('transform');
      }
    });
  },1500);
  
  // Intentar animación con Anime.js
  if(window.anime&&typeof anime==='function'){
    try{
      // Al terminar hay que QUITAR el transform que deja anime.js, no dejarlo
      // en translateY(0). Un elemento con transform se convierte en el marco
      // de referencia de todo position:fixed que tenga dentro, asi que el
      // transform residual de #page-content hacia que los modales se anclaran
      // al alto del contenido en vez de a la pantalla: en paginas largas
      // (Cobros, Clientes) el modal se abria cientos de pixeles mas abajo del
      // area visible y solo se veia el fondo oscurecido. En las tarjetas
      // ademas pisaba el efecto de elevacion al pasar el raton, porque un
      // estilo en linea gana a la hoja de estilos.
      const limpiarTransform = (anim) => {
        anim.animatables.forEach(a => a.target.style.removeProperty('transform'));
      };
      anime({targets:'#nav .nav-item',translateX:[-12,0],opacity:[0,1],delay:anime.stagger(50,{start:100}),duration:400,easing:'easeOutQuart',complete:limpiarTransform});
      anime({targets:'.stat-card,.card-anim',translateY:[16,0],opacity:[0,1],delay:anime.stagger(60,{start:200}),duration:450,easing:'easeOutQuart',complete:limpiarTransform});
      anime({targets:'#page-content',opacity:[0,1],translateY:[8,0],duration:400,easing:'easeOutQuart',delay:150,complete:limpiarTransform});
    }catch(e){
      console.warn('[CreditosPro] Anime.js error:',e);
      // Fallback inmediato
      document.querySelectorAll('#nav .nav-item, .stat-card, .card-anim, #page-content').forEach(el=>{
        el.style.opacity='1';
        el.style.removeProperty('transform');
      });
    }
  }else{
    // Anime.js no cargó, mostrar todo inmediatamente
    document.querySelectorAll('#nav .nav-item, .stat-card, .card-anim, #page-content').forEach(el=>{
      el.style.opacity='1';
      el.style.removeProperty('transform');
    });
  }
});

// ── PWA ──
// El registro del Service Worker y la inicializacion de IndexedDB
// ocurren en pwa.js (initPwa), cargado mas abajo — no duplicar aqui.
let _pwaP=null;
window.addEventListener('beforeinstallprompt',e=>{
  e.preventDefault();_pwaP=e;
  if(!localStorage.getItem('pwa_d'))document.getElementById('pwa-banner').classList.add('show');
});

// iPhone/iPad: Safari NUNCA dispara beforeinstallprompt, asi que el boton
// "Instalar" no aparece jamas y el cobrador no se entera de que puede
// instalar la app. Ahi se explica el camino manual (Compartir -> Añadir a
// pantalla de inicio), que es la unica via en iOS.
(function avisoInstalarEnIphone(){
  const esIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
             || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const yaInstalada = window.navigator.standalone === true
             || window.matchMedia('(display-mode: standalone)').matches;
  if(!esIOS || yaInstalada || localStorage.getItem('pwa_d')) return;
  const b = document.getElementById('pwa-banner');
  if(!b) return;
  b.querySelector('.pwa-text').innerHTML =
    '<strong>Instalar CreditosPro</strong>' +
    '<span>Toca Compartir y luego "Añadir a pantalla de inicio"</span>';
  const btn = document.getElementById('pwa-install-btn');
  btn.textContent = 'Entendido';
  btn.addEventListener('click', () => {
    b.classList.remove('show');
    localStorage.setItem('pwa_d','1');
  });
  setTimeout(()=>b.classList.add('show'), 2500);
})();
document.getElementById('pwa-install-btn').addEventListener('click',async()=>{
  if(!_pwaP)return;
  _pwaP.prompt();
  const{outcome}=await _pwaP.userChoice;
  document.getElementById('pwa-banner').classList.remove('show');
  if(outcome==='accepted')toast('CreditosPro instalado','success');
  localStorage.setItem('pwa_d','1');_pwaP=null;
});

// Al cerrar sesion se borra el cache del service worker: las pantallas
// guardadas para trabajar sin señal son de ESTE usuario, y el celular puede
// pasar a otro cobrador.
function cerrarSesion(ev){
  // La confirmacion es la ventana de la app, que no bloquea el hilo como
  // confirm(): se detiene la navegacion y se retoma al aceptar.
  const destino = (ev && ev.currentTarget && ev.currentTarget.href) || '/auth/logout';
  if(ev) ev.preventDefault();
  const pendientes = pendientesSinSenal();
  const aviso = pendientes
    ? `Hay ${pendientes} registro(s) guardados sin señal que aún no se han enviado. Si cierras sesión sin señal se perderán.`
    : '¿Cerrar sesión?';
  confirmar(aviso, {aceptar: 'Cerrar sesión', titulo: '¿Cerrar sesión?'}).then(async ok => {
    if(!ok) return;
    await vaciarColaSinSenal();
    _borrarDatosSinSenal();
    try { localStorage.removeItem(_COLA); } catch(e) {}
    try{
      if(navigator.serviceWorker && navigator.serviceWorker.controller){
        navigator.serviceWorker.controller.postMessage({type:'LIMPIAR_CACHE'});
      }
    }catch(e){}
    location.href = destino;
  });
  return false;
}

// ── VENTANAS DE CONFIRMACION Y DE TEXTO ──
// En lugar de confirm() y prompt() del navegador: esas bloquean la pagina,
// no se pueden estilizar y encabezan el aviso con la direccion del servidor
// ("creditospro-production.up.railway.app dice..."). Estas usan el mismo
// modal que el resto de la app y devuelven una promesa:
//   if (!(await confirmar('¿Retirar este gasto?'))) return;
//   const motivo = await pedirTexto('Motivo', {placeholder: 'opcional'});  // null = cancelo
function _dialogo({titulo, mensaje, aceptar, cancelar, peligro, campo}){
  return new Promise(resolve => {
    // Un aviso que sigue en pantalla quedaria encima de los botones (en el
    // celular la ventana sale abajo, justo donde vive el aviso).
    const aviso = document.getElementById('toast');
    if(aviso){ clearTimeout(aviso._t); aviso.style.display = 'none'; }
    const fondo = document.createElement('div');
    fondo.className = 'modal-overlay open dialogo-app';
    fondo.setAttribute('role', 'dialog');
    fondo.setAttribute('aria-modal', 'true');
    const caja = document.createElement('div');
    caja.className = 'modal';
    caja.style.maxWidth = '420px';

    const cab = document.createElement('div');
    cab.className = 'modal-header';
    const t = document.createElement('div');
    t.className = 'modal-title';
    t.textContent = titulo || 'Confirmar';           // textContent: nunca HTML
    cab.appendChild(t);

    const cuerpo = document.createElement('div');
    cuerpo.className = 'modal-body';
    if(mensaje){
      const m = document.createElement('div');
      m.className = 'fs-13';
      m.style.whiteSpace = 'pre-line';
      m.textContent = mensaje;
      cuerpo.appendChild(m);
    }
    let entrada = null;
    if(campo){
      entrada = document.createElement('input');
      entrada.type = campo.tipo || 'text';
      entrada.value = campo.valor || '';
      entrada.placeholder = campo.placeholder || '';
      entrada.maxLength = campo.max || 300;
      entrada.autocomplete = 'off';
      entrada.style.marginTop = mensaje ? '12px' : '0';
      entrada.style.width = '100%';
      cuerpo.appendChild(entrada);
    }

    const pie = document.createElement('div');
    pie.className = 'modal-footer';
    const no = document.createElement('button');
    no.type = 'button'; no.className = 'btn';
    no.textContent = cancelar || 'Cancelar';
    const si = document.createElement('button');
    si.type = 'button'; si.className = 'btn ' + (peligro ? 'btn-danger' : 'btn-gold');
    si.textContent = aceptar || 'Aceptar';
    pie.appendChild(no); pie.appendChild(si);

    caja.appendChild(cab); caja.appendChild(cuerpo); caja.appendChild(pie);
    fondo.appendChild(caja);
    document.body.appendChild(fondo);

    let hecho = false;
    const cerrar = valor => {
      if(hecho) return;
      hecho = true;
      vigia.disconnect();
      fondo.remove();
      resolve(valor);
    };
    const respuestaSi = () => cerrar(campo ? entrada.value : true);
    const respuestaNo = () => cerrar(campo ? null : false);
    si.addEventListener('click', respuestaSi);
    no.addEventListener('click', respuestaNo);
    fondo.addEventListener('click', e => { if(e.target === fondo) respuestaNo(); });
    caja.addEventListener('keydown', e => {
      if(e.key === 'Enter' && (entrada ? e.target === entrada : true)){ e.preventDefault(); respuestaSi(); }
    });
    // Escape (y cualquier codigo que cierre los modales abiertos) le quita
    // la clase "open": eso cuenta como cancelar.
    const vigia = new MutationObserver(() => {
      if(!fondo.classList.contains('open')) respuestaNo();
    });
    vigia.observe(fondo, {attributes: true, attributeFilter: ['class']});
    setTimeout(() => (entrada || si).focus(), 30);
  });
}

function confirmar(mensaje, opciones){
  const o = opciones || {};
  return _dialogo({titulo: o.titulo || 'Confirmar', mensaje,
                   aceptar: o.aceptar || 'Sí, continuar', cancelar: o.cancelar,
                   peligro: !!o.peligro});
}

function pedirTexto(mensaje, opciones){
  const o = opciones || {};
  return _dialogo({titulo: o.titulo || 'Escribe', mensaje,
                   aceptar: o.aceptar || 'Guardar', cancelar: o.cancelar,
                   campo: {valor: o.valor, placeholder: o.placeholder, tipo: o.tipo, max: o.max}});
}

// Lee la respuesta del servidor sin romperse si no es JSON. Antes, cualquier
// respuesta que no fuera JSON (un 500 sin manejar, o un 502 del proxy cuando
// el servidor se esta reiniciando) hacia fallar response.json(), caia en el
// catch y se mostraba "Error de conexión. Intenta nuevamente." -- culpando al
// internet del usuario y sin dejar rastro de que fue lo que paso realmente.
async function leerRespuesta(r){
  let datos = null, texto = '';
  try { datos = await r.clone().json(); }
  catch(e){ try { texto = (await r.text()).slice(0,200); } catch(e2){} }
  if (datos) {
    // Por si algun endpoint aun contesta {"detail": [...]}: una lista de
    // objetos en un aviso se lee "[object Object],[object Object]".
    if (!datos.error && datos.detail && !datos.ok) {
      datos.error = typeof datos.detail === 'string'
        ? datos.detail : 'Revisa los datos del formulario';
    }
    if (Array.isArray(datos.detail)) delete datos.detail;
    return datos;
  }
  if (r.status === 502 || r.status === 503 || r.status === 504) {
    return { error: 'El servidor no está respondiendo en este momento (puede estar actualizándose). Espera unos segundos e intenta de nuevo.' };
  }
  if (r.status === 401 || r.status === 403) {
    return { error: 'Tu sesión expiró. Vuelve a iniciar sesión.' };
  }
  console.error('[Respuesta no JSON]', r.status, texto);
  return { error: `El servidor respondió con un error (${r.status}). Intenta de nuevo.` };
}

// ── ANTI DOBLE CLIC ──
// Envuelve una accion async: bloquea el boton al primer clic y lo restaura al
// terminar. Si el usuario le da 5 veces seguidas, los clics 2..5 se ignoran
// (el boton ya esta disabled) en vez de mandar 5 peticiones al servidor.
async function conBoton(btn, textoCargando, fn){
  if(!btn) return await fn();
  if(btn.disabled) return;            // ya hay una peticion en curso
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span>' + (textoCargando || 'Guardando...');
  try{
    return await fn();
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

// Marca/limpia un error debajo de un campo concreto (en vez de un alert global).
// Acepta el id del campo o el elemento mismo.
function errorCampo(campo, mensaje){
  const inp = (typeof campo === 'string') ? document.getElementById(campo) : campo;
  if(!inp) return;
  let box = inp.parentElement.querySelector('.field-error');
  if(!box){
    box = document.createElement('div');
    box.className = 'field-error';
    inp.parentElement.appendChild(box);
  }
  if(mensaje){
    box.textContent = mensaje; box.classList.add('show'); inp.classList.add('has-error');
  }else{
    box.classList.remove('show'); inp.classList.remove('has-error');
  }
}
function limpiarErroresCampos(contenedor){
  (contenedor||document).querySelectorAll('.field-error.show').forEach(b=>b.classList.remove('show'));
  (contenedor||document).querySelectorAll('.has-error').forEach(i=>i.classList.remove('has-error'));
}

// ── COORDENADAS → DIRECCION LEGIBLE ──
// Un cobrador en la calle no puede verificar "6.28521, -75.56153". Esto lo
// convierte en "Calle 52A #51-20, Bello" usando OpenStreetMap (gratis, sin
// llave). Si falla o no hay internet devuelve null y el llamador muestra las
// coordenadas: nunca bloquea el registro del cobro.
const _cacheDirecciones = {};
async function direccionDesdeCoords(lat, lng){
  const clave = lat.toFixed(5)+','+lng.toFixed(5);
  if(clave in _cacheDirecciones) return _cacheDirecciones[clave];
  try{
    const ctrl = new AbortController();
    const corte = setTimeout(()=>ctrl.abort(), 6000);
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18`
              + `&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lng)}`;
    const r = await fetch(url, {signal: ctrl.signal, headers:{'Accept':'application/json'}});
    clearTimeout(corte);
    if(!r.ok) return null;
    const d = await r.json();
    const a = d.address || {};
    const via = [a.road, a.house_number].filter(Boolean).join(' #');
    const zona = a.neighbourhood || a.suburb || a.city_district || '';
    const ciudad = a.city || a.town || a.village || a.municipality || '';
    const texto = [via, zona, ciudad].filter(Boolean).join(', ') || d.display_name || null;
    _cacheDirecciones[clave] = texto;
    return texto;
  }catch(e){
    return null;   // sin internet o servicio caido: se muestran las coordenadas
  }
}

// ── CSRF ──
function getCsrf(){return document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('cp_csrf='))?.split('=')[1]||''}

// ── API HELPER ──
async function api(method,url,data=null){
  const opts={method,headers:{'x-csrf-token':getCsrf()}};
  if(data){if(data instanceof FormData)opts.body=data;else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data);}}
  const r=await window.fetch(url,opts);return r.json();
}

// Patch global fetch to always send CSRF on POST/PUT/DELETE
const _origFetch = window.fetch;
window.fetch = function(url, opts={}) {
  if(opts.method && !['GET','HEAD','OPTIONS'].includes(opts.method.toUpperCase())){
    opts.headers = opts.headers || {};
    if(!opts.headers['x-csrf-token']) opts.headers['x-csrf-token'] = getCsrf();
  }
  return _origFetch(url, opts);
};

// ── COLA SIN SEÑAL ──
// Para lo que se registra en la calle y no es un cobro: el "no pagó" y el
// orden de la ruta. (Los cobros tienen su propia cola en pwa.js, con foto y
// clave contra duplicados.) Se guarda en el celular y se envia sola cuando
// vuelve la señal. `clave` reemplaza lo anterior con la misma clave: del
// orden de una zona solo importa el ultimo.
const _COLA = 'cp-cola-sin-senal';
function _leerCola(){ try { return JSON.parse(localStorage.getItem(_COLA) || '[]'); } catch(e){ return []; } }
function _guardarCola(c){ try { localStorage.setItem(_COLA, JSON.stringify(c)); } catch(e){} }
function encolarSinSenal(url, campos, clave){
  const cola = _leerCola().filter(x => !clave || x.clave !== clave);
  cola.push({url, campos, clave: clave || null, t: Date.now()});
  _guardarCola(cola);
}
function pendientesSinSenal(){ return _leerCola().length; }
let _vaciando = false;
async function vaciarColaSinSenal(){
  if (_vaciando || !navigator.onLine) return 0;
  const cola = _leerCola();
  if (!cola.length) return 0;
  _vaciando = true;
  const quedan = [];
  let enviados = 0;
  try {
    for (const x of cola) {
      try {
        const fd = new FormData();
        Object.entries(x.campos || {}).forEach(([k, v]) => fd.append(k, v == null ? '' : v));
        const r = await window.fetch(x.url, {method: 'POST', body: fd});
        // 4xx definitivo (ya no aplica, datos invalidos): se descarta para no
        // reintentar para siempre. 5xx o sin respuesta: se reintenta luego.
        if (r.ok || (r.status >= 400 && r.status < 500 && r.status !== 408 && r.status !== 429)) enviados++;
        else quedan.push(x);
      } catch(e) { quedan.push(x); }
    }
  } finally {
    // Lo que se encolo mientras se vaciaba no se pierde.
    const nuevos = _leerCola().filter(x => !cola.some(y => y.t === x.t && y.url === x.url));
    _guardarCola(quedan.concat(nuevos));
    _vaciando = false;
  }
  if (enviados && typeof window.alVaciarColaSinSenal === 'function') window.alVaciarColaSinSenal(enviados);
  return enviados;
}
window.addEventListener('online', () => setTimeout(vaciarColaSinSenal, 1500));
setTimeout(vaciarColaSinSenal, 2500);

// Lo guardado en el celular para trabajar sin señal es de quien inicio
// sesion: al salir se borra (antes se intenta enviar lo pendiente).
function _borrarDatosSinSenal(){
  try {
    Object.keys(localStorage).filter(k => k.startsWith('cp-ruta:'))
      .forEach(k => localStorage.removeItem(k));
  } catch(e) {}
}
