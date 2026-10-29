/* Bethorahzan: responsive, keyboard-accessible mobile search + cause selection */
(() => {
  'use strict';
  const doc = document;
  const header = doc.querySelector('.institution-topbar');
  const trigger = doc.getElementById('mobileSearchToggle');
  const search = doc.getElementById('jumpSearch');
  const results = doc.getElementById('jumpResults');
  const isSmall = () => window.matchMedia('(max-width: 700px)').matches;
  function closeSearch(returnFocus = false) {
    if (!header || !trigger) return;
    if (header.classList.contains('mobile-search-open')) {
      header.classList.remove('mobile-search-open');
      trigger.setAttribute('aria-expanded', 'false');
      if (results) results.hidden = true;
      if (search) search.setAttribute('aria-expanded', 'false');
      if (returnFocus) trigger.focus();
    }
  }
  function openSearch() {
    if (!header || !trigger || !search) return;
    header.classList.add('mobile-search-open');
    trigger.setAttribute('aria-expanded', 'true');
    search.focus();
  }
  if (trigger) trigger.addEventListener('click', () => {
    if (header?.classList.contains('mobile-search-open')) closeSearch(true);
    else openSearch();
  });
  doc.addEventListener('keydown', e => {
    if (e.key === 'Escape' && header?.classList.contains('mobile-search-open')) closeSearch(true);
    if (e.key === '/' && isSmall() && !/^(INPUT|TEXTAREA)$/.test(doc.activeElement?.tagName) && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();openSearch();
    }
  });
  doc.addEventListener('pointerdown', e => {
    if (header?.classList.contains('mobile-search-open') && !header.contains(e.target)) closeSearch();
  });
  window.addEventListener('resize', () => {if (!isSmall()) closeSearch();},{passive:true});
  const select = doc.getElementById('cause_id');
  const cards = Array.from(doc.querySelectorAll('[data-select-cause]'));
  function syncCauses() {
    cards.forEach(card => card.setAttribute('aria-pressed', String(select && card.dataset.selectCause === select.value)));
  }
  if (select && cards.length) {
    cards.forEach(card => card.addEventListener('click', () => {
      select.value = card.dataset.selectCause;
      select.dispatchEvent(new Event('change', {bubbles:true}));
      syncCauses();
      const form = doc.getElementById('givingForm');
      if (form) form.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
    }));
    select.addEventListener('change',syncCauses);
    syncCauses();
  }
})();
