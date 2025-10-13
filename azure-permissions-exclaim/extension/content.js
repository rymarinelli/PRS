(() => {
  if (window.__mmExclaimInitialized) {
    return;
  }
  window.__mmExclaimInitialized = true;

  const BACKEND_URL = 'http://localhost:5001/recommend';
  const hostId = 'mm-exclaim-root';

  let currentIssue = null;
  let panelOpen = false;
  let lastResourceId = null;

  const hostEl = document.createElement('div');
  hostEl.id = hostId;
  hostEl.setAttribute('role', 'complementary');
  hostEl.style.position = 'fixed';
  hostEl.style.bottom = '24px';
  hostEl.style.right = '24px';
  hostEl.style.zIndex = '2147483647';
  hostEl.style.all = 'initial';

  const defaultParent = document.documentElement;
  let activeAnchor = null;
  let activeAnchorOriginalPosition = null;
  const anchorAttribute = 'data-mm-exclaim-anchor';

  const shadow = hostEl.attachShadow({ mode: 'open' });

  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = chrome.runtime.getURL('overlay.css');
  shadow.appendChild(link);

  const container = document.createElement('div');
  container.className = 'mm-container';
  shadow.appendChild(container);

  const button = document.createElement('button');
  button.className = 'mm-exclaim-button';
  button.type = 'button';
  button.setAttribute('aria-label', 'View permission recommendation');
  button.setAttribute('aria-expanded', 'false');
  button.textContent = '!';
  container.appendChild(button);

  const panel = document.createElement('div');
  panel.className = 'mm-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-live', 'polite');
  panel.hidden = true;
  container.appendChild(panel);

  const title = document.createElement('h2');
  title.className = 'mm-panel-title';
  panel.appendChild(title);

  const badge = document.createElement('span');
  badge.className = 'mm-panel-badge';
  badge.textContent = 'informed by alerts';
  panel.appendChild(badge);

  const summary = document.createElement('p');
  summary.className = 'mm-panel-summary';
  panel.appendChild(summary);

  const actions = document.createElement('div');
  actions.className = 'mm-panel-actions';
  panel.appendChild(actions);

  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'mm-panel-button';
  copyBtn.textContent = 'Copy az CLI fix';
  actions.appendChild(copyBtn);

  const detailsBtn = document.createElement('button');
  detailsBtn.type = 'button';
  detailsBtn.className = 'mm-panel-button mm-secondary';
  detailsBtn.textContent = 'Open details';
  actions.appendChild(detailsBtn);

  defaultParent.appendChild(hostEl);

  function restoreAnchorPosition() {
    if (activeAnchor && activeAnchorOriginalPosition !== null) {
      activeAnchor.style.position = activeAnchorOriginalPosition;
    }
    activeAnchor = null;
    activeAnchorOriginalPosition = null;
  }

  function applyDefaultPlacement() {
    if (hostEl.parentElement !== defaultParent) {
      defaultParent.appendChild(hostEl);
    }
    restoreAnchorPosition();
    hostEl.style.position = 'fixed';
    hostEl.style.bottom = '24px';
    hostEl.style.right = '24px';
    hostEl.style.left = '';
    hostEl.style.top = '';
    hostEl.classList.remove('mm-anchored');
  }

  function applyAnchorPlacement(anchor) {
    if (!anchor) {
      applyDefaultPlacement();
      return;
    }
    if (activeAnchor === anchor && hostEl.parentElement === anchor) {
      return;
    }
    restoreAnchorPosition();
    const computed = window.getComputedStyle(anchor);
    if (computed.position === 'static') {
      activeAnchorOriginalPosition = anchor.style.position || '';
      anchor.style.position = 'relative';
    } else {
      activeAnchorOriginalPosition = null;
    }
    anchor.appendChild(hostEl);
    hostEl.style.position = 'absolute';
    hostEl.style.bottom = '16px';
    hostEl.style.right = '16px';
    hostEl.style.left = '';
    hostEl.style.top = '';
    hostEl.classList.add('mm-anchored');
    activeAnchor = anchor;
  }

  function findAnchor() {
    return document.querySelector(`[${anchorAttribute}]`);
  }

  function syncPlacement({ preferAnchor } = { preferAnchor: true }) {
    if (preferAnchor && currentIssue) {
      const anchor = findAnchor();
      if (anchor) {
        applyAnchorPlacement(anchor);
        return;
      }
    }
    applyDefaultPlacement();
  }

  syncPlacement({ preferAnchor: false });

  function togglePanel(forceOpen) {
    if (!currentIssue) {
      return;
    }
    panelOpen = typeof forceOpen === 'boolean' ? forceOpen : !panelOpen;
    panel.hidden = !panelOpen;
    button.setAttribute('aria-expanded', String(panelOpen));
  }

  async function copyFix() {
    if (!currentIssue || !currentIssue.azFix) {
      return;
    }
    try {
      await navigator.clipboard.writeText(currentIssue.azFix);
      const original = copyBtn.textContent;
      copyBtn.textContent = 'Copied!';
      copyBtn.disabled = true;
      setTimeout(() => {
        copyBtn.textContent = original;
        copyBtn.disabled = false;
      }, 2000);
    } catch (err) {
      console.warn('Clipboard copy failed', err);
    }
  }

  function openDetails() {
    if (!currentIssue || !currentIssue.panelUrl) {
      return;
    }
    try {
      const url = new URL(currentIssue.panelUrl);
      if (currentIssue.resourceId) {
        url.searchParams.set('rid', currentIssue.resourceId);
      }
      if (currentIssue.issueId) {
        url.searchParams.set('issue', currentIssue.issueId);
      }
      window.open(url.toString(), '_blank', 'noopener');
    } catch (err) {
      console.warn('Unable to open details panel', err);
    }
  }

  button.addEventListener('click', () => {
    if (!currentIssue) {
      return;
    }
    togglePanel();
  });
  copyBtn.addEventListener('click', copyFix);
  detailsBtn.addEventListener('click', openDetails);

  function hideIssue() {
    currentIssue = null;
    panelOpen = false;
    panel.hidden = true;
    button.classList.remove('mm-visible');
    button.setAttribute('aria-expanded', 'false');
    syncPlacement({ preferAnchor: false });
  }

  function showIssue(issue) {
    currentIssue = issue;
    panelOpen = false;
    panel.hidden = true;
    button.classList.add('mm-visible');
    button.setAttribute('aria-expanded', 'false');
    title.textContent = issue.title || 'Permission recommendation available';
    badge.textContent = issue.source || 'informed by alerts';
    summary.textContent = issue.summary || 'Review the suggested mitigation steps.';
    syncPlacement({ preferAnchor: true });
  }

  async function fetchRecommendation(resourceId) {
    try {
      const response = await fetch(BACKEND_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          resourceId,
          page: window.location.hash || ''
        })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data && data.hasIssue) {
        showIssue(data);
      } else {
        hideIssue();
      }
    } catch (err) {
      console.warn('Failed to fetch recommendation', err);
      hideIssue();
    }
  }

  function parseResourceIdFromHash(hash) {
    if (!hash) {
      return null;
    }
    const decoded = decodeURIComponent(hash);
    const marker = '/resourceId/';
    const markerIdx = decoded.indexOf(marker);
    if (markerIdx !== -1) {
      const remainder = decoded.substring(markerIdx + marker.length);
      const stopIdx = remainder.search(/[?&#]/);
      const resource = stopIdx === -1 ? remainder : remainder.substring(0, stopIdx);
      return resource.startsWith('/') ? resource : `/${resource}`;
    }
    const match = decoded.match(/resourceId=([^&#]+)/i);
    if (match && match[1]) {
      const res = decodeURIComponent(match[1]);
      return res.startsWith('/') ? res : `/${res}`;
    }
    return null;
  }

  function handleNavigation() {
    const hash = window.location.hash || '';
    const resourceId = parseResourceIdFromHash(hash);
    if (!resourceId) {
      hideIssue();
      lastResourceId = null;
      return;
    }
    if (resourceId === lastResourceId) {
      return;
    }
    lastResourceId = resourceId;
    fetchRecommendation(resourceId);
  }

  const debouncedHandle = (() => {
    let timeoutId;
    return () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(handleNavigation, 150);
    };
  })();

  window.addEventListener('hashchange', debouncedHandle);
  window.addEventListener('popstate', debouncedHandle);

  const placementObserver = new MutationObserver(() => {
    if (currentIssue) {
      syncPlacement({ preferAnchor: true });
    }
  });

  placementObserver.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [anchorAttribute]
  });

  // initial check once DOM ready enough
  debouncedHandle();
})();
