// Boton de ojo en cada campo de contraseña: muestra u oculta lo escrito para
// que se pueda revisar antes de guardar.
//
// Un solo archivo, sin depender de app.js, porque tambien lo usan paginas que
// no heredan de base.html (registro, activacion, acceso a la plataforma). Se
// engancha solo a todos los <input type="password"> de la pagina, tambien a
// los que se crean despues (modales que se arman con JavaScript). Un campo
// que ya trae su propio boton se marca con data-sin-ojo y se deja en paz.
(function () {
  var OJO = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
    '<circle cx="12" cy="12" r="3"/></svg>';
  var OJO_TACHADO = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8' +
    'a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19' +
    'm-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

  function ponerOjo(campo) {
    if (campo.dataset.ojo || campo.hasAttribute('data-sin-ojo')) return;
    campo.dataset.ojo = '1';

    var envoltura = document.createElement('span');
    envoltura.style.cssText = 'position:relative;display:block;width:100%';
    campo.parentNode.insertBefore(envoltura, campo);
    envoltura.appendChild(campo);
    campo.style.paddingRight = '44px';
    campo.style.width = '100%';

    var boton = document.createElement('button');
    boton.type = 'button';                      // nunca envia el formulario
    boton.className = 'ojo-clave';
    boton.setAttribute('aria-label', 'Mostrar contraseña');
    boton.title = 'Mostrar contraseña';
    boton.innerHTML = OJO;
    boton.style.cssText = 'position:absolute;right:4px;top:50%;transform:translateY(-50%);' +
      'width:36px;height:36px;display:flex;align-items:center;justify-content:center;' +
      'background:none;border:none;padding:0;cursor:pointer;color:inherit;opacity:.55';
    boton.addEventListener('click', function () {
      var ver = campo.type === 'password';
      campo.type = ver ? 'text' : 'password';
      boton.innerHTML = ver ? OJO_TACHADO : OJO;
      var texto = ver ? 'Ocultar contraseña' : 'Mostrar contraseña';
      boton.setAttribute('aria-label', texto);
      boton.title = texto;
      boton.setAttribute('aria-pressed', ver ? 'true' : 'false');
    });
    envoltura.appendChild(boton);
  }

  function revisar(raiz) {
    var campos = (raiz || document).querySelectorAll('input[type="password"]');
    for (var i = 0; i < campos.length; i++) ponerOjo(campos[i]);
  }

  // Al enviar, el campo vuelve a ser de contraseña: que el navegador no lo
  // guarde como texto normal en su historial de formularios.
  document.addEventListener('submit', function (e) {
    var vistos = e.target.querySelectorAll('input[data-ojo="1"][type="text"]');
    for (var i = 0; i < vistos.length; i++) vistos[i].type = 'password';
  }, true);

  function arrancar() {
    revisar(document);
    if (window.MutationObserver) {
      new MutationObserver(function (cambios) {
        for (var i = 0; i < cambios.length; i++) {
          var nodos = cambios[i].addedNodes;
          for (var j = 0; j < nodos.length; j++) {
            if (nodos[j].nodeType === 1) {
              if (nodos[j].matches && nodos[j].matches('input[type="password"]')) ponerOjo(nodos[j]);
              else revisar(nodos[j]);
            }
          }
        }
      }).observe(document.body, {childList: true, subtree: true});
    }
  }

  window.ponerOjosClave = revisar;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrancar);
  else arrancar();
})();
