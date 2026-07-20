/**
 * Product switcher — sliding indicator, prefetch, logo transition overlay.
 */
(function (global) {
    'use strict';

    var NAV_KEY = 'hibs-product-nav';
    var NAV_DELAY_MS = 340;

    function ready(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    function overlayEl() {
        return document.getElementById('hibs-product-transition');
    }

    function showTransition(label) {
        var overlay = overlayEl();
        if (!overlay) return;
        var dest = document.getElementById('hibs-product-transition-label');
        if (dest) dest.textContent = label || 'Switching…';
        overlay.hidden = false;
        overlay.setAttribute('aria-hidden', 'false');
        overlay.classList.add('is-visible');
        document.documentElement.classList.add('hibs-product-navigating');
    }

    function hideTransition() {
        var overlay = overlayEl();
        if (!overlay) return;
        overlay.classList.remove('is-visible');
        document.documentElement.classList.remove('hibs-product-navigating');
        window.setTimeout(function () {
            if (!overlay.classList.contains('is-visible')) {
                overlay.hidden = true;
                overlay.setAttribute('aria-hidden', 'true');
            }
        }, 280);
    }

    function positionIndicator(switchEl, indicator, pill) {
        if (!switchEl || !indicator || !pill) return;
        var rect = pill.getBoundingClientRect();
        var parent = switchEl.getBoundingClientRect();
        indicator.style.width = rect.width + 'px';
        indicator.style.transform = 'translateX(' + (rect.left - parent.left) + 'px)';
        switchEl.classList.add('is-ready');
    }

    function syncIndicator(switchEl) {
        var indicator = switchEl.querySelector('.hibs-product-switch-indicator');
        var active =
            switchEl.querySelector('.hibs-product-pill.active') ||
            switchEl.querySelector('.line-tab.active') ||
            switchEl.querySelector('[data-product-nav].active');
        if (!indicator || !active) return;
        positionIndicator(switchEl, indicator, active);
    }

    function prefetchOnce(href) {
        if (!href || href.indexOf('javascript:') === 0) return;
        try {
            var link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = href;
            document.head.appendChild(link);
        } catch (e) { /* noop */ }
    }

    function navLabel(pill) {
        var custom = pill.getAttribute('data-product-label');
        if (custom) return custom;
        var text = (pill.textContent || '').replace(/\s+/g, ' ').trim();
        return text ? 'Opening ' + text + '…' : 'Switching…';
    }

    function isProductNavLink(el) {
        return (
            el &&
            el.matches &&
            (el.matches('.hibs-product-pill') ||
                el.matches('.line-tab[data-product-nav]') ||
                el.matches('[data-hibs-product-nav]'))
        );
    }

    function bindSwitch(switchEl) {
        if (!switchEl || switchEl.getAttribute('data-hibs-switch-bound') === '1') return;
        switchEl.setAttribute('data-hibs-switch-bound', '1');

        var indicator = switchEl.querySelector('.hibs-product-switch-indicator');
        var pills = switchEl.querySelectorAll(
            '.hibs-product-pill, .line-tab[data-product-nav], [data-hibs-product-nav]'
        );

        syncIndicator(switchEl);

        pills.forEach(function (pill) {
            pill.addEventListener('mouseenter', function () {
                prefetchOnce(pill.href);
            }, { once: true, passive: true });

            pill.addEventListener('focus', function () {
                if (indicator) positionIndicator(switchEl, indicator, pill);
            });

            pill.addEventListener('click', function (evt) {
                if (evt.defaultPrevented || evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.altKey) {
                    return;
                }
                if (pill.classList.contains('active')) {
                    evt.preventDefault();
                    return;
                }
                var href = pill.getAttribute('href');
                if (!href) return;
                evt.preventDefault();
                var label = navLabel(pill);
                try {
                    sessionStorage.setItem(NAV_KEY, label);
                } catch (e) { /* noop */ }
                showTransition(label);
                window.setTimeout(function () {
                    global.location.href = href;
                }, NAV_DELAY_MS);
            });
        });

        if (typeof global.ResizeObserver === 'function') {
            try {
                var ro = new global.ResizeObserver(function () {
                    syncIndicator(switchEl);
                });
                ro.observe(switchEl);
            } catch (e) { /* noop */ }
        }
    }

    ready(function () {
        document.querySelectorAll('[data-hibs-product-switch]').forEach(bindSwitch);

        var pending;
        try {
            pending = sessionStorage.getItem(NAV_KEY);
        } catch (e) {
            pending = null;
        }
        if (pending) {
            try {
                sessionStorage.removeItem(NAV_KEY);
            } catch (e2) { /* noop */ }
            showTransition(pending);
            window.setTimeout(hideTransition, 420);
        }

        var resizeTimer;
        window.addEventListener('resize', function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(function () {
                document.querySelectorAll('[data-hibs-product-switch]').forEach(syncIndicator);
            }, 80);
        }, { passive: true });
    });
})(window);
