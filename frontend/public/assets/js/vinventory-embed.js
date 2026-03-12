(function () {
    var script = document.currentScript;
    if (!script) return;

    var origin = new URL(script.src, window.location.href).origin;
    var src = script.getAttribute('data-src') || (origin + '/vinventory');
    var targetSelector = script.getAttribute('data-target');
    var minHeight = script.getAttribute('data-min-height') || '2200px';

    var mount = targetSelector ? document.querySelector(targetSelector) : null;
    if (!mount) {
        mount = document.createElement('div');
        script.parentNode.insertBefore(mount, script);
    }

    mount.classList.add('vch-vinventory-embed');
    mount.innerHTML = '';

    var iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.loading = 'lazy';
    iframe.referrerPolicy = 'strict-origin-when-cross-origin';
    iframe.title = 'VirtualCarHub Inventory';
    iframe.style.width = '100%';
    iframe.style.display = 'block';
    iframe.style.border = '0';
    iframe.style.background = 'transparent';
    iframe.style.minHeight = minHeight;

    mount.appendChild(iframe);
})();
