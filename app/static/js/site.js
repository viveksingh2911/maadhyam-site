/* Public site behaviour: theme toggle, mobile nav, consent banner, share links. */
(function () {
  'use strict';

  // ---- Colour theme -------------------------------------------------------
  var root = document.documentElement;

  function syncThemeIcons() {
    var dark = root.dataset.theme === 'dark';
    document.querySelectorAll('[data-theme-icon="light"]').forEach(function (el) { el.hidden = dark; });
    document.querySelectorAll('[data-theme-icon="dark"]').forEach(function (el) { el.hidden = !dark; });
  }

  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('mi-theme', next); } catch (e) {}
      syncThemeIcons();
    });
  });
  syncThemeIcons();

  // ---- Mobile navigation --------------------------------------------------
  var toggle = document.querySelector('.nav-toggle');
  var mobileNav = document.getElementById('mobile-nav');
  if (toggle && mobileNav) {
    toggle.addEventListener('click', function () {
      var open = mobileNav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // ---- Cookie consent -----------------------------------------------------
  var bar = document.getElementById('cookie-bar');
  if (bar && window.miConsentState !== 'granted' && window.miConsentState !== 'denied') {
    bar.hidden = false;
  }
  if (bar) {
    bar.addEventListener('click', function (event) {
      var action = event.target.closest('[data-consent]');
      if (!action) return;
      if (action.dataset.consent === 'accept' && window.miGrantConsent) window.miGrantConsent();
      if (action.dataset.consent === 'deny' && window.miDenyConsent) window.miDenyConsent();
      bar.hidden = true;
    });
  }

  // ---- Copy-link buttons --------------------------------------------------
  document.querySelectorAll('[data-copy-link]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.dataset.copyLink || location.href;
      var done = function () {
        var original = btn.textContent;
        btn.textContent = 'Link copied';
        setTimeout(function () { btn.textContent = original; }, 1800);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(done, function () {});
      }
    });
  });

  // ---- Reveal on scroll ---------------------------------------------------
  // A scroll-position check rather than IntersectionObserver: jumping straight
  // past an element (anchor links, fast scrolling, find-in-page) must never
  // leave content stuck at opacity 0.
  var reveals = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
  if (reveals.length && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    reveals.forEach(function (el, i) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(14px)';
      var delay = Math.min(i * 60, 240) + 'ms';
      el.style.transition = 'opacity 520ms cubic-bezier(.22,.68,.32,1) ' + delay +
                            ', transform 520ms cubic-bezier(.22,.68,.32,1) ' + delay;
    });

    var ticking = false;
    var sweep = function () {
      ticking = false;
      var limit = window.innerHeight - 40;
      reveals = reveals.filter(function (el) {
        if (el.getBoundingClientRect().top > limit) return true;
        el.style.opacity = '1';
        el.style.transform = 'none';
        return false;
      });
      if (!reveals.length) {
        window.removeEventListener('scroll', request);
        window.removeEventListener('resize', request);
      }
    };
    var request = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(sweep);
    };

    window.addEventListener('scroll', request, { passive: true });
    window.addEventListener('resize', request);
    window.addEventListener('load', request);
    sweep();
  }
})();
