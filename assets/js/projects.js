/* ==========================================================================
   projects.js — data/projects.generated.json → 프로젝트 카드 렌더링
   --------------------------------------------------------------------------
   index.html 에는 sync 가 생성한 정적 카드가 이미 들어 있다 (JS 없이도 표시, SEO).
   이 스크립트는 같은 JSON 을 읽어 동일한 마크업으로 다시 그린다.
   fetch 가 실패하면(file:// 로 열었을 때 등) 정적 카드를 그대로 둔다.

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
  var STATUS_LABEL = {
    active: '진행 중', completed: '완료', paused: '일시 중단', unused: '미사용', archived: '아카이브'
  };
  var PLACEHOLDER = '내용을 입력하세요.';

  function E(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
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

  function chips(p) {
    var cls = p.tagClass ? ('chip ' + p.tagClass).trim() : 'chip';
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
    a += ' data-slug="' + E(p.slug) + '" data-source="' + E(p.source || 'github') + '"';
    if (p.status) a += ' data-status="' + E(p.status) + '"';
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
      '</span>\n<div class="proj-main">\n<div class="proj-title">' + E(p.title) + '</div>' + badge(p.status) +
      '\n<div class="proj-sub">' + E(p.subtitle) + '</div>\n<div class="proj-chips">' + chips(p) +
      '\n</div>\n</div>\n<span class="arrow">▶</span>\n</summary>\n<div class="detail">' + body + '\n</div>\n</details>';
  }

  function renderProjectList(projects) {
    return (projects || []).map(renderProjectCard).join('\n');
  }

  function mount() {
    var list = document.querySelector('.project-list');
    if (!list || typeof fetch !== 'function') return;
    fetch(DATA_URL, { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) {
        if (!data || !Array.isArray(data.projects)) return;
        list.innerHTML = renderProjectList(data.projects);
        list.setAttribute('data-rendered', 'json');
        list.setAttribute('data-generated-at', data.generatedAt || '');
      })
      .catch(function () { /* 정적 카드 유지 */ });
  }

  return {
    renderProjectCard: renderProjectCard,
    renderProjectList: renderProjectList,
    formatPeriod: formatPeriod,
    mount: mount
  };
}));
