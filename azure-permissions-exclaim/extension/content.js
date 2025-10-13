(() => {
  if (window.__azRbacAdvisorInitialized) {
    return;
  }
  window.__azRbacAdvisorInitialized = true;

  const BACKEND_URL = 'http://localhost:5001/recommend';
  const hostId = 'azra-advisor-root';

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
  const anchorAttribute = 'data-azra-anchor';

  const shadow = hostEl.attachShadow({ mode: 'open' });

  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = chrome.runtime.getURL('overlay.css');
  shadow.appendChild(link);

  const container = document.createElement('div');
  container.className = 'azra-container';
  shadow.appendChild(container);

  const button = document.createElement('button');
  button.className = 'azra-alert-button';
  button.type = 'button';
  button.setAttribute('aria-label', 'View permission recommendation');
  button.setAttribute('aria-expanded', 'false');
  button.textContent = '!';
  container.appendChild(button);

  const panel = document.createElement('div');
  panel.className = 'azra-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-live', 'polite');
  panel.hidden = true;
  container.appendChild(panel);

  const title = document.createElement('h2');
  title.className = 'azra-panel-title';
  panel.appendChild(title);

  const badge = document.createElement('span');
  badge.className = 'azra-panel-badge';
  badge.textContent = 'informed by alerts';
  panel.appendChild(badge);

  const summary = document.createElement('p');
  summary.className = 'azra-panel-summary';
  panel.appendChild(summary);

  const modelMeta = document.createElement('div');
  modelMeta.className = 'azra-model-meta';
  panel.appendChild(modelMeta);
  modelMeta.hidden = true;

  const scoreLabel = document.createElement('div');
  scoreLabel.className = 'azra-model-score';
  modelMeta.appendChild(scoreLabel);

  const trainingLabel = document.createElement('div');
  trainingLabel.className = 'azra-training-meta';
  trainingLabel.hidden = true;
  modelMeta.appendChild(trainingLabel);

  const factorSection = document.createElement('div');
  factorSection.className = 'azra-factor-section';
  modelMeta.appendChild(factorSection);
  factorSection.hidden = true;

  const factorHeading = document.createElement('span');
  factorHeading.className = 'azra-factor-heading';
  factorHeading.textContent = 'Top signals:';
  factorSection.appendChild(factorHeading);

  const factorList = document.createElement('ul');
  factorList.className = 'azra-factor-list';
  factorSection.appendChild(factorList);

  const actions = document.createElement('div');
  actions.className = 'azra-panel-actions';
  panel.appendChild(actions);

  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'azra-panel-button';
  copyBtn.textContent = 'Copy az CLI fix';
  actions.appendChild(copyBtn);

  const detailsBtn = document.createElement('button');
  detailsBtn.type = 'button';
  detailsBtn.className = 'azra-panel-button azra-secondary';
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
    hostEl.classList.remove('azra-anchored');
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
    hostEl.classList.add('azra-anchored');
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
    button.classList.remove('azra-visible');
    button.setAttribute('aria-expanded', 'false');
    modelMeta.hidden = true;
    factorSection.hidden = true;
    factorList.replaceChildren();
    trainingLabel.textContent = '';
    trainingLabel.hidden = true;
    syncPlacement({ preferAnchor: false });
  }

  function showIssue(issue) {
    currentIssue = issue;
    panelOpen = false;
    panel.hidden = true;
    button.classList.add('azra-visible');
    button.setAttribute('aria-expanded', 'false');
    title.textContent = issue.title || 'Permission recommendation available';
    badge.textContent = issue.source || 'informed by alerts';
    summary.textContent = issue.summary || 'Review the suggested mitigation steps.';

    let metaVisible = false;

    if (typeof issue.modelScore === 'number') {
      const pct = Math.round(issue.modelScore * 100);
      scoreLabel.textContent = `Model confidence: ${pct}% risk`;
      metaVisible = true;
    } else {
      scoreLabel.textContent = '';
    }

    const trainingMeta = issue.modelTraining && typeof issue.modelTraining === 'object' ? issue.modelTraining : null;
    if (trainingMeta) {
      const parts = [];
      if (typeof trainingMeta.size === 'number') {
        parts.push(`trained on ${trainingMeta.size} simulated alerts`);
      }
      if (typeof trainingMeta.accuracy === 'number') {
        const accPct = Math.round(trainingMeta.accuracy * 1000) / 10;
        parts.push(`training accuracy ${accPct}%`);
      }
      if (typeof trainingMeta.lastTrained === 'string') {
        parts.push(`last trained ${trainingMeta.lastTrained}`);
      }
      trainingLabel.textContent = parts.join(' · ');
      trainingLabel.hidden = parts.length === 0;
      metaVisible = metaVisible || parts.length > 0;
    } else {
      trainingLabel.textContent = '';
      trainingLabel.hidden = true;
    }

    factorList.replaceChildren();
    if (Array.isArray(issue.topFactors) && issue.topFactors.length) {
      issue.topFactors.slice(0, 3).forEach((factor) => {
        if (!factor || typeof factor.feature !== 'string') {
          return;
        }
        const item = document.createElement('li');
        item.className = 'azra-factor-item';
        const contribution = typeof factor.contribution === 'number' ? factor.contribution : 0;
        const direction = contribution >= 0 ? '↑' : '↓';
        item.textContent = `${direction} ${factor.feature.replace(/_/g, ' ')} (${Math.abs(contribution).toFixed(2)})`;
        factorList.appendChild(item);
      });
      factorSection.hidden = false;
      metaVisible = true;
    } else {
      factorSection.hidden = true;
    }

    modelMeta.hidden = !metaVisible;
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
