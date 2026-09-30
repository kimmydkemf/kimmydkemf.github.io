/* ==========================================================================
   projects.js — data/projects.generated.json → 프로젝트 영역 렌더링 + 상태 필터
   --------------------------------------------------------------------------
   index.html 에는 sync 가 생성한 정적 카드(Featured + 상태 그룹)가 이미 들어 있다
   (JS 없이도 표시, SEO). 이 스크립트는
     1. 같은 JSON 을 읽어 동일한 마크업으로 다시 그리고
     2. 상태 필터 바를 붙이고
     3. #proj-{slug} 해시로 들어오면 해당 카드를 연다.
   fetch 가 실패하면(file:// 로 열었을 때 등) 정적 카드 위에서 2·3 만 동작한다.

   scripts/render_cards.py 와 마크업을 1:1 로 맞춘다 (parity 테스트로 검증).
   마크업을 바꿀 때는 두 파일을 함께 수정한다.
   ========================================================================== */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }   // node (테스트)
  root.PortfolioRender = api;
  if (typeof document !== 'undefined') { api.mount(); }
}(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var DATA_URL = 'data/projects.generated.json';
  var FILTER_KEY = 'projectFilter';
  var STATUS_LABEL = {
    active: '진행 중', completed: '완료', paused: '일시 중단', unused: '미사용', archived: '아카이브'
  };
  var STATUS_ORDER = ['active', 'completed', 'paused', 'unused', 'archived'];
  var GROUPS = [
    ['current', '진행 중', 'Current'],
    ['paused', '일시 중단', 'Paused'],
    ['completed', '완료', 'Completed'],
    ['archive', '미사용 · 아카이브', 'Unused · Archived']
  ];
  var GROUP_OF = { active: 'current', paused: 'paused', completed: 'completed', unused: 'archive', archived: 'archive' };
  var FEATURED_MAX = 5;
  var PLACEHOLDER = '내용을 입력하세요.';

  function E(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  }

  function displayStatus(p) {
    if (p.status && STATUS_LABEL[p.status]) return p.status;
    return p.ongoing ? 'active' : 'completed';
  }

  function cardId(p) { return 'proj-' + (p.slug || ''); }

  function formatPeriod(started, ended, ongoing, fallback) {
    if (!started) return fallback || '?';
    if (ongoing) return started + ' – Present';
    if (ended && ended !== started) return started + ' – ' + ended;
    return started;
  }

  function multiline(text) {
    return String(text || '').split(/\r?\n/).filter(function (l) { return l.trim(); })
      .map(E).join('<br>\n');
  }

  function section(title, body) {
    return '\n<div class="dl-section">\n<h4>' + E(title) + '</h4>' + body + '\n</div>';
  }

  function badge(status) {
    if (!status || !STATUS_LABEL[status]) return '';
    return '\n<span class="status-badge status-' + status + '">' + STATUS_LABEL[status] + '</span>';
  }

  function livePill(p) {
    if (!p.liveUrl || p.status === 'unused') return '';
    return '\n<a class="proj-live" href="' + E(p.liveUrl) + '" target="_blank" rel="noopener">Live Demo ↗</a>';
  }

  function links(p) {
    var out = '';
    if (p.liveUrl && p.status !== 'unused') {
      out += '\n<a class="proj-link live" href="' + E(p.liveUrl) + '" target="_blank" rel="noopener">Live Demo</a>';
    }
    if (p.repositoryUrl) {
      out += '\n<a class="proj-link" href="' + E(p.repositoryUrl) + '" target="_blank" rel="noopener">GitHub</a>';
    }
    if (!out) return '';
    return section('Links', '\n<div class="proj-links">' + out + '\n</div>');
  }

  function videos(p) {
    var list = (p.videos || []).filter(function (v) { return v && v.url; });
    if (!list.length) return '';
    var body = '';
    list.forEach(function (v) {
      if (v.label) body += '\n<p class="video-label">' + E(v.label) + '</p>';
      body += '\n<div class="video-wrap">\n<iframe src="' + E(v.url) + '" allowfullscreen></iframe>\n</div>';
    });
    return section('시연 영상', body);
  }

  function team(p) {
    var list = p.team || [];
    if (!list.length) return '';
    var members = '';
    list.forEach(function (m) {
      var me = m.me ? '<span class="me">me</span>' : '';
      var role = m.role ? '\n<div class="member-role">' + E(m.role) + '</div>' : '';
      members += '\n<div class="member-card">\n<div class="member-name">' + E(m.name) + me + '</div>' + role + '\n</div>';
    });
    return section('팀 구성', '\n<div class="member-grid">' + members + '\n</div>');
  }

  function chipClass(p) { return p.tagClass ? ('chip ' + p.tagClass).trim() : 'chip'; }

  function chips(p) {
    var cls = chipClass(p);
    var out = '';
    (p.tech || []).slice(0, 7).forEach(function (t) {
      out += '\n<span class="' + cls + '">' + E(t) + '</span>';
    });
    (p.awards || []).forEach(function (a) {
      out += '\n<span class="chip award">🏆 ' + E(a) + '</span>';
    });
    return out;
  }

  function attrs(p) {
    var a = '';
    if (p.status === 'unused') a += ' class="proj-unused"';
    a += ' id="' + E(cardId(p)) + '"';
    a += ' data-slug="' + E(p.slug) + '" data-source="' + E(p.source || 'github') + '"';
    if (p.status) a += ' data-status="' + E(p.status) + '"';
    a += ' data-display-status="' + displayStatus(p) + '"';
    if (p.featured) a += ' data-featured="true"';
    return a;
  }

  function periodStr(p) {
    return formatPeriod(p.started || '', p.ended || '', !!p.ongoing, p.periodFallback || '');
  }

  function renderUnused(p) {
    var reason = p.unusedReason || '';
    var firstLine = reason.split(/\r?\n/)[0] || '';
    var sub = p.subtitle || (reason.trim() ? firstLine : '');
    var body = '';
    if (reason.trim()) body += section('미사용 사유', '\n<p>' + multiline(reason) + '</p>');
    var rb = p.replacedBy || {};
    if (rb.title) {
      var link = rb.url || rb.repository || '';
      if (link) {
        body += section('대체 프로젝트', '\n<p>이 프로젝트는 ' + E(rb.title) + '(으)로 통합되었습니다.<br>\n<a href="' +
          E(link) + '" target="_blank" rel="noopener">→ ' + E(rb.title) + ' 보기</a></p>');
      } else {
        body += section('대체 프로젝트', '\n<p>이 프로젝트는 ' + E(rb.title) + '(으)로 통합되었습니다.</p>');
      }
    }
    if (p.repositoryUrl) {
      body += section('Repository', '\n<p><a href="' + E(p.repositoryUrl) + '" target="_blank" rel="noopener">' +
        E(p.repositoryUrl) + '</a></p>');
    }
    return '\n<details' + attrs(p) + '>\n<summary>\n<span class="proj-period">' + E(periodStr(p)) +
      '</span>\n<div class="proj-main">\n<div class="proj-title">' + E(p.title) + '</div>' + badge('unused') +
      '\n<div class="proj-sub">' + E(sub) + '</div>\n</div>\n<span class="arrow">▶</span>\n</summary>\n<div class="detail">' +
      body + '\n</div>\n</details>';
  }

  function renderProjectCard(p) {
    if (p.status === 'unused') return renderUnused(p);
    var intro = multiline(p.summary || '') || PLACEHOLDER;
    var body = section('프로젝트 소개', '\n<p>' + intro + '</p>');
    if (p.highlights && p.highlights.length) {
      body += section(p.highlightsTitle || '주요 기능', '\n<ul>\n' +
        p.highlights.map(function (h) { return '<li>' + E(h) + '</li>'; }).join('\n') + '\n</ul>');
    }
    if (p.status === 'paused' && p.pauseReason) body += section('일시 중단 사유', '\n<p>' + multiline(p.pauseReason) + '</p>');
    if (p.myRole) body += section('담당 역할', '\n<p>' + E(p.myRole) + '</p>');
    body += videos(p);
    body += links(p);
    body += team(p);

    return '\n<details' + attrs(p) + '>\n<summary>\n<span class="proj-period">' + E(periodStr(p)) +
      '</span>\n<div class="proj-main">\n<div class="proj-title">' + E(p.title) + '</div>' + badge(p.status) + livePill(p) +
      '\n<div class="proj-sub">' + E(p.subtitle) + '</div>\n<div class="proj-chips">' + chips(p) +
      '\n</div>\n</div>\n<span class="arrow">▶</span>\n</summary>\n<div class="detail">' + body + '\n</div>\n</details>';
  }

  function renderProjectList(projects) {
    return (projects || []).map(renderProjectCard).join('\n');
  }

  // ── Featured / 그룹 섹션 ───────────────────────────────────────────────────
  function coverSrc(p) {
    var src = p.coverImage || '';
    return /^(https?:\/\/|assets\/)/.test(src) ? src : '';
  }

  function renderFeaturedCard(p) {
    var title = p.title || '';
    var cover = coverSrc(p);
    var coverHtml;
    if (cover) {
      coverHtml = '\n<div class="feat-cover"><img src="' + E(cover) + '" alt="' + E(title) + ' 미리보기" loading="lazy"></div>';
    } else {
      var initial = title ? Array.from(title)[0] : '?';
      coverHtml = '\n<div class="feat-cover feat-cover-empty" aria-hidden="true"><span>' + E(initial) + '</span></div>';
    }
    var cls = chipClass(p);
    var chipHtml = (p.tech || []).slice(0, 4).map(function (t) {
      return '\n<span class="' + cls + '">' + E(t) + '</span>';
    }).join('');
    var linkHtml = '';
    if (p.liveUrl && p.status !== 'unused') {
      linkHtml += '\n<a class="proj-link live" href="' + E(p.liveUrl) + '" target="_blank" rel="noopener">Live Demo</a>';
    }
    if (p.repositoryUrl) {
      linkHtml += '\n<a class="proj-link" href="' + E(p.repositoryUrl) + '" target="_blank" rel="noopener">GitHub</a>';
    }
    linkHtml += '\n<a class="proj-link more" href="#' + E(cardId(p)) + '">자세히</a>';

    return '\n<article class="feat-card" data-slug="' + E(p.slug) + '" data-display-status="' + displayStatus(p) + '">' +
      coverHtml + '\n<div class="feat-body">\n<div class="feat-meta">\n<span class="proj-period">' + E(periodStr(p)) +
      '</span>' + badge(p.status) + '\n</div>\n<h4 class="feat-title">' + E(title) + '</h4>\n<p class="feat-sub">' +
      E(p.subtitle) + '</p>\n<div class="proj-chips">' + chipHtml + '\n</div>\n<div class="proj-links">' + linkHtml +
      '\n</div>\n</div>\n</article>';
  }

  function featuredProjects(projects) {
    return (projects || []).filter(function (p) { return p.featured && p.status !== 'unused'; }).slice(0, FEATURED_MAX);
  }

  function renderSections(projects) {
    projects = projects || [];
    var out = '';
    var featured = featuredProjects(projects);
    if (featured.length) {
      out += '\n<div class="proj-featured">\n<h3 class="proj-group-title">Featured</h3>\n<div class="feat-grid">' +
        featured.map(renderFeaturedCard).join('') + '\n</div>\n</div>';
    }
    GROUPS.forEach(function (g) {
      var items = projects.filter(function (p) { return GROUP_OF[displayStatus(p)] === g[0]; });
      if (!items.length) return;
      out += '\n<div class="proj-group" data-group="' + g[0] + '">\n<h3 class="proj-group-title">' + g[1] +
        '<span class="proj-group-en">' + g[2] + '</span><span class="proj-group-count">' + items.length +
        '</span></h3>\n<div class="proj-group-list">' + items.map(renderProjectCard).join('') + '\n</div>\n</div>';
    });
    return out;
  }

  // ── 상태 필터 (DOM 기반 — 정적 카드에서도 동작) ─────────────────────────────
  function storageGet() { try { return window.localStorage.getItem(FILTER_KEY); } catch (e) { return null; } }
  function storageSet(v) { try { window.localStorage.setItem(FILTER_KEY, v); } catch (e) { /* 무시 */ } }

  function buildFilterBar(list) {
    var old = list.querySelector('.proj-filter');
    if (old) old.parentNode.removeChild(old);
    var cards = list.querySelectorAll('details[data-display-status]');
    if (!cards.length) return null;
    var counts = {};
    Array.prototype.forEach.call(cards, function (d) {
      var s = d.getAttribute('data-display-status');
      counts[s] = (counts[s] || 0) + 1;
    });
    var html = '<button type="button" class="proj-filter-btn" data-filter="all" aria-pressed="false">전체' +
      '<span class="count">' + cards.length + '</span></button>';
    STATUS_ORDER.forEach(function (s) {
      if (!counts[s]) return;
      html += '<button type="button" class="proj-filter-btn" data-filter="' + s + '" aria-pressed="false">' +
        STATUS_LABEL[s] + '<span class="count">' + counts[s] + '</span></button>';
    });
    var bar = document.createElement('div');
    bar.className = 'proj-filter';
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-label', '프로젝트 상태 필터');
    bar.innerHTML = html;
    list.insertBefore(bar, list.firstChild);
    bar.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('.proj-filter-btn') : null;
      if (!btn) return;
      var f = btn.getAttribute('data-filter');
      applyFilter(list, f);
      storageSet(f);
    });
    return bar;
  }

  function applyFilter(list, f) {
    var bar = list.querySelector('.proj-filter');
    if (bar && !bar.querySelector('[data-filter="' + f + '"]')) f = 'all';
    if (bar) {
      Array.prototype.forEach.call(bar.querySelectorAll('.proj-filter-btn'), function (b) {
        var on = b.getAttribute('data-filter') === f;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    var featured = list.querySelector('.proj-featured');
    if (featured) featured.hidden = f !== 'all';
    Array.prototype.forEach.call(list.querySelectorAll('.proj-group'), function (g) {
      var visible = 0;
      Array.prototype.forEach.call(g.querySelectorAll('details[data-display-status]'), function (d) {
        var show = f === 'all' || d.getAttribute('data-display-status') === f;
        d.hidden = !show;
        if (show) visible++;
      });
      g.hidden = visible === 0;
      var count = g.querySelector('.proj-group-count');
      if (count) count.textContent = String(visible);
    });
    list.setAttribute('data-filter', f);
  }

  function openFromHash(list) {
    var h = window.location.hash || '';
    if (h.indexOf('#proj-') !== 0) return;
    var el;
    try { el = document.getElementById(decodeURIComponent(h.slice(1))); } catch (e) { return; }
    if (!el || el.tagName !== 'DETAILS') return;
    if (el.hidden) applyFilter(list, 'all');
    el.open = true;
    el.scrollIntoView({ block: 'start' });
  }

  function enhance(list) {
    if (!buildFilterBar(list)) return;
    applyFilter(list, storageGet() || 'all');
    openFromHash(list);
  }

  function mount() {
    var list = document.querySelector('.project-list');
    if (!list) return;
    window.addEventListener('hashchange', function () { openFromHash(list); });

    function run() {
      if (typeof fetch !== 'function') { enhance(list); return; }
      fetch(DATA_URL, { cache: 'no-cache' })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
        .then(function (data) {
          if (!data || !Array.isArray(data.projects)) return;
          list.innerHTML = renderSections(data.projects);
          list.setAttribute('data-rendered', 'json');
          list.setAttribute('data-generated-at', data.generatedAt || '');
        })
        .catch(function () { /* 정적 카드 유지 */ })
        .then(function () { enhance(list); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
    else run();
  }

  return {
    renderProjectCard: renderProjectCard,
    renderProjectList: renderProjectList,
    renderSections: renderSections,
    renderFeaturedCard: renderFeaturedCard,
    displayStatus: displayStatus,
    formatPeriod: formatPeriod,
    mount: mount
  };
}));
