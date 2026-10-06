"use strict";

const main = document.getElementById("main");
document.querySelector(".skip-link").addEventListener("click", event => {
  event.preventDefault();
  main.focus();
});
let controller;
let pollTimer;
let session;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function link(text, href, className) {
  const node = el("a", text, className);
  node.href = href;
  return node;
}
function button(text, action, className) {
  const node = el("button", text, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}
function field(label, control, className = "") {
  const node = el("label", null, `field ${className}`);
  node.append(el("span", label), control);
  return node;
}
function date(value) {
  return value ? new Date(value).toLocaleString(undefined, {dateStyle: "medium", timeStyle: "short"}) : "Unavailable";
}
function status(value) {
  return el("span", value.charAt(0).toUpperCase() + value.slice(1), `status ${value}`);
}
function route() {
  const [tab, query = ""] = location.hash.slice(1).split("?");
  return {tab: tab === "runs" ? "runs" : "jobs", params: new URLSearchParams(query)};
}
function url(tab, params) {
  const query = params.toString();
  return `#${tab}${query ? `?${query}` : ""}`;
}
function options(values, placeholder, selected) {
  const select = el("select");
  for (const value of ["", ...values]) {
    const option = el("option", value || placeholder);
    option.value = value;
    select.append(option);
  }
  select.value = selected || "";
  return select;
}
async function api(path, config = {}, signal = controller.signal) {
  const response = await fetch(`/api/${path}`, {...config, signal});
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail :
      Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : "Request failed. Try again.";
    throw new Error(detail);
  }
  return data;
}
function notice(text, isError = false) {
  const node = el("p", text, `notice ${isError ? "error" : "muted"}`);
  node.setAttribute("role", isError ? "alert" : "status");
  return node;
}
function safeLink(value) {
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return el("span", value || "Unavailable");
    const node = link(value, parsed.href);
    node.target = "_blank";
    node.rel = "noopener noreferrer";
    return node;
  } catch {
    return el("span", value || "Unavailable");
  }
}
function dataList(values) {
  const dl = el("dl");
  for (const [key, value] of Object.entries(values)) {
    const dd = el("dd");
    if (key === "source_url") dd.append(safeLink(value));
    else if (value !== null && typeof value === "object") dd.append(el("pre", JSON.stringify(value, null, 2)));
    else dd.textContent = value === null || value === undefined ? "Unavailable" : String(value);
    dl.append(el("dt", key), dd);
  }
  return dl;
}
function pagination(data, params, tab) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const bar = el("div", null, "pagination");
  bar.append(el("span", `Page ${data.page.toLocaleString()} of ${pages.toLocaleString()} · ${data.total.toLocaleString()} results`, "muted"));
  const buttons = el("div", null, "buttons");
  function go(page) {
    const next = new URLSearchParams(params);
    next.set("page", page);
    location.hash = url(tab, next);
  }
  const previous = button("Previous", () => go(data.page - 1));
  previous.disabled = data.page <= 1;
  const next = button("Next", () => go(data.page + 1));
  next.disabled = data.page >= pages;
  buttons.append(previous, next);
  if (data.page > pages) buttons.append(button("First page", () => go(1)));
  bar.append(buttons);
  return bar;
}
function table(headers, rows) {
  const wrapper = el("div", null, "table-wrap");
  const node = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const header of headers) {
    const th = el("th", header);
    th.scope = "col";
    headRow.append(th);
  }
  head.append(headRow);
  const body = el("tbody");
  for (const cells of rows) {
    const row = el("tr");
    cells.forEach((content, index) => {
      const cell = el("td");
      if (index > 0) cell.dataset.label = headers[index];
      cell.append(content);
      row.append(cell);
    });
    body.append(row);
  }
  node.append(head, body);
  wrapper.append(node);
  return wrapper;
}

async function jobs(params) {
  document.title = "Jobs · Job Scrapper";
  main.append(el("h1", "Jobs"), el("p", "Browse collected listings and the details behind each job.", "muted"));
  const loading = notice("Loading jobs…");
  main.append(loading);
  const query = new URLSearchParams();
  for (const key of ["q", "source", "company", "page", "page_size"]) {
    if (params.has(key)) query.set(key, params.get(key));
  }
  const [data, filters] = await Promise.all([api(`jobs?${query}`), api("filters")]);
  loading.remove();
  const form = el("form", null, "toolbar");
  const search = el("input");
  search.type = "search";
  search.maxLength = 200;
  search.placeholder = "Job title or company";
  search.value = params.get("q") || "";
  const source = options(filters.sources, "All sources", params.get("source"));
  const company = options(filters.companies, "All companies", params.get("company"));
  const size = options(["25", "50", "100"], "Rows", String(data.page_size));
  size.querySelector("option").remove();
  function apply() {
    const next = new URLSearchParams({page_size: size.value});
    if (search.value.trim()) next.set("q", search.value.trim());
    if (source.value) next.set("source", source.value);
    if (company.value) next.set("company", company.value);
    const target = url("jobs", next);
    if (location.hash === target) render();
    else location.hash = target;
  }
  const submit = el("button", "Search", "primary");
  submit.type = "submit";
  form.append(field("Search jobs", search, "search"), field("Source", source),
    field("Company", company), field("Rows", size), submit);
  form.addEventListener("submit", event => {event.preventDefault(); apply();});
  [source, company, size].forEach(control => control.addEventListener("change", apply));
  main.append(form);
  if (!data.items.length) main.append(notice(data.total ? "This page has no jobs. Return to the first page." : "No jobs match these filters. Try another search or start a scrape."));
  else main.append(table(["Job / company", "Source", "Posted", "Scraped"], data.items.map(job => {
    const next = new URLSearchParams(params);
    next.set("job", job.id);
    const title = el("div");
    title.append(link(job.title, url("jobs", next), "job-title"), el("div", job.company_name, "company"));
    return [title, el("span", job.source), el("span", date(job.posted_at)), el("span", date(job.scraped_at))];
  })));
  main.append(pagination(data, params, "jobs"));
}

async function jobDetail(params) {
  const backParams = new URLSearchParams(params);
  backParams.delete("job");
  main.append(link("Back to jobs", url("jobs", backParams), "back"));
  const loading = notice("Loading job details…");
  main.append(loading);
  const job = await api(`jobs/${encodeURIComponent(params.get("job"))}`);
  loading.remove();
  document.title = `${job.title} · Job Scrapper`;
  const detail = el("article", null, "detail");
  detail.append(el("h1", job.title), el("p", job.company_name, "muted"));
  const meta = el("div", null, "detail-meta");
  meta.append(el("span", `Source: ${job.source}`), el("span", `Posted: ${date(job.posted_at)}`), el("span", `Scraped: ${date(job.scraped_at)}`));
  detail.append(meta, safeLink(job.source_url), el("h2", "Description"), el("div", job.description_text, "description"), el("h2", "Fetched attributes"));
  detail.append(Object.keys(job.attributes || {}).length ? dataList(job.attributes) : el("p", "No attributes were stored for this job.", "muted"));
  detail.append(el("h2", `Source sightings (${job.sightings.length})`));
  for (const sighting of job.sightings) {
    detail.append(el("h3", sighting.source), dataList(sighting));
  }
  if (!job.sightings.length) detail.append(el("p", "No source sightings were stored.", "muted"));
  const raw = el("details");
  const metadata = {...job};
  for (const key of ["title", "company_name", "description_text", "attributes", "sightings", "posted_at", "scraped_at"]) delete metadata[key];
  raw.append(el("summary", "Raw identifiers and deduplication metadata"), dataList(metadata));
  detail.append(raw);
  main.append(detail);
}

function resultContent(name, result, account = false) {
  const node = el("section", null, account ? "account" : "source-result");
  const heading = el("div", null, "source-heading");
  heading.append(el("h3", name));
  if (result.status) heading.append(status(result.status));
  if (result.truncated) heading.append(el("span", "Incomplete coverage", "error"));
  node.append(heading);
  if (result.found !== undefined) node.append(el("p", `${result.found.toLocaleString()} found · ${result.inserted.toLocaleString()} inserted · ${result.skipped.toLocaleString()} skipped`, "counts"));
  else if (result.status === "running") node.append(el("p", "Collecting listings. Counts appear when this source finishes.", "muted"));
  if (result.errors?.length) {
    const list = el("ul", null, "error-list");
    result.errors.forEach(error => list.append(el("li", error)));
    node.append(list);
  }
  for (const [key, value] of Object.entries(result.accounts || {})) node.append(resultContent(key, value, true));
  return node;
}

async function runs(params) {
  document.title = "Scrape runs · Job Scrapper";
  main.append(el("h1", "Scrape runs"), el("p", "Start a collection and review results by source and company account.", "muted"));
  session = await api("session");
  const form = el("form", null, "panel");
  const sources = el("fieldset");
  sources.append(el("legend", "Select sources"));
  const grid = el("div", null, "source-grid");
  for (const source of session.sources) {
    const label = el("label", null, "check");
    const checkbox = el("input");
    checkbox.type = "checkbox";
    checkbox.name = "source";
    checkbox.value = source;
    label.append(checkbox, el("span", source));
    grid.append(label);
  }
  sources.append(grid);
  const actions = el("div", null, "run-actions");
  const days = el("input");
  days.type = "number";
  days.min = "1";
  days.max = "365";
  days.step = "1";
  days.value = "1";
  days.required = true;
  const start = el("button", "Start scrape", "primary");
  start.type = "submit";
  actions.append(field("Days", days), start);
  const message = el("p", "Select one or more sources to start.", "muted form-message");
  message.setAttribute("role", "status");
  form.append(sources, actions, el("p", "Company ATS sources collect all open jobs, regardless of days. For a small check, choose one source; Workday can take longer.", "muted form-message"), message);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const selected = [...form.querySelectorAll("input[name=source]:checked")].map(input => input.value);
    if (!selected.length) {message.textContent = "Select at least one source."; return;}
    start.disabled = true;
    message.textContent = "Starting scrape…";
    try {
      const run = await api("runs", {method: "POST", headers: {"Content-Type": "application/json", "X-Scrape-Token": session.token}, body: JSON.stringify({sources: selected, days: Number(days.value)})});
      location.hash = url("runs", new URLSearchParams({run: run.id}));
    } catch (error) {
      if (error.name !== "AbortError") {
        message.textContent = error.message;
        message.className = "error form-message";
        start.disabled = false;
      }
    }
  });
  main.append(form, el("h2", "Run history"));
  const history = el("div");
  const detail = el("section", null, "run-selected");
  main.append(history, detail);
  const signal = controller.signal;
  async function refresh() {
    try {
      const data = await api(`runs?page=${encodeURIComponent(params.get("page") || "1")}`, {}, signal);
      history.replaceChildren();
      if (!data.items.length) history.append(notice("No recorded runs yet. Only runs started with the new shared runner appear here."));
      else history.append(table(["Started / sources", "Status", "Day window"], data.items.map(run => {
        const next = new URLSearchParams(params);
        next.set("run", run.id);
        const summary = el("div");
        summary.append(link(date(run.started_at), url("runs", next), "job-title"), el("div", run.sources.join(", "), "company"));
        return [summary, status(run.status), el("span", String(run.days))];
      })));
      history.append(pagination(data, params, "runs"));
      let selected;
      if (params.has("run")) {
        selected = await api(`runs/${encodeURIComponent(params.get("run"))}`, {}, signal);
        detail.replaceChildren(el("h2", "Run details"));
        detail.append(status(selected.status));
        const end = selected.finished_at ? new Date(selected.finished_at) : new Date();
        const elapsed = Math.max(0, Math.floor((end - new Date(selected.started_at)) / 1000));
        detail.append(el("p", `Started ${date(selected.started_at)} · Elapsed ${Math.floor(elapsed / 60)}m ${elapsed % 60}s`, "muted"));
        if (selected.finished_at) detail.append(el("p", `Finished ${date(selected.finished_at)}`, "muted"));
        if (selected.error_message) detail.append(notice(selected.error_message, true));
        for (const [name, result] of Object.entries(selected.results)) detail.append(resultContent(name, result));
      }
      const active = selected?.status === "running" || data.items.some(run => run.status === "running");
      start.disabled = active;
      if (active) message.textContent = "A scrape is running. You can browse jobs while it collects.";
      else message.textContent = "Select one or more sources to start.";
      if (active && !signal.aborted) pollTimer = setTimeout(refresh, 3000);
    } catch (error) {
      if (error.name !== "AbortError") {
        detail.replaceChildren(notice(error.message, true), button("Retry", refresh));
      }
    }
  }
  await refresh();
}

async function render() {
  clearTimeout(pollTimer);
  if (controller) controller.abort();
  controller = new AbortController();
  const {tab, params} = route();
  main.replaceChildren();
  document.getElementById("nav-jobs").toggleAttribute("aria-current", tab === "jobs");
  document.getElementById("nav-runs").toggleAttribute("aria-current", tab === "runs");
  document.getElementById(`nav-${tab}`).setAttribute("aria-current", "page");
  try {
    if (tab === "runs") await runs(params);
    else if (params.has("job")) await jobDetail(params);
    else await jobs(params);
  } catch (error) {
    if (error.name !== "AbortError") {
      main.querySelectorAll('[role="status"]').forEach(node => node.remove());
      main.append(notice(error.message, true), button("Retry", render));
    }
  }
}

window.addEventListener("hashchange", render);
render();
