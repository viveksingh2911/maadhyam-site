/* Admin portal behaviour: theme, slugs, counters, markdown editor + preview,
   live SERP preview, media picker, delete confirmation, drag-and-drop upload. */
(function () {
  'use strict';

  var root = document.documentElement;

  function syncThemeIcons() {
    var dark = root.dataset.theme === 'dark';
    document.querySelectorAll('[data-theme-icon="light"]').forEach(function (el) { el.hidden = dark; });
    document.querySelectorAll('[data-theme-icon="dark"]').forEach(function (el) { el.hidden = !dark; });
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('mi-theme', root.dataset.theme); } catch (e) {}
      syncThemeIcons();
    });
  });
  syncThemeIcons();

  // ---- Slug generation ----------------------------------------------------
  function slugify(value) {
    return (value || '')
      .toLowerCase()
      .normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9\s-]/g, '')
      .trim().replace(/[\s_-]+/g, '-').replace(/^-+|-+$/g, '')
      .slice(0, 90);
  }

  var titleInput = document.querySelector('[data-slug-source]');
  var slugInput = document.querySelector('[data-slug-target]');
  if (titleInput && slugInput) {
    var slugTouched = slugInput.value.trim().length > 0;
    slugInput.addEventListener('input', function () { slugTouched = true; });
    titleInput.addEventListener('input', function () {
      if (!slugTouched) slugInput.value = slugify(titleInput.value);
      updateSerp();
    });
  }

  // ---- Character counters -------------------------------------------------
  document.querySelectorAll('[data-counter-for]').forEach(function (counter) {
    var field = document.getElementById(counter.dataset.counterFor);
    if (!field) return;
    var min = parseInt(counter.dataset.min || '0', 10);
    var max = parseInt(counter.dataset.max || '0', 10);
    var update = function () {
      var len = field.value.length;
      counter.textContent = len + (max ? ' / ' + max : '') + ' characters';
      counter.classList.toggle('is-over', max > 0 && len > max);
      counter.classList.toggle('is-warn', !(max > 0 && len > max) && min > 0 && len > 0 && len < min);
    };
    field.addEventListener('input', update);
    update();
  });

  // ---- Live search-result preview ----------------------------------------
  var serp = document.getElementById('serp-preview');
  function updateSerp() {
    if (!serp) return;
    var titleField = document.getElementById('meta_title') || document.getElementById('title');
    var fallbackTitle = document.getElementById('title');
    var descField = document.getElementById('meta_description');
    var fallbackDesc = document.getElementById('excerpt') || document.getElementById('summary');
    var slugField = document.getElementById('slug');

    var t = (titleField && titleField.value.trim()) || (fallbackTitle && fallbackTitle.value.trim()) || 'Untitled';
    var d = (descField && descField.value.trim()) || (fallbackDesc && fallbackDesc.value.trim()) || '';
    var template = serp.dataset.titleTemplate || '{title} | {site}';
    var site = serp.dataset.site || '';
    var full = template.replace('{title}', t).replace('{site}', site);

    serp.querySelector('[data-serp-title]').textContent = full.length > 62 ? full.slice(0, 62) + '…' : full;
    serp.querySelector('[data-serp-desc]').textContent = d.length > 160 ? d.slice(0, 160) + '…' : (d || 'No description yet - search engines will pick a snippet from the page body.');
    var base = serp.dataset.base || '';
    serp.querySelector('[data-serp-url]').textContent = base + '/' + ((slugField && slugField.value) || 'your-slug');
  }
  ['meta_title', 'meta_description', 'title', 'slug', 'excerpt', 'summary'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', updateSerp);
  });
  updateSerp();

  // ---- Markdown editor ----------------------------------------------------
  var editor = document.querySelector('[data-editor]');
  if (editor) {
    var wrap = function (before, after, placeholder) {
      var start = editor.selectionStart;
      var end = editor.selectionEnd;
      var selected = editor.value.slice(start, end) || placeholder || '';
      editor.value = editor.value.slice(0, start) + before + selected + after + editor.value.slice(end);
      editor.focus();
      editor.selectionStart = start + before.length;
      editor.selectionEnd = start + before.length + selected.length;
      editor.dispatchEvent(new Event('input'));
    };

    document.querySelectorAll('[data-md]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var kind = btn.dataset.md;
        if (kind === 'bold') wrap('**', '**', 'bold text');
        else if (kind === 'italic') wrap('_', '_', 'italic text');
        else if (kind === 'h2') wrap('\n## ', '\n', 'Section heading');
        else if (kind === 'h3') wrap('\n### ', '\n', 'Sub heading');
        else if (kind === 'quote') wrap('\n> ', '\n', 'Quoted line');
        else if (kind === 'ul') wrap('\n* ', '\n', 'List item');
        else if (kind === 'ol') wrap('\n1. ', '\n', 'First item');
        else if (kind === 'link') wrap('[', '](https://)', 'link text');
        else if (kind === 'image') openPicker(function (item) { wrap('\n![' + (item.alt || '') + '](' + item.url + ')\n', '', ''); });
        else if (kind === 'table') wrap('\n| Column | Column |\n| --- | --- |\n| Value | Value |\n', '', '');
        else if (kind === 'hr') wrap('\n\n---\n\n', '', '');
      });
    });

    // Preview toggle
    var preview = document.getElementById('editor-preview');
    var tabs = document.querySelectorAll('[data-editor-tab]');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function (e) {
        e.preventDefault();
        var mode = tab.dataset.editorTab;
        tabs.forEach(function (t) { t.classList.toggle('is-active', t === tab); });
        editor.classList.toggle('hidden', mode !== 'write');
        if (preview) {
          preview.classList.toggle('hidden', mode !== 'preview');
          if (mode === 'preview') preview.innerHTML = renderMarkdown(editor.value);
        }
      });
    });

    // Tab key inserts two spaces rather than leaving the field.
    editor.addEventListener('keydown', function (e) {
      if (e.key === 'Tab') {
        e.preventDefault();
        var s = editor.selectionStart;
        editor.value = editor.value.slice(0, s) + '  ' + editor.value.slice(editor.selectionEnd);
        editor.selectionStart = editor.selectionEnd = s + 2;
      }
    });
  }

  // Small markdown subset, preview only. The server renders the stored HTML.
  function renderMarkdown(src) {
    var esc = function (s) {
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    };
    // Block structure is detected on the raw line; only the text content is
    // escaped, so a leading ">" is still recognised as a blockquote.
    var lines = (src || '').split('\n');
    var out = [];
    var inList = null;
    var flush = function () { if (inList) { out.push('</' + inList + '>'); inList = null; } };

    lines.forEach(function (line) {
      if (/^\s*$/.test(line)) { flush(); return; }
      if (/^#{3}\s+/.test(line)) { flush(); out.push('<h3>' + esc(line.replace(/^#{3}\s+/, '')) + '</h3>'); return; }
      if (/^#{2}\s+/.test(line)) { flush(); out.push('<h2>' + esc(line.replace(/^#{2}\s+/, '')) + '</h2>'); return; }
      if (/^#\s+/.test(line)) { flush(); out.push('<h1>' + esc(line.replace(/^#\s+/, '')) + '</h1>'); return; }
      if (/^>\s?/.test(line)) { flush(); out.push('<blockquote>' + esc(line.replace(/^>\s?/, '')) + '</blockquote>'); return; }
      if (/^---+$/.test(line)) { flush(); out.push('<hr>'); return; }
      if (/^\s*[-*]\s+/.test(line)) {
        if (inList !== 'ul') { flush(); out.push('<ul>'); inList = 'ul'; }
        out.push('<li>' + esc(line.replace(/^\s*[-*]\s+/, '')) + '</li>');
        return;
      }
      if (/^\s*\d+\.\s+/.test(line)) {
        if (inList !== 'ol') { flush(); out.push('<ol>'); inList = 'ol'; }
        out.push('<li>' + esc(line.replace(/^\s*\d+\.\s+/, '')) + '</li>');
        return;
      }
      if (/^\s*\|.*\|\s*$/.test(line)) {
        // Table rows are shown verbatim; the saved page renders them properly.
        flush();
        out.push('<p class="mono">' + esc(line) + '</p>');
        return;
      }
      flush();
      out.push('<p>' + esc(line) + '</p>');
    });
    flush();

    return out.join('\n')
      .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, '<img src="$2" alt="$1">')
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/_([^_\n]+)_/g, '<em>$1</em>')
      .replace(/`([^`\n]+)`/g, '<code>$1</code>');
  }

  // ---- Media picker -------------------------------------------------------
  var pickerCallback = null;
  var dialog = document.getElementById('media-picker');

  function openPicker(callback) {
    if (!dialog) return;
    pickerCallback = callback;
    dialog.hidden = false;
    var body = dialog.querySelector('[data-picker-body]');
    body.innerHTML = '<p class="muted small">Loading library...</p>';
    fetch('/admin/media/picker.json')
      .then(function (r) { return r.json(); })
      .then(function (items) {
        if (!items.length) {
          body.innerHTML = '<p class="muted small">Nothing uploaded yet. <a href="/admin/media">Open the media library</a>.</p>';
          return;
        }
        body.innerHTML = '<div class="media-grid"></div>';
        var grid = body.querySelector('.media-grid');
        items.forEach(function (item) {
          var el = document.createElement('button');
          el.type = 'button';
          el.className = 'media-item';
          el.style.cursor = 'pointer';
          el.style.textAlign = 'left';
          el.style.font = 'inherit';
          el.innerHTML =
            '<div class="media-thumb">' +
            (item.is_image ? '<img src="' + item.url + '" alt="">' : '<span class="tiny">FILE</span>') +
            '</div><div class="media-info"><strong>' + item.name + '</strong><span class="muted">' + item.size + '</span></div>';
          el.addEventListener('click', function () {
            if (pickerCallback) pickerCallback(item);
            dialog.hidden = true;
          });
          grid.appendChild(el);
        });
      })
      .catch(function () { body.innerHTML = '<p class="small" style="color:var(--danger)">Could not load the media library.</p>'; });
  }

  document.querySelectorAll('[data-pick-media]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var target = document.getElementById(btn.dataset.pickMedia);
      var altTarget = btn.dataset.pickAlt ? document.getElementById(btn.dataset.pickAlt) : null;
      openPicker(function (item) {
        if (target) { target.value = item.url; target.dispatchEvent(new Event('input')); }
        if (altTarget && !altTarget.value && item.alt) altTarget.value = item.alt;
        var thumb = btn.closest('.field') && btn.closest('.field').querySelector('[data-media-thumb]');
        if (thumb) { thumb.src = item.url; thumb.hidden = false; }
      });
    });
  });

  if (dialog) {
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog || e.target.closest('[data-picker-close]')) dialog.hidden = true;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') dialog.hidden = true;
    });
  }

  // ---- Confirm destructive actions ---------------------------------------
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // ---- Drag and drop upload ----------------------------------------------
  var zone = document.querySelector('.dropzone');
  var fileInput = document.getElementById('media-files');
  if (zone && fileInput) {
    ['dragenter', 'dragover'].forEach(function (evt) {
      zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.add('is-over'); });
    });
    ['dragleave', 'drop'].forEach(function (evt) {
      zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.remove('is-over'); });
    });
    zone.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        zone.closest('form').submit();
      }
    });
    zone.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
      if (fileInput.files.length) fileInput.closest('form').submit();
    });
  }

  // ---- Status shortcut: publish button sets the select then submits -------
  document.querySelectorAll('[data-set-status]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var select = document.getElementById('status');
      if (select) select.value = btn.dataset.setStatus;
    });
  });
})();
