/* Bethorahzan institutional interface — progressive enhancement only.
   All primary navigation is server-rendered and still works with JavaScript off. */
(() => {
  'use strict';
  const doc = document;
  const body = doc.body;
  const toggle = doc.getElementById('sidebarToggle');
  const sidebar = doc.getElementById('institutionSidebar');
  const scrim = doc.getElementById('sidebarScrim');
  const theme = doc.getElementById('themeToggle');
  const search = doc.getElementById('jumpSearch');
  const results = doc.getElementById('jumpResults');
  let lastFocused = null;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sidebarOpen = () => body.classList.contains('sidebar-is-open');
  const setSidebar = (open) => {
    if (!sidebar || !toggle) return;
    body.classList.toggle('sidebar-is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      lastFocused = doc.activeElement;
      const link = sidebar.querySelector('.sidebar-item.is-active, .sidebar-item');
      if (link) link.focus({preventScroll:true});
    } else if (lastFocused && lastFocused.isConnected) {
      lastFocused.focus({preventScroll:true});
    }
  };
  if (toggle) toggle.addEventListener('click', () => setSidebar(!sidebarOpen()));
  if (scrim) scrim.addEventListener('click', () => setSidebar(false));
  if (sidebar) sidebar.addEventListener('click', e => {if(e.target.closest('a') && sidebarOpen())setSidebar(false)});
  doc.addEventListener('keydown', e => {
    if(e.key === 'Escape') {if(sidebarOpen())setSidebar(false);closeResults();}
    if (e.key === '/' && search && !/^(INPUT|TEXTAREA)$/.test(doc.activeElement?.tagName) && !e.ctrlKey && !e.metaKey) {e.preventDefault();search.focus();}
    if (e.key === 'Tab' && sidebarOpen() && window.innerWidth <= 1150) {
      const focusable = [...sidebar.querySelectorAll('a, button, input, [tabindex]:not([tabindex="-1"])')].filter(n => n.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && doc.activeElement === first) {e.preventDefault();last.focus();}
      if (!e.shiftKey && doc.activeElement === last) {e.preventDefault();first.focus();}
    }
  });
  window.matchMedia('(min-width: 1151px)').addEventListener?.('change',e => {if(e.matches && sidebarOpen())setSidebar(false)});

  // Optional appearance choice never blocks access to content.
  try {if(window.localStorage.getItem('boz-appearance') === 'light')body.classList.add('theme-light');}catch(_e){}
  const syncTheme = () => {if(theme){let active = body.classList.contains('theme-light');theme.setAttribute('aria-label',active?'Switch to midnight theme':'Switch to light theme');theme.querySelector('i')?.classList.toggle('bi-moon-stars',active);theme.querySelector('i')?.classList.toggle('bi-sun',!active);}};
  syncTheme();
  if(theme)theme.addEventListener('click',()=>{body.classList.toggle('theme-light');try{window.localStorage.setItem('boz-appearance',body.classList.contains('theme-light')?'light':'dark');}catch(_e){}syncTheme();});

  // Keyboard-accessible section finder. Links are supplied by Flask, never guessed.
  let pages = [];
  try {pages = JSON.parse(doc.getElementById('site-jump-pages')?.textContent || '[]');}catch(_e){}
  let activeIndex = -1;
  function closeResults(){if(results){results.hidden = true;results.innerHTML = '';}if(search){search.setAttribute('aria-expanded','false');search.removeAttribute('aria-activedescendant');}activeIndex=-1;}
  function matches(){return pages.filter(p => (p.label||'').toLowerCase().includes((search.value||'').trim().toLowerCase())).slice(0,9);}
  function renderResults(){if(!search||!results)return;const text = search.value.trim();if(!text){closeResults();return;}const found=matches();results.replaceChildren();if(found.length){found.forEach((p,i)=>{const a=doc.createElement('a');a.href=p.href;a.className='jump-option';a.id='jump-option-'+i;a.setAttribute('role','option');const icon=doc.createElement('i');icon.className='bi bi-'+p.icon;icon.setAttribute('aria-hidden','true');const span=doc.createElement('span');span.textContent=p.label;a.append(icon,span);results.append(a);});}else{const empty=doc.createElement('div');empty.className='jump-empty';empty.textContent='No matching section. Try “events”, “giving”, or “member”.';results.append(empty);}results.hidden=false;activeIndex=-1;search.setAttribute('aria-expanded','true');}
  if(search){search.addEventListener('input',renderResults);search.addEventListener('focus',()=>{if(search.value.trim())renderResults()});search.addEventListener('keydown',e=>{const found=matches();if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(results.hidden)renderResults();activeIndex=(activeIndex+(e.key==='ArrowDown'?1:-1)+found.length)%Math.max(found.length,1);if(found.length){search.setAttribute('aria-activedescendant','jump-option-'+activeIndex);results.querySelectorAll('.jump-option').forEach((a,i)=>a.classList.toggle('is-focused',i===activeIndex));}}else if(e.key==='Enter'&&found.length){e.preventDefault();window.location.assign(found[Math.max(activeIndex,0)].href);}else if(e.key==='Escape'){closeResults();}});doc.addEventListener('pointerdown',e=>{if(!e.target.closest('#quickJump'))closeResults()});}

  // Scroll entrance animations and respectful motion defaults.
  if (!reduced && 'IntersectionObserver' in window) {
    body.classList.add('js-motion');
    const observer = new IntersectionObserver(entries => {entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');observer.unobserve(entry.target);}});},{threshold:.06,rootMargin:'0px 0px -24px 0px'});
    doc.querySelectorAll('.reveal').forEach(el=>observer.observe(el));
    // Ensure eager content is visible before the browser can paint it after a slow load.
    window.setTimeout(()=>{doc.querySelectorAll('.reveal:not(.is-visible)').forEach(el=>{if(el.getBoundingClientRect().top < window.innerHeight)el.classList.add('is-visible');});},600);
  }

  // Purposeful count-up: 3 dimensions, 12 generals, 4 causes (not fabricated activity numbers).
  const countNodes = [...doc.querySelectorAll('[data-count]')];
  if(countNodes.length) {
    const animateCount = el => {const end = Math.min(1000,Math.max(0,Number(el.dataset.count)||0));if(reduced){el.textContent=String(end);return;}const start=performance.now(),duration=1100;function frame(t){const p=Math.min(1,(t-start)/duration);el.textContent=String(Math.round(end*(1-(1-p)**3)));if(p<1)requestAnimationFrame(frame);}requestAnimationFrame(frame);};
    if('IntersectionObserver' in window){const obs=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){animateCount(entry.target);obs.unobserve(entry.target);}}));countNodes.forEach(el=>obs.observe(el));}else countNodes.forEach(animateCount);
  }

  // Ambient constellation lines: decorative, lightweight, with motion preference respected.
  const canvas = doc.getElementById('heroParticles');
  if(canvas && !reduced){const ctx=canvas.getContext('2d');if(ctx){let width=0,height=0,points=[],frame=0,visible=true;const parent=canvas.parentElement;
    function resize(){const rect=parent.getBoundingClientRect();width=Math.max(1,Math.floor(rect.width));height=Math.max(1,Math.floor(rect.height));const dpr=Math.min(2,window.devicePixelRatio||1);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);points=Array.from({length:Math.min(38,Math.max(14,Math.floor(width/33)))},(_,i)=>({x:((i*157.3)%width),y:((i*99.7)%height),vx:(i%3-1)*.085,vy:(i%5-2)*.025,r:(i%3===0?1.6:.9)}));}
    resize();if('ResizeObserver' in window)new ResizeObserver(resize).observe(parent);else window.addEventListener('resize',resize,{passive:true});
    function draw(){if(!visible)return;frame++;ctx.clearRect(0,0,width,height);for(let i=0;i<points.length;i++){const p=points[i];p.x+=p.vx;p.y+=p.vy;if(p.x<0)p.x=width;if(p.x>width)p.x=0;if(p.y<0)p.y=height;if(p.y>height)p.y=0;ctx.fillStyle='rgba(235,185,139,.55)';ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();for(let j=i+1;j<points.length;j++){const q=points[j],dx=p.x-q.x,dy=p.y-q.y,dist=dx*dx+dy*dy;if(dist<125*125){ctx.strokeStyle=`rgba(234,177,124,${(1-dist/(125*125))*.17})`;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}}}requestAnimationFrame(draw);}
    doc.addEventListener('visibilitychange',()=>{if(doc.hidden)visible=false;else if(!visible){visible=true;requestAnimationFrame(draw)}});requestAnimationFrame(draw);
  }}
})();
