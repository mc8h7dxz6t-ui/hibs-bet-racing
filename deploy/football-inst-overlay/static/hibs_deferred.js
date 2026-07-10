/* Progressive dashboard/insights loads — fetch HTML fragments after first paint. */
(function (global) {
    "use strict";

    function bindInsightsAccaSlips(root) {
        var scope = root || document;
        scope.querySelectorAll(".btn-acca-slip[data-acca-href]").forEach(function (btn) {
            if (btn.dataset.bound === "1") return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                var href = btn.getAttribute("data-acca-href");
                if (href) global.location.href = href;
            });
        });
    }

    function updateInsightsPills(summary) {
        if (!summary) return;
        var eligible = document.getElementById("insights-eligible-pill");
        var excluded = document.getElementById("insights-excluded-pill");
        if (eligible && summary.fixtures_eligible != null) {
            eligible.textContent = summary.fixtures_eligible + " eligible";
        }
        if (excluded && summary.fixtures_excluded != null) {
            excluded.textContent = summary.fixtures_excluded + " data-gated";
        }
    }

    function loadDeferredMount(mount) {
        var url = mount.getAttribute("data-fetch-url");
        if (!url) return Promise.resolve();

        return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then(function (resp) {
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                return resp.json();
            })
            .then(function (payload) {
                if (payload && payload.html) {
                    mount.innerHTML = payload.html;
                    bindInsightsAccaSlips(mount);
                }
                if (mount.id === "insights-deferred-mount" && payload && payload.summary) {
                    updateInsightsPills(payload.summary);
                }
                mount.setAttribute("aria-busy", "false");
            })
            .catch(function (err) {
                mount.setAttribute("aria-busy", "false");
                var msg = document.createElement("p");
                msg.className = "hibs-deferred-loading";
                msg.textContent = "Could not load this section (" + err.message + ").";
                mount.innerHTML = "";
                mount.appendChild(msg);
            });
    }

    function loadAssistantSnapshot() {
        if (!global.HIBS_DEFER_ASSISTANT) return Promise.resolve();
        return fetch("/api/assistant/snapshot", {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        })
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (payload) {
                if (!payload) return;
                global.HIBS_ASSISTANT = payload;
                if (typeof global.HibsAssistantInit === "function") {
                    global.HibsAssistantInit();
                }
            })
            .catch(function () {
                /* assistant is optional on first paint */
            });
    }

    function init() {
        var mounts = document.querySelectorAll(".hibs-deferred[data-fetch-url]");
        var jobs = Array.prototype.map.call(mounts, loadDeferredMount);
        jobs.push(loadAssistantSnapshot());
        return Promise.all(jobs);
    }

    global.HibsDeferred = {
        init: init,
        bindInsightsAccaSlips: bindInsightsAccaSlips,
        loadDeferredMount: loadDeferredMount,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})(window);
