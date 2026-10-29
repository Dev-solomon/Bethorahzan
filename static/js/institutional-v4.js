/* Bethorahzan universal enhancement: no dependencies, no links or forms overridden. */
(() => {
  'use strict';
  const doc = document;
  const body = doc.body;
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false;
  const selector = '.inner-section .info-card, .inner-section .list-card, .inner-section .form-panel, .admin-main .admin-stat, .admin-main .info-card, .inner-section .empty-state, .inner-section .slab, .inner-section .dark-info';
  const targets = Array.from(doc.querySelectorAll(selector));
  targets.forEach(el => el.classList.add('boz-glow-card'));
  // Animate only if IntersectionObserver is available; revealed content remains accessible.
  if (!reduced && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('boz-in');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .06, rootMargin: '0px 0px -16px 0px' });
    targets.forEach(el => {el.classList.add('boz-enter'); observer.observe(el);});
    body.classList.add('boz-page-motion');
    // Avoid delayed/hidden content if a device throttles observers.
    window.setTimeout(() => targets.forEach(el => {
      if (el.getBoundingClientRect().top < window.innerHeight + 140) el.classList.add('boz-in');
    }), 800);
  }
  // A warm, restrained spotlight follows hover on card surfaces; mouse-only.
  if (window.matchMedia?.('(hover: hover) and (pointer: fine)').matches) {
    targets.forEach(el => el.addEventListener('pointermove', e => {
      const box = el.getBoundingClientRect();
      el.style.setProperty('--glow-x', `${e.clientX - box.left}px`);
      el.style.setProperty('--glow-y', `${e.clientY - box.top}px`);
    }, {passive:true}));
  }
  // Supplement the long member/admin pages with a discreet return-to-top control.
  const up = doc.createElement('button');
  up.className = 'boz-back-top';
  up.type = 'button';
  up.setAttribute('aria-label','Return to top');
  up.title = 'Return to top';
  const arrow = doc.createElement('i');
  arrow.className = 'bi bi-arrow-up';
  arrow.setAttribute('aria-hidden','true');
  up.append(arrow);
  doc.body.append(up);
  let queued = false;
  const update = () => { up.classList.toggle('is-visible', window.scrollY > 560); queued=false; };
  window.addEventListener('scroll', () => {if(!queued){queued=true;window.requestAnimationFrame(update);}}, {passive:true});
  up.addEventListener('click', () => window.scrollTo({top:0,behavior:reduced?'auto':'smooth'}));
  update();
})();
