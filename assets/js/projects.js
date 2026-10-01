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
    active: '진행 중', completed: '완료', paused: '일시 중단', unused: '미사용', archived: '과거'
  };
  var STATUS_ORDER = ['active', 'completed', 'paused', 'unused', 'archived'];
  var GROUPS = [
    ['current', '진행 중', 'Current'],
    ['paused', '일시 중단', 'Paused'],
    ['completed', '완료', 'Completed'],
    ['archive', '지난 프로젝트', 'Past']
  ];
  var GROUP_OF = { active: 'current', paused: 'paused', completed: 'completed', unused: 'archive', archived: 'archive' };
  var FEATURED_MAX = 5;
  var CHIP_LIMIT = 4;
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

  var HUES = 6;
  function hueIndex(p) {
    var s = String(p.slug || p.title || ''), sum = 0;
    for (var i = 0; i < s.length; i++) sum += s.charCodeAt(i);
    return sum % HUES + 1;
  }
  function monogram(p) {
    var s = String(p.title || '');
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      if (/[0-9A-Za-z\u3131-\uD79D]/.test(ch)) return ch.toUpperCase();
    }
    return '·';
  }
  function mark(p) {
    return '\n<span class="mark hue-' + hueIndex(p) + '" aria-hidden="true">' + E(monogram(p)) + '</span>';
  }

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
    return '\n<a class="proj-live" href="' + E(p.liveUrl) + '" target="_blank" rel="noopener">Live ↗</a>';
  }

  function repoPill(p) {
    if (!p.repositoryUrl) return '';
    return '\n<a class="proj-repo" href="' + E(p.repositoryUrl) + '" target="_blank" rel="noopener">GitHub ↗</a>';
  }

  function cardLinks(p) {
    var inner = livePill(p) + repoPill(p);
    return inner ? '\n<div class="card-links">' + inner + '\n</div>' : '';
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

  function usableSrc(src) {
    src = src || '';
    return /^(https?:\/\/|assets\/)/.test(src) ? src : '';
  }

  function shots(p) {
    var s = p.screenshots || {};
    var desktop = usableSrc(s.desktop), mobile = usableSrc(s.mobile);
    if (!desktop || p.status === 'unused') return '';
    var title = E(p.title);
    var body = '\n<img class="shot-desktop" src="' + E(desktop) + '" alt="' + title + ' 데스크톱 화면" loading="lazy" width="1440" height="900">';
    if (mobile) {
      body += '\n<img class="shot-mobile" src="' + E(mobile) + '" alt="' + title + ' 모바일 화면" loading="lazy" width="390" height="844">';
    }
    return section('화면', '\n<div class="shot-row">' + body + '\n</div>');
  }

  function videos(p) {
    var list = (p.videos || []).filter(function (v) { return v && v.url; });
    if (!list.length) return '';
    var body = '';
    list.forEach(function (v) {
      var label = v.label ? '\n<p class="video-label">' + E(v.label) + '</p>' : '';
      body += '\n<figure class="video">' + label + '\n<div class="video-wrap">\n<iframe src="' + E(v.url) +
        '" allowfullscreen></iframe>\n</div>\n</figure>';
    });
    return section('시연 영상', '\n<div class="video-row">' + body + '\n</div>');
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

  function isArchivedView(p) {
    var s = displayStatus(p);
    return s === 'archived' || s === 'unused';
  }

  function chips(p) {
    var cls = chipClass(p);
    var tech = p.tech || [];
    var out = '';
    if (!isArchivedView(p)) {
      tech.slice(0, CHIP_LIMIT).forEach(function (t) {
        out += '\n<span class="' + cls + '">' + E(t) + '</span>';
      });
      if (tech.length > CHIP_LIMIT) {
        out += '\n<span class="chip more" title="펼치면 전체 기술 스택">+' + (tech.length - CHIP_LIMIT) + '</span>';
      }
    }
    (p.awards || []).forEach(function (a) {
      out += '\n<span class="chip award">🏆 ' + E(a) + '</span>';
    });
    return out;
  }

  function techSection(p) {
    var tech = p.tech || [];
    if (!tech.length || (tech.length <= CHIP_LIMIT && !isArchivedView(p))) return '';
    var cls = chipClass(p);
    var chipHtml = tech.map(function (t) { return '\n<span class="' + cls + '">' + E(t) + '</span>'; }).join('');
    return section('기술 스택', '\n<div class="proj-chips">' + chipHtml + '\n</div>');
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
    return '\n<details' + attrs(p) + '>\n<summary>\n<div class="card-top">' + badge('unused') +
      '\n<span class="proj-period">' + E(periodStr(p)) + '</span>\n</div>\n<div class="card-head">' + mark(p) +
      '\n<div class="proj-main">\n<div class="proj-title">' + E(p.title) + '</div>\n<div class="proj-sub">' + E(sub) +
      '</div>\n</div>\n</div>\n</summary>\n<div class="detail">' + body + '\n</div>\n</details>';
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
    body += techSection(p);
    body += shots(p);
    body += videos(p);
    body += links(p);
    body += team(p);

    return '\n<details' + attrs(p) + '>\n<summary>\n<div class="card-top">' + badge(p.status) +
      '\n<span class="proj-period">' + E(periodStr(p)) + '</span>\n</div>\n<div class="card-head">' + mark(p) +
      '\n<div class="proj-main">\n<div class="proj-title">' + E(p.title) + '</div>\n<div class="proj-sub">' + E(p.subtitle) +
      '</div>\n</div>\n</div>\n<div class="card-foot">\n<div class="proj-chips">' +
      chips(p) + '\n</div>' + cardLinks(p) + '\n</div>\n</summary>\n<div class="detail">' + body + '\n</div>\n</details>';
  }

  function renderProjectList(projects) {
    return (projects || []).map(renderProjectCard).join('\n');
  }

  // ── Featured / 그룹 섹션 ───────────────────────────────────────────────────
  function coverSrc(p) {
    return usableSrc(p.coverImage) || usableSrc((p.screenshots || {}).desktop);
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
      E(p.subtitle) + '</p>\n<div class="proj-chips">' + chipHtml + '\n</div>\n<div class="card-links">' + linkHtml +
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
      var cards = '', lastYear = null;
      items.forEach(function (p) {
        if (g[0] === 'archive') {
          var year = (p.started || '').slice(0, 4) || '기타';
          if (year !== lastYear) { cards += '\n<div class="tl-year" aria-hidden="true">' + E(year) + '</div>'; lastYear = year; }
        }
        cards += renderProjectCard(p);
      });
      out += '\n<div class="proj-group" data-group="' + g[0] + '">\n<h3 class="proj-group-title">' + g[1] +
        '<span class="proj-group-en">' + g[2] + '</span><span class="proj-group-count">' + items.length +
        '</span></h3>\n<div class="proj-group-list">' + cards + '\n</div>\n</div>';
    });
    return out;
  }

  // ── 첫 화면 사실 요약 (STATS 마커 안) ───────────────────────────────────────
  function projectStats(projects) {
    var c = { total: projects.length, current: 0, paused: 0, completed: 0, archive: 0, live: 0, since: '' };
    var years = [];
    projects.forEach(function (p) {
      c[GROUP_OF[displayStatus(p)]] += 1;
      if (p.liveUrl && p.status !== 'unused') c.live += 1;
      var y = (p.started || '').slice(0, 4);
      if (/^\d{4}$/.test(y)) years.push(parseInt(y, 10));
    });
    if (years.length) c.since = String(Math.min.apply(null, years));
    return c;
  }

  function yearCounts(projects) {
    var years = projects.map(function (p) { return (p.started || '').slice(0, 4); }).filter(function (y) { return /^\d{4}$/.test(y); }).map(Number);
    if (!years.length) return [];
    var lo = Math.min.apply(null, years), hi = Math.max.apply(null, years), out = [];
    for (var y = lo; y <= hi; y++) out.push([String(y), years.filter(function (v) { return v === y; }).length]);
    return out;
  }

  function renderYearBars(projects) {
    var rows = yearCounts(projects);
    if (!rows.length) return '';
    var peak = Math.max.apply(null, rows.map(function (r) { return r[1]; })) || 1;
    return '\n<div class="year-bars" aria-label="연도별 시작한 프로젝트 수">' + rows.map(function (r) {
      return '\n<div class="ybar" style="--v:' + (r[1] / peak).toFixed(2) + '" title="' + r[0] + ' · ' + r[1] + '개"><i></i><b>' + r[0].slice(2) + '</b></div>';
    }).join('') + '\n</div>';
  }

  function renderStats(projects, generatedAt) {
    var c = projectStats(projects);
    var rows = [
      ['프로젝트', c.total + '<span class="unit">개</span>', 'total'],
      ['진행 중', String(c.current), 'current'],
      ['완료', String(c.completed + c.paused), 'done'],
      ['지난 프로젝트', String(c.archive), 'archive']
    ];
    if (c.since) rows.push(['기록 시작', c.since, 'since']);
    if (generatedAt) rows.push(['마지막 동기화', E(String(generatedAt).slice(0, 10).replace(/-/g, '.')), 'synced']);
    return renderYearBars(projects) + rows.map(function (r) {
      return '\n<div class="fact" data-fact="' + r[2] + '"><dt>' + E(r[0]) + '</dt><dd>' + r[1] + '</dd></div>';
    }).join('');
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

  // ── 그룹 접기: 지난 프로젝트는 기본으로 접어 둔다 (기록 중심 최소 표현) ──────
  var FOLD_GROUPS = ['archive'];

  function setFold(g, folded) {
    g.classList.toggle('is-folded', folded);
    var b = g.querySelector('.proj-group-toggle');
    if (b) {
      b.textContent = folded ? '펼치기' : '접기';
      b.setAttribute('aria-expanded', folded ? 'false' : 'true');
    }
  }

  function setupFolds(list) {
    FOLD_GROUPS.forEach(function (key) {
      var g = list.querySelector('.proj-group[data-group="' + key + '"]');
      if (!g || g.querySelector('.proj-group-toggle')) return;
      var title = g.querySelector('.proj-group-title');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'proj-group-toggle';
      title.insertBefore(btn, title.querySelector('.proj-group-count'));
      btn.addEventListener('click', function () { setFold(g, !g.classList.contains('is-folded')); });
      setFold(g, true);
    });
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
    if (f === 'archived' || f === 'unused') {
      Array.prototype.forEach.call(list.querySelectorAll('.proj-group.is-folded'), function (g) { setFold(g, false); });
    }
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
    var g = el.closest ? el.closest('.proj-group.is-folded') : null;
    if (g) setFold(g, false);
    el.open = true;
    el.scrollIntoView({ block: 'start' });
  }

  function enhance(list) {
    if (!buildFilterBar(list)) return;
    setupFolds(list);
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
          var facts = document.getElementById('facts');
          if (facts) facts.innerHTML = renderStats(data.projects, data.generatedAt);
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
    renderStats: renderStats,
    displayStatus: displayStatus,
    formatPeriod: formatPeriod,
    mount: mount
  };
}));
