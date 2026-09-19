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
function cerrarSesion(){
  if(!confirm('Cerrar sesion?')) return false;
  try{
    if(navigator.serviceWorker && navigator.serviceWorker.controller){
      navigator.serviceWorker.controller.postMessage({type:'LIMPIAR_CACHE'});
    }
  }catch(e){}
  return true;
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
  if (datos) return datos;
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
