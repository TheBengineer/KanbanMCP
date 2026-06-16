/* ── SortableJS Drag-and-Drop ── */

function initSortable(container) {
  if (container.sortable) return;
  container.sortable = new Sortable(container, {
    group: "cards",
    animation: 150,
    ghostClass: "card-ghost",
    onEnd: function (evt) {
      const cardId = evt.item.dataset.cardId;
      const newListId = evt.to.dataset.listId;
      const position = evt.newIndex * 1000;
      htmx.ajax("PATCH", "/cards/" + cardId + "/move", {
        values: { list_id: newListId, position: position },
      });
    },
  });
}

function initSubtaskSortable(container) {
  if (container.sortable) return;
  container.sortable = new Sortable(container, {
    animation: 150,
    ghostClass: "card-ghost",
    onEnd: function (evt) {
      const subtaskId = evt.item.id.replace("subtask-", "");
      const position = evt.newIndex * 1000;
      htmx.ajax("PATCH", "/subtasks/" + subtaskId + "/move", {
        values: { position: position },
      });
    },
  });
}

/* ── Progress Bar ── */

function updateProgress(ctx) {
  (ctx || document).querySelectorAll(".card").forEach(function (card) {
    var el = card.querySelector(".subtask-progress");
    var checks = card.querySelectorAll(".subtask-checkbox");
    if (!el || !checks.length) {
      if (el) el.style.display = "none";
      return;
    }
    var done = card.querySelectorAll(".subtask-checkbox:checked").length;
    el.textContent = done + "/" + checks.length + " done";
    el.style.display = "";
  });
}

document.addEventListener("click", function (evt) {
  if (evt.target.closest(".subtask-checkbox")) {
    setTimeout(function () { updateProgress(evt.target.closest(".card") ? null : document); }, 50);
  }
});

/* ── Boot ── */

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".cards").forEach(initSortable);
  document.querySelectorAll(".subtask-list").forEach(initSubtaskSortable);
  updateProgress(document);

  // Before HTMX swaps, destroy Sortable instances only on targeted sub-elements
  document.body.addEventListener("htmx:beforeSwap", function (evt) {
    var target = evt.detail.target;
    if (!target || target === document.body) return;
    target.querySelectorAll(".cards, .subtask-list").forEach(function (el) {
      if (el.sortable) {
        el.sortable.destroy();
        el.sortable = null;
      }
    });
  });

  // After HTMX swaps new content, init Sortable and update progress on fresh containers
  document.body.addEventListener("htmx:afterSettle", function (evt) {
    var target = evt.detail.target;
    if (!target) return;
    target.querySelectorAll(".cards").forEach(initSortable);
    target.querySelectorAll(".subtask-list").forEach(initSubtaskSortable);
    updateProgress(target);
  });

  // After any card move completes, trigger a board-wide refresh
  document.body.addEventListener("htmx:afterRequest", function (evt) {
    var pathInfo = evt.detail.pathInfo;
    if (pathInfo && pathInfo.requestPath && pathInfo.requestPath.indexOf("/cards/") !== -1 && pathInfo.requestPath.indexOf("/move") !== -1) {
      htmx.trigger("body", "boardRefresh");
    }
  });

  // Close modal on overlay click (not on content click)
  document.addEventListener("click", function (evt) {
    var overlay = evt.target.closest(".modal-overlay");
    if (overlay && evt.target === overlay) {
      overlay.classList.remove("active");
    }
  });

  // Close modal on Escape key
  document.addEventListener("keydown", function (evt) {
    if (evt.key === "Escape") {
      var modal = document.getElementById("modal");
      if (modal) modal.innerHTML = "";
    }
  });

  // Listen for boardRefresh event — triggers a full page reload
  document.addEventListener("boardRefresh", function () {
    window.location.reload();
  });
});
