(function () {
  const BOOTSTRAP = window.KMQDB_SUBDOMAIN_BOOTSTRAP || {};
  const app = document.getElementById("app");
  const state = {
    bookshelfPayloads: new Map(),
    bookshelfPromises: new Map(),
    bookshelfErrors: new Map(),
    ruleMenuPayloads: new Map(),
    ruleMenuPromise: null,
    ruleMenuError: null,
    ruleTargetPayloads: new Map(),
    ruleTargetPromise: null,
    ruleTargetError: null,
    publicationPayloads: new Map(),
    publicationPromises: new Map(),
    publicationErrors: new Map(),
    publicationNodePackets: new Map(),
    publicationNodePromises: new Map(),
    publicationNodeErrors: new Map(),
    sourceNodePackets: new Map(),
    sourceNodePromises: new Map(),
    sourceNodeErrors: new Map(),
    rendererScriptPromises: new Map(),
    rendererInterfacePromise: null,
    rendererInterfaceError: null,
    enabledSourcesByRuleset: new Map(),
    openSourceIds: new Set(),
    openRuleIds: new Set(),
    activeSourceId: "",
    activeSourceLocator: "",
    activeRuleId: "",
    activeRuleFamilyId: "",
    activeRuleFacet: "",
    activeRuleNameSlug: "",
    activeRuleSourceId: "",
    activeRuleLocator: "",
    activeCategory: "sources",
    showSourceDates: true,
    sourceSort: "date",
    sourceMenuSettingsOpen: false,
    wrapSourceNames: true,
  };
  let workspaceController = null;

  const navCategories = ["sources", "rules", "data", "tools"];
  const sourceSortModes = ["alpha", "date", "reverse-date"];
  const ttrpgShowDatesKey = "kmqdb:ttrpg:source-menu:metadata";
  const ttrpgSourceSortKey = "kmqdb:ttrpg:source-menu:sort";
  const ttrpgWrapNamesKey = "kmqdb:ttrpg:source-menu:wrap-lines";
  const pf2erRuleset = {
    id: "pf2er",
    title: "2E Remaster",
    family: {
      key: "pathfinder",
      title: "Pathfinder",
    },
    defaultSources: new Set(["core-gmc", "core-pc1", "core-mc1", "core-hotw", "core-pc2", "core-gg", "core-woi"]),
    mandatorySources: new Set(["core-gmc", "core-pc1", "core-mc1"]),
  };
  const pf2erRuleFamilies = [
    { id: "cc-ancestries", name: "Ancestries", slug: "ancestries" },
    { id: "cc-heritages", name: "Heritages", slug: "heritages" },
    { id: "cc-backgrounds", name: "Backgrounds", slug: "backgrounds" },
    { id: "cc-classes", name: "Classes", slug: "classes" },
    { id: "cc-skills", name: "Skills", slug: "skills" },
    { id: "cc-feats", name: "Feats", slug: "feats" },
    { id: "cc-actions", name: "Actions", slug: "actions" },
    { id: "cc-spells", name: "Spells", slug: "spells" },
    { id: "explorationactivities", name: "Exploration Activities", slug: "exploration-activities" },
    { id: "items", name: "Items", slug: "items" },
  ];
  const pf2erRuleFamilyById = new Map(pf2erRuleFamilies.map((family) => [family.id, family]));
  const pf2erRuleFamilyBySlug = new Map(pf2erRuleFamilies.map((family) => [family.slug, family]));

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function routePath() {
    return window.location.pathname.replace(/^\/+|\/+$/g, "");
  }

  function routeHref(path) {
    const normalized = String(path || "").replace(/^\/+|\/+$/g, "");
    return `/${normalized}${normalized ? "/" : ""}`;
  }

  function routeParts() {
    return routePath().split("/").filter(Boolean).map((part) => decodeURIComponent(part));
  }

  function ruleEntryRouteSlug(entry) {
    return String(entry?.name || entry?.id || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function pf2erRuleEntryBySlug(familyId, slug) {
    const normalized = String(slug || "");
    if (!familyId || !normalized) return null;
    return pf2erTargetableRuleEntries(pf2erRuleset, familyId)
      .find((entry) => ruleEntryRouteSlug(entry) === normalized) || null;
  }

  function pf2erStateHref(
    category = state.activeCategory,
    sourceId = state.activeRuleSourceId,
    locator = state.activeRuleLocator,
  ) {
    const safeRuleset = pf2erRuleset.id;
    const safeCategory = navCategories.includes(category) ? category : "sources";
    if (safeCategory === "rules") {
      const family = pf2erRuleFamilyById.get(state.activeRuleFamilyId);
      const facet = state.activeRuleFacet;
      if (!family || !["name", "source"].includes(facet)) return routeHref(`${safeRuleset}/rules`);
      const entry = currentRuleEntry(pf2erRuleset);
      const nameSlug = ruleEntryRouteSlug(entry) || state.activeRuleNameSlug;
      if (facet === "name") {
        const namePart = nameSlug ? `/${encodeURIComponent(nameSlug)}` : "";
        const sourcePart = nameSlug && sourceId ? `/${encodeURIComponent(String(sourceId))}` : "";
        const locatorPart = nameSlug && sourceId && locator ? `/${encodeURIComponent(String(locator))}` : "";
        return routeHref(`${safeRuleset}/rules/${family.slug}/by-name${namePart}${sourcePart}${locatorPart}`);
      }
      const sourcePart = sourceId ? `/${encodeURIComponent(String(sourceId))}` : "";
      const namePart = sourceId && nameSlug ? `/${encodeURIComponent(nameSlug)}` : "";
      const locatorPart = sourceId && nameSlug && locator ? `/${encodeURIComponent(String(locator))}` : "";
      return routeHref(`${safeRuleset}/rules/${family.slug}/by-source${sourcePart}${namePart}${locatorPart}`);
    }
    if (safeCategory === "sources" && state.activeSourceId) {
      const source = encodeURIComponent(state.activeSourceId);
      const view = state.activeSourceLocator ? encodeURIComponent(state.activeSourceLocator) : "overview";
      return routeHref(`${safeRuleset}/sources/${source}/${view}`);
    }
    return routeHref(`${safeRuleset}/${safeCategory}`);
  }

  function splitPf2erRuleRouteParts(parts) {
    const family = pf2erRuleFamilyBySlug.get(String(parts[2] || ""));
    const facet = parts[3] === "by-name" ? "name" : parts[3] === "by-source" ? "source" : "";
    if (!family || !facet) return { familyId: family?.id || "", facet, ruleId: "", nameSlug: "", sourceId: "", locator: "" };
    const nameSlug = String(parts[facet === "name" ? 4 : 5] || "");
    const entry = pf2erRuleEntryBySlug(family.id, nameSlug);
    return {
      familyId: family.id,
      facet,
      ruleId: String(entry?.id || ""),
      nameSlug,
      sourceId: String(parts[facet === "name" ? 5 : 4] || ""),
      locator: String(parts[6] || ""),
    };
  }

  function replaceRouteStateFromPath(parts) {
    const category = navCategories.includes(parts[1]) ? parts[1] : "sources";
    state.activeCategory = category;
    if (category === "rules") {
      state.activeRuleId = "";
      state.activeRuleFamilyId = "";
      state.activeRuleFacet = "";
      state.activeRuleNameSlug = "";
      state.activeRuleSourceId = "";
      state.activeRuleLocator = "";
      const split = splitPf2erRuleRouteParts(parts);
      state.activeRuleId = split.ruleId;
      state.activeRuleFamilyId = split.familyId || "";
      state.activeRuleFacet = split.facet || "";
      state.activeRuleNameSlug = split.nameSlug || "";
      state.activeRuleSourceId = split.sourceId;
      state.activeRuleLocator = split.locator;
      if (state.activeRuleFamilyId) state.openRuleIds.add(state.activeRuleFamilyId);
      if (state.activeRuleFamilyId && state.activeRuleFacet) state.openRuleIds.add(`${state.activeRuleFamilyId}--by-${state.activeRuleFacet}`);
    } else if (category === "sources") {
      state.activeSourceId = parts[2] || "";
      state.activeSourceLocator = parts[3] && parts[3] !== "overview" ? parts[3] : "";
    }
  }

  function pushAppRoute(href) {
    const url = new URL(href, window.location.origin);
    if (url.pathname !== window.location.pathname) window.history.pushState({}, "", url.pathname);
  }

  function replaceAppRoute(href) {
    const url = new URL(href, window.location.origin);
    if (url.pathname !== window.location.pathname) window.history.replaceState({}, "", url.pathname);
  }

  function ttrpgApiUrl(path, params = {}) {
    const query = new URLSearchParams(params);
    const suffix = query.size ? `?${query.toString()}` : "";
    return `/.api/${String(path || "").replace(/^\/+|\/+$/g, "")}${suffix}`;
  }

  function bookshelfApiUrl() {
    return ttrpgApiUrl("bookshelf");
  }

  function ruleSourceNodeApiUrl(rootTarget, selectedLocator) {
    return ttrpgApiUrl("rules/source-node", {
      source: String(rootTarget?.source || ""),
      root: String(rootTarget?.locator || ""),
      selected: String(selectedLocator || rootTarget?.locator || ""),
    });
  }

  function publicationApiUrl(sourceId) {
    return ttrpgApiUrl(`sources/${encodeURIComponent(String(sourceId || ""))}/publication`);
  }

  function publicationNodeApiUrl(sourceId, rootLocator, selectedLocator, scope) {
    return ttrpgApiUrl(`sources/${encodeURIComponent(String(sourceId || ""))}/node`, {
      root: String(rootLocator || ""),
      selected: String(selectedLocator || rootLocator || ""),
      scope: String(scope || ""),
    });
  }

  function sourceAssetUrl(path) {
    const value = String(path || "");
    if (!value) return "";
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin ? url.href : "";
  }

  function loadRendererScript(path) {
    const url = sourceAssetUrl(path);
    if (!url) return Promise.reject(new Error("Source renderer script is missing a same-origin URL"));
    if (state.rendererScriptPromises.has(url)) return state.rendererScriptPromises.get(url);
    const promise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = url;
      script.async = false;
      script.dataset.ttrpgSourceAsset = "js";
      script.addEventListener("load", resolve, { once: true });
      script.addEventListener("error", () => reject(new Error(`Unable to load source renderer: ${url}`)), { once: true });
      document.head.appendChild(script);
    });
    state.rendererScriptPromises.set(url, promise);
    return promise;
  }

  function loadSourceInterface(packet) {
    const scripts = Array.isArray(packet?.presentation?.scripts)
      ? packet.presentation.scripts.filter(Boolean)
      : [];
    if (state.rendererInterfacePromise) return state.rendererInterfacePromise;
    state.rendererInterfacePromise = scripts
      .reduce((pending, path) => pending.then(() => loadRendererScript(path)), Promise.resolve())
      .then(() => {
        if (window.KMQDB_RULESET_RENDERER?.renderSourceNodeView) return window.KMQDB_RULESET_RENDERER;
        throw new Error("Source renderer did not register");
      })
      .then((renderer) => {
        state.rendererInterfaceError = null;
        renderRoute();
        return renderer;
      })
      .catch((failure) => {
        state.rendererInterfaceError = failure;
        renderRoute();
      })
      .finally(() => {
        state.rendererInterfacePromise = null;
      });
    return state.rendererInterfacePromise;
  }

  function categoryLabel(category) {
    return category === "sources" ? "Sources" : category.slice(0, 1).toUpperCase() + category.slice(1);
  }

  function formatSourceDate(value) {
    const match = String(value || "").match(/^(\d{4})-(\d{2})/);
    return !match || match[1] === "0000" ? "" : `${match[1]}/${match[2]}`;
  }

  function sourceNameCompare(left, right) {
    return String(left?.name || left?.id || "").localeCompare(String(right?.name || right?.id || ""), undefined, { numeric: true });
  }

  function sourceDateCompare(left, right) {
    const clean = (value) => {
      const text = String(value || "").trim();
      return !text || text.startsWith("0000-") ? "" : text;
    };
    const leftDate = clean(left?.date);
    const rightDate = clean(right?.date);
    if (leftDate && rightDate && leftDate !== rightDate) {
      return state.sourceSort === "reverse-date" ? rightDate.localeCompare(leftDate) : leftDate.localeCompare(rightDate);
    }
    if (leftDate !== rightDate) return leftDate ? -1 : 1;
    return sourceNameCompare(left, right);
  }

  function sourceSiblingCompare(left, right) {
    return state.sourceSort === "alpha" ? sourceNameCompare(left, right) : sourceDateCompare(left, right);
  }

  function sourceSortValueLabel(mode) {
    if (mode === "alpha") return "A-Z";
    if (mode === "reverse-date") return "Newest";
    return "Oldest";
  }

  function storageKey(ruleset, name) {
    return `kmqdb:ttrpg:${ruleset?.id || "unknown"}:${name}`;
  }

  function safeReadJson(key, defaultValue) {
    try {
      const raw = window.localStorage?.getItem(key);
      return raw ? JSON.parse(raw) : defaultValue;
    } catch (_) {
      return defaultValue;
    }
  }

  function safeWriteJson(key, value) {
    try {
      window.localStorage?.setItem(key, JSON.stringify(value));
    } catch (_) {
      // Preferences are optional and never authoritative.
    }
  }

  function initializePreferences() {
    const sort = String(safeReadJson(ttrpgSourceSortKey, "date") || "");
    state.sourceSort = sourceSortModes.includes(sort) ? sort : "date";
    state.showSourceDates = safeReadJson(ttrpgShowDatesKey, true) !== false;
    state.wrapSourceNames = safeReadJson(ttrpgWrapNamesKey, true) !== false;
  }

  initializePreferences();

  function defaultSourceIds(ruleset) {
    return new Set(ruleset?.defaultSources || []);
  }

  function mandatorySourceIds(ruleset) {
    return new Set(ruleset?.mandatorySources || []);
  }

  function sourceIsMandatory(ruleset, id) {
    return mandatorySourceIds(ruleset).has(String(id || ""));
  }

  function enabledSourcesForRuleset(ruleset) {
    const rulesetId = ruleset?.id || "";
    if (!rulesetId) return new Set();
    if (!state.enabledSourcesByRuleset.has(rulesetId)) {
      const stored = safeReadJson(storageKey(ruleset, "enabled-sources"), null);
      const storedIds = stored?.schema === 1 && Array.isArray(stored.enabled) ? stored.enabled : null;
      const values = storedIds === null
        ? defaultSourceIds(ruleset)
        : new Set(storedIds.map(String).filter(Boolean));
      for (const sourceId of mandatorySourceIds(ruleset)) values.add(sourceId);
      state.enabledSourcesByRuleset.set(rulesetId, values);
    }
    return new Set(state.enabledSourcesByRuleset.get(rulesetId));
  }

  function writeEnabledSources(ruleset, values) {
    const normalized = new Set([...values].map(String).filter(Boolean));
    for (const sourceId of mandatorySourceIds(ruleset)) normalized.add(sourceId);
    state.enabledSourcesByRuleset.set(ruleset.id, normalized);
    safeWriteJson(storageKey(ruleset, "enabled-sources"), {
      schema: 1,
      enabled: [...normalized].sort(),
    });
  }

  function toggleEnabledSource(ruleset, sourceId) {
    const id = String(sourceId || "");
    if (!id || sourceIsMandatory(ruleset, id)) return;
    const values = enabledSourcesForRuleset(ruleset);
    if (values.has(id)) values.delete(id);
    else values.add(id);
    writeEnabledSources(ruleset, values);
  }

  function fetchJsonOnce(url, options, onSuccess, onFailure, onFinally) {
    return fetch(url, options)
      .then((response) => {
        if (!response.ok) return response.json().catch(() => ({})).then((payload) => {
          throw new Error(payload.error || `Request returned ${response.status}`);
        });
        return response.json();
      })
      .then(onSuccess)
      .catch(onFailure)
      .finally(onFinally);
  }

  function fetchBookshelf(ruleset) {
    const key = ruleset?.id || "";
    if (!key || state.bookshelfPayloads.has(key) || state.bookshelfPromises.has(key)) return null;
    const promise = fetchJsonOnce(
      bookshelfApiUrl(),
      { credentials: "include" },
      (payload) => {
        state.bookshelfPayloads.set(key, payload);
        state.bookshelfErrors.delete(key);
        initializeOpenSources(payload, ruleset);
        renderRoute();
        return payload;
      },
      (failure) => {
        state.bookshelfErrors.set(key, failure);
        renderRoute();
      },
      () => state.bookshelfPromises.delete(key),
    );
    state.bookshelfPromises.set(key, promise);
    return promise;
  }

  function normalizeRuleMenuPayload(ruleset, config) {
    if (config.navigation !== "name-source-facets") {
      throw new Error("PF2ER rules menu must use name-source-facets navigation");
    }
    const rawEntries = Array.isArray(config.entries) ? config.entries : [];
    const entries = rawEntries.map((entry) => {
      const id = String(entry?.id || "");
      if (!id) return null;
      return {
        id,
        slug: String(entry.slug || id),
        name: String(entry.name || id),
        seq: Number.isFinite(Number(entry.seq)) ? Number(entry.seq) : null,
      };
    }).filter(Boolean);
    return {
      ruleset: ruleset.id || "",
      name: `${ruleset.family?.title || ""} ${ruleset.title || ""}`.trim(),
      available: true,
      navigation: "name-source-facets",
      entries,
    };
  }

  function fetchRulesMenuConfig(ruleset) {
    if (!ruleset?.id || state.ruleMenuPayloads.has(ruleset.id) || state.ruleMenuPromise) return null;
    state.ruleMenuPromise = fetchJsonOnce(
      "/.static/rules-menu.json",
      {},
      (payload) => {
        const normalized = normalizeRuleMenuPayload(ruleset, payload?.rulesets?.[ruleset.id] || {});
        state.ruleMenuPayloads.set(ruleset.id, normalized);
        state.ruleMenuError = null;
        initializeOpenRules(normalized, ruleset);
        renderRoute();
        return normalized;
      },
      (failure) => {
        state.ruleMenuError = failure;
        renderRoute();
      },
      () => { state.ruleMenuPromise = null; },
    );
    return state.ruleMenuPromise;
  }

  function fetchRulesTargets(ruleset) {
    if (!ruleset?.id || state.ruleTargetPayloads.has(ruleset.id) || state.ruleTargetPromise) return null;
    state.ruleTargetPromise = fetchJsonOnce(
      "/.static/rules-targets.json",
      { cache: "no-store" },
      (payload) => {
        state.ruleTargetPayloads.set(ruleset.id, payload?.rulesets?.[ruleset.id] || { entries: {} });
        state.ruleTargetError = null;
        renderRoute();
      },
      (failure) => {
        state.ruleTargetError = failure;
        renderRoute();
      },
      () => { state.ruleTargetPromise = null; },
    );
    return state.ruleTargetPromise;
  }

  function sourceNodePacketKey(ruleset, rootTarget, selectedLocator) {
    return [ruleset?.id || "", rootTarget?.source || "", rootTarget?.locator || "", selectedLocator || ""].join("|");
  }

  function fetchSourceNodePacket(ruleset, rootTarget, selectedLocator) {
    const key = sourceNodePacketKey(ruleset, rootTarget, selectedLocator);
    if (!ruleset?.id || !rootTarget?.source || !rootTarget?.locator || state.sourceNodePackets.has(key) || state.sourceNodePromises.has(key)) return null;
    const promise = fetchJsonOnce(
      ruleSourceNodeApiUrl(rootTarget, selectedLocator),
      { credentials: "include", cache: "no-store" },
      (payload) => {
        state.sourceNodePackets.set(key, payload);
        state.sourceNodeErrors.delete(key);
        renderRoute();
        return payload;
      },
      (failure) => {
        state.sourceNodeErrors.set(key, failure);
        renderRoute();
      },
      () => state.sourceNodePromises.delete(key),
    );
    state.sourceNodePromises.set(key, promise);
    return promise;
  }

  function fetchPublication(sourceId) {
    const id = String(sourceId || "");
    if (!id || state.publicationPayloads.has(id) || state.publicationPromises.has(id)) return null;
    const promise = fetchJsonOnce(
      publicationApiUrl(id),
      { credentials: "include", cache: "no-store" },
      (payload) => {
        state.publicationPayloads.set(id, payload);
        state.publicationErrors.delete(id);
        renderRoute();
        return payload;
      },
      (failure) => {
        state.publicationErrors.set(id, failure);
        renderRoute();
      },
      () => state.publicationPromises.delete(id),
    );
    state.publicationPromises.set(id, promise);
    return promise;
  }

  function publicationNodePacketKey(sourceId, rootLocator, selectedLocator) {
    return [sourceId || "", rootLocator || "", selectedLocator || ""].join("|");
  }

  function fetchPublicationNode(sourceId, rootLocator, selectedLocator, scope) {
    const key = publicationNodePacketKey(sourceId, rootLocator, selectedLocator);
    if (!sourceId || !rootLocator || !selectedLocator || !scope || state.publicationNodePackets.has(key) || state.publicationNodePromises.has(key)) return null;
    const promise = fetchJsonOnce(
      publicationNodeApiUrl(sourceId, rootLocator, selectedLocator, scope),
      { credentials: "include", cache: "no-store" },
      (payload) => {
        state.publicationNodePackets.set(key, payload);
        state.publicationNodeErrors.delete(key);
        renderRoute();
        return payload;
      },
      (failure) => {
        state.publicationNodeErrors.set(key, failure);
        renderRoute();
      },
      () => state.publicationNodePromises.delete(key),
    );
    state.publicationNodePromises.set(key, promise);
    return promise;
  }

  function readStoredSet(ruleset, name) {
    const stored = safeReadJson(storageKey(ruleset, name), null);
    return Array.isArray(stored) ? new Set(stored.map(String).filter(Boolean)) : null;
  }

  function persistOpenMenuState(ruleset) {
    if (!ruleset?.id) return;
    safeWriteJson(storageKey(ruleset, "open-source-ids"), [...state.openSourceIds].sort());
    safeWriteJson(storageKey(ruleset, "open-rule-ids"), [...state.openRuleIds].sort());
  }

  function initializeOpenSources(payload, ruleset) {
    if (!payload || payload.__ttrpgInitialized) return;
    const stored = readStoredSet(ruleset, "open-source-ids");
    state.openSourceIds = stored || new Set((payload.entries || []).filter((entry) => !entry.parent).map((entry) => String(entry.id)));
    payload.__ttrpgInitialized = true;
  }

  function initializeOpenRules(payload, ruleset) {
    if (!payload || payload.__ttrpgInitialized) return;
    const stored = readStoredSet(ruleset, "open-rule-ids");
    state.openRuleIds = stored || new Set((payload.entries || []).filter((entry) => !entry.parent).map((entry) => String(entry.id)));
    if (state.activeRuleFamilyId) state.openRuleIds.add(state.activeRuleFamilyId);
    if (state.activeRuleFamilyId && state.activeRuleFacet) state.openRuleIds.add(`${state.activeRuleFamilyId}--by-${state.activeRuleFacet}`);
    const parts = String(state.activeRuleId || "").split("-").filter(Boolean);
    for (let index = 1; index < parts.length; index += 1) state.openRuleIds.add(parts.slice(0, index).join("-"));
    payload.__ttrpgInitialized = true;
  }

  function sourceEntriesByParent(payload) {
    const byParent = new Map();
    for (const entry of Array.isArray(payload?.entries) ? payload.entries : []) {
      const parent = String(entry.parent || "");
      if (!byParent.has(parent)) byParent.set(parent, []);
      byParent.get(parent).push(entry);
    }
    for (const children of byParent.values()) children.sort(sourceSiblingCompare);
    return byParent;
  }

  function sourceNode(entry, childrenByParent, ruleset, depth = 0) {
    const id = String(entry.id || "");
    const children = childrenByParent.get(id) || [];
    const label = String(entry.name || id);
    const date = state.showSourceDates ? formatSourceDate(entry.date) : "";
    if (children.length) {
      return {
        id,
        label,
        labelHtml: `<span class="ttrpg-source-menu__label">${escapeHtml(label)}</span>`,
        metaHtml: date ? `<span class="ttrpg-source-menu__date">${escapeHtml(date)}</span>` : "",
        selectable: false,
        expandable: true,
        open: state.openSourceIds.has(id),
        className: depth === 0 ? "ttrpg-source-menu__section" : "ttrpg-source-menu__group",
        rowClass: `ttrpg-source-menu__branch-row ttrpg-source-menu__branch-row--depth-${Math.min(depth, 1)}`,
        targetClass: "ttrpg-source-menu__branch-target",
        markerClass: "ttrpg-source-menu__marker",
        childrenClass: "ttrpg-source-menu__children",
        toggleRawAttrs: "data-ttrpg-source-toggle",
        children: children.map((child) => sourceNode(child, childrenByParent, ruleset, depth + 1)),
      };
    }
    const enabled = enabledSourcesForRuleset(ruleset).has(id);
    const mandatory = sourceIsMandatory(ruleset, id);
    return {
      id,
      label,
      labelHtml: `<span class="ttrpg-source-menu__label">${escapeHtml(label)}</span>`,
      metaHtml: date ? `<span class="ttrpg-source-menu__date">${escapeHtml(date)}</span>` : "",
      active: state.activeSourceId === id,
      rowClass: "ttrpg-source-menu__leaf-row",
      targetClass: "ttrpg-source-menu__leaf-target",
      markerClass: "ttrpg-source-menu__marker",
      markerAction: "bookmark",
      markerActive: enabled,
      markerLabel: mandatory ? `${label} is always enabled` : `${enabled ? "Disable" : "Enable"} ${label}`,
      markerAttrs: { "data-ttrpg-source-marker": id, "data-ttrpg-source-mandatory": mandatory ? "1" : "0" },
      selectTag: "button",
      targetAttrs: { "data-ttrpg-source-id": id },
    };
  }

  function ruleTargetEntries(ruleset) {
    const entries = state.ruleTargetPayloads.get(ruleset?.id || "")?.entries;
    return entries && typeof entries === "object" && !Array.isArray(entries) ? entries : null;
  }

  function ruleTargets(ruleset, ruleId) {
    const values = ruleTargetEntries(ruleset)?.[String(ruleId || "")];
    return Array.isArray(values)
      ? values.map((target) => ({ source: String(target?.source || ""), locator: String(target?.locator || "") })).filter((target) => target.source && target.locator)
      : [];
  }

  function enabledRuleTargets(ruleset, ruleId) {
    const enabled = enabledSourcesForRuleset(ruleset);
    return ruleTargets(ruleset, ruleId).filter((target) => enabled.has(target.source));
  }

  function ruleNameCompare(left, right) {
    const alphabeticKey = (entry) => String(entry?.name || entry?.id || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "");
    return alphabeticKey(left).localeCompare(
      alphabeticKey(right),
      undefined,
      { numeric: true },
    ) || String(left?.id || "").localeCompare(String(right?.id || ""));
  }

  function sourcePublicationCompare(left, right) {
    const publicationDate = (entry) => {
      const value = String(entry?.date || "").trim();
      return !value || value.startsWith("0000-") ? "" : value;
    };
    const leftDate = publicationDate(left);
    const rightDate = publicationDate(right);
    if (leftDate && rightDate && leftDate !== rightDate) return leftDate.localeCompare(rightDate);
    if (leftDate !== rightDate) return leftDate ? -1 : 1;
    return sourceNameCompare(left, right);
  }

  function pf2erTargetableRuleEntries(ruleset, familyId, enabledOnly = false) {
    if (!pf2erRuleFamilyById.has(String(familyId || ""))) return [];
    const payload = currentRulePayload(ruleset);
    const prefix = `${familyId}-`;
    return (payload?.entries || [])
      .filter((entry) => (entry.id === familyId || String(entry.id || "").startsWith(prefix)))
      .filter((entry) => ruleTargets(ruleset, entry.id).length)
      .filter((entry) => !enabledOnly || enabledRuleTargets(ruleset, entry.id).length)
      .sort(ruleNameCompare);
  }

  function pf2erFamilySources(ruleset, familyId) {
    const enabled = enabledSourcesForRuleset(ruleset);
    const sourceIds = new Set();
    for (const entry of pf2erTargetableRuleEntries(ruleset, familyId)) {
      for (const target of ruleTargets(ruleset, entry.id)) {
        if (enabled.has(target.source)) sourceIds.add(target.source);
      }
    }
    const sources = sourceEntriesById(ruleset);
    return [...sourceIds]
      .map((id) => sources.get(id) || { id, name: id, date: "" })
      .sort(sourcePublicationCompare);
  }

  function ruleNode(entry, depth = 0) {
    const id = String(entry.id || "");
    const children = Array.isArray(entry.children) ? entry.children : [];
    const label = String(entry.name || id);
    const ruleId = String(entry.ruleId || "");
    const sourceId = String(entry.sourceId || "");
    const familyId = String(entry.familyId || "");
    const facet = String(entry.facet || "");
    let active = false;
    let targetAttrs = {};
    if (ruleId) {
      active = state.activeRuleFacet === "name" && state.activeRuleFamilyId === familyId && state.activeRuleId === ruleId;
      targetAttrs = {
        "data-ttrpg-rule-name-id": ruleId,
        "data-ttrpg-rule-family-id": familyId,
      };
    } else if (sourceId) {
      active = state.activeRuleFacet === "source" && state.activeRuleFamilyId === familyId && state.activeRuleSourceId === sourceId;
      targetAttrs = {
        "data-ttrpg-rule-source-id": sourceId,
        "data-ttrpg-rule-family-id": familyId,
      };
    } else if (entry.synthetic) {
      active = state.activeRuleFamilyId === familyId && (!facet || state.activeRuleFacet === facet);
      targetAttrs = {};
    }
    const selectable = Boolean(ruleId || sourceId);
    const common = {
      id,
      label,
      labelHtml: `<span class="ttrpg-source-menu__label">${escapeHtml(label)}</span>`,
      active,
      selectable,
      selectTag: selectable ? "button" : undefined,
      targetAttrs,
    };
    if (!children.length) return { ...common, rowClass: "ttrpg-source-menu__leaf-row", targetClass: "ttrpg-source-menu__leaf-target", markerClass: "ttrpg-source-menu__marker" };
    return {
      ...common,
      expandable: true,
      open: state.openRuleIds.has(id),
      className: depth === 0 ? "ttrpg-source-menu__section" : "ttrpg-source-menu__group",
      rowClass: `ttrpg-source-menu__branch-row ttrpg-source-menu__branch-row--depth-${Math.min(depth, 1)}`,
      targetClass: "ttrpg-source-menu__branch-target",
      markerClass: "ttrpg-source-menu__marker",
      childrenClass: "ttrpg-source-menu__children",
      toggleRawAttrs: "data-ttrpg-rule-toggle",
      children: children.map((child) => ruleNode(child, depth + 1)),
    };
  }

  function pf2erRuleFacetTree(ruleset) {
    return pf2erRuleFamilies.map((family) => {
      const rules = pf2erTargetableRuleEntries(ruleset, family.id, true);
      const sources = pf2erFamilySources(ruleset, family.id);
      if (!rules.length && !sources.length) return null;
      return {
        id: family.id,
        name: family.name,
        familyId: family.id,
        synthetic: true,
        children: [
          {
            id: `${family.id}--by-name`,
            name: "By Name",
            familyId: family.id,
            facet: "name",
            synthetic: true,
            children: rules.map((entry) => ({
              id: `${family.id}--name--${entry.id}`,
              name: entry.name,
              familyId: family.id,
              facet: "name",
              ruleId: entry.id,
            })),
          },
          {
            id: `${family.id}--by-source`,
            name: "By Source",
            familyId: family.id,
            facet: "source",
            synthetic: true,
            children: sources.map((source) => ({
              id: `${family.id}--source--${source.id}`,
              name: source.name || source.id,
              familyId: family.id,
              facet: "source",
              sourceId: source.id,
            })),
          },
        ],
      };
    }).filter(Boolean);
  }

  function renderCategorySelect() {
    return `<label class="ttrpg-category-control"><span class="sr-only">Section</span><select class="ttrpg-category-select" data-ttrpg-category-select>${navCategories.map((category) => `<option value="${category}" ${state.activeCategory === category ? "selected" : ""}>${escapeHtml(categoryLabel(category))}</option>`).join("")}</select></label>`;
  }

  function rulesetNavSettingsOptions() {
    const options = [
      { kind: "toggle", label: "Wrap Lines", active: state.wrapSourceNames, attrs: { "data-ttrpg-nav-preference": "wrap-lines" } },
    ];
    if (state.activeCategory === "sources") options.push(
      { kind: "toggle", label: "Metadata", active: state.showSourceDates, attrs: { "data-ttrpg-nav-preference": "metadata" } },
      { kind: "cycle", label: "Sorting", value: sourceSortValueLabel(state.sourceSort), choices: sourceSortModes.map((mode) => ({ label: sourceSortValueLabel(mode), value: mode, active: state.sourceSort === mode })), attrs: { "data-ttrpg-source-sort-cycle": true } },
    );
    return options;
  }

  function renderRulesetNavSettings() {
    return `<div class="kmqdb-menu__settings ttrpg-source-bar__settings" data-ttrpg-nav-settings ${state.sourceMenuSettingsOpen ? "" : "hidden"}>${window.kmqdbMenu.renderSettingsOptions(rulesetNavSettingsOptions())}</div>`;
  }

  function renderRulesetNavSettingsButton() {
    return `<button class="kmqdb-shell-bar__gear ttrpg-source-menu__config-control ${state.sourceMenuSettingsOpen ? "is-open" : ""}" type="button" title="${escapeHtml(`${categoryLabel(state.activeCategory)} settings`)}" aria-label="${escapeHtml(`${categoryLabel(state.activeCategory)} settings`)}" aria-expanded="${state.sourceMenuSettingsOpen ? "true" : "false"}" data-kmqdb-menu-settings-toggle>${window.kmqdbMenu.renderGearIcon()}</button>`;
  }

  function renderRulesetSourceBar() {
    return `<header class="kmqdb-shell-bar ttrpg-source-bar" data-kmqdb-workspace-slot="secondary-bar"><button class="kmqdb-shell-bar__button kmqdb-shell-bar__button--open" type="button" title="Open ${escapeHtml(categoryLabel(state.activeCategory))}" aria-label="Open ${escapeHtml(categoryLabel(state.activeCategory))}" data-kmqdb-workspace-open="secondary">${window.kmqdbWorkspace.openIcon()}</button><button class="kmqdb-shell-bar__button kmqdb-shell-bar__button--close" type="button" title="Collapse ${escapeHtml(categoryLabel(state.activeCategory))}" aria-label="Collapse ${escapeHtml(categoryLabel(state.activeCategory))}" data-kmqdb-workspace-close="secondary">${window.kmqdbWorkspace.closeIcon()}</button><div class="ttrpg-source-bar__control">${renderCategorySelect()}</div>${renderRulesetNavSettingsButton()}${renderRulesetNavSettings()}</header>`;
  }

  function renderRulesetSourceDrawerBar() {
    return `<header class="kmqdb-shell-bar ttrpg-source-bar ttrpg-source-bar--drawer" data-kmqdb-workspace-drawer-bar="secondary"><button class="kmqdb-shell-bar__button kmqdb-shell-bar__button--close" type="button" title="Close ${escapeHtml(categoryLabel(state.activeCategory))}" aria-label="Close ${escapeHtml(categoryLabel(state.activeCategory))}" data-kmqdb-workspace-close="secondary">${window.kmqdbWorkspace.closeIcon()}</button><div class="ttrpg-source-bar__control">${renderCategorySelect()}</div>${renderRulesetNavSettingsButton()}${renderRulesetNavSettings()}</header>`;
  }

  function renderSourceMenuBody(ruleset) {
    if (!ruleset?.id) return `<p class="ttrpg-source-menu__empty">No source list is configured for this ruleset.</p>`;
    const payload = state.bookshelfPayloads.get(ruleset.id);
    if (state.bookshelfErrors.has(ruleset.id)) return `<p class="ttrpg-source-menu__empty">Source list unavailable.</p>`;
    if (!payload) {
      fetchBookshelf(ruleset);
      return `<p class="ttrpg-source-menu__empty">Loading sources...</p>`;
    }
    const byParent = sourceEntriesByParent(payload);
    const nodes = (byParent.get("") || []).map((entry) => sourceNode(entry, byParent, ruleset));
    return nodes.length ? nodes.map((node) => window.kmqdbMenu.renderNode(node, 0, { stickyLevels: 2 })).join("") : `<p class="ttrpg-source-menu__empty">No sources found.</p>`;
  }

  function currentRulePayload(ruleset) {
    return state.ruleMenuPayloads.get(ruleset?.id || "") || null;
  }

  function currentRuleEntry(ruleset) {
    return (currentRulePayload(ruleset)?.entries || []).find((entry) => String(entry.id || "") === state.activeRuleId) || null;
  }

  function renderRulesMenuBody(ruleset) {
    if (!ruleset?.id) return `<p class="ttrpg-source-menu__empty">No rules list is configured for this ruleset.</p>`;
    const payload = currentRulePayload(ruleset);
    if (!payload) {
      if (state.ruleMenuError) return `<p class="ttrpg-source-menu__empty">Rules menu unavailable.</p>`;
      fetchRulesMenuConfig(ruleset);
      return `<p class="ttrpg-source-menu__empty">Loading rules menu...</p>`;
    }
    if (!ruleTargetEntries(ruleset)) {
      if (state.ruleTargetError) return `<p class="ttrpg-source-menu__empty">Rules targets unavailable.</p>`;
      fetchRulesTargets(ruleset);
      return `<p class="ttrpg-source-menu__empty">Loading rule targets...</p>`;
    }
    if (state.bookshelfErrors.has(ruleset.id)) return `<p class="ttrpg-source-menu__empty">Source metadata unavailable.</p>`;
    if (!state.bookshelfPayloads.has(ruleset.id)) {
      fetchBookshelf(ruleset);
      return `<p class="ttrpg-source-menu__empty">Loading source metadata...</p>`;
    }
    const roots = pf2erRuleFacetTree(ruleset);
    return roots.length ? roots.map((entry) => window.kmqdbMenu.renderNode(ruleNode(entry), 0, { stickyLevels: 2 })).join("") : `<p class="ttrpg-source-menu__empty">No rule entries are available for the selected sources.</p>`;
  }

  function renderRulesetNavPanel(ruleset) {
    const body = state.activeCategory === "sources"
      ? renderSourceMenuBody(ruleset)
      : state.activeCategory === "rules"
        ? renderRulesMenuBody(ruleset)
        : `<p class="ttrpg-source-menu__empty">${escapeHtml(categoryLabel(state.activeCategory))} menu items will live here.</p>`;
    return window.kmqdbMenu.renderPanel({
      kind: "ttrpg-sources",
      className: `ttrpg-source-menu ${state.wrapSourceNames ? "" : "ttrpg-source-menu--truncate"}`,
      ariaLabel: `${ruleset.family.title} ${ruleset.title} menu`,
      beforeHeader: renderRulesetSourceDrawerBar(),
      showHeader: false,
      scrollClass: "ttrpg-source-menu__scroll",
      bodyClass: "ttrpg-source-menu__body",
      bodyHtml: body,
      stickyLevels: 2,
    });
  }

  function sourceEntriesById(ruleset) {
    return new Map((state.bookshelfPayloads.get(ruleset?.id || "")?.entries || []).map((entry) => [String(entry.id || ""), entry]));
  }

  function sourceSummaryList(ruleset) {
    const entries = sourceEntriesById(ruleset);
    return [...enabledSourcesForRuleset(ruleset)].map((id) => entries.get(id) || { id, name: id, date: "" }).sort(sourceSiblingCompare);
  }

  function ruleTargetsByPublication(ruleset, targets) {
    const sources = sourceEntriesById(ruleset);
    return [...targets].sort((left, right) => sourcePublicationCompare(
      sources.get(left.source) || { id: left.source, name: left.source, date: "" },
      sources.get(right.source) || { id: right.source, name: right.source, date: "" },
    ));
  }

  function selectedRuleContext(ruleset) {
    if (state.activeRuleFacet && !state.bookshelfPayloads.has(ruleset.id)) {
      fetchBookshelf(ruleset);
      return { rule: null, targets: [], loading: true, message: "Loading source metadata..." };
    }
    const rule = currentRuleEntry(ruleset);
    if (!rule) {
      const message = state.activeRuleFacet === "source"
        ? "Select an entry from Active Sources."
        : "Select a rule entry from the navigation.";
      return { rule: null, targets: [], error: message };
    }
    const targets = ruleTargetsByPublication(ruleset, enabledRuleTargets(ruleset, rule.id));
    if (!targets.length) {
      return { rule, targets, error: "No exact source target is available for the selected publications." };
    }
    let rootTarget = null;
    if (state.activeRuleSourceId) {
      rootTarget = targets.find((target) => target.source === state.activeRuleSourceId) || null;
      if (!rootTarget) return { rule, targets, error: `The route source ${state.activeRuleSourceId} is not mapped to this rule entry.` };
    } else {
      rootTarget = targets[0];
    }
    const selectedLocator = state.activeRuleLocator || rootTarget.locator;
    if (!state.activeRuleSourceId || !state.activeRuleLocator) {
      state.activeRuleSourceId = rootTarget.source;
      state.activeRuleLocator = selectedLocator;
      replaceAppRoute(pf2erStateHref("rules", rootTarget.source, selectedLocator));
    }
    const key = sourceNodePacketKey(ruleset, rootTarget, selectedLocator);
    const packet = state.sourceNodePackets.get(key);
    const failure = state.sourceNodeErrors.get(key);
    if (!packet && !failure) fetchSourceNodePacket(ruleset, rootTarget, selectedLocator);
    return { rule, targets, rootTarget, selectedLocator, packet, failure, key };
  }

  function renderedSourceNodeView(ruleset) {
    const context = selectedRuleContext(ruleset);
    if (context.loading) return { ...context, status: "loading" };
    if (context.error) return { ...context, status: "error", message: context.error };
    if (context.failure) return { ...context, status: "error", message: context.failure.message || "The exact source target is unavailable." };
    if (!context.packet) return { ...context, status: "loading", message: "Loading exact source node..." };
    if (state.rendererInterfaceError) return { ...context, status: "error", message: state.rendererInterfaceError.message };
    if (!window.KMQDB_RULESET_RENDERER?.renderSourceNodeView) {
      loadSourceInterface(context.packet);
      return { ...context, status: "loading", message: "Loading source view..." };
    }
    try {
      const view = window.KMQDB_RULESET_RENDERER.renderSourceNodeView(context.packet, {
        assetOrigin: window.location.origin,
        selectedLocator: context.selectedLocator,
      });
      return { ...context, status: "ready", view };
    } catch (failure) {
      console.warn("Unable to render exact source node", failure);
      return { ...context, status: "error", message: failure.message || "The source node could not be rendered." };
    }
  }

  function publicationNodeMatches(nodes, locator, root = null, matches = []) {
    for (const node of Array.isArray(nodes) ? nodes : []) {
      if (!node || node.kind === "overview") continue;
      const top = root || node;
      if (String(node.locator || "") === locator) matches.push({ node, root: top });
      publicationNodeMatches(node.children, locator, top, matches);
    }
    return matches;
  }

  function selectedPublicationContext() {
    const sourceId = state.activeSourceId;
    if (!sourceId) return { status: "empty", message: "Select a publication source." };
    const publication = state.publicationPayloads.get(sourceId);
    const publicationFailure = state.publicationErrors.get(sourceId);
    if (publicationFailure) return { status: "error", message: publicationFailure.message || "The publication is unavailable." };
    if (!publication) {
      fetchPublication(sourceId);
      return { status: "loading", message: "Loading publication..." };
    }
    if (!state.activeSourceLocator) return { status: "overview", publication };
    const matches = publicationNodeMatches(publication.toc, state.activeSourceLocator);
    if (!matches.length) return { status: "error", publication, message: `Source locator not found: ${state.activeSourceLocator}` };
    if (matches.length !== 1) return { status: "error", publication, message: `Source locator is ambiguous: ${state.activeSourceLocator}` };
    const { node, root } = matches[0];
    const rootLocator = String(root.locator || "");
    if (!rootLocator) return { status: "error", publication, message: "The publication section has no content target." };
    const key = publicationNodePacketKey(sourceId, rootLocator, state.activeSourceLocator);
    const packet = state.publicationNodePackets.get(key);
    const failure = state.publicationNodeErrors.get(key);
    if (!packet && !failure) fetchPublicationNode(sourceId, rootLocator, state.activeSourceLocator, publication.scope);
    const context = {
      publication,
      node,
      root,
      rootLocator,
      selectedLocator: state.activeSourceLocator,
      packet,
      failure,
      key,
    };
    if (failure) return { ...context, status: "error", message: failure.message || "The exact source target is unavailable." };
    if (!packet) return { ...context, status: "loading", message: "Loading publication content..." };
    if (state.rendererInterfaceError) return { ...context, status: "error", message: state.rendererInterfaceError.message };
    if (!window.KMQDB_RULESET_RENDERER?.renderSourceNodeView) {
      loadSourceInterface(packet);
      return { ...context, status: "loading", message: "Loading source view..." };
    }
    try {
      const view = window.KMQDB_RULESET_RENDERER.renderSourceNodeView(packet, {
        assetOrigin: window.location.origin,
        selectedLocator: state.activeSourceLocator,
      });
      return { ...context, status: "ready", view };
    } catch (failure) {
      console.warn("Unable to render publication node", failure);
      return { ...context, status: "error", message: failure.message || "The publication node could not be rendered." };
    }
  }

  function renderSourceTargetChooser(ruleset, context) {
    if (!context?.targets?.length || context.targets.length < 2) return "";
    const sources = sourceEntriesById(ruleset);
    return `<div class="ttrpg-source-targets" aria-label="Mapped sources">${context.targets.map((target) => `<button type="button" class="ttrpg-source-targets__button ${target.source === context.rootTarget?.source ? "is-active" : ""}" data-ttrpg-rule-source-target="${escapeHtml(target.source)}" data-ttrpg-rule-root-locator="${escapeHtml(target.locator)}">${escapeHtml(sources.get(target.source)?.name || target.source)}</button>`).join("")}</div>`;
  }

  function activeRuleChoiceNode(id, label, active, attrs) {
    return {
      id,
      label,
      labelHtml: `<span>${escapeHtml(label)}</span>`,
      active,
      rowClass: "ttrpg-active-sources__source-row",
      targetClass: "ttrpg-active-sources__source-target",
      markerClass: "ttrpg-active-sources__source-marker",
      selectTag: "button",
      targetAttrs: attrs,
    };
  }

  function renderActiveRuleChoices(nodes, summary, emptyMessage) {
    const body = nodes.length
      ? nodes.map((node) => window.kmqdbMenu.renderNode(node)).join("")
      : `<p class="ttrpg-active-sources__empty">${escapeHtml(emptyMessage)}</p>`;
    return `<section class="ttrpg-active-sources__menu"><header class="ttrpg-active-sources__header"><h3>Active Sources</h3><p>${escapeHtml(summary)}</p></header><div class="ttrpg-active-sources__scroll"><div class="ttrpg-active-sources__body">${body}</div></div></section>`;
  }

  function renderPf2erActiveRuleChoices(ruleset, sourceNodeContext = null) {
    if (state.activeRuleFacet === "name") {
      const context = sourceNodeContext || renderedSourceNodeView(ruleset);
      const chooser = renderSourceTargetChooser(ruleset, context);
      if (context.status !== "ready") return `${chooser}<section class="ttrpg-active-sources__menu"><header class="ttrpg-active-sources__header"><h3>Active Sources</h3></header><p class="ttrpg-active-sources__status">${escapeHtml(context.message || "")}</p></section>`;
      return `${chooser}${context.view.navigationHtml}`;
    }
    if (state.activeRuleFacet === "source") {
      const sources = sourceEntriesById(ruleset);
      const sourceId = state.activeRuleSourceId;
      if (!sourceId) return renderActiveRuleChoices([], "By Source", "Select a publication source.");
      const entries = pf2erTargetableRuleEntries(ruleset, state.activeRuleFamilyId)
        .map((entry) => ({
          entry,
          target: ruleTargets(ruleset, entry.id).find((target) => target.source === sourceId),
        }))
        .filter((item) => item.target)
        .sort((left, right) => ruleNameCompare(left.entry, right.entry));
      const nodes = entries.map(({ entry, target }) => activeRuleChoiceNode(
        `active-rule--${entry.id}`,
        entry.name || entry.id,
        state.activeRuleId === entry.id,
        {
          "data-ttrpg-active-rule-id": entry.id,
          "data-ttrpg-active-rule-locator": target.locator,
        },
      ));
      const sourceName = sources.get(sourceId)?.name || sourceId;
      return renderActiveRuleChoices(nodes, `${sourceName} · ${nodes.length} ${nodes.length === 1 ? "entry" : "entries"}`, "This source has no entries in the selected rule family.");
    }
    return renderActiveRuleChoices([], "Rules", "Choose By Name or By Source.");
  }

  function publicationMenuNode(sourceId, node, activeRootLocator = "") {
    const locator = String(node?.locator || "");
    const overview = node?.kind === "overview";
    const id = overview ? `${sourceId}:overview` : `${sourceId}:${locator || node?.label || "section"}`;
    const selectable = overview || !!locator;
    return {
      id,
      label: String(node?.label || locator || "Section"),
      active: overview
        ? !state.activeSourceLocator
        : state.activeSourceLocator === locator || activeRootLocator === locator,
      selectable,
      selectTag: selectable ? "button" : "span",
      expandable: false,
      open: false,
      rowClass: "ttrpg-active-sources__source-row ttrpg-publication-toc__row",
      targetClass: "ttrpg-active-sources__source-target ttrpg-publication-toc__target",
      markerClass: "ttrpg-active-sources__source-marker",
      targetAttrs: selectable ? {
        "data-ttrpg-publication-source": sourceId,
        "data-ttrpg-publication-locator": locator,
        "data-ttrpg-publication-root": locator,
        "data-ttrpg-publication-overview": overview ? "1" : "0",
      } : {},
      children: [],
    };
  }

  function renderPublicationContents(context) {
    const publication = context?.publication || state.publicationPayloads.get(state.activeSourceId);
    if (!state.activeSourceId) {
      return `<section class="ttrpg-active-sources__menu ttrpg-publication-toc"><header class="ttrpg-active-sources__header"><h3>Contents</h3></header><p class="ttrpg-active-sources__empty">Select a publication source.</p></section>`;
    }
    if (!publication) {
      const message = context?.status === "error" ? context.message : "Loading publication...";
      return `<section class="ttrpg-active-sources__menu ttrpg-publication-toc"><header class="ttrpg-active-sources__header"><h3>Contents</h3></header><p class="ttrpg-active-sources__status">${escapeHtml(message)}</p></section>`;
    }
    const activeRootLocator = String(context?.rootLocator || "");
    const nodes = (Array.isArray(publication.toc) ? publication.toc : [])
      .map((node) => publicationMenuNode(state.activeSourceId, node, activeRootLocator));
    const sourceName = publication.source?.name || state.activeSourceId;
    return `<section class="ttrpg-active-sources__menu ttrpg-publication-toc"><header class="ttrpg-active-sources__header"><h3>Contents</h3><p>${escapeHtml(sourceName)}</p></header><div class="ttrpg-active-sources__scroll"><div class="ttrpg-active-sources__body">${nodes.map((node) => window.kmqdbMenu.renderNode(node)).join("")}</div></div></section>`;
  }

  function renderActiveSourcesPanel(ruleset, context = null) {
    if (state.activeCategory === "sources") return renderPublicationContents(context);
    if (state.activeCategory === "rules") return renderPf2erActiveRuleChoices(ruleset, context);
    return `<section class="ttrpg-active-sources__menu"><header class="ttrpg-active-sources__header"><h3>${escapeHtml(categoryLabel(state.activeCategory))}</h3></header><p class="ttrpg-active-sources__empty">Nothing selected.</p></section>`;
  }

  function publicationDescriptionParagraphs(value) {
    return String(value || "").split(/\n\s*\n/).map((paragraph) => paragraph.trim()).filter(Boolean);
  }

  function renderPublicationOverview(publication) {
    const source = publication?.source || {};
    const meta = source.meta && typeof source.meta === "object" ? source.meta : {};
    const details = [
      ["Published", String(source.date || "").split(".", 1)[0]],
      ["SKU", source.sku],
      ["ISBN", source.isbn],
      ["Pages", source.pages],
    ].filter((entry) => entry[1] !== null && entry[1] !== undefined && String(entry[1]).trim());
    const description = publicationDescriptionParagraphs(meta.description);
    return `<article class="ttrpg-publication-overview"><figure class="ttrpg-publication-overview__cover"><img src="${escapeHtml(source.cover || "")}" alt="${escapeHtml(`${source.name || source.id || "Publication"} cover`)}" loading="eager" decoding="async"></figure><div class="ttrpg-publication-overview__body"><p class="ttrpg-publication-overview__eyebrow">Overview</p><h3>${escapeHtml(source.name || source.id || "Publication")}</h3>${details.length ? `<dl>${details.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>` : ""}<div class="ttrpg-publication-overview__description">${description.length ? description.map((paragraph) => `<p>${escapeHtml(paragraph).replaceAll("\n", "<br>")}</p>`).join("") : `<p>No overview is available for this publication.</p>`}</div></div></article>`;
  }

  function renderWorkspaceContent(ruleset, context = null) {
    if (state.activeCategory === "sources") {
      const publicationContext = context || selectedPublicationContext();
      if (publicationContext.status === "overview") return renderPublicationOverview(publicationContext.publication);
      if (publicationContext.status !== "ready") return `<section class="ttrpg-workspace__panel"><p class="ttrpg-workspace__${publicationContext.status === "error" ? "empty" : "meta"}">${escapeHtml(publicationContext.message || "Select a publication source.")}</p></section>`;
      return publicationContext.view.contentHtml;
    }
    if (state.activeCategory !== "rules") return `<p>${escapeHtml(categoryLabel(state.activeCategory))} content will live here.</p>`;
    const ruleContext = context || renderedSourceNodeView(ruleset);
    if (ruleContext.status !== "ready") return `<section class="ttrpg-workspace__panel"><p class="ttrpg-workspace__${ruleContext.status === "error" ? "empty" : "meta"}">${escapeHtml(ruleContext.message || "")}</p></section>`;
    return ruleContext.view.contentHtml;
  }

  function workspaceHeader(ruleset, context = null) {
    if (state.activeCategory === "sources" && state.activeSourceId) {
      const publication = context?.publication || state.publicationPayloads.get(state.activeSourceId);
      const source = publication?.source || sourceEntriesById(ruleset).get(state.activeSourceId) || { name: state.activeSourceId };
      if (state.activeSourceLocator) {
        const match = publicationNodeMatches(publication?.toc, state.activeSourceLocator)[0];
        return {
          eyebrow: `Sources / ${source.name || state.activeSourceId}`,
          title: String(match?.node?.label || state.activeSourceLocator),
        };
      }
      return { eyebrow: "Sources / Overview", title: String(source.name || state.activeSourceId) };
    }
    if (state.activeCategory === "rules") {
      const entry = currentRuleEntry(ruleset);
      if (state.activeRuleFamilyId) {
        const family = pf2erRuleFamilyById.get(state.activeRuleFamilyId);
        const facetName = state.activeRuleFacet === "name" ? "By Name" : state.activeRuleFacet === "source" ? "By Source" : "";
        const source = sourceEntriesById(ruleset).get(state.activeRuleSourceId);
        const eyebrow = ["Rules", family?.name, facetName];
        if (state.activeRuleFacet === "source" && source) eyebrow.push(source.name || source.id);
        return {
          eyebrow: eyebrow.filter(Boolean).join(" / "),
          title: String(entry?.name || (state.activeRuleFacet === "source" && source?.name) || family?.name || "Rules"),
        };
      }
    }
    return { eyebrow: categoryLabel(state.activeCategory), title: `${ruleset.family.title} ${ruleset.title}` };
  }

  function updateActiveRuleSelectionInPlace(ruleset, control) {
    const menu = control?.closest?.(".ttrpg-active-sources");
    menu?.querySelectorAll?.("[data-ttrpg-active-rule-id].is-active").forEach((element) => element.classList.remove("is-active"));
    menu?.querySelectorAll?.("[data-kmqdb-menu-node].is-active").forEach((element) => element.classList.remove("is-active"));
    control?.classList?.add("is-active");
    control?.closest?.("[data-kmqdb-menu-node]")?.classList.add("is-active");
    const header = workspaceHeader(ruleset);
    const headerElement = app.querySelector(".ttrpg-workspace__header");
    const eyebrowElement = headerElement?.querySelector("p");
    const titleElement = headerElement?.querySelector("h2");
    if (eyebrowElement) eyebrowElement.textContent = header.eyebrow;
    if (titleElement) titleElement.textContent = header.title;
    app.querySelector(".ttrpg-workspace__content")?.setAttribute("aria-label", `${header.title} content`);
  }

  function renderRulesetTopbar() {
    return `<header class="kmqdb-shell-bar ttrpg-appbar" data-kmqdb-workspace-slot="primary-bar"><span class="ttrpg-appbar__spacer" aria-hidden="true"></span><a class="kmqdb-shell-bar__brand ttrpg-appbar__home" href="/" data-route>TTRPG</a><span class="kmqdb-shell-bar__auth" aria-hidden="true"></span></header>`;
  }

  function renderRulesetLogo(ruleset) {
    return `<header class="ttrpg-ruleset-logo" aria-labelledby="ruleset-title" data-kmqdb-workspace-slot="secondary-title"><h1 id="ruleset-title" class="ttrpg-ruleset-logo__title">${escapeHtml(ruleset.family.title)}</h1><p class="ttrpg-ruleset-logo__version">${escapeHtml(ruleset.title)}</p></header>`;
  }

  function renderRulesetShell(ruleset) {
    const context = state.activeCategory === "rules"
      ? renderedSourceNodeView(ruleset)
      : state.activeCategory === "sources"
        ? selectedPublicationContext()
        : null;
    const header = workspaceHeader(ruleset, context);
    const middleLabel = state.activeCategory === "sources" ? "Publication contents" : "Active sources";
    return `<section class="ttrpg-ruleset ttrpg-ruleset-shell" data-kmqdb-workspace-key="kmqdb.ttrpg.workspace">${renderRulesetTopbar()}${renderRulesetLogo(ruleset)}${renderRulesetSourceBar()}<aside class="ttrpg-sidebar" aria-label="TTRPG navigation" data-kmqdb-workspace-slot="secondary-panel">${renderRulesetNavPanel(ruleset)}</aside><div class="ttrpg-sidebar-splitter" role="separator" tabindex="0" aria-label="Resize TTRPG navigation" aria-orientation="vertical" data-kmqdb-workspace-divider="secondary"></div><main class="ttrpg-workspace" aria-label="${escapeHtml(categoryLabel(state.activeCategory))}" data-kmqdb-workspace-slot="detail"><header class="ttrpg-workspace__header"><button class="ttrpg-workspace__context-open" type="button" title="Open ${middleLabel}" aria-label="Open ${middleLabel}" data-kmqdb-workspace-open="context">${window.kmqdbWorkspace.openIcon()}</button><div><p>${escapeHtml(header.eyebrow)}</p><h2>${escapeHtml(header.title)}</h2></div></header><div class="ttrpg-workspace__body" data-kmqdb-workspace-split><aside class="ttrpg-active-sources" aria-label="${middleLabel}" data-kmqdb-workspace-slot="context-panel"><button class="ttrpg-active-sources__close" type="button" title="Collapse ${middleLabel}" aria-label="Collapse ${middleLabel}" data-kmqdb-workspace-close="context">${window.kmqdbWorkspace.closeIcon()}</button>${renderActiveSourcesPanel(ruleset, context)}</aside><div class="ttrpg-context-splitter" role="separator" tabindex="0" aria-label="Resize ${middleLabel}" aria-orientation="vertical" data-kmqdb-workspace-divider="context"></div><section class="ttrpg-workspace__content" aria-label="${escapeHtml(header.title)} content" data-kmqdb-workspace-slot="content">${renderWorkspaceContent(ruleset, context)}</section></div></main></section>`;
  }

  function destroyWorkspace() {
    workspaceController?.destroy();
    workspaceController = null;
  }

  function activateWorkspace() {
    const shell = app.querySelector(".ttrpg-ruleset-shell");
    workspaceController = window.kmqdbWorkspace.create(shell, {
      key: "kmqdb.ttrpg.workspace",
      widths: {
        secondary: {
          property: "--kmqdb-workspace-secondary-width",
          storageKey: "kmqdb:ttrpg:workspace:source-width",
          minimum: 304,
          reserve: 420,
          fallback: 368,
        },
        context: {
          property: "--kmqdb-workspace-context-width",
          storageKey: "kmqdb:ttrpg:workspace:context-width",
          minimum: 224,
          reserve: 420,
          fallback: 320,
        },
      },
    });
  }

  function activateRenderedSourceNodeView() {
    const activation = window.KMQDB_RULESET_RENDERER?.activateSourceNodeView?.(app);
    if (!activation?.catch) return;
    activation.catch((failure) => {
      const message = failure?.message || "The source-node view could not be activated.";
      console.error(message, failure);
      if (state.rendererInterfaceError?.message === message) return;
      state.rendererInterfaceError = failure instanceof Error ? failure : new Error(message);
      renderRoute();
    });
  }

  function renderLanding() {
    destroyWorkspace();
    app.classList.remove("is-ttrpg-ruleset-page");
    document.title = "TTRPG - KMQDB";
    app.innerHTML = `<section class="ttrpg-overview" aria-labelledby="ttrpg-title"><header class="ttrpg-overview__header"><p class="ttrpg-overview__eyebrow">KMQDB</p><h1 id="ttrpg-title">TTRPG</h1></header><div class="ttrpg-family-grid"><article class="ttrpg-family-card ttrpg-family-card--pathfinder"><h2>${escapeHtml(pf2erRuleset.family.title)}</h2><div class="ttrpg-family-card__editions"><a class="ttrpg-family-card__edition" href="${routeHref(pf2erRuleset.id)}" data-route><span class="ttrpg-family-card__dash" aria-hidden="true">-</span><span>${escapeHtml(pf2erRuleset.title)}</span></a></div></article></div></section>`;
  }

  function renderRuleset(id) {
    if (id !== pf2erRuleset.id) return renderNotFound();
    const ruleset = pf2erRuleset;
    fetchBookshelf(ruleset);
    fetchRulesTargets(ruleset);
    app.classList.add("is-ttrpg-ruleset-page");
    document.title = `${ruleset.family.title} ${ruleset.title} - TTRPG`;
    destroyWorkspace();
    app.innerHTML = renderRulesetShell(ruleset);
    activateWorkspace();
    activateRenderedSourceNodeView();
  }

  function renderNotFound() {
    destroyWorkspace();
    app.classList.remove("is-ttrpg-ruleset-page");
    document.title = "Not Found - TTRPG";
    app.innerHTML = `<section class="ttrpg-ruleset" aria-labelledby="not-found-title"><nav class="ttrpg-topbar" aria-label="TTRPG"><a class="ttrpg-topbar__link" href="/" data-route>TTRPG</a></nav><header class="ttrpg-ruleset__header"><p class="ttrpg-overview__eyebrow">404</p><h1 id="not-found-title">Not Found</h1></header></section>`;
  }

  function renderRoute() {
    const parts = routeParts();
    if (!parts[0]) return renderLanding();
    if (parts[0] !== pf2erRuleset.id) return renderNotFound();
    if (parts[1] && !navCategories.includes(parts[1])) return renderNotFound();
    if (parts[1] === "sources" && parts.length > 4) return renderNotFound();
    replaceRouteStateFromPath(parts);
    if (parts[1] === "sources" && parts[2] && !parts[3]) replaceAppRoute(pf2erStateHref("sources"));
    renderRuleset(parts[0]);
  }

  document.addEventListener("click", (event) => {
    if (state.activeCategory === "rules" && window.KMQDB_RULESET_RENDERER?.handleSourceNodeBranchToggle?.(event)) return;
    const sourceNodeTarget = state.activeCategory === "rules"
      ? window.KMQDB_RULESET_RENDERER?.sourceNodeTargetFromEvent?.(event)
      : null;
    if (sourceNodeTarget?.source && sourceNodeTarget?.locator) {
      event.preventDefault();
      const ruleset = pf2erRuleset;
      const context = selectedRuleContext(ruleset);
      const selected = context.packet && context.rootTarget?.source === sourceNodeTarget.source
        ? window.KMQDB_RULESET_RENDERER?.selectSourceNodeView?.(
          app,
          context.packet,
          sourceNodeTarget.locator,
          { behavior: "smooth" },
        )
        : null;
      state.activeRuleSourceId = sourceNodeTarget.source;
      state.activeRuleLocator = sourceNodeTarget.locator;
      pushAppRoute(pf2erStateHref("rules", sourceNodeTarget.source, sourceNodeTarget.locator));
      if (selected) {
        const key = sourceNodePacketKey(ruleset, context.rootTarget, sourceNodeTarget.locator);
        state.sourceNodePackets.set(key, context.packet);
        state.sourceNodeErrors.delete(key);
        return;
      }
      renderRoute();
      return;
    }
    if (window.kmqdbMenu?.handleBranchToggle?.(event, {
      scope: ".ttrpg-source-menu",
      store: (context) => context.toggle?.hasAttribute("data-ttrpg-rule-toggle") ? state.openRuleIds : state.openSourceIds,
      render: () => {
        persistOpenMenuState(pf2erRuleset);
        renderRoute();
      },
    })) return;
    const settingsToggle = event.target.closest(".ttrpg-source-bar [data-kmqdb-menu-settings-toggle]");
    if (settingsToggle) {
      event.preventDefault();
      state.sourceMenuSettingsOpen = !state.sourceMenuSettingsOpen;
      renderRoute();
      return;
    }
    const preference = event.target.closest("[data-ttrpg-nav-preference]");
    if (preference) {
      event.preventDefault();
      if (preference.dataset.ttrpgNavPreference === "metadata") {
        state.showSourceDates = !state.showSourceDates;
        safeWriteJson(ttrpgShowDatesKey, state.showSourceDates);
      } else {
        state.wrapSourceNames = !state.wrapSourceNames;
        safeWriteJson(ttrpgWrapNamesKey, state.wrapSourceNames);
      }
      state.sourceMenuSettingsOpen = true;
      renderRoute();
      return;
    }
    const sortCycle = event.target.closest("[data-ttrpg-source-sort-cycle]");
    if (sortCycle) {
      event.preventDefault();
      const index = sourceSortModes.indexOf(state.sourceSort);
      state.sourceSort = sourceSortModes[(index + 1) % sourceSortModes.length];
      safeWriteJson(ttrpgSourceSortKey, state.sourceSort);
      state.sourceMenuSettingsOpen = true;
      renderRoute();
      return;
    }
    const sourceMarker = event.target.closest("[data-ttrpg-source-marker]");
    if (sourceMarker) {
      event.preventDefault();
      toggleEnabledSource(pf2erRuleset, sourceMarker.dataset.ttrpgSourceMarker);
      renderRoute();
      return;
    }
    const publicationTarget = event.target.closest("[data-ttrpg-publication-source]");
    if (publicationTarget) {
      event.preventDefault();
      const sourceId = String(publicationTarget.dataset.ttrpgPublicationSource || "");
      const locator = String(publicationTarget.dataset.ttrpgPublicationLocator || "");
      const rootLocator = String(publicationTarget.dataset.ttrpgPublicationRoot || "");
      const context = selectedPublicationContext();
      const selected = locator && context.packet && context.rootLocator === rootLocator
        ? window.KMQDB_RULESET_RENDERER?.selectSourceNodeView?.(
          app,
          context.packet,
          locator,
          { behavior: "smooth", updateMenu: false },
        )
        : null;
      state.activeCategory = "sources";
      state.activeSourceId = sourceId;
      state.activeSourceLocator = locator;
      pushAppRoute(pf2erStateHref("sources"));
      workspaceController?.closeDrawers();
      if (selected) {
        const key = publicationNodePacketKey(sourceId, rootLocator, locator);
        state.publicationNodePackets.set(key, context.packet);
        state.publicationNodeErrors.delete(key);
      }
      renderRoute();
      return;
    }
    const ruleNameButton = event.target.closest("[data-ttrpg-rule-name-id]");
    if (ruleNameButton) {
      event.preventDefault();
      state.activeRuleId = String(ruleNameButton.dataset.ttrpgRuleNameId || "");
      state.activeRuleFamilyId = String(ruleNameButton.dataset.ttrpgRuleFamilyId || "");
      state.activeRuleFacet = "name";
      state.activeRuleNameSlug = "";
      state.activeRuleSourceId = "";
      state.activeRuleLocator = "";
      state.activeCategory = "rules";
      state.openRuleIds.add(state.activeRuleFamilyId);
      state.openRuleIds.add(`${state.activeRuleFamilyId}--by-name`);
      pushAppRoute(pf2erStateHref("rules", "", ""));
      workspaceController?.closeDrawers();
      renderRoute();
      return;
    }
    const ruleSourceButton = event.target.closest("[data-ttrpg-rule-source-id]");
    if (ruleSourceButton) {
      event.preventDefault();
      state.activeRuleId = "";
      state.activeRuleFamilyId = String(ruleSourceButton.dataset.ttrpgRuleFamilyId || "");
      state.activeRuleFacet = "source";
      state.activeRuleNameSlug = "";
      state.activeRuleSourceId = String(ruleSourceButton.dataset.ttrpgRuleSourceId || "");
      state.activeRuleLocator = "";
      state.activeCategory = "rules";
      state.openRuleIds.add(state.activeRuleFamilyId);
      state.openRuleIds.add(`${state.activeRuleFamilyId}--by-source`);
      pushAppRoute(pf2erStateHref("rules", state.activeRuleSourceId, ""));
      workspaceController?.closeDrawers();
      renderRoute();
      return;
    }
    const activeRule = event.target.closest("[data-ttrpg-active-rule-id]");
    if (activeRule) {
      event.preventDefault();
      const ruleset = pf2erRuleset;
      const context = selectedRuleContext(ruleset);
      const ruleId = String(activeRule.dataset.ttrpgActiveRuleId || "");
      const locator = String(activeRule.dataset.ttrpgActiveRuleLocator || "");
      const sourceId = state.activeRuleSourceId;
      const selected = context.packet && context.rootTarget?.source === sourceId
        ? window.KMQDB_RULESET_RENDERER?.selectSourceNodeView?.(
          app,
          context.packet,
          locator,
          { behavior: "smooth", updateMenu: false },
        )
        : null;
      state.activeRuleId = ruleId;
      state.activeRuleNameSlug = "";
      state.activeRuleLocator = locator;
      pushAppRoute(pf2erStateHref("rules", state.activeRuleSourceId, state.activeRuleLocator));
      if (selected) {
        const rootTarget = ruleTargets(ruleset, ruleId).find((target) => target.source === sourceId) || { source: sourceId, locator };
        const key = sourceNodePacketKey(ruleset, rootTarget, locator);
        state.sourceNodePackets.set(key, context.packet);
        state.sourceNodeErrors.delete(key);
        updateActiveRuleSelectionInPlace(ruleset, activeRule);
        return;
      }
      renderRoute();
      return;
    }
    const sourceTarget = event.target.closest("[data-ttrpg-rule-source-target]");
    if (sourceTarget) {
      event.preventDefault();
      state.activeRuleSourceId = String(sourceTarget.dataset.ttrpgRuleSourceTarget || "");
      state.activeRuleLocator = String(sourceTarget.dataset.ttrpgRuleRootLocator || "");
      pushAppRoute(pf2erStateHref("rules", state.activeRuleSourceId, state.activeRuleLocator));
      renderRoute();
      return;
    }
    const sourceButton = event.target.closest("[data-ttrpg-source-id]");
    if (sourceButton) {
      event.preventDefault();
      state.activeSourceId = String(sourceButton.dataset.ttrpgSourceId || "");
      state.activeSourceLocator = "";
      state.activeCategory = "sources";
      pushAppRoute(pf2erStateHref("sources"));
      workspaceController?.closeDrawers();
      renderRoute();
      return;
    }
    const link = event.target.closest("a[data-route]");
    if (!link || link.origin !== window.location.origin) return;
    event.preventDefault();
    window.history.pushState({}, "", link.href);
    renderRoute();
  });

  document.addEventListener("change", (event) => {
    const select = event.target.closest("[data-ttrpg-category-select]");
    if (!select) return;
    state.activeCategory = String(select.value || "sources");
    pushAppRoute(pf2erStateHref(state.activeCategory));
    workspaceController?.closeDrawers();
    renderRoute();
  });

  window.addEventListener("popstate", renderRoute);
  if (BOOTSTRAP.path && BOOTSTRAP.path !== window.location.pathname) window.history.replaceState({}, "", BOOTSTRAP.path);
  renderRoute();
}());
