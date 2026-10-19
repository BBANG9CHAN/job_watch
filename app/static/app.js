(() => {
  // ---------- 시각 표시: "2026-10-11 18:00:00"(KST) → "3시간 전" ----------
  const parseKst = (s) => (s ? new Date(s.replace(" ", "T") + "+09:00") : null);
  const rel = (date) => {
    const diff = (Date.now() - date.getTime()) / 1000;
    const future = diff < 0;
    const d = Math.abs(diff);
    let text;
    if (d < 60) text = future ? "곧" : "방금";
    else if (d < 3600) text = `${Math.round(d / 60)}분`;
    else if (d < 86400) text = `${Math.round(d / 3600)}시간`;
    else text = `${Math.round(d / 86400)}일`;
    if (text === "곧" || text === "방금") return text;
    return future ? `${text} 후` : `${text} 전`;
  };
  const renderTimes = () => {
    document.querySelectorAll("time[data-rel]").forEach((el) => {
      const d = parseKst(el.dataset.rel);
      if (d && !isNaN(d)) el.textContent = rel(d);
    });
  };
  renderTimes();
  setInterval(renderTimes, 60000);

  // ---------- NEW 표시: 지난 방문 이후 처음 발견된 공고 ----------
  // 30분 넘게 비웠다가 다시 들어오면 그 사이 들어온 공고에 NEW가 붙는다.
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* 무시 */ } },
  };
  const now = Date.now();
  const last = Number(store.get("jw_last_visit") || 0);
  let prev = Number(store.get("jw_prev_visit") || 0);
  if (!last || now - last > 30 * 60 * 1000) {
    prev = last;
    store.set("jw_prev_visit", String(prev));
  }
  store.set("jw_last_visit", String(now));
  if (prev) {
    document.querySelectorAll(".job[data-seen]").forEach((li) => {
      const seen = parseKst(li.dataset.seen);
      if (seen && seen.getTime() > prev) li.querySelector(".new-badge").hidden = false;
    });
  }

  // ---------- 필터: 값 바꾸면 바로 적용 ----------
  const filters = document.getElementById("filters");
  if (filters) {
    filters.querySelectorAll("select").forEach((s) => s.addEventListener("change", () => filters.submit()));
  }

  // ---------- 관심 / 지원 / 숨김 ----------
  const list = document.querySelector(".jobs");
  if (list) {
    const viewing = list.dataset.statusFilter || "";
    list.addEventListener("click", async (e) => {
      const btn = e.target.closest(".icon-btn");
      if (!btn) return;
      const li = btn.closest(".job");
      if (btn.classList.contains("act-app")) {
        // 지원 기록이 있으면 편집창, 없으면 바로 '접수'로 추가
        if (li.dataset.appStage) {
          window.openApplication({ key: li.dataset.appKey });
        } else {
          btn.disabled = true;
          try {
            const data = await saveApplication({ key: li.dataset.appKey, stage: "applied" });
            markCardApplied(li, data.stage, data.stage_label);
          } catch (err) {
            alert("지원 기록 실패: " + err.message);
          } finally {
            btn.disabled = false;
          }
        }
        return;
      }
      const current = (li.className.match(/status-(\w+)/) || [])[1] || "none";
      const target = current === btn.dataset.status ? "" : btn.dataset.status;
      btn.disabled = true;
      try {
        const res = await fetch("/api/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keys: li.dataset.keys.split(","), status: target }),
        });
        if (!res.ok) throw new Error(await res.text());
        li.className = li.className.replace(/status-\w+/, `status-${target || "none"}`);
        // 지금 보는 목록 조건에서 빠지는 공고는 접어서 치운다
        const stillVisible = viewing === "all" || viewing === "applied"
          || (viewing === "" ? target !== "hidden" : target === viewing);
        if (!stillVisible) {
          li.style.transition = "opacity .2s";
          li.style.opacity = "0";
          setTimeout(() => li.remove(), 200);
        }
      } catch (err) {
        alert("변경 실패: " + err.message);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ---------- 디스코드로 정리본 보내기 (화면에 보이는 필터 그대로) ----------
  const exportBtn = document.getElementById("export-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", async () => {
      const n = exportBtn.dataset.count;
      if (!confirm(`지금 보고 있는 목록 ${n}건을 사이트별로 정리해서 디스코드로 보낼까요?`)) return;
      const label = exportBtn.textContent;
      exportBtn.disabled = true;
      exportBtn.textContent = "보내는 중…";
      try {
        const res = await fetch("/api/export-discord", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.fromEntries(new URLSearchParams(location.search))),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || res.status);
        exportBtn.textContent = `✓ ${data.count}건 보냄 (메시지 ${data.messages}개)`;
        setTimeout(() => { exportBtn.textContent = label; exportBtn.disabled = false; }, 5000);
      } catch (err) {
        alert("보내기 실패: " + err.message);
        exportBtn.textContent = label;
        exportBtn.disabled = false;
      }
    });
  }

  // ---------- 지금 수집 ----------
  const crawlBtn = document.getElementById("crawl-btn");
  const info = document.getElementById("crawl-info");
  const waitForFinish = () => {
    const timer = setInterval(async () => {
      try {
        const s = await (await fetch("/api/state")).json();
        if (!s.running) {
          clearInterval(timer);
          location.reload();
        }
      } catch { /* 다음 주기에 재시도 */ }
    }, 3000);
  };
  if (crawlBtn) {
    crawlBtn.addEventListener("click", async () => {
      crawlBtn.disabled = true;
      info.innerHTML = '<span class="dot dot-run"></span> 수집 중… (사이트 9곳, 1~2분 걸려요)';
      try {
        await fetch("/api/crawl", { method: "POST" });
      } catch { /* 상태 조회로 확인 */ }
      waitForFinish();
    });
  }
  if (info && info.dataset.running === "true") waitForFinish();

  // ---------- 지원 현황: 편집창 ----------
  const STAGES = window.STAGES || {};
  const modal = document.getElementById("app-modal");
  const form = document.getElementById("app-form");
  const F = form ? form.elements : {};  // form.title 은 폼 자체 속성과 겹치므로 elements 로 접근
  const $ = (sel) => modal.querySelector(sel);

  const todayStr = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };

  async function saveApplication(payload) {
    const res = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.status);
    return data;
  }

  function markCardApplied(li, stage, label) {
    li.dataset.appStage = stage;
    const badge = li.querySelector(".app-badge");
    badge.className = `stage stage-${stage} app-badge`;
    badge.textContent = label;
    badge.hidden = false;
    const btn = li.querySelector(".act-app");
    btn.classList.add("has-app");
    btn.title = "지원 기록 보기·수정";
  }

  function showError(msg) {
    const el = $("#am-error");
    el.textContent = msg;
    el.hidden = !msg;
  }

  function renderHistory(events) {
    const box = $("#am-history");
    const ol = box.querySelector("ol");
    ol.replaceChildren();
    for (const ev of events || []) {
      const li = document.createElement("li");
      const when = document.createElement("span");
      when.className = "muted";
      when.textContent = ev.at.slice(5, 16).replace("-", "/") + " ";
      const what = document.createElement("span");
      what.textContent = (STAGES[ev.stage] || ev.stage) + (ev.step ? ` · ${ev.step}` : "");
      li.append(when, what);
      ol.append(li);
    }
    box.hidden = !(events && events.length);
  }

  window.openApplication = async function ({ key = "", manual = false } = {}) {
    form.reset();
    showError("");
    F.key.value = key;
    $("#am-manual").hidden = true;
    $("#am-link").hidden = true;
    $("#am-delete").hidden = true;
    renderHistory([]);

    if (manual) {
      $("#am-sub").textContent = "직접 추가";
      $("#am-title").textContent = "지원한 공고 추가";
      $("#am-manual").hidden = false;
      F.stage.value = "applied";
      F.applied_at.value = todayStr();
      modal.showModal();
      F.company.focus();
      return;
    }

    let data;
    try {
      const res = await fetch(`/api/applications/${encodeURIComponent(key)}`);
      data = await res.json();
      if (!res.ok) throw new Error(data.error || res.status);
    } catch (err) {
      alert("불러오기 실패: " + err.message);
      return;
    }
    const { job, application: app } = data;
    $("#am-sub").textContent = [job.site_label, job.company].filter(Boolean).join(" · ");
    $("#am-title").textContent = job.title;
    if (job.url) {
      $("#am-link").href = job.url;
      $("#am-link").hidden = false;
    }
    if (job.site === "manual") {
      $("#am-manual").hidden = false;
      F.company.value = job.company || "";
      F.title.value = job.title || "";
      F.url.value = job.url || "";
    }
    if (app) {
      F.stage.value = app.stage;
      F.step.value = app.step || "";
      F.applied_at.value = app.applied_at || "";
      F.next_date.value = app.next_date || "";
      F.memo.value = app.memo || "";
      renderHistory(app.events);
      $("#am-delete").hidden = false;
    } else {
      F.stage.value = "applied";
      F.applied_at.value = todayStr();
    }
    modal.showModal();
  };

  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close]")) modal.close();
    });
    $("#am-steps").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      F.step.value = chip.textContent.trim();
      // '서류 합격'·'면접' 같은 걸 고르면 단계도 진행중으로
      if (F.stage.value === "applied" && chip.textContent.trim() !== "서류 검토중") F.stage.value = "progress";
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = Object.fromEntries(new FormData(form).entries());
      if ($("#am-manual").hidden) {
        delete payload.company;
        delete payload.title;
        delete payload.url;
      }
      const btn = $("#am-save");
      btn.disabled = true;
      try {
        await saveApplication(payload);
        modal.close();
        location.reload();
      } catch (err) {
        showError(err.message);
      } finally {
        btn.disabled = false;
      }
    });
    $("#am-delete").addEventListener("click", async () => {
      if (!confirm("이 지원 기록을 삭제할까요? (공고 자체는 남아요)")) return;
      try {
        const res = await fetch(`/api/applications/${encodeURIComponent(F.key.value)}/delete`, { method: "POST" });
        if (!res.ok) throw new Error(res.status);
        modal.close();
        location.reload();
      } catch (err) {
        showError("삭제 실패: " + err.message);
      }
    });
  }

  // 보드 카드·다가오는 일정 클릭, 직접 추가, 더 보기
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".app-card, .upcoming-item");
    if (card) return window.openApplication({ key: card.dataset.appKey });
    if (e.target.closest("[data-app-new]")) return window.openApplication({ manual: true });
    const more = e.target.closest(".show-more");
    if (more) {
      const col = more.closest(".col");
      col.classList.toggle("expanded");
      more.textContent = col.classList.contains("expanded") ? "접기" : `${more.dataset.more}건 더 보기`;
    }
  });
})();
