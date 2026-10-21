(function () {
  var root = document.documentElement;

  // ----- theme toggle
  var toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.addEventListener('click', function () {
    var dark = root.dataset.theme
      ? root.dataset.theme === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
  });

  // ----- "/" focuses search (or jumps to the blog page)
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || /input|textarea/i.test(document.activeElement.tagName)) return;
    var box = document.getElementById('search');
    e.preventDefault();
    if (box) box.focus(); else location.href = '/blog/#search';
  });

  // ----- blog search + topic filter
  var input = document.getElementById('search');
  var list = document.getElementById('post-list');
  if (input && list) {
    var rows = Array.prototype.slice.call(list.children);
    var texts = rows.map(function (li) { return li.textContent.toLowerCase(); });
    var topics = rows.map(function (li) { var c = li.querySelector('.chip'); return c ? c.textContent : ''; });
    var filters = document.querySelectorAll('.filter[data-topic]');
    var count = document.getElementById('result-count');
    var empty = document.getElementById('empty');
    var topic = '';

    function apply() {
      var words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      var shown = 0;
      rows.forEach(function (li, i) {
        var ok = (!topic || topics[i] === topic || topics[i].indexOf(topic + ' ·') === 0) &&
          words.every(function (w) { return texts[i].indexOf(w) !== -1; });
        li.hidden = !ok;
        if (ok) shown++;
      });
      count.textContent = (words.length || topic) ? shown + ' of ' + rows.length + ' posts' : '';
      empty.hidden = shown !== 0;
    }
    input.addEventListener('input', apply);
    Array.prototype.forEach.call(filters, function (btn) {
      btn.addEventListener('click', function () {
        topic = btn.dataset.topic;
        Array.prototype.forEach.call(filters, function (b) { b.classList.toggle('is-active', b === btn); });
        apply();
      });
    });
    var q = new URLSearchParams(location.search).get('q');
    if (q) { input.value = q; apply(); }
    if (location.hash === '#search') input.focus();
  }

  // ----- highlight current section in the table of contents
  var tocLinks = document.querySelectorAll('.toc a');
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var byId = {};
    Array.prototype.forEach.call(tocLinks, function (a) { byId[decodeURIComponent(a.hash.slice(1))] = a; });
    var current;
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var link = byId[en.target.id];
        if (!en.isIntersecting || !link) return;
        if (current) current.classList.remove('is-active');
        current = link;
        current.classList.add('is-active');
      });
    }, { rootMargin: '-80px 0px -70% 0px' });
    document.querySelectorAll('.prose h2[id], .prose h3[id]').forEach(function (h) { observer.observe(h); });
  }
})();
